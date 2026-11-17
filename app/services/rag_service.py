"""RAG 服务：把各组件组装成完整问答链路。

chunk(入库时) -> embedding(入库时) -> 检索(此时) -> prompt -> LLM
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.rag.embedder import get_embedder
from app.rag.llm import get_llm
from app.rag.prompt import build_prompt
from app.rag.retriever import retrieve


async def answer_question(db: AsyncSession, question: str) -> tuple[str, list[dict]]:
    """返回 (answer, sources)。sources 为 [{"content","score","document_id"}, ...]。"""
    embedder = get_embedder(settings.embedding_provider)

    sources = await retrieve(db, embedder, question, settings.top_k)

    llm = get_llm(settings.llm_provider)
    messages = build_prompt(question, [s["content"] for s in sources])
    answer = await llm.chat(messages)

    return answer, sources
