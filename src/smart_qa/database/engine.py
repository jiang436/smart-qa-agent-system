"""核心数据库 — SQLAlchemy 引擎和会话管理

提供:
  - create_engine / async_session_factory (全局单例)
  - init_db() / close_db() 生命周期管理
  - get_db() 异步会话生成器 (供 FastAPI Depends 使用)
  - get_session_factory() 供后台任务/流式处理创建独立会话

Usage:
    from smart_qa.database.engine import init_db, close_db, get_db
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from smart_qa.config import settings
from smart_qa.observability.logger import logger

# 全局引擎和工厂
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


async def init_db(dsn: str | None = None):
    """初始化数据库引擎并创建所有表"""
    global _engine, _session_factory
    dsn = dsn or settings.postgres_dsn
    _engine = create_async_engine(dsn, echo=False, pool_size=10, max_overflow=20, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    from smart_qa.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 迁移：添加 messages 列（已有表时新增）
        try:
            await conn.execute(text("ALTER TABLE sessions ADD COLUMN messages TEXT"))
            logger.info("数据库迁移: sessions.messages 列已添加")
        except Exception:
            pass  # 列已存在

    logger.info("数据库已初始化，所有表已就绪")


async def close_db():
    """关闭数据库连接池"""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("数据库连接已关闭")


def get_session_factory() -> async_sessionmaker:
    """获取会话工厂（供后台任务 / 流式处理使用）"""
    if not _session_factory:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖: 获取数据库会话

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
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
