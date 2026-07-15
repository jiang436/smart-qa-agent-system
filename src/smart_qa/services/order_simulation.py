"""订单模拟服务 — 虚拟耗材订购 + 物流追踪（模拟数据，非真实订单）

⚠️ 重要说明：整个订单系统是演示用途的模拟场景
===============================================
本模块不连接任何真实电商或物流 API，所有数据均为模拟生成。

模拟内容：
  - 订单号（ORD + 随机字符）— 非真实电商订单号
  - 快递单号（SF + 随机字符）— 非真实快递单号
  - 物流事件 — 使用预设模板按顺序播放，非真实物流扫描
  - 价格 — 演示价格，无真实支付
  - 地址 — 默认地址，无真实收货地址

目的：
  1. 演示耗材购买的完整对话闭环（推荐→确认→下单→物流跟踪）
  2. 展示 Agent 跟踪订单状态和回答物流查询的能力
  3. 覆盖网购常见的异常场景（损坏/丢失/缺货/退货）

支持的状态流转:
  pending → confirmed → paid → processing → shipped → in_transit ─┬→ delivered (正常签收, 80%)
                                                                   ├→ damaged (运输损坏) → returned → refunded (8%)
                                                                   ├→ lost (物流丢失) → refunded (5%)
                                                                   ├→ out_of_stock (缺货) → refunded (2%)
                                                                   └→ returned (用户退货) → refunded (5%)

物流模板（5 种场景）:
  每个场景是一系列预设物流事件，按顺序播放。
  OrderSimulationService.advance() 每次推进一个环节。
"""

import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_qa.models.virtual_order import LogisticsEvent, VirtualOrder
from smart_qa.observability.logger import logger

# ══════════════════════════════════════════════════════════════
# 物流事件模板（模拟数据）
# ══════════════════════════════════════════════════════════════
# 每个场景是一系列预设的物流事件，OrderSimulationService.advance()
# 每次调用从对应模板中取下一个事件写入 LogisticsEvent 表。
#
# 这些事件内容为演示用途，不代表真实的物流扫描记录。
# ══════════════════════════════════════════════════════════════
LOGISTICS_SCENARIOS: dict[str, list[dict[str, Any]]] = {
    "normal": [  # 正常送达（80% 概率）
        {"event_type": "scan", "message": "订单已提交，等待仓库处理", "location": "系统"},
        {"event_type": "scan", "message": "仓库已接单，开始备货", "location": "华东仓储中心"},
        {"event_type": "shipped", "message": "包裹已出库，等待快递公司揽收", "location": "华东仓储中心"},
        {"event_type": "scan", "message": "【顺丰速运】已揽收", "location": "上海分拣中心"},
        {"event_type": "location_update", "message": "包裹已到达分拣中心", "location": "上海分拣中心"},
        {"event_type": "location_update", "message": "包裹正在发往目的地", "location": "沪昆高速"},
        {"event_type": "location_update", "message": "包裹已到达目的地分拣中心", "location": "目的地分拣中心"},
        {"event_type": "scan", "message": "快递员已揽件，正在派送中", "location": "配送站"},
        {"event_type": "scan", "message": "【已签收】包裹已由本人签收", "location": "用户地址"},
    ],
    "damaged": [  # 运输损坏（8% 概率）
        {"event_type": "scan", "message": "订单已提交，等待仓库处理", "location": "系统"},
        {"event_type": "shipped", "message": "包裹已出库", "location": "华东仓储中心"},
        {"event_type": "scan", "message": "【中通快递】已揽收", "location": "上海分拣中心"},
        {"event_type": "location_update", "message": "包裹正在运输中", "location": "运输途中"},
        {"event_type": "damaged", "message": "⚠️ 运输途中包裹受损，内部耗材可能有损坏", "location": "中转站"},
        {"event_type": "scan", "message": "质检确认货物损坏，已启动售后流程", "location": "售后中心"},
        {"event_type": "returned", "message": "商品已退回仓库，退款处理中", "location": "华东仓储中心"},
        {"event_type": "scan", "message": "✅ 退款已完成", "location": "系统"},
    ],
    "lost": [  # 物流丢失（5% 概率）
        {"event_type": "scan", "message": "订单已提交，等待仓库处理", "location": "系统"},
        {"event_type": "shipped", "message": "包裹已出库", "location": "华东仓储中心"},
        {"event_type": "scan", "message": "【圆通速递】已揽收", "location": "上海分拣中心"},
        {"event_type": "location_update", "message": "包裹正在运输中", "location": "运输途中"},
        {"event_type": "lost", "message": "⚠️ 物流信息中断超过48小时，疑似包裹丢失", "location": "不明"},
        {"event_type": "scan", "message": "快递公司确认包裹丢失，已启动赔付流程", "location": "客服中心"},
        {"event_type": "scan", "message": "✅ 赔付完成，退款已原路返回", "location": "系统"},
    ],
    "out_of_stock": [  # 缺货（2% 概率）
        {"event_type": "scan", "message": "订单已提交，等待仓库处理", "location": "系统"},
        {"event_type": "out_of_stock", "message": "⚠️ 该商品暂时缺货，预计补货时间未知", "location": "仓储系统"},
        {"event_type": "scan", "message": "已为您自动取消订单，无需任何操作", "location": "系统"},
        {"event_type": "scan", "message": "✅ 退款已完成", "location": "系统"},
    ],
    "returned": [  # 用户退货（5% 概率）
        {"event_type": "scan", "message": "订单已提交，等待仓库处理", "location": "系统"},
        {"event_type": "shipped", "message": "包裹已出库", "location": "华东仓储中心"},
        {"event_type": "scan", "message": "【顺丰速运】已揽收", "location": "上海分拣中心"},
        {"event_type": "location_update", "message": "包裹正在运输中", "location": "运输途中"},
        {"event_type": "scan", "message": "【已签收】包裹已由本人签收", "location": "用户地址"},
        {"event_type": "returned", "message": "用户申请退货，已同意", "location": "系统"},
        {"event_type": "scan", "message": "快递员已上门取件", "location": "用户地址"},
        {"event_type": "scan", "message": "仓库已收到退货，质检中", "location": "华东仓储中心"},
        {"event_type": "scan", "message": "✅ 退货退款已完成", "location": "系统"},
    ],
}


