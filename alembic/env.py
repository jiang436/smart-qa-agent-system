"""Alembic 迁移环境 — 支持 async PostgreSQL + 从项目 config 读取数据库 URL"""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Alembic Config 对象
config = context.config

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 从环境变量或项目配置读取数据库 URL
# 优先使用环境变量（容器/CI），其次用 .env 配置
db_url = os.environ.get("POSTGRES_DSN") or config.get_main_option("sqlalchemy.url")

# 导入所有 ORM Model 的 MetaData 以支持 autogenerate
try:
    from smart_qa.models.base import Base

    target_metadata = Base.metadata
except ImportError:
    target_metadata = None


def run_migrations_offline() -> None:
    """离线模式 — 仅输出 SQL，不连接数据库"""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """在给定连接上执行迁移"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """在线模式 — async engine + 自动 migrate"""
    connectable = create_async_engine(db_url, echo=False)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
