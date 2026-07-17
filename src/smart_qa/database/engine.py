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

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,  # noqa: F401 — used in init_db() but ruff's analysis misses it
)

from smart_qa.config import settings
from smart_qa.models.user import User
from smart_qa.observability.logger import logger

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


async def init_db(dsn: str | None = None):
    """初始化数据库引擎并创建所有表

    在 FastAPI 应用启动时由 web.py lifespan 调用。
    只会执行一次（通过模块级全局变量保证）。

    流程:
        1. create_async_engine → 连接池
        2. async_sessionmaker → 会话工厂
        3. Base.metadata.create_all → 自动建表
        4. 创建默认管理员 admin/admin（仅首次启动时）

    ALTER TABLE 迁移使用同步引擎单独连接执行，
    不污染 async 连接的事务状态。
    """
    global _engine, _session_factory
    dsn = dsn or settings.postgres_dsn
    _engine = create_async_engine(dsn, echo=False, pool_size=10, max_overflow=20, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    from smart_qa.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # ── 默认管理员（仅首次启动时创建） ──
        try:
            result = await conn.execute(select(User).where(User.username == "admin"))
            if not result.fetchone():
                password_hash, salt = User.hash_password("admin")
                await conn.execute(
                    text(
                        "INSERT INTO users (username, password_hash, role, salt, display_name, created_at) VALUES (:u, :h, :r, :s, :d, :c)"
                    ),
                    {
                        "u": "admin",
                        "h": password_hash,
                        "r": "admin",
                        "s": salt,
                        "d": "管理员",
                        "c": __import__("datetime").datetime.utcnow(),
                    },
                )
                logger.info("默认管理员已创建: admin / admin")
        except Exception as e:
            logger.debug("管理员创建跳过: {}", e)

    # ── 历史迁移：单独 async 连接执行，不污染主事务 ──
    try:
        async with _engine.begin() as mig_conn:
            await mig_conn.execute(text("ALTER TABLE sessions ADD COLUMN messages TEXT"))
            logger.info("数据库迁移: sessions.messages 列已添加")
    except ProgrammingError as e:
        if "already exists" not in str(e).lower():
            logger.warning("数据库迁移异常（非列重复）: {}", e)
    except Exception:
        pass

    logger.info("数据库已初始化，所有表已就绪")


async def close_db():
    """关闭数据库连接池

    在 FastAPI 应用关闭时由 web.py lifespan 调用。
    释放所有连接资源，清空引擎引用。
    """
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
    """FastAPI 依赖注入函数: 获取数据库会话"""
    if not _session_factory:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
