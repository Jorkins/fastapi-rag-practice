"""进程内定时任务：APScheduler。

实践点（与 Celery Beat 的分工）：
1. APScheduler：单机、轻量、进程内，适合「定时统计/清理/重建索引」等不重活；
2. Celery Beat：分布式、可横向扩容、任务持久化，适合「文档切分+向量化」等重活；
3. 两者可共存。在 async 环境必须用 AsyncIOScheduler，否则会阻塞事件循环。
"""
from sqlalchemy import func, select

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.db import async_session_factory
from app.core.logging import get_logger
from app.models.document import Document

logger = get_logger(__name__)


async def _report_ready_count() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(Document).where(Document.status == "ready")
        )
        count = result.scalar() or 0
    logger.info("定时任务：当前就绪文档数 = %d", count)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        _report_ready_count,
        "interval",
        seconds=60,
        id="report-ready-count",
        replace_existing=True,
    )
    return scheduler


def shutdown_scheduler(scheduler: AsyncIOScheduler) -> None:
    scheduler.shutdown(wait=False)
