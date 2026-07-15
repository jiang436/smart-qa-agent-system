"""用户认证路由 — 注册 / 登录 / 登出 / 用户信息"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_qa.api.auth_deps import get_current_user
from smart_qa.database.engine import get_db
from smart_qa.models.auth_schema import (
    AuthResponse,
    ErrorResponse,
    LoginRequest,
    LogoutRequest,
    RegisterRequest,
    UserInfoResponse,
)
from smart_qa.models.user import User, UserSession
from smart_qa.observability.logger import logger

router = APIRouter(tags=["auth"])

SESSION_TTL_HOURS = 72  # 会话过期时间（3 天）


@router.post("/register", response_model=AuthResponse, responses={409: {"model": ErrorResponse}})
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """用户注册

    创建新用户账户，返回 Bearer 令牌。
    用户名唯一，重复注册返回 409。
    第一个注册的用户自动成为管理员（role=admin）。
    """
    try:
        existing = await db.execute(select(User).where(User.username == req.username))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="用户名已存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {str(e)[:100]}") from e

    # 检查是否是第一个用户（自动成为管理员）
    count_result = await db.execute(select(User).limit(1))
    is_first = count_result.first() is None

    password_hash, salt = User.hash_password(req.password)
    user = User(
        username=req.username,
        password_hash=password_hash,
        salt=salt,
        display_name=req.display_name or req.username,
        role="admin" if is_first else "user",
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"用户创建失败: {str(e)[:100]}") from e

    token = await _create_session(db, str(user.id))
    logger.info("用户注册 user_id={} username={} role={}", user.id, req.username, user.role)
    return AuthResponse(
        token=token,
        user_id=str(user.id),
        username=user.username,
        role=user.role,
        display_name=user.display_name or user.username,
    )


@router.post("/login", response_model=AuthResponse, responses={401: {"model": ErrorResponse}})
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    try:
        result = await db.execute(select(User).where(User.username == req.username))
        user = result.scalar_one_or_none()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {str(e)[:100]}") from e

    if user is None or not user.verify_password(req.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = await _create_session(db, str(user.id))
    logger.info("用户登录 user_id={} username={} role={}", user.id, req.username, user.role)
    return AuthResponse(
        token=token,
        user_id=str(user.id),
        username=user.username,
        role=user.role,
        display_name=user.display_name or user.username,
    )


@router.post("/logout", response_model=dict, responses={401: {"model": ErrorResponse}})
async def logout(req: LogoutRequest, db: AsyncSession = Depends(get_db)):
    """用户登出"""
    try:
        result = await db.execute(
            select(UserSession).where(UserSession.token == req.token, UserSession.is_active == True)  # noqa: E712
        )
        session = result.scalar_one_or_none()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {str(e)[:100]}") from e

    if session is None:
        raise HTTPException(status_code=401, detail="令牌无效")

    session.is_active = False
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"登出失败: {str(e)[:100]}") from e

    logger.info("用户登出 user_id={}", session.user_id)
    return {"status": "ok", "message": "已登出"}


@router.get("/user/me", response_model=UserInfoResponse)
async def get_me(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """获取当前登录用户信息

    需要 Authorization: Bearer <token> 头。
    返回用户 ID、用户名、角色、显示名称。
    """
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserInfoResponse(
        user_id=str(user.id),
        username=user.username,
        role=user.role,
        display_name=user.display_name or user.username,
    )


async def _create_session(db: AsyncSession, user_id: str) -> str:
    """创建用户会话（颁发令牌）"""
    token = UserSession.generate_token()
    session = UserSession(
        user_id=user_id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS),
    )
    db.add(session)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"令牌签发失败: {str(e)[:100]}") from e
    return token
