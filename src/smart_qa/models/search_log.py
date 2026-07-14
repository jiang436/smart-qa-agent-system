"""搜索日志 + 用户反馈 ORM 模型"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from smart_qa.models.base import Base


class SearchLog(Base):
    """搜索日志 — 记录每次搜索/对话请求"""

    __tablename__ = "search_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    user_id = Column(String(64), index=True, nullable=False, default="anonymous")
    query = Column(Text, nullable=False)
    intent = Column(String(32), nullable=True)
    answer_length = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    source = Column(String(32), default="chat")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SearchFeedback(Base):
    """用户反馈 — 对搜索结果的满意度"""

    __tablename__ = "search_feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_log_id = Column(Integer, index=True, nullable=False)
    user_id = Column(String(64), nullable=False)
    action = Column(String(16), nullable=False)  # like / dislike
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
