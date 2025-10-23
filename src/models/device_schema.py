"""设备相关 Schema"""

from pydantic import BaseModel, Field


class DeviceStatus(BaseModel):
    """设备状态"""

    user_id: str = Field(..., description="用户 ID")
    device_name: str | None = None
    device_model: str | None = None
    battery: int | None = None
    status: str | None = None
    water_level: str | None = None
    dust_bin: str | None = None
    mop: str | None = None
    online: bool = False
    source: str | None = None


class ScheduleCreate(BaseModel):
    """创建定时任务"""

    user_id: str = Field(..., description="用户 ID")
    time: str = Field(..., description="清扫时间，格式 HH:MM", pattern=r"^\d{1,2}:\d{2}$")
    room: str = Field(default="全屋", description="清扫房间名称")


class ScheduleResponse(BaseModel):
    """定时任务响应"""

    status: str = Field(..., description="ok / error")
    message: str = Field(default="", description="结果说明")
    task: dict | None = None
