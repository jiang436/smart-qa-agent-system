"""用户画像持久化模型 — 长期记忆层（LTM）

存储从对话中提取的「确信不会变的事实」:
  - 设备型号 / 序列号
  - 使用偏好（偏好模式、定时习惯等）
  - 居住环境（户型、面积等）
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from smart_qa.models.base import Base


class UserProfile(Base):
    """用户画像 — LTM 持久化

    每条记录对应一个用户，包含所有已知的确定性事实。
    非确定性信息（临时偏好、单次故障）不存入。
    """

    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, unique=True)

    # ── 设备信息 ──
    device_model = Column(String(64), nullable=True)  # X30 Pro / T10 / …
    device_sn = Column(String(64), nullable=True)  # 序列号

    # ── 偏好 ──
    preferred_mode = Column(String(32), nullable=True)  # 安静/标准/强力
    mopping_enabled = Column(String(8), nullable=True)  # "yes" / "no"

    # ── 环境 ──
    home_layout = Column(String(64), nullable=True)  # 三室一厅 / 复式 / …

    # ── 标签（JSON 数组，自由格式关键词） ──
    tags = Column(Text, nullable=True)

    # ── 元数据 ──
    conversation_count = Column(Integer, default=1, nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, device={self.device_model})>"
