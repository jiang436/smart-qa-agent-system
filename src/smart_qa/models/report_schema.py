"""报告相关 Schema — Pydantic 数据校验"""

from pydantic import BaseModel, Field


class UsageStats(BaseModel):
    """使用统计"""

    total_cleans: int = Field(default=0, ge=0, description="清扫次数")
    total_area: float = Field(default=0.0, ge=0, description="累计清扫面积 m²")
    total_duration: float = Field(default=0.0, ge=0, description="累计时长 分钟")
    avg_area_per_clean: float = Field(default=0.0, ge=0, description="平均每次面积 m²")
    error_count: int = Field(default=0, ge=0, description="异常次数")
    total_days: int = Field(default=30, ge=1, le=365, description="统计天数")


class ConsumableStatus(BaseModel):
    """耗材状态"""

    name: str = Field(..., min_length=1, max_length=32, description="耗材名称")
    remaining_days: int = Field(default=0, ge=0, description="剩余天数")
    total_days: int = Field(default=90, ge=1, description="建议更换周期")
    status: str = Field(default="good", pattern=r"^(good|warning|danger)$", description="good / warning / danger")
    last_replaced: str | None = Field(None, max_length=64, description="上次更换时间")


class ReportResponse(BaseModel):
    """报告响应"""

    report_type: str = Field(
        default="monthly", pattern=r"^(monthly|weekly|abnormal|consumable)$", description="报告类型"
    )
    device_model: str | None = Field(None, max_length=32)
    stats: UsageStats | None = None
    consumables: list[ConsumableStatus] = Field(default_factory=list)
    suggestions: str = Field(default="", max_length=2000)
    generated_at: str | None = Field(None, max_length=32)
