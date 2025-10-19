"""数据模型 — SQLAlchemy ORM 表定义"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from .consumable import ConsumableOrder
from .device import UserDevice
from .session import Session
from .usage import DeviceUsageLog

__all__ = ["Base", "Session", "UserDevice", "ConsumableOrder", "DeviceUsageLog"]
