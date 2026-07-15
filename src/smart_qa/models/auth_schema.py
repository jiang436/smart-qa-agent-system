"""用户认证 Schema — Pydantic 数据校验"""

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """注册请求"""

    username: str = Field(..., min_length=2, max_length=64, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    display_name: str = Field(default="", max_length=64, description="显示名称")


class LoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class AuthResponse(BaseModel):
    """认证响应"""

    token: str = Field(..., description="Bearer 令牌")
    user_id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    role: str = Field(default="user", description="角色: user / admin")
    display_name: str = Field(default="", description="显示名称")


class LogoutRequest(BaseModel):
    """登出请求"""

    token: str = Field(..., min_length=1, description="要注销的令牌")


class ErrorResponse(BaseModel):
    """错误响应"""

    detail: str = Field(..., description="错误信息")


class UserInfoResponse(BaseModel):
    """用户信息响应"""

    user_id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    role: str = Field(..., description="角色: user / admin")
    display_name: str = Field(default="", description="显示名称")
