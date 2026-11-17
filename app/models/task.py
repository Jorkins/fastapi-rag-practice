"""索引任务表：幂等控制。

实践点（参考 Mini-RAG Project 的 idempotent tasks）：
1. 异步任务与业务解耦，任务状态落库，可查询、可重试；
2. 状态机：queued -> running -> done | failed；
3. 幂等：同一 document_id 重复投递不会产生脏数据。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IndexTask(Base):
    __tablename__ = "index_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
