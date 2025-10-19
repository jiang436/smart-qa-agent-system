"""设备使用日志表"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class DeviceUsageLog(Base):
    __tablename__ = "device_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_model: Mapped[str] = mapped_column(String(64), nullable=False)
    clean_area: Mapped[float] = mapped_column(Float, default=0.0)
    duration_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    battery_consumed: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
