"""审批相关 Schema — Pydantic 数据校验"""

from pydantic import BaseModel, Field


class ApproveRequest(BaseModel):
    """审批请求"""

    session_id: str = Field(..., min_length=1, max_length=64, description="会话 ID")
    decision: str = Field(
        ...,
        pattern=r"^(approve|reject|modify)$",
        description="审批决策: approve / reject / modify",
    )
    feedback: str = Field(default="", max_length=500, description="反馈意见（仅 modify 时需要）")


class ApproveResponse(BaseModel):
    """审批响应"""

    status: str = Field(..., pattern=r"^(ok|error)$")
    decision: str | None = Field(None, description="最终决策")
    message: str = Field(default="", max_length=200)
