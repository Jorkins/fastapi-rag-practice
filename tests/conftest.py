"""测试配置：用内存 SQLite + eager 模式 + 关调度器。"""
import os

import pytest

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["ENABLE_SCHEDULER"] = "false"


@pytest.fixture(autouse=True)
async def _setup_db():
    """每个测试前建表、后清空，保证隔离。

    ASGITransport 不会自动触发 lifespan，因此这里手动初始化。
    """
    from app.core.db import Base, engine, init_db

    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
