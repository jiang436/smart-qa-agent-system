"""对话相关 Schema"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求"""

    user_id: str = Field(..., description="用户 ID")
    message: str = Field(..., description="用户消息内容")
    session_id: str = Field(default="", description="会话 ID，为空则自动创建")

    model_config = {"json_schema_extra": {"example": {"user_id": "U1001", "message": "怎么设置定时清扫？"}}}


class ChatResponse(BaseModel):
    """对话响应"""

    answer: str = Field(..., description="AI 回答内容")
    session_id: str = Field(..., description="会话 ID")
    intent: str = Field(default="", description="识别的意图: qa / troubleshoot / consumables / general")
