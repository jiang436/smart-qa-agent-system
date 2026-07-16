"""初始化数据库 — 创建所有表并写入种子数据（含默认管理员）

Usage:
    uv run python -m smart_qa.scripts.init_db
"""

import asyncio

from smart_qa.config import settings
from smart_qa.database.engine import get_db
from smart_qa.database.engine import init_db as _init_engine
from smart_qa.database.postgres import PostgresClient


async def init_db():
    """创建所有数据库表（默认管理员账户由 engine.init_db 自动创建）"""
    print("[InitDB] 开始初始化数据库...")
    await _init_engine(settings.postgres_dsn)
    print("[InitDB] 数据库表创建完成（含默认管理员 admin / admin）")


async def seed_data():
    """写入测试种子数据"""
    print("[InitDB] 写入种子数据...")

    async for db in get_db():
        # ── 用户设备 ──
        devices = [
            ("U1001", "X30Pro_Virtual_01", "X30 Pro", "v3.2.1"),
            ("U1002", "T10_Virtual_01", "T10", "v2.8.0"),
            ("U1003", "X20Pro_Virtual_01", "X20 Pro", "v3.1.0"),
        ]
        for uid, dn, dm, fw in devices:
            existing = await PostgresClient.get_user_device(db, uid)
            if not existing:
                await PostgresClient.bind_device(db, uid, dn, dm, fw)
                print(f"  [Device] {uid} -> {dm}")

        # ── 耗材订单 ──
        for uid, dev, pt, pn, qty, price, src in [
            ("U1001", "X30 Pro", "side_brush", "X30 Pro 原装边刷", 1, 29.9, "oem"),
            ("U1002", "T10", "main_brush", "T10 主刷", 1, 49.0, "oem"),
            ("U1003", "X20 Pro", "side_brush", "X20 Pro 边刷", 2, 25.0, "oem"),
        ]:
            last = await PostgresClient.get_last_order(db, uid, pt)
            if not last:
                await PostgresClient.create_order(db, uid, dev, pt, pn, qty, price, src)
                print(f"  [Order] {uid} -> {pn}")

        # ── 使用日志 ──
        logs = [
            ("U1001", "X30Pro_Virtual_01", "X30 Pro", 45.5, 32.0, 18),
            ("U1001", "X30Pro_Virtual_01", "X30 Pro", 38.2, 28.0, 15),
            ("U1002", "T10_Virtual_01", "T10", 30.0, 25.0, 12),
            ("U1003", "X20Pro_Virtual_01", "X20 Pro", 60.5, 45.0, 25),
        ]
        for uid, dn, dm, area, dur, batt in logs:
            await PostgresClient.log_usage(db, uid, dn, dm, area, dur, batt)
        print(f"[InitDB] 种子数据写入完成 ({len(logs)} 条日志)")
        break  # 只用第一个 session


async def main():
    await init_db()
    await seed_data()
    print("[InitDB] 全部完成")


if __name__ == "__main__":
    asyncio.run(main())
