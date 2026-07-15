"""用户认证依赖注入 — FastAPI Depends

提取并验证 Authorization: Bearer <token> 头。
所有需要登录的路由通过此依赖获取当前用户 ID。

用法:
    @router.get("/me")
    async def get_me(user_id: str = Depends(get_current_user)):
        return {"user_id": user_id}

    # 可选的认证（未登录也能访问，user_id 可能为 None）
    @router.get("/public")
    async def public(user_id: str | None = Depends(get_optional_user)):
        ...
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_qa.database.engine import get_db
from smart_qa.models.user import UserSession


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> str:
    """获取当前登录用户 ID（必需认证）

    从 Authorization header 提取 Bearer token，
    在 user_sessions 表中验证令牌有效性。

    Raises:
        HTTPException 401: 未提供 token / token 无效 / token 已过期
        HTTPException 500: 数据库不可用

    Returns:
        user_id — 当前登录用户的 ID（字符串）
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="令牌为空")

    try:
        result = await db.execute(
            select(UserSession).where(
                UserSession.token == token,
                UserSession.is_active == True,  # noqa: E712
                UserSession.expires_at > __import__("datetime").datetime.utcnow(),
            )
        )
        session = result.scalar_one_or_none()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {str(e)[:100]}") from e

    if session is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    return session.user_id


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> str | None:
    """获取当前登录用户 ID（可选认证）

    与 get_current_user 相同，但未登录时返回 None 而非 401。
    用于无需强制登录但需要用户上下文的路由。
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None

    token = auth.removeprefix("Bearer ").strip()
    if not token:
        return None

    try:
        result = await db.execute(
            select(UserSession).where(
                UserSession.token == token,
                UserSession.is_active == True,  # noqa: E712
                UserSession.expires_at > __import__("datetime").datetime.utcnow(),
            )
        )
        session = result.scalar_one_or_none()
    except Exception:
        return None

    return session.user_id if session else None
