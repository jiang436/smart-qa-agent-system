"""Redis 客户端 — 异步连接池管理器

提供对 Redis 的基础操作封装，所有方法均为类方法（classmethod），
使用模块级单例连接池。

设计说明:
    通过 init_redis() / close_redis() 在应用生命周期中管理连接，
    get_client() 返回原始 redis.asyncio.Redis 实例供高级使用（如语义缓存的 SCAN 搜索）。
    所有操作方法均包含异常处理，确保 Redis 不可用时不影响主流程。

    Redis 在项目中的用途:
    - L1 语义缓存（SemanticCache 通过 get_client() 使用）
    - SSE 流式会话持久化（get_messages / update_session）
    - 限流计数（increment_counter）
    - 常规键值存储（get / set / get_json / set_json）

用法:
    from smart_qa.database.redis import RedisClient, init_redis, close_redis, get_client

    await init_redis()
    redis_client = get_client()
    await RedisClient.set_json("key", {"data": "value"})
    await close_redis()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from smart_qa.config import settings
from smart_qa.observability.logger import logger

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

# 模块级 Redis 连接实例
# 通过 init_redis() 初始化，get_client() 获取。
_redis: AsyncRedis | None = None


async def init_redis():
    """初始化 Redis 连接池

    在 FastAPI 应用启动时由 web.py lifespan 调用。
    使用 settings.redis_url 配置连接字符串。

    异常处理:
        Redis 不可用时记录 waring 而非 error——系统仍可运行（降级模式）。
    """
    global _redis
    try:
        from redis.asyncio import Redis

        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
        logger.info("Redis 连接成功: {}", settings.redis_url)
    except Exception as e:
        logger.warning("Redis 连接失败，语义缓存降级为 local: {}", str(e)[:100])
        _redis = None


async def close_redis():
    """关闭 Redis 连接池

    在 FastAPI 应用关闭时由 web.py lifespan 调用。
    连接池关闭后所有未完成的命令将失败。
    """
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
        logger.info("Redis 连接已关闭")


def get_client() -> AsyncRedis | None:
    """获取 Redis 客户端实例

    返回值:
        AsyncRedis | None — Redis 异步客户端，Redis 不可用时返回 None

    注意:
        调用方需要检查返回值是否为 None。
        SemanticCache 就是通过此方式获取 Redis 进行高级操作。
    """
    return _redis


class RedisClient:
    """Redis 操作封装 — 类方法方式提供基础 CRUD

    所有方法均为 @classmethod，通过模块级 _redis 实例执行。
    异常不向上传播——调用方无需 try/except。
    """

    @classmethod
    def get_client(cls) -> AsyncRedis | None:
        """获取原始 Redis 客户端实例（类方法）

        与模块级 get_client() 相同，兼容 SemanticCache 等组件的调用方式。

        Returns:
            AsyncRedis | None — Redis 客户端或 None
        """
        return _redis

    _TAG = "[RedisClient]"

    @classmethod
    def _r(cls) -> AsyncRedis | None:
        """获取当前 Redis 实例（内部辅助方法）"""
        return _redis

    @classmethod
    async def get(cls, key: str) -> str | None:
        """获取字符串值"""
        r = cls._r()
        if r is None:
            return None
        try:
            return await r.get(key)
        except Exception as e:
            logger.warning("{} GET {} 失败: {}", cls._TAG, key, e)
            return None

    @classmethod
    async def set(cls, key: str, value: str, expire: int = 3600):
        """设置字符串值（带 TTL）

        Args:
            key: Redis key
            value: 字符串值
            expire: 过期时间（秒，默认 3600=1小时）
        """
        r = cls._r()
        if r is None:
            return
        try:
            await r.setex(key, expire, value)
        except Exception as e:
            logger.warning("{} SET {} 失败: {}", cls._TAG, key, e)

    @classmethod
    async def delete(cls, key: str):
        """删除 key"""
        r = cls._r()
        if r is None:
            return
        try:
            await r.delete(key)
        except Exception as e:
            logger.warning("{} DEL {} 失败: {}", cls._TAG, key, e)

    @classmethod
    async def get_json(cls, key: str) -> dict | None:
        """获取并解析 JSON 值"""
        import json

        val = await cls.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return None

    @classmethod
    async def set_json(cls, key: str, value: dict, expire: int = 3600):
        """将字典序列化为 JSON 后存储（带 TTL）"""
        import json

        await cls.set(key, json.dumps(value, ensure_ascii=False), expire=expire)

    @classmethod
    async def get_messages(cls, key: str) -> list[dict]:
        """获取对话消息列表"""
        data = await cls.get_json(key)
        return data if isinstance(data, list) else []

    @classmethod
    async def update_session(cls, session_id: str, data: dict, ttl: int = 7200):
        """更新会话数据（2h TTL）

        Args:
            session_id: 会话 ID
            data: 会话数据字典
            ttl: TTL 秒（默认 7200=2小时）
        """
        await cls.set_json(f"session:{session_id}", data, expire=ttl)

    @classmethod
    async def increment_counter(cls, key: str) -> int:
        """原子递增计数器

        Args:
            key: 计数器 key

        Returns:
            int — 递增后的值，Redis 不可用时返回 0
        """
        r = cls._r()
        if r is None:
            return 0
        try:
            return await r.incr(key)
        except Exception as e:
            logger.warning("{} INCR {} 失败: {}", cls._TAG, key, e)
            return 0
