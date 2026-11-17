"""问答接口：走完整 RAG 链路，并把问答记录落库。"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.chat import ChatMessage
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import answer_question

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    summary="知识库问答",
    description="传入问题，走检索增强生成链路：问题向量化 → 检索 top_k 切片 → 拼 Prompt → LLM 生成，返回答案与引用来源，并落一条问答记录。",
)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    answer, sources = await answer_question(db, req.question)

    # 问答记录落库：session_id 可选，不传则每条独立
    # sources 在服务层是 list[dict]，response_model 是边缘才转换的，直接序列化
    db.add(
        ChatMessage(
            session_id=req.session_id or "",
            question=req.question,
            answer=answer,
            sources=json.dumps(sources, ensure_ascii=False, default=str),
        )
    )
    await db.commit()

    return ChatResponse(answer=answer, sources=sources)
