"""用户设备绑定表"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class UserDevice(Base):
    __tablename__ = "user_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_model: Mapped[str] = mapped_column(String(64), nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    bound_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
