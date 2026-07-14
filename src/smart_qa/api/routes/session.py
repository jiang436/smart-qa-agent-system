"""会话路由 — GET /session/{id}/history, GET /sessions"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, func, select

from smart_qa.memory.conversation_store import load_messages
from smart_qa.models.session import Session
from smart_qa.observability.logger import logger

router = APIRouter()


@router.get("/sessions")
async def list_sessions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    """获取所有会话摘要列表（管理后台 / 侧栏用）"""
    try:
        from smart_qa.database.engine import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            total = await db.scalar(select(func.count(Session.id)))
            result = await db.execute(
                select(Session).order_by(desc(Session.updated_at)).offset((page - 1) * page_size).limit(page_size)
            )
            sessions = []
            for row in result.scalars().all():
                msgs = row.get_messages()
                preview = ""
                for m in msgs:
                    if m.get("role") == "user" and m.get("content"):
                        preview = m["content"][:80]
                        break
                sessions.append(
                    {
                        "session_id": row.session_id,
                        "user_id": row.user_id,
                        "intent": row.intent or "",
                        "message_count": row.message_count or len(msgs),
                        "preview": preview,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
                        "created_at": row.created_at.isoformat() if row.created_at else "",
                    }
                )
            return {"total": total or 0, "page": page, "page_size": page_size, "sessions": sessions}
    except Exception as e:
        logger.warning("会话列表查询失败: {}", e)
        return {"total": 0, "page": page, "page_size": page_size, "sessions": []}


@router.get("/session/{session_id}/history")
async def get_session_history(session_id: str):
    """获取对话历史"""
    if not session_id or len(session_id) > 64:
        raise HTTPException(status_code=400, detail="无效的会话 ID")
    try:
        messages = await load_messages(session_id)
        return {"session_id": session_id, "messages": messages, "total": len(messages)}
    except Exception:
        return {"session_id": session_id, "messages": [], "note": "会话存储服务暂不可用"}
