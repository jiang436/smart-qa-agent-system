"""Session Repository — 多轮对话持久化接口

用法:
    repo = PostgresSessionRepository()
    await repo.save("s1", "u1", [...messages...], intent="qa")
    msgs = await repo.load("s1")

测试:
    repo = InMemorySessionRepository()
"""
from __future__ import annotations

import json
from typing import Protocol, runtime_checkable


@runtime_checkable
class SessionRepository(Protocol):
    """会话存储接口"""

    async def save(self, session_id: str, user_id: str, messages: list,
                   intent: str | None = None) -> None:
        """持久化对话消息 (UPSERT)"""
        ...

    async def load(self, session_id: str, limit: int = 50) -> list[dict]:
        """加载对话历史，按时间顺序"""
        ...


def _to_serializable(messages: list) -> list[dict]:
    """将 LangChain Message 对象转为可序列化 dict"""
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append(m)
        else:
            result.append({
                "role": getattr(m, "type", "") or getattr(m, "role", ""),
                "content": getattr(m, "content", ""),
            })
    return result


class PostgresSessionRepository:
    """PostgreSQL 实现"""

    async def save(self, session_id: str, user_id: str, messages: list,
                   intent: str | None = None) -> None:
        if not session_id or not messages:
            return
        messages = _to_serializable(messages)
        try:
            from sqlalchemy import text

            from smart_qa.database.engine import get_session_factory

            factory = get_session_factory()
            async with factory() as db:
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
                            SET messages = :msgs, message_count = :cnt,
                                intent = COALESCE(:intent, intent), updated_at = NOW()
                            WHERE session_id = :sid
                        """),
                        {"msgs": msgs_json, "cnt": msg_count, "intent": intent, "sid": session_id},
                    )
                else:
                    await db.execute(
                        text("""
                            INSERT INTO sessions (session_id, user_id, messages, message_count, intent, created_at, updated_at)
                            VALUES (:sid, :uid, :msgs, :cnt, :intent, NOW(), NOW())
                        """),
                        {"sid": session_id, "uid": user_id, "msgs": msgs_json, "cnt": msg_count, "intent": intent},
                    )
                await db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("PG 保存对话失败 session=%s err=%s", session_id, e)

    async def load(self, session_id: str, limit: int = 50) -> list[dict]:
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
            import logging
            logging.getLogger(__name__).debug("PG 加载对话失败 session=%s err=%s", session_id, e)
        return []


class InMemorySessionRepository:
    """内存实现（测试用）"""

    def __init__(self):
        self._store: dict[str, dict] = {}

    async def save(self, session_id: str, user_id: str, messages: list,
                   intent: str | None = None) -> None:
        self._store[session_id] = {
            "user_id": user_id,
            "messages": _to_serializable(messages),
            "intent": intent or "",
        }

    async def load(self, session_id: str, limit: int = 50) -> list[dict]:
        record = self._store.get(session_id)
        if record:
            msgs = record.get("messages", [])
            return msgs[-limit:] if isinstance(msgs, list) else []
        return []
