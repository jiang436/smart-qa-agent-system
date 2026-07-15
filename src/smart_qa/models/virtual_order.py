"""虚拟订单模型 — 耗材订购 + 物流追踪

⚠️ 重要说明：此为模拟数据，非真实订单系统
===========================================
整个订单和物流系统是演示用途的模拟场景（Mock/Simulation），

目的：
  - 演示耗材购买的完整对话闭环（推荐 → 确认 → 下单 → 物流跟踪）
  - 展示 Agent 跟踪订单状态的能力
  - 覆盖网购常见的异常场景（损坏/丢失/缺货/退货）

非真实：
  - 不连接任何真实电商/物流 API（如淘宝、京东、顺丰）
  - 不下发真实快递单号（tracking_number 是随机生成的模拟号）
  - 不产生真实支付（无支付宝/微信集成）
  - 物流事件使用预设模板（LOGISTICS_SCENARIOS）按顺序播放

状态机流转:
  pending → confirmed → paid → processing → shipped → in_transit ─┬→ delivered (正常签收)
                                                                   ├→ damaged (运输损坏) → returned → refunded
                                                                   ├→ lost (物流丢失) → refunded
                                                                   ├→ out_of_stock (缺货) → refunded
                                                                   └→ returned (用户退货) → refunded
"""

import secrets
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from smart_qa.models.base import Base


class VirtualOrder(Base):
    """虚拟订单（模拟数据，非真实订单）

    每个订单从创建到完结经历多个状态，状态变更由 OrderSimulationService 驱动。
    物流轨迹通过 LogisticsEvent 表记录。

    ⚠️ 所有数据均为模拟生成，不涉及真实交易。
    """

    __tablename__ = "virtual_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # ── 商品信息（模拟数据） ──
    part_type: Mapped[str] = mapped_column(String(64), nullable=False)  # side_brush / hepa_filter / ...
    part_name: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Float, nullable=False)  # 模拟价格，无真实支付

    # ── 收货信息（模拟地址） ──
    shipping_address: Mapped[str] = mapped_column(String(256), default="默认收货地址")

    # ── 物流信息（模拟快递，无真实物流对接） ──
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
        comment="pending|confirmed|paid|processing|shipped|in_transit|delivered|out_of_stock|damaged|lost|returned|refunded",
    )
    tracking_number: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 模拟单号，非真实快递单号
    express_company: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 模拟快递公司名

    # ── 时间线 ──
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def generate_order_id() -> str:
        """生成唯一模拟订单号（格式: ORD + 12 位随机字符）

        注意：此订单号仅用于演示，不代表任何真实电商订单。
        """
        return "ORD" + secrets.token_hex(6).upper()


class LogisticsEvent(Base):
    """物流事件（模拟数据，非真实物流追踪）

    每个事件记录一次模拟的物流扫描/状态变更。
    事件内容来自预设模板（LOGISTICS_SCENARIOS），非真实物流接口数据。

    字段说明:
      event_type: 事件类型（shipped/scan/location_update/delivery_attempt/delayed/out_of_stock/damaged/lost/returned/delivered）
      message:    模拟的物流状态描述文本
      location:   模拟的地点名称
      timestamp:  事件时间（模拟时间，非真实扫描时间）
    """

    __tablename__ = "logistics_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="shipped|scan|location_update|delivery_attempt|delayed|out_of_stock|damaged|lost|returned|delivered",
    )
    message: Mapped[str] = mapped_column(String(256), nullable=False)  # 模拟物流描述，如"包裹已出库"
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 模拟地点，如"上海分拣中心"
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
