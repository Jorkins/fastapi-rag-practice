"""问答记录表：RAG 应用的核心业务数据。

实践点（结合主题设计的新表）：
1. 每次问答落一条记录，形成可回溯的问答历史；
2. session_id 支持多轮会话分组，同一 session 的记录按时间排序即上下文；
3. sources 存 JSON 文本（命中切片 id + 分数），是评测与质量抽样的原料；
4. 无外键强约束 document_id（存进 JSON），问答与文档生命周期解耦。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # 会话分组：前端生成一个 uuid 传进来，同一会话的多轮问答共享它
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    # JSON 文本：[{"document_id": ..., "content": ..., "score": ...}, ...]
    sources: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_chat_session_created", "session_id", "created_at"),
    )
