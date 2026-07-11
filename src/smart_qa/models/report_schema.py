"""报告相关 Schema"""

from pydantic import BaseModel, Field


class UsageStats(BaseModel):
    """使用统计"""

    total_cleans: int = 0
    total_area: float = 0.0
    total_duration: float = 0.0
    avg_area_per_clean: float = 0.0
    error_count: int = 0
    total_days: int = 30


class ConsumableStatus(BaseModel):
    """耗材状态"""

    name: str = Field(..., description="耗材名称")
    remaining_days: int = 0
    total_days: int = 90
    status: str = Field(default="good", description="good / warning / danger")
    last_replaced: str | None = None


class ReportResponse(BaseModel):
    """报告响应"""

    report_type: str = Field(default="monthly", description="monthly / weekly / abnormal / consumable")
    device_model: str | None = None
    stats: UsageStats | None = None
    consumables: list[ConsumableStatus] = Field(default_factory=list)
    suggestions: str = ""
    generated_at: str | None = None
