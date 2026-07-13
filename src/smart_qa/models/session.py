"""会话记录表 — 含对话消息持久化"""

import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from smart_qa.models.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(String(64), index=True, nullable=False)
    intent = Column(String(32), nullable=True)
    scenario = Column(String(32), nullable=True)
    message_count = Column(Integer, default=0)
    messages = Column(Text, nullable=True)  # JSON 数组：完整对话历史
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_messages(self) -> list[dict]:
        """反序列化消息历史"""
        if not self.messages:
            return []
        try:
            return json.loads(self.messages)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_messages(self, msgs: list[dict]):
        """序列化消息历史"""
        self.messages = json.dumps(msgs, ensure_ascii=False)
        self.message_count = len(msgs)
