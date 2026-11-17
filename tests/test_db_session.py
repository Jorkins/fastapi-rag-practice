"""SQLAlchemy 2.0 async 会话行为测试：session-per-request 语义、事务边界、懒加载防护。"""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import selectinload

from app.core.db import async_session_factory
from app.models.document import Chunk, Document


async def test_commit_visible_across_sessions():
    """session-per-request：一个会话 commit 后，新会话能看到数据。"""
    async with async_session_factory() as s1:
        s1.add(Document(filename="a.txt", content="x", status="pending"))
        await s1.commit()

    async with async_session_factory() as s2:
        rows = (await s2.execute(select(Document))).scalars().all()
        assert len(rows) == 1
        assert rows[0].filename == "a.txt"


async def test_uncommitted_data_not_leaked():
    """未 commit 的数据对其他会话不可见（事务隔离）。"""
    async with async_session_factory() as s1:
        s1.add(Document(filename="b.txt", content="y", status="pending"))
        # 不 commit，直接退出上下文（触发回滚）

    async with async_session_factory() as s2:
        rows = (await s2.execute(select(Document))).scalars().all()
        assert rows == []


async def test_expire_on_commit_false_keeps_attributes():
    """expire_on_commit=False：commit 后对象属性仍可访问，不必重新查询。

    这是 async 下的关键配置——开启 expire 会在访问属性时触发
    懒加载，在 async 会话里直接抛 MissingGreenlet。
    """
    async with async_session_factory() as session:
        doc = Document(filename="c.txt", content="z", status="pending")
        session.add(doc)
        await session.commit()
        # commit 后直接访问属性，不 refresh、不再查库
        assert doc.filename == "c.txt"
        assert doc.id is not None


async def test_rollback_on_error():
    """事务内抛异常且不 commit，数据不落库；显式 rollback 后会话可继续用。"""
    async with async_session_factory() as session:
        session.add(Document(filename="d.txt", content="w", status="pending"))
        await session.rollback()

        rows = (await session.execute(select(Document))).scalars().all()
        assert rows == []

        # 回滚后会话可继续写入
        session.add(Document(filename="e.txt", content="v", status="pending"))
        await session.commit()
        rows = (await session.execute(select(Document))).scalars().all()
        assert [r.filename for r in rows] == ["e.txt"]


async def test_lazy_relationship_raises_explicitly():
    """lazy="raise"：未预加载就访问 relationship，显式抛错。

    async 下默认懒加载会抛 MissingGreenlet（事件循环里跑阻塞 IO）；
    lazy="raise" 把它变成可读的 InvalidRequestError，问题在查询侧暴露。
    """
    async with async_session_factory() as session:
        doc = Document(filename="f.txt", content="p", status="pending")
        session.add(doc)
        await session.flush()
        session.add(Chunk(document_id=doc.id, content="c", embedding=None, chunk_index=0))
        await session.commit()

    async with async_session_factory() as session:
        doc = (await session.execute(select(Document))).scalars().first()
        assert doc is not None
        with pytest.raises(InvalidRequestError):
            _ = doc.chunks  # 未预加载 → 显式抛错


async def test_selectinload_preloads_relationship():
    """selectin 预加载后，relationship 访问正常，且不产生 N+1 查询。"""
    async with async_session_factory() as session:
        doc = Document(filename="g.txt", content="q", status="pending")
        session.add(doc)
        await session.flush()
        session.add(Chunk(document_id=doc.id, content="c1", embedding=None, chunk_index=0))
        session.add(Chunk(document_id=doc.id, content="c2", embedding=None, chunk_index=1))
        await session.commit()

    async with async_session_factory() as session:
        result = await session.execute(select(Document).options(selectinload(Document.chunks)))
        docs = result.scalars().all()
        assert len(docs) == 1
        # 预加载后访问不再查库
        assert len(docs[0].chunks) == 2
