"""HITL 确认路由 — POST /approve"""

from fastapi import APIRouter

from smart_qa.models.approval_schema import ApproveRequest, ApproveResponse
from smart_qa.observability.logger import logger

router = APIRouter()


@router.post("/approve", response_model=ApproveResponse)
async def approve_action(req: ApproveRequest):
    """HITL 确认 — 用户对高风险操作进行确认/拒绝/修改

    请求体:
      {"session_id": "...", "decision": "approve", "feedback": ""}
    """
    from smart_qa.agent.agents.hitl import HITLManager

    logger.info("HITL 审批 session={} decision={} feedback={}", req.session_id, req.decision, req.feedback)

    hitl = HITLManager()
    result = hitl.resolve_approval(req.session_id, req.decision, req.feedback)

    if "error" in result:
        logger.warning("HITL 审批异常 session={} err={}", req.session_id, result["error"])
        return ApproveResponse(
            status="error",
            decision=None,
            message=result["error"],
        )

    return ApproveResponse(
        status="ok",
        decision=result.get("decision", req.decision),
        message=result.get("feedback", ""),
    )
