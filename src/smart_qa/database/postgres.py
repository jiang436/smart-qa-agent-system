"""数据库 — PostgreSQL 数据访问层 (CRUD)"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_qa.models import Session


class PostgresClient:
    """PostgreSQL 数据访问客户端"""

    # ── 会话操作 ──

    @staticmethod
    async def create_session(db: AsyncSession, session_id: str, user_id: str) -> Session:
        rec = Session(session_id=session_id, user_id=user_id)
        db.add(rec)
        await db.commit()
        return rec

    @staticmethod
    async def get_session(db: AsyncSession, session_id: str) -> Session | None:
        result = await db.execute(select(Session).where(Session.session_id == session_id))
        return result.scalar_one_or_none()
