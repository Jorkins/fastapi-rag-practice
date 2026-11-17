"""问答相关 schema。"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="用户问题")
    # 可选：多轮会话分组 id，同一会话传同一个值
    session_id: str | None = Field(default=None, max_length=36)


class Source(BaseModel):
    content: str
    score: float
    document_id: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
