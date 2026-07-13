"""设备相关 Schema — Pydantic 数据校验"""

from pydantic import BaseModel, Field


class DeviceStatus(BaseModel):
    """设备状态"""

    user_id: str = Field(..., min_length=1, max_length=64, description="用户 ID")
    device_name: str | None = Field(None, max_length=64)
    device_model: str | None = Field(None, max_length=32)
    battery: int | None = Field(None, ge=0, le=100, description="电量 0-100")
    status: str | None = Field(None, description="standby / cleaning / charging / offline / error")
    water_level: str | None = Field(None, max_length=16)
    dust_bin: str | None = Field(None, max_length=16)
    mop: str | None = Field(None, max_length=16)
    online: bool = False
    source: str | None = Field(None, max_length=32)


class ScheduleCreate(BaseModel):
    """创建定时任务"""

    user_id: str = Field(..., min_length=1, max_length=64, description="用户 ID")
    time: str = Field(
        ...,
        description="清扫时间 HH:MM",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    room: str = Field(default="全屋", max_length=32, description="清扫房间名称")


class ScheduleResponse(BaseModel):
    """定时任务响应"""

    status: str = Field(..., pattern=r"^(ok|error)$")
    message: str = Field(default="", max_length=200)
    task: dict | None = None