class OrderSimulationService:
    """订单模拟服务（模拟数据，非真实订单系统）

    模拟完整电商订单流程，所有数据存储在 PostgreSQL 中。
    每次调用 advance_logistics() 推进一个物流环节。

    典型用法:
        service = OrderSimulationService()
        order = await service.create_order(db, user_id, part_type, part_name, price)
        order = await service.confirm_order(db, order)
        order = await service.start_shipping(db, order, scenario="normal")
        order, event = await service.advance_logistics(db, order, scenario)

    ⚠️ 注意:
        - 订单号、快递单号均为随机生成，不代表真实物流信息
        - 物流事件来自预设模板，非真实物流接口数据
        - 价格仅为演示数值，无真实支付发生
    """

    @staticmethod
    async def create_order(
        db: AsyncSession,
        user_id: str,
        part_type: str,
        part_name: str,
        price: float,
        quantity: int = 1,
        shipping_address: str = "默认收货地址",
    ) -> VirtualOrder:
        """创建虚拟订单（模拟数据）

        生成模拟订单，初始状态为 pending。
        不产生真实订单，不连接任何电商系统。

        Args:
            db: 数据库会话
            user_id: 用户 ID
            part_type: 耗材类型（side_brush / hepa_filter / ...）
            part_name: 耗材名称（如"边刷"）
            price: 模拟价格（无真实支付）
            quantity: 数量
            shipping_address: 模拟收货地址

        Returns:
            VirtualOrder — 状态为 pending 的订单
        """
        order = VirtualOrder(
            order_id=VirtualOrder.generate_order_id(),
            user_id=user_id,
            part_type=part_type,
            part_name=part_name,
            quantity=quantity,
            price=price,
            status="pending",
            shipping_address=shipping_address,
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)
        logger.info("虚拟订单已创建 order={} user={} part={}", order.order_id, user_id, part_name)
        return order

    @staticmethod
    async def confirm_order(db: AsyncSession, order: VirtualOrder) -> VirtualOrder:
        """确认订单（模拟支付和备货）

        将订单状态从 pending 推进到 processing（经过 confirmed → paid → processing），
        模拟确认支付和仓库备货的流程。

        Args:
            order: 待确认的订单

        Returns:
            VirtualOrder — 状态为 processing 的订单
        """
        order.status = "confirmed"
        await db.commit()
        await db.refresh(order)
        order.status = "paid"
        await db.commit()
        order.status = "processing"
        await db.commit()
        await db.refresh(order)
        logger.info("订单已确认 order={} status=processing", order.order_id)
        return order

    @staticmethod
    async def start_shipping(db: AsyncSession, order: VirtualOrder, scenario: str = "normal") -> VirtualOrder:
        """模拟发货 — 选择物流场景并生成第一个物流事件

        根据 scenario 参数选择对应的物流模板，生成模拟快递单号和物流公司名，
        并写入第一个物流事件。

        Args:
            order: 已确认的订单
            scenario: 物流场景名（normal/damaged/lost/out_of_stock/returned）
                      决定后续 advance_logistics() 播放哪个模板

        Returns:
            VirtualOrder — 状态更新为 shipped，含模拟 tracking_number 和 express_company
        """
        if scenario not in LOGISTICS_SCENARIOS:
            scenario = "normal"

        order.status = "shipped"
        order.tracking_number = "SF" + secrets.token_hex(6).upper()  # 模拟快递单号，非真实
        express_list = {
            "normal": "顺丰速运",
            "damaged": "中通快递",
            "lost": "圆通速递",
            "out_of_stock": "系统",
            "returned": "顺丰速运",
        }
        order.express_company = express_list.get(scenario, "顺丰速运")

        events = LOGISTICS_SCENARIOS[scenario]
        if events:
            first = events[0]
            event = LogisticsEvent(
                order_id=order.order_id,
                event_type=first["event_type"],
                message=first["message"],
                location=first.get("location"),
                timestamp=datetime.utcnow(),
            )
            db.add(event)

        await db.commit()
        await db.refresh(order)
        logger.info("订单已发货 order={} scenario={} tracking={}", order.order_id, scenario, order.tracking_number)
        return order

    @staticmethod
    async def advance_logistics(
        db: AsyncSession, order: VirtualOrder, scenario: str | None = None
    ) -> tuple[VirtualOrder, LogisticsEvent | None]:
        """推进物流到下一个环节（模拟）

        读取订单已有的物流事件数，从对应场景模板中获取下一事件写入数据库。
        如果模板已播完，自动将状态设置为 delivered 或保持最终状态。

        Args:
            order: 当前订单
            scenario: 物流场景名。为 None 时默认使用 normal。

        Returns:
            (order, event_or_None) —
                order: 更新后的订单（状态可能已变更）
                event: 最新的物流事件（模板播完时返回 None）

        物流事件内容说明:
            所有事件来自 LOGISTICS_SCENARIOS 预设模板。
            事件中的地点名（如"上海分拣中心"）、快递公司名（如"顺丰速运"）
            均为模拟数据，不代表真实物流路径。
        """
        if scenario is None:
            scenario = "normal"

        events_template = LOGISTICS_SCENARIOS.get(scenario, LOGISTICS_SCENARIOS["normal"])

        result = await db.execute(
            select(LogisticsEvent).where(LogisticsEvent.order_id == order.order_id).order_by(LogisticsEvent.id)
        )
        existing_events = result.scalars().all()
        step = len(existing_events)

        if step >= len(events_template):
            if order.status in ("shipped", "in_transit"):
                order.status = "delivered"
            await db.commit()
            await db.refresh(order)
            return order, None

        next_event_data = events_template[step]
        event = LogisticsEvent(
            order_id=order.order_id,
            event_type=next_event_data["event_type"],
            message=next_event_data["message"],
            location=next_event_data.get("location"),
            timestamp=datetime.utcnow() + timedelta(seconds=step * 2),
        )
        db.add(event)

        event_type = next_event_data["event_type"]
        status_map: dict[str, str] = {
            "shipped": "shipped",
            "location_update": "in_transit",
            "delayed": "in_transit",
            "damaged": "damaged",
            "lost": "lost",
            "returned": "returned",
            "out_of_stock": "out_of_stock",
            "delivered": "delivered",
        }
        if event_type in status_map:
            order.status = status_map[event_type]

        await db.commit()
        await db.refresh(order)
        logger.info("物流推进 order={} event={} status={}", order.order_id, event_type, order.status)
        return order, event

    @staticmethod
    async def simulate_full_flow(
        db: AsyncSession, user_id: str, part_type: str, part_name: str, price: float, scenario: str = "normal"
    ) -> VirtualOrder:
        """完整模拟一个订单从创建到完结的流程

        一次性创建、确认、发货，并依次推进所有物流环节到最终状态。
        用于测试或演示场景。

        Args:
            scenario: normal / damaged / lost / out_of_stock / returned

        Returns:
            VirtualOrder — 最终状态的订单（含所有物流事件）
        """
        order = await OrderSimulationService.create_order(db, user_id, part_type, part_name, price)
        order = await OrderSimulationService.confirm_order(db, order)
        order = await OrderSimulationService.start_shipping(db, order, scenario)

        while True:
            order, event = await OrderSimulationService.advance_logistics(db, order, scenario)
            if event is None:
                break

        return order
