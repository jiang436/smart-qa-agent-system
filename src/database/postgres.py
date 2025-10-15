"""数据库 — PostgreSQL 数据访问层 (CRUD)

基于 app/models/ 中的 ORM 模型和 app/core/database.py 中的会话管理，
提供实体级别的数据访问操作。

注意: ORM 表定义已迁移到 app/models/ 中。
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ConsumableOrder, DeviceUsageLog, Session, UserDevice


class PostgresClient:
    """PostgreSQL 数据访问客户端

    所有方法接受 AsyncSession 参数（通过 Depends(get_db) 注入），
    不再维护类级别的引擎单例。
    """

    # ── 会话操作 ──

    @staticmethod
    async def create_session(db: AsyncSession, session_id: str, user_id: str) -> Session:
        rec = Session(session_id=session_id, user_id=user_id)
        db.add(rec)
        await db.commit()
        return rec

    @staticmethod
    async def get_session(db: AsyncSession, session_id: str) -> Session | None:
        result = await db.execute(select(Session).where(Session.session_id == session_id))
        return result.scalar_one_or_none()

    # ── 用户设备 ──

    @staticmethod
    async def get_user_device(db: AsyncSession, user_id: str) -> UserDevice | None:
        result = await db.execute(
            select(UserDevice)
            .where(UserDevice.user_id == user_id, UserDevice.is_active == True)
            .order_by(UserDevice.bound_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def bind_device(
        db: AsyncSession, user_id: str, device_name: str, device_model: str, firmware_version: str | None = None
    ) -> UserDevice:
        old = await db.execute(select(UserDevice).where(UserDevice.user_id == user_id, UserDevice.is_active == True))
        for rec in old.scalars().all():
            rec.is_active = False
        device = UserDevice(
            user_id=user_id, device_name=device_name, device_model=device_model, firmware_version=firmware_version
        )
        db.add(device)
        await db.commit()
        return device

    # ── 耗材订单 ──

    @staticmethod
    async def get_last_order(db: AsyncSession, user_id: str, part_type: str) -> ConsumableOrder | None:
        result = await db.execute(
            select(ConsumableOrder)
            .where(ConsumableOrder.user_id == user_id, ConsumableOrder.part_type == part_type)
            .order_by(ConsumableOrder.ordered_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_order(
        db: AsyncSession,
        user_id: str,
        device_model: str,
        part_type: str,
        part_name: str,
        quantity: int = 1,
        price: float | None = None,
        source: str | None = None,
    ) -> ConsumableOrder:
        order = ConsumableOrder(
            order_id=str(uuid.uuid4())[:12],
            user_id=user_id,
            device_model=device_model,
            part_type=part_type,
            part_name=part_name,
            quantity=quantity,
            price=price,
            source=source,
        )
        db.add(order)
        await db.commit()
        return order

    # ── 使用日志 ──

    @staticmethod
    async def get_usage_stats(db: AsyncSession, user_id: str, days: int = 30) -> dict:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(DeviceUsageLog).where(
                DeviceUsageLog.user_id == user_id,
                DeviceUsageLog.recorded_at >= since,
            )
        )
        logs = result.scalars().all()
        if not logs:
            return {"total_cleans": 0, "total_area": 0, "total_duration": 0, "avg_area_per_clean": 0, "error_count": 0}
        return {
            "total_cleans": len(logs),
            "total_area": round(sum(l.clean_area for l in logs), 1),
            "total_duration": round(sum(l.duration_minutes for l in logs), 1),
            "avg_area_per_clean": round(sum(l.clean_area for l in logs) / len(logs), 1),
            "error_count": sum(1 for l in logs if l.error_code),
        }

    @staticmethod
    async def log_usage(
        db: AsyncSession,
        user_id: str,
        device_name: str,
        device_model: str,
        clean_area: float = 0,
        duration_minutes: float = 0,
        battery_consumed: int = 0,
        error_code: str | None = None,
        status: str = "completed",
    ) -> DeviceUsageLog:
        log = DeviceUsageLog(
            user_id=user_id,
            device_name=device_name,
            device_model=device_model,
            clean_area=clean_area,
            duration_minutes=duration_minutes,
            battery_consumed=battery_consumed,
            error_code=error_code,
            status=status,
        )
        db.add(log)
        await db.commit()
        return log
