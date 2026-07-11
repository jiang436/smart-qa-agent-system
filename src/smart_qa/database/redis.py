"""数据库 — Redis 异步客户端"""

import json

import redis.asyncio as aioredis

from smart_qa.config import settings


class RedisClient:
    _client: aioredis.Redis | None = None

    @classmethod
    async def init_redis(cls, url: str | None = None):
        url = url or settings.redis_url
        cls._client = await aioredis.from_url(url, encoding="utf-8", decode_responses=True, max_connections=20)
        await cls._client.ping()
        print("[Redis] 连接已建立")

    @classmethod
    async def close_redis(cls):
        if cls._client:
            await cls._client.close()
            cls._client = None
            print("[Redis] 连接已关闭")

    @classmethod
    def _ensure(cls):
        if not cls._client:
            raise RuntimeError("Redis 未初始化")

    @classmethod
    async def get(cls, key: str) -> str | None:
        cls._ensure()
        return await cls._client.get(key)

    @classmethod
    async def set(cls, key: str, value: str, ttl: int | None = None):
        cls._ensure()
        if ttl:
            await cls._client.setex(key, ttl, value)
        else:
            await cls._client.set(key, value)

    @classmethod
    async def delete(cls, key: str):
        cls._ensure()
        await cls._client.delete(key)

    @classmethod
    async def get_json(cls, key: str) -> dict | None:
        data = await cls.get(key)
        return json.loads(data) if data else None

    @classmethod
    async def set_json(cls, key: str, value: dict, ttl: int | None = None):
        await cls.set(key, json.dumps(value, ensure_ascii=False), ttl=ttl)

    @classmethod
    async def get_messages(cls, session_id: str, limit: int = 20) -> list[dict]:
        session = await cls.get_json(f"session:{session_id}")
        if session:
            return session.get("messages", [])[-limit:]
        return []

    @classmethod
    async def update_session(cls, session_id: str, updates: dict):
        session = await cls.get_json(f"session:{session_id}") or {}
        session.update(updates)
        ttl = await cls._client.ttl(f"session:{session_id}")
        await cls.set_json(f"session:{session_id}", session, ttl=max(ttl, 60) if ttl > 0 else None)

    @classmethod
    async def increment_counter(cls, key: str, ttl: int = 86400) -> int:
        cls._ensure()
        count = await cls._client.incr(key)
        if count == 1:
            await cls._client.expire(key, ttl)
        return count


async def init_redis():
    await RedisClient.init_redis()


async def close_redis():
    await RedisClient.close_redis()
