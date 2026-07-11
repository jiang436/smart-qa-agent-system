"""HITL 确认路由 — POST /approve"""

from fastapi import APIRouter, HTTPException

from smart_qa.agent.agents.hitl import HITLManager

router = APIRouter()


@router.post("/approve")
async def approve_action(session_id: str, decision: str, feedback: str = ""):
    """HITL 确认 — 用户对高风险操作进行确认/拒绝/修改"""
    hitl = HITLManager()
    result = hitl.resolve_approval(session_id, decision, feedback)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return {
        "status": "ok",
        "decision": result.get("decision", decision),
        "feedback": result.get("feedback", ""),
        "context": result.get("context", {}),
    }
