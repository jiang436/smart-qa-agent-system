"""会话路由 — GET /session/{id}/history, GET /sessions, DELETE /session/{id}"""

import json

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/sessions")
async def list_sessions(
    user_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """列出用户的所有会话"""
    try:
        from sqlalchemy import text

        from smart_qa.database.engine import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            rows = await db.execute(
                text("""
                    SELECT session_id, intent, message_count, messages, updated_at
                    FROM sessions
                    WHERE user_id = :uid
                    ORDER BY updated_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"uid": user_id, "limit": limit, "offset": offset},
            )
            sessions = []
            for row in rows.fetchall():
                preview = ""
                try:
                    msgs = json.loads(row[3]) if row[3] else []
                    if msgs and isinstance(msgs, list):
                        for m in msgs:
                            if m.get("role") == "user":
                                content = m.get("content", "")
                                preview = content[:60] + ("..." if len(content) > 60 else "")
                                break
                except Exception:
                    pass
                sessions.append({
                    "session_id": row[0],
                    "intent": row[1] or "general",
                    "message_count": row[2] or 0,
                    "preview": preview,
                    "updated_at": row[4].isoformat() if row[4] else "",
                })
            return {"sessions": sessions, "total": len(sessions)}
    except Exception as e:
        return {"sessions": [], "total": 0, "note": str(e)[:200]}


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


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    if not session_id or len(session_id) > 64:
        raise HTTPException(status_code=400, detail="无效的会话 ID")
    try:
        from sqlalchemy import text

        from smart_qa.database.engine import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            await db.execute(
                text("DELETE FROM sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )
            await db.commit()
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
