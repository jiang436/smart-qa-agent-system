"""Embedding 模型 — 统一入口

使用方式:
    from smart_qa.knowledge.vector_store import get_embedding

    emb = get_embedding()
    vectors = emb.encode(["查询文本"])
    dim = emb.dimension       # 向量维度（切换后端后自动变化）

后端切换:
    通过环境变量 EMBEDDING_BACKEND 切换:
      local  → sentence-transformers（默认）
      ollama → Ollama 本地模型（需运行 ollama serve）
      api    → OpenAI 兼容远程 API
"""

from __future__ import annotations

import numpy as np

from smart_qa.config import settings
from smart_qa.knowledge.embedding_backends import (
    EmbeddingBackend,
    create_embedding_backend,
)


class EmbeddingModel:
    """Embedding 模型（单例 + 可插拔后端）

    根据 settings.embedding_backend 自动选择后端。
    """

    _instance: EmbeddingModel | None = None
    _backend: EmbeddingBackend | None = None

    def __new__(cls) -> EmbeddingModel:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._backend is not None:
            return
        self._backend = create_embedding_backend(
            backend=settings.embedding_backend,
            model=settings.embedding_model,
            api_key=settings.embedding_api_key or settings.llm_api_key,
            base_url=settings.embedding_base_url or settings.llm_base_url,
        )

    @property
    def dimension(self) -> int:
        if self._backend is None:
            return 512
        return self._backend.dimension

    def encode(self, texts: str | list[str]) -> np.ndarray:
        is_single = isinstance(texts, str)
        if is_single:
            texts = [texts]
        result = self._backend.encode(texts)
        return result[0:1] if is_single else result

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        dot = np.dot(vec1, vec2)
        norm = np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-10
        return float(dot / norm)


def get_embedding() -> EmbeddingModel:
    return EmbeddingModel()
