"""统一任务派发：屏蔽 eager 与分布式两种模式的差异。

实践点：
1. eager 模式下（本地无 Redis），Celery 的 delay() 会同步执行任务，
   而任务内部用 asyncio.run() 包异步逻辑——若在 FastAPI 事件循环里调用
   会抛 "asyncio.run() cannot be called from a running event loop"；
2. 因此在这里统一判断：eager 直接 await 异步逻辑，分布式才走 delay()；
3. 业务代码只依赖 dispatch_index，不关心底层是同步还是异步。
"""
from app.core.config import settings


async def dispatch_index(document_id: str) -> None:
    if settings.celery_task_always_eager:
        from app.tasks.indexing import _index

        await _index(document_id)
    else:
        from app.tasks.indexing import index_document

        index_document.delay(document_id)
