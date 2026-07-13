"""语义缓存 — 用 Embedding 做相似度匹配

和传统缓存（key=原问题）的区别:
  - 传统缓存: "怎么重置" ≠ "如何恢复出厂设置" → 各存一条
  - 语义缓存: "怎么重置" ≈ "如何恢复出厂设置" → 命中同一个答案

存储后端:
  - 无 Redis: 本地 dict（开发测试用，重启丢失）
  - 有 Redis: Redis Hash（生产用，持久化，跨实例共享，TTL 自动过期）

写回策略:
  get(): 查 Redis → 有则返回，无则查本地（写穿式回退）
  set(): 有 Redis → 写 Redis + 写本地；无 Redis → 只写本地
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

import numpy as np

from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.observability.logger import logger

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis


class SemanticCache:
    """语义缓存

    用法:
        cache = SemanticCache(redis_client=async_redis_obj)

        # 查缓存（async）
        answer = await cache.get("怎么重置扫地机")
        if answer:
            return answer

        # 写缓存（async）
        await cache.set("怎么重置扫地机", "长按重置键3秒...")
    """

    def __init__(
        self,
        redis_client: AsyncRedis | None = None,
        threshold: float = 0.95,
        ttl: int = 1800,
    ):
        self.embedding = get_embedding()
        self.redis: AsyncRedis | None = redis_client
        self.threshold = threshold
        self.ttl = ttl

        # 如果没传 redis_client，尝试从全局 RedisClient 获取
        if self.redis is None:
            try:
                from smart_qa.database.redis import RedisClient

                self.redis = RedisClient.get_client()
            except (ImportError, AttributeError):
                pass

        # 本地回退（写穿式缓存）
        self._local_store: list[tuple[str, str, np.ndarray]] = []

        if self.redis:
            logger.info(
                "语义缓存后端=Redis ttl={}s threshold={}",
                self.ttl,
                self.threshold,
            )
        else:
            logger.info(
                "语义缓存后端=local(重启丢失) threshold={}",
                self.threshold,
            )

    # ═══════════════════════════════════════
    # 公开接口（async）
    # ═══════════════════════════════════════

    async def get(self, query: str) -> str | None:
        """查语义缓存

        流程:
          1. 有 Redis → Redis 遍历 + 余弦相似度
          2. 无 Redis → 本地 dict 遍历
        """
        query_vec = self.embedding.encode(query)

        r = self.redis
        if r is not None:
            return await self._search_redis(r, query_vec)
        return self._search_local(query_vec)

    async def set(self, query: str, answer: str):
        """写语义缓存（带 TTL）

        流程:
          1. 有 Redis → 写 Redis Hash + 写本地（写穿）
          2. 无 Redis → 只写本地（LRU 限 1000 条）
        """
        query_vec = self.embedding.encode(query)
        vec_1d = query_vec[0]

        r = self.redis
        if r is not None:
            await self._store_redis(r, query, answer, vec_1d)

        # 写穿：本地也存一份，减少 Redis 读放大
        self._local_store.append((query, answer, vec_1d))
        if len(self._local_store) > 1000:
            self._local_store.pop(0)

    async def clear(self):
        """清空所有缓存（生产慎用）"""
        r = self.redis
        if r is not None:
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor, match="semantic_cache:*", count=200)
                if keys:
                    await r.delete(*keys)
                if cursor == 0:
                    break
        self._local_store.clear()
        logger.info("语义缓存已清空")

    # ═══════════════════════════════════════
    # Redis 后端
    # ═══════════════════════════════════════

    async def _search_redis(self, r: Any, query_vec: np.ndarray) -> str | None:
        """Redis 语义搜索 — SCAN + 余弦相似度

        直接遍历全量缓存条目计算相似度。
        对 < 10000 条规模足够，numpy 计算是微秒级的。
        如果规模超 10 万条，可以升级到 Redis Stack FT.SEARCH + VSS。

        Returns:
            命中且超过阈值 → 答案文本
            未命中 → None
        """
        start = time.time()
        best_score = -1.0
        best_answer: str | None = None

        try:
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor, match="semantic_cache:*", count=200)
                for key in keys:
                    data: dict[str, str] = await r.hgetall(key)
                    if not data:
                        continue
                    answer = data.get("answer")
                    emb_raw = data.get("embedding")
                    if not answer or not emb_raw:
                        continue
                    stored_vec = np.array(json.loads(emb_raw), dtype=np.float32)
                    score = self.embedding.cosine_similarity(query_vec[0], stored_vec)
                    if score > best_score:
                        best_score = score
                        best_answer = answer
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Redis 缓存搜索异常: {}", e)
            return self._search_local(query_vec)  # 降级到本地

        elapsed = time.time() - start
        if best_score >= self.threshold:
            logger.info(
                "Redis缓存命中 score={:.3f} elapsed={:.0f}ms",
                best_score,
                elapsed * 1000,
            )
            return best_answer

        logger.debug(
            "Redis缓存未命中 best_score={:.3f} threshold={} elapsed={:.0f}ms",
            best_score,
            self.threshold,
            elapsed * 1000,
        )
        return None

    async def _store_redis(self, r: Any, query: str, answer: str, vec_1d: np.ndarray):
        """Redis 存储 — Hash 结构

        Key:     semantic_cache:<md5(query)>
        Fields:  query / answer / embedding(JSON) / created_at

        TTL 自动过期缓存条目。
        """
        try:
            key = _cache_key(query)
            await r.hset(
                key,
                mapping={
                    "query": query[:200],
                    "answer": answer,
                    "embedding": json.dumps(vec_1d.tolist()),
                    "created_at": str(time.time()),
                },
            )
            if self.ttl > 0:
                await r.expire(key, self.ttl)
        except Exception as e:
            logger.warning(
                "Redis 缓存写入失败: {} query={}",
                e,
                query[:60],
            )

    # ═══════════════════════════════════════
    # 本地后端（写穿回退）
    # ═══════════════════════════════════════

    def _search_local(self, query_vec: np.ndarray) -> str | None:
        """本地语义搜索 — O(n) 遍历"""
        if not self._local_store:
            return None

        best_score = -1.0
        best_answer: str | None = None

        for _stored_query, answer, stored_vec in self._local_store:
            score = self.embedding.cosine_similarity(query_vec[0], stored_vec)
            if score > best_score:
                best_score = score
                best_answer = answer

        if best_score >= self.threshold:
            logger.info(
                "本地缓存命中 score={:.3f} threshold={}",
                best_score,
                self.threshold,
            )
            return best_answer

        logger.debug(
            "本地缓存未命中 best_score={:.3f} threshold={}",
            best_score,
            self.threshold,
        )
        return None


def _cache_key(query: str) -> str:
    """生成 Redis key（确定性 MD5）"""
    md5 = hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"semantic_cache:{md5}"
