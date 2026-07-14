"""核心数据库 — SQLAlchemy 引擎和会话管理

提供:
  - create_engine / async_session_factory (全局单例)
  - init_db() / close_db() 生命周期管理
  - get_db() 异步会话生成器 (供 FastAPI Depends 使用)
  - get_session_factory() 供后台任务/流式处理创建独立会话

Usage:
    from smart_qa.database.engine import init_db, close_db, get_db

设计说明:
    全局引擎是惰性初始化的——init_db() 在应用启动时调用一次，
    之后通过 get_db() (请求级) 或 get_session_factory() (后台任务) 获取会话。
    会话生命周期由 async context manager 管理，确保 commit / rollback 正确。
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from smart_qa.config import settings
from smart_qa.observability.logger import logger

# ── 模块级单例 ──
# 在 init_db() 中初始化，之后通过 get_db() / get_session_factory() 使用。
# 注意：不在 `__init__.py` 中公开，防止导入时意外触发。
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


async def init_db(dsn: str | None = None):
    """初始化数据库引擎并创建所有表

    在 FastAPI 应用启动时由 web.py lifespan 调用。
    只会执行一次（通过模块级全局变量保证）。

    参数:
        dsn: PostgreSQL 连接字符串
             形如 "postgresql+asyncpg://user:pass@host:5432/db"
             为 None 时从 settings.postgres_dsn 读取。

    流程:
        1. create_async_engine → 连接池 (pool_size=10, max_overflow=20, pool_pre_ping)
        2. async_sessionmaker → 会话工厂 (expire_on_commit=False 防序列化后过期)
        3. Base.metadata.create_all → 自动建表
        4. ALTER TABLE sessions ADD COLUMN messages → 历史迁移（列已有时忽略）

    异常处理:
        连接失败：此函数抛出异常，由上层 lifespan 捕获并 log warning，系统降级运行。
        迁移列重复：仅 ProgrammingError("already exists") 静默忽略，其他异常 log warning。
    """
    global _engine, _session_factory
    dsn = dsn or settings.postgres_dsn
    _engine = create_async_engine(dsn, echo=False, pool_size=10, max_overflow=20, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    from smart_qa.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(text("ALTER TABLE sessions ADD COLUMN messages TEXT"))
            logger.info("数据库迁移: sessions.messages 列已添加")
        except ProgrammingError as e:
            if "already exists" not in str(e).lower():
                logger.warning("数据库迁移异常（非列重复）: {}", e)

    logger.info("数据库已初始化，所有表已就绪")


async def close_db():
    """关闭数据库连接池

    在 FastAPI 应用关闭时由 web.py lifespan 调用。
    释放所有连接资源，清空引擎引用。

    注意事项:
        await _engine.dispose() 可能阻塞等待活跃事务完成。
        调用后 _engine 和 _session_factory 置为 None。
    """
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("数据库连接已关闭")


def get_session_factory() -> async_sessionmaker:
    """获取会话工厂（供后台任务 / 流式处理使用）

    区别于 get_db()（请求级会话，由 FastAPI Depends 管理生命周期），
    此函数返回 async_sessionmaker 实例，调用方自行管理会话生命周期。

    返回值:
        async_sessionmaker[AsyncSession] — 使用方式：
            async with get_session_factory()() as session:
                ...

    异常:
        RuntimeError: 数据库未初始化时调用（需先调用 init_db()）

    典型使用场景:
        - SSE 流式处理的异步持久化（stream_handler.py）
        - 定时任务 / 运维脚本
        - 需在独立事务中执行的批量操作
    """
    if not _session_factory:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入函数: 获取数据库会话

    通过 FastAPI 的 Depends() 机制注入到路由处理函数中。
    自动管理事务生命周期：yield 前创建会话，路由返回后 commit，异常时 rollback。

    用法:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...

    Yields:
        AsyncSession — SQLAlchemy 异步会话实例

    异常:
        RuntimeError: 数据库未初始化时调用
        路由内部异常: 自动 rollback 并向上传播
    """
    if not _session_factory:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
