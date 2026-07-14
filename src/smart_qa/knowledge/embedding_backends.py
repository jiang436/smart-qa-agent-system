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
        import torch
        from sentence_transformers import SentenceTransformer

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._model = SentenceTransformer(model_name, device=device)
        logger.info("Embedding 本地模型已加载: {} (device={})", model_name, device)

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
    """远程 API 嵌入（OpenAI 兼容）— 自动检测维度"""

    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self._dim: int | None = None

    @property
    def dimension(self) -> int:
        if self._dim is None:
            return 768  # 首次调用前返回常见默认值
        return self._dim

    def encode(self, texts: list[str]) -> np.ndarray:
        resp = self.client.embeddings.create(input=texts, model=self.model)
        data = np.array([item.embedding for item in resp.data], dtype=np.float32)
        if self._dim is None and data.size > 0:
            self._dim = data.shape[-1]
        return data


def create_embedding_backend(
    backend: str = "local",
    model: str = "BAAI/bge-small-zh-v1.5",
    api_key: str = "",
    base_url: str = "",
) -> EmbeddingBackend:
    """工厂函数: 根据配置创建 EmbeddingBackend 实例"""
    if backend == "ollama":
        return OllamaEmbedding(model=model, base_url=base_url or "http://localhost:11434")
    elif backend == "api":
        return APIEmbedding(api_key=api_key, base_url=base_url, model=model)
    else:
        return LocalEmbedding(model_name=model)
