"""知识库上传文件记录表"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from smart_qa.models.base import Base


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)  # pdf / md / txt
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    dimension: Mapped[int] = mapped_column(Integer, default=512)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
