"""订单管理 Schema — Pydantic 数据校验"""

from datetime import datetime

from pydantic import BaseModel, Field


class OrderCreateRequest(BaseModel):
    """创建订单请求"""

    user_id: str = Field(..., min_length=1, max_length=64)
    part_type: str = Field(..., min_length=1, max_length=64)
    part_name: str = Field(..., min_length=1, max_length=128)
    price: float = Field(..., gt=0)
    quantity: int = Field(default=1, ge=1)
    shipping_address: str = Field(default="默认收货地址", max_length=256)


class LogisticsEventResponse(BaseModel):
    """物流事件响应"""

    event_type: str
    message: str
    location: str | None = None
    timestamp: datetime


class OrderResponse(BaseModel):
    """订单响应"""

    order_id: str
    user_id: str
    part_type: str
    part_name: str
    quantity: int
    price: float
    status: str
    tracking_number: str | None = None
    express_company: str | None = None
    shipping_address: str
    created_at: datetime
    updated_at: datetime
    logistics: list[LogisticsEventResponse] = []


class OrderStatusResponse(BaseModel):
    """订单状态查询响应"""

    order_id: str
    status: str
    status_label: str
    tracking_number: str | None = None
    express_company: str | None = None
    logistics: list[LogisticsEventResponse] = []


class OrderListResponse(BaseModel):
    """订单列表响应"""

    orders: list[OrderResponse]
    total: int


# 状态标签映射
STATUS_LABELS: dict[str, str] = {
    "pending": "待确认",
    "confirmed": "已确认",
    "paid": "已付款",
    "processing": "备货中",
    "shipped": "已发货",
    "in_transit": "运输中",
    "delivered": "已签收",
    "out_of_stock": "缺货",
    "damaged": "货物损坏",
    "lost": "物流丢失",
    "returned": "退货中",
    "refunded": "已退款",
}
