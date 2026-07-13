"""对话相关 Schema — Pydantic 数据校验"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求"""

    user_id: str = Field(..., min_length=1, max_length=64, description="用户 ID")
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息内容")
    session_id: str = Field(default="", max_length=64, description="会话 ID，为空则自动创建")

    model_config = {"json_schema_extra": {"example": {"user_id": "U1001", "message": "怎么设置定时清扫？"}}}


class ChatResponse(BaseModel):
    """对话响应"""

    answer: str = Field(..., min_length=0, description="AI 回答内容")
    session_id: str = Field(..., max_length=64, description="会话 ID")
    intent: str = Field(
        default="general",
        pattern=r"^(qa|troubleshoot|consumables|device_control|report|general)$",
        description="识别的意图",
    )
