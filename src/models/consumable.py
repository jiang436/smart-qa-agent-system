"""耗材订单表"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class ConsumableOrder(Base):
    __tablename__ = "consumable_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    device_model: Mapped[str] = mapped_column(String(64), nullable=False)
    part_type: Mapped[str] = mapped_column(String(64), nullable=False)
    part_name: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ordered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
