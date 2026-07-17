"""初始化数据库 — 创建所有表

Usage:
    python -m smart_qa.scripts.init_db
"""

import asyncio

from smart_qa.config import settings
from smart_qa.database.engine import init_db as _init_engine


async def init_db():
    """创建所有数据库表"""
    print("[InitDB] 开始初始化数据库...")
    await _init_engine(settings.postgres_dsn)
    print("[InitDB] 数据库表创建完成")


async def main():
    await init_db()
    print("[InitDB] 全部完成")


if __name__ == "__main__":
    asyncio.run(main())
