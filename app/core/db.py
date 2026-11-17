"""SQLAlchemy 2.0 async 数据库层。

实践点：
1. create_async_engine + async_sessionmaker 构建异步引擎与会话工厂；
2. DeclarativeBase 作为所有模型基类，init_db 用 create_all 建表（教学用）；
   生产建议改用 Alembic 迁移，见 README；
3. get_db 作为 FastAPI 依赖，请求结束自动关闭会话。
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个会话。"""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """启动时建表。教学用；生产用 Alembic。"""
    # 避免循环导入：这里延迟 import 模型以触发元数据注册
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
