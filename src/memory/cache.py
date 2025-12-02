"""语义缓存 — 用 Embedding 做相似度匹配

和传统缓存（key=原问题）的区别:
  - 传统缓存: "怎么重置" ≠ "如何恢复出厂设置" → 各存一条
  - 语义缓存: "怎么重置" ≈ "如何恢复出厂设置" → 命中同一个答案

实现:
  1. set(query, answer): 编码 query → 存储 (embedding, query, answer)
  2. get(query): 编码 query → 和所有缓存的 embedding 算相似度 → 返回最高分 > 阈值
  3. 存储可以用 Redis（生产）或本地 dict（开发）
"""

import numpy as np

from src.knowledge.vector_store import get_embedding
from src.observability.logger import logger


class SemanticCache:
    def __init__(self, redis_client=None, threshold: float = 0.95):
        self.embedding = get_embedding()
        self.redis = redis_client
        self.threshold = threshold
        self._local_store: list[tuple[str, str, np.ndarray]] = []  # (query, answer, embedding)

    def get(self, query: str) -> str | None:
        query_vec = self.embedding.encode(query)

        if self.redis:
            return self._search_redis(query_vec)
        else:
            return self._search_local(query_vec)

    def set(self, query: str, answer: str):
        query_vec = self.embedding.encode(query)

        if self.redis:
            self._store_redis(query, answer, query_vec)
        else:
            self._local_store.append((query, answer, query_vec[0]))
            # LRU 简单限制
            if len(self._local_store) > 1000:
                self._local_store.pop(0)

    def _search_local(self, query_vec: np.ndarray) -> str | None:
        if not self._local_store:
            return None

        best_score = -1.0
        best_answer = None

        for _stored_query, answer, stored_vec in self._local_store:
            score = self.embedding.cosine_similarity(query_vec[0], stored_vec)
            if score > best_score:
                best_score = score
                best_answer = answer

        # 所有条目比较完后，检查最高分是否超过阈值
        if best_score >= self.threshold:
            logger.info("缓存命中 score={:.3f} threshold={}", best_score, self.threshold)
            return best_answer

        logger.debug("缓存未命中 best_score={:.3f} threshold={}", best_score, self.threshold)
        return None

    def _search_redis(self, query_vec: np.ndarray) -> str | None:
        # TODO: Redis vector search implementation
        return None

    def _store_redis(self, query: str, answer: str, query_vec: np.ndarray):
        # TODO: Redis vector store
        pass

    def clear(self):
        self._local_store.clear()
