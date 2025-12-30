"""会话路由 — GET /session/{id}/history"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/session/{session_id}/history")
async def get_session_history(session_id: str):
    """获取对话历史"""
    try:
        from src.database.redis import RedisClient

        messages = await RedisClient.get_messages(session_id)
        return {"session_id": session_id, "messages": messages, "total": len(messages)}
    except Exception:
        return {"session_id": session_id, "messages": [], "note": "会话存储服务暂不可用"}
