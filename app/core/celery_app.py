"""Celery 实例与 Beat 定时调度。

实践点：
1. broker/backend 走 Redis，配置从 settings 来；
2. task_always_eager 支持本地降级（无 Redis 同步执行）；
3. beat_schedule 声明周期性任务（分布式定时），与进程内 APScheduler 互补。
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "fastapi_rag",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.indexing"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
)

# 分布式定时任务：每 10 分钟清理一次失败文档
celery_app.conf.beat_schedule = {
    "cleanup-failed-docs-every-10-min": {
        "task": "app.tasks.indexing.cleanup_failed_docs",
        "schedule": 600.0,
    },
}
