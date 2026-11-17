"""文档与切片模型。

实践点：
1. Mapped + mapped_column 是 SQLAlchemy 2.0 推荐的声明式写法；
2. Document 存原始文本（教学简化），生产存对象存储 key + 路径；
3. Chunk.embedding 用 JSON 文本存向量（教学简化），生产用 pgvector 列；
4. relationship 用 lazy="raise"：async 下未预加载就访问会显式抛错，
   防止懒加载在事件循环里抛 MissingGreenlet。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[str] = mapped_column(Text)
    # pending -> indexing -> ready | failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="raise"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    # JSON 序列化的向量（list[float]）；生产建议 pgvector 的 vector 类型
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)

    document: Mapped["Document"] = relationship(back_populates="chunks", lazy="raise")
