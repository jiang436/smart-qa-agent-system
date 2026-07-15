"""订单管理路由 — 创建 / 查询 / 跟踪物流"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_qa.database.engine import get_db
from smart_qa.models.order_schema import (
    STATUS_LABELS,
    LogisticsEventResponse,
    OrderListResponse,
    OrderResponse,
    OrderStatusResponse,
)
from smart_qa.models.virtual_order import LogisticsEvent, VirtualOrder
from smart_qa.observability.logger import logger
from smart_qa.services.order_simulation import LOGISTICS_SCENARIOS, OrderSimulationService

router = APIRouter(tags=["orders"])


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(user_id: str, page: int = 1, page_size: int = 20, db: AsyncSession = Depends(get_db)):
    """查询用户的订单列表"""
    try:
        result = await db.execute(
            select(VirtualOrder)
            .where(VirtualOrder.user_id == user_id)
            .order_by(VirtualOrder.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        orders = result.scalars().all()

        count_result = await db.execute(select(VirtualOrder).where(VirtualOrder.user_id == user_id))
        total = len(count_result.scalars().all())

        return OrderListResponse(
            orders=[await _order_to_response(o, db) for o in orders],
            total=total,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


@router.get("/orders/{order_id}", response_model=OrderStatusResponse)
async def track_order(order_id: str, db: AsyncSession = Depends(get_db)):
    """查询订单详情和物流轨迹"""
    try:
        result = await db.execute(select(VirtualOrder).where(VirtualOrder.order_id == order_id))
        order = result.scalar_one_or_none()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e

    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    return await _order_to_status_response(order, db)


@router.post("/orders/simulate", response_model=OrderResponse)
async def simulate_order(
    user_id: str,
    part_type: str = "side_brush",
    part_name: str = "边刷",
    price: float = 29.9,
    scenario: str = "normal",
    db: AsyncSession = Depends(get_db),
):
    """模拟一个完整的订单流程（用于测试/演示）

    Args:
        user_id: 用户 ID
        part_type: 耗材类型
        part_name: 耗材名称
        price: 价格
        scenario: 物流场景（normal/damaged/lost/out_of_stock/returned）
    """
    if scenario not in LOGISTICS_SCENARIOS:
        raise HTTPException(status_code=400, detail=f"无效场景: {scenario}，可选: {list(LOGISTICS_SCENARIOS.keys())}")

    order = await OrderSimulationService.simulate_full_flow(
        db=db, user_id=user_id, part_type=part_type, part_name=part_name, price=price, scenario=scenario
    )
    logger.info("模拟订单完成 order={} scenario={} status={}", order.order_id, scenario, order.status)
    return await _order_to_response(order, db)


@router.post("/orders/{order_id}/advance", response_model=OrderStatusResponse)
async def advance_order(order_id: str, scenario: str = "normal", db: AsyncSession = Depends(get_db)):
    """推进订单到下一个物流环节"""
    result = await db.execute(select(VirtualOrder).where(VirtualOrder.order_id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    order, _event = await OrderSimulationService.advance_logistics(db, order, scenario)
    logger.info("人工推进物流 order={} status={}", order.order_id, order.status)
    return await _order_to_status_response(order, db)


async def _order_to_response(order: VirtualOrder, db: AsyncSession) -> OrderResponse:
    """将 ORM 订单转为响应"""
    events = await _get_events(order.order_id, db)
    return OrderResponse(
        order_id=order.order_id,
        user_id=order.user_id,
        part_type=order.part_type,
        part_name=order.part_name,
        quantity=order.quantity,
        price=order.price,
        status=order.status,
        tracking_number=order.tracking_number,
        express_company=order.express_company,
        shipping_address=order.shipping_address,
        created_at=order.created_at,
        updated_at=order.updated_at,
        logistics=events,
    )


async def _order_to_status_response(order: VirtualOrder, db: AsyncSession) -> OrderStatusResponse:
    """将 ORM 订单转为状态查询响应"""
    events = await _get_events(order.order_id, db)
    return OrderStatusResponse(
        order_id=order.order_id,
        status=order.status,
        status_label=STATUS_LABELS.get(order.status, order.status),
        tracking_number=order.tracking_number,
        express_company=order.express_company,
        logistics=events,
    )


async def _get_events(order_id: str, db: AsyncSession) -> list[LogisticsEventResponse]:
    """获取订单的物流事件列表"""
    try:
        result = await db.execute(
            select(LogisticsEvent).where(LogisticsEvent.order_id == order_id).order_by(LogisticsEvent.id)
        )
        events = result.scalars().all()
        return [
            LogisticsEventResponse(
                event_type=e.event_type,
                message=e.message,
                location=e.location,
                timestamp=e.timestamp,
            )
            for e in events
        ]
    except Exception:
        return []
