"""检索环节：给定 query，返回最相关的 top_k 个切片。

实践点：
1. 查询向量与所有切片向量算相似度，取 top_k；
2. 生产换成向量库 ANN 检索 + 可选重排（rerank）提升精度；
3. 这里把相似度分数一并返回，便于前端展示「证据」。
"""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Chunk
from app.rag.embedder import Embedder
from app.rag.store import cosine_similarity


async def retrieve(
    db: AsyncSession,
    embedder: Embedder,
    query: str,
    top_k: int,
) -> list[dict]:
    """返回 [{"content", "score", "document_id"}, ...]，按相似度降序。"""
    query_vec = (await embedder.embed([query]))[0]

    result = await db.execute(select(Chunk).where(Chunk.embedding.is_not(None)))
    chunks = result.scalars().all()

    scored: list[tuple[float, Chunk]] = []
    for chunk in chunks:
        try:
            emb = json.loads(chunk.embedding)
        except (TypeError, ValueError):
            continue
        scored.append((cosine_similarity(query_vec, emb), chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "content": c.content,
            "score": round(s, 4),
            "document_id": c.document_id,
        }
        for s, c in scored[:top_k]
    ]
