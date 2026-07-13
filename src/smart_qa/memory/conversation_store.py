"""对话持久化存储 — PostgreSQL 版

替代 Redis 作为多轮对话的持久化后端。
PostgreSQL 保证服务重启后对话上下文不丢失。

用法:
    from smart_qa.memory.conversation_store import save_messages, load_messages

    # 保存 (自动创建/更新 session 记录)
    await save_messages(session_id, user_id, messages, intent="qa")

    # 加载
    msgs = await load_messages(session_id)  # -> list[dict]
"""

from __future__ import annotations

import json

from smart_qa.observability.logger import logger

_TTL_DAYS = 7


async def save_messages(
    session_id: str,
    user_id: str,
    messages: list,
    intent: str | None = None,
):
    """持久化对话消息到 PostgreSQL

    自动 UPSERT：session 存在则更新，不存在则创建。
    """
    if not session_id or not messages:
        return

    try:
        from sqlalchemy import text

        from smart_qa.database.engine import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            # 检查 session 是否存在
            row = await db.execute(
                text("SELECT id FROM sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )
            msgs_json = json.dumps(messages, ensure_ascii=False)
            msg_count = len(messages)

            if row.fetchone():
                await db.execute(
                    text("""
                        UPDATE sessions
                        SET messages = :msgs,
                            message_count = :cnt,
                            intent = COALESCE(:intent, intent),
                            updated_at = NOW()
                        WHERE session_id = :sid
                    """),
                    {"msgs": msgs_json, "cnt": msg_count, "intent": intent, "sid": session_id},
                )
            else:
                await db.execute(
                    text("""
                        INSERT INTO sessions
                            (session_id, user_id, messages, message_count, intent)
                        VALUES
                            (:sid, :uid, :msgs, :cnt, :intent)
                    """),
                    {"sid": session_id, "uid": user_id, "msgs": msgs_json, "cnt": msg_count, "intent": intent},
                )
            await db.commit()
    except Exception as e:
        logger.warning("PG 保存对话失败 session={} err={}", session_id, e)


async def load_messages(session_id: str, limit: int = 50) -> list[dict]:
    """从 PostgreSQL 加载对话历史

    Returns:
        消息列表 [{role, content}, ...]，按时间顺序
        无历史则返回 []
    """
    if not session_id:
        return []

    try:
        from sqlalchemy import text

        from smart_qa.database.engine import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            row = await db.execute(
                text("SELECT messages FROM sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )
            result = row.fetchone()
            if result and result[0]:
                msgs = json.loads(result[0])
                return msgs[-limit:] if isinstance(msgs, list) else []
    except Exception as e:
        logger.debug("PG 加载对话失败 session={} err={}", session_id, e)

    return []
