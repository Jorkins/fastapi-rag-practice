"""应用入口。

实践点：
1. lifespan 上下文管理器替代已弃用的 @app.on_event，
   统一管理启动（建表、启调度器）与关闭（停调度器）；
2. 路由通过 include_router 挂载，按业务拆分。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import chat, documents
from app.core.config import settings
from app.core.db import init_db
from app.core.errors import register_exception_handlers
from app.scheduler import create_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = create_scheduler() if settings.enable_scheduler else None
    if scheduler is not None:
        scheduler.start()
    yield
    if scheduler is not None:
        shutdown_scheduler(scheduler)


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

# 统一异常处理：AppError / HTTPException / 未捕获异常 → 一致的错误结构
register_exception_handlers(app)

app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
