"""搜索日志 & 反馈路由 — POST /search/log, POST /search/feedback, GET /search/logs"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_qa.database.engine import get_db
from smart_qa.models.search_log import SearchFeedback, SearchLog
from smart_qa.observability.logger import logger

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/log")
async def log_search(
    query: str,
    user_id: str = "anonymous",
    session_id: str = "",
    intent: str = "",
    answer_length: int = 0,
    duration_ms: int = 0,
    source: str = "chat",
    db: AsyncSession = Depends(get_db),
):
    """记录一次搜索/对话（由 chat 端点内部调用）"""
    try:
        record = SearchLog(
            session_id=session_id or "unknown",
            user_id=user_id,
            query=query[:500],
            intent=intent or "",
            answer_length=answer_length,
            duration_ms=duration_ms,
            source=source,
            created_at=datetime.utcnow(),
        )
        db.add(record)
        await db.commit()
        return {"status": "ok", "id": record.id}
    except Exception as e:
        logger.warning("搜索日志写入失败: {}", e)
        return {"status": "error", "message": str(e)[:100]}


@router.post("/feedback")
async def submit_feedback(
    search_log_id: int, user_id: str, action: str, detail: str = "", db: AsyncSession = Depends(get_db)
):
    """提交用户反馈（like / dislike）"""
    if action not in ("like", "dislike"):
        return {"status": "error", "message": "action 必须为 like 或 dislike"}
    try:
        fb = SearchFeedback(
            search_log_id=search_log_id,
            user_id=user_id,
            action=action,
            detail=detail[:500] or None,
            created_at=datetime.utcnow(),
        )
        db.add(fb)
        await db.commit()
        return {"status": "ok", "id": fb.id}
    except Exception as e:
        logger.warning("反馈写入失败: {}", e)
        return {"status": "error", "message": str(e)[:100]}


@router.get("/logs")
async def list_search_logs(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)
):
    """搜索日志列表（管理后台用）"""
    try:
        total = await db.scalar(select(func.count(SearchLog.id)))
        result = await db.execute(
            select(SearchLog).order_by(desc(SearchLog.created_at)).offset((page - 1) * page_size).limit(page_size)
        )
        logs = []
        for row in result.scalars().all():
            logs.append(
                {
                    "id": row.id,
                    "session_id": row.session_id,
                    "user_id": row.user_id,
                    "query": row.query[:100],
                    "intent": row.intent,
                    "answer_length": row.answer_length,
                    "duration_ms": row.duration_ms,
                    "source": row.source,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
            )
        return {"total": total or 0, "page": page, "page_size": page_size, "logs": logs}
    except Exception as e:
        logger.warning("搜索日志查询失败: {}", e)
        return {"total": 0, "page": page, "page_size": page_size, "logs": []}
