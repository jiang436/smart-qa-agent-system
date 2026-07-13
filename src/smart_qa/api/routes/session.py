"""会话路由 — GET /session/{id}/history"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/session/{session_id}/history")
async def get_session_history(session_id: str):
    """获取对话历史"""
    if not session_id or len(session_id) > 64:
        raise HTTPException(status_code=400, detail="无效的会话 ID")
    try:
        from smart_qa.memory.conversation_store import load_messages

        messages = await load_messages(session_id)
        return {"session_id": session_id, "messages": messages, "total": len(messages)}
    except Exception:
        return {"session_id": session_id, "messages": [], "note": "会话存储服务暂不可用"}
