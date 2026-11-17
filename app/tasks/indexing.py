"""文档索引任务：Celery 异步执行「切分 + 向量化 + 入库」。

实践点（对应 Mini-RAG Project 的 idempotent task 设计）：
1. Celery 任务入口是同步函数，内部用 asyncio.run 包异步逻辑
   （SQLAlchemy async 需要事件循环）；
2. 任务状态落库（IndexTask），可查询、可重试；
3. 异常要回滚，并把 document 置为 failed，避免「半索引」脏状态；
4. eager 模式下（本地无 Redis）`delay()` 同步执行，便于开发调试。
"""
import asyncio
import json

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import async_session_factory
from app.core.logging import get_logger
from app.models.document import Chunk, Document
from app.models.task import IndexTask
from app.rag.chunker import chunk_text
from app.rag.embedder import get_embedder

logger = get_logger(__name__)


async def _index(document_id: str) -> None:
    async with async_session_factory() as db:
        doc = await db.get(Document, document_id)
        if doc is None:
            return
        task = IndexTask(document_id=document_id, status="running")
        db.add(task)
        doc.status = "indexing"
        await db.commit()

        try:
            embedder = get_embedder(settings.embedding_provider)
            chunks = chunk_text(doc.content, settings.chunk_size, settings.chunk_overlap)
            embeddings = await embedder.embed(chunks)

            for i, (text, emb) in enumerate(zip(chunks, embeddings)):
                db.add(
                    Chunk(
                        document_id=document_id,
                        content=text,
                        embedding=json.dumps(emb),
                        chunk_index=i,
                    )
                )

            task.status = "done"
            doc.status = "ready"
            await db.commit()
            logger.info("文档 %s 索引完成，共 %d 个切片", document_id, len(chunks))
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            # 重新获取最新状态再标记失败
            doc = await db.get(Document, document_id)
            task.status = "failed"
            task.error = str(exc)[:500]
            if doc is not None:
                doc.status = "failed"
            await db.commit()
            logger.exception("文档 %s 索引失败", document_id)
            raise


@celery_app.task(name="app.tasks.indexing.index_document")
def index_document(document_id: str) -> str:
    """Celery 任务入口。"""
    asyncio.run(_index(document_id))
    return document_id


@celery_app.task(name="app.tasks.indexing.cleanup_failed_docs")
def cleanup_failed_docs() -> int:
    """Beat 周期任务：清理失败的文档，避免堆积。返回删除数量。"""
    return asyncio.run(_cleanup_failed())


async def _cleanup_failed() -> int:
    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.status == "failed"))
        docs = result.scalars().all()
        for doc in docs:
            await db.delete(doc)
        await db.commit()
        logger.info("清理失败文档 %d 条", len(docs))
        return len(docs)
