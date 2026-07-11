"""Embedding 模型封装 — BAAI/bge-small-zh-v1.5"""

import numpy as np

from smart_qa.observability.logger import logger


class EmbeddingModel:
    MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    NORMALIZE = True
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = None
        return cls._instance

    def __init__(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL_NAME)
            logger.info("Embedding 模型已加载: {}", self.MODEL_NAME)
        except Exception as e:
            logger.warning("Embedding 本地模型加载失败，回退 API 模式: {}", e)
            self._model = "api_fallback"

    def encode(self, texts: str | list[str]) -> np.ndarray:
        is_single = isinstance(texts, str)
        if is_single:
            texts = [texts]

        if self._model == "api_fallback":
            return self._encode_via_api(texts)
        else:
            embeddings = self._model.encode(texts, normalize_embeddings=self.NORMALIZE)
            result = np.array(embeddings)
            return result[0:1] if is_single else result

    def _encode_via_api(self, texts: list[str]) -> np.ndarray:
        import json
        import urllib.request

        from smart_qa.config import settings

        url = settings.llm_base_url.replace("/v1", "/embeddings")
        headers = {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
        data = json.dumps({"input": texts, "model": "text-embedding-ada-002"}).encode()
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            vectors = [item["embedding"] for item in resp["data"]]
            return np.array(vectors, dtype=np.float32)
        except Exception as e:
            logger.warning("API Embedding 失败: {}", e)
            return np.zeros((len(texts), 512), dtype=np.float32)

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        dot = np.dot(vec1, vec2)
        return float(dot / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-10))


def get_embedding() -> EmbeddingModel:
    return EmbeddingModel()
