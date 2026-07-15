"""嵌入模型后端 — 可插拔: Local / Ollama / API"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import requests

from smart_qa.observability.logger import logger


class EmbeddingBackend(ABC):
    """嵌入模型后端基类"""

    dimension: int = 512

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray: ...


class LocalEmbedding(EmbeddingBackend):
    """sentence-transformers 本地模型（默认）"""

    dimension: int = 512

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        logger.info("Embedding 本地模型已加载: {}", model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts, normalize_embeddings=True)  # type: ignore[return-value]


class OllamaEmbedding(EmbeddingBackend):
    """Ollama 本地嵌入模型（OpenAI 兼容接口）"""

    def __init__(self, model: str = "qwen3-embedding:4b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._dim: int | None = None
        logger.info("Ollama Embedding 后端: {} @ {}", model, base_url)

    @property
    def dimension(self) -> int:
        if self._dim is None:
            emb = self.encode(["hello"])
            self._dim = int(emb.shape[-1])
        return self._dim if self._dim is not None else 2560

    def encode(self, texts: list[str]) -> np.ndarray:
        resp = requests.post(
            f"{self.base_url}/v1/embeddings",
            json={"model": self.model, "input": texts, "encoding_format": "float"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return np.array([item["embedding"] for item in data["data"]], dtype=np.float32)


class APIEmbedding(EmbeddingBackend):
    """远程 API 嵌入（OpenAI 兼容）"""

    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self._dim: int | None = None

    @property
    def dimension(self) -> int:
        if self._dim is None:
            emb = self.encode(["hello"])
            self._dim = int(emb.shape[-1])
        return self._dim if self._dim is not None else 1024

    def encode(self, texts: list[str]) -> np.ndarray:
        resp = self.client.embeddings.create(input=texts, model=self.model)
        return np.array([item.embedding for item in resp.data], dtype=np.float32)


class FallbackEmbedding(EmbeddingBackend):
    """兜底嵌入 — API 主路，本地降级

    自动切换:
      API 可用 → 直接用 API
      API 超时/报错 → 自动切本地模型
      本地也失败 → 抛异常
    """

    def __init__(self, primary: EmbeddingBackend, fallback: EmbeddingBackend):
        self.primary = primary
        self.fallback = fallback
        self._using_fallback = False
        self._dim: int | None = None

    @property
    def dimension(self) -> int:
        if self._dim is None:
            try:
                self._dim = self.primary.dimension
            except Exception:
                self._dim = self.fallback.dimension
        return self._dim if self._dim is not None else 1024

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._using_fallback:
            try:
                return self.primary.encode(texts)
            except Exception as e:
                logger.warning("API Embedding 不可用，降级本地模型: {}", e)
                self._using_fallback = True
        return self.fallback.encode(texts)


def create_embedding_backend(
    backend: str = "local",
    model: str = "BAAI/bge-small-zh-v1.5",
    api_key: str = "",
    base_url: str = "",
    fallback_model: str = "",
) -> EmbeddingBackend:
    """工厂函数: 根据配置创建 EmbeddingBackend 实例

    支持 "api" + fallback_model → API 主路 + 本地兜底
    """
    if backend == "ollama":
        return OllamaEmbedding(model=model, base_url=base_url or "http://localhost:11434")
    elif backend == "api":
        primary = APIEmbedding(api_key=api_key, base_url=base_url, model=model)
        if fallback_model:
            fallback = LocalEmbedding(model_name=fallback_model)
            logger.info("Embedding: API({})+本地({}) 兜底模式", model, fallback_model)
            return FallbackEmbedding(primary, fallback)
        return primary
    else:
        return LocalEmbedding(model_name=model)
