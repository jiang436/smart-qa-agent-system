"""用户账户模型 — 认证 + 会话管理"""

import hashlib
import secrets
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from smart_qa.models.base import Base


class User(Base):
    """用户账户

    存储登录凭证和密码哈希。
    密码使用 pbkdf2_hmac 加盐哈希存储，不存储明文。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # user / admin
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @staticmethod
    def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
        """对密码进行 pbkdf2_hmac 加盐哈希

        Args:
            password: 明文密码
            salt: 盐值，为 None 时自动生成 16 字节

        Returns:
            (password_hash, salt) 元组，salt 用于存储，hash 用于验证
        """
        if salt is None:
            salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return key.hex(), salt

    def verify_password(self, password: str) -> bool:
        """校验密码

        Args:
            password: 待校验的明文密码

        Returns:
            True 匹配，False 不匹配
        """
        key, _ = self.hash_password(password, self.salt)
        return key == self.password_hash


class UserSession(Base):
    """用户会话 — 登录成功后颁发的令牌

    一个用户可以拥有多个活跃会话（多设备登录）。
    会话有过期时间，过期后需重新登录。
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)

    @staticmethod
    def generate_token() -> str:
        """生成随机令牌"""
        return secrets.token_urlsafe(48)
