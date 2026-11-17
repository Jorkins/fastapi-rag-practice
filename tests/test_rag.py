"""RAG 链路与 API 冒烟测试。"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.rag.chunker import chunk_text
from app.rag.embedder import MockEmbedder


# ---- 单元测试：chunker ----
def test_chunk_text_basic():
    text = "abcdefghij"
    chunks = chunk_text(text, chunk_size=4, overlap=2)
    # a b c d | c d e f | e f g h | g h i j
    assert chunks == ["abcd", "cdef", "efgh", "ghij"]


def test_chunk_text_empty():
    assert chunk_text("   ") == []


def test_chunk_text_overlap_guard():
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=4, overlap=4)


# ---- 单元测试：embedder ----
@pytest.mark.asyncio
async def test_mock_embedder_deterministic():
    emb = MockEmbedder()
    v1 = await emb.embed(["hello world"])
    v2 = await emb.embed(["hello world"])
    assert v1 == v2
    assert len(v1[0]) == MockEmbedder.dim


# ---- API 冒烟测试：upload -> chat ----
@pytest.mark.asyncio
async def test_upload_and_chat():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 上传
        files = {"file": ("a.txt", b"FastAPI is a web framework. SQLAlchemy handles the database.", "text/plain")}
        resp = await client.post("/documents/upload", files=files)
        assert resp.status_code == 201, resp.text
        doc_id = resp.json()["id"]

        # 问答（mock 模式）
        resp = await client.post("/chat", json={"question": "What is FastAPI?"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["answer"]
        assert isinstance(body["sources"], list)

        # 文档状态应为 ready
        resp = await client.get("/documents")
        assert any(d["id"] == doc_id and d["status"] == "ready" for d in resp.json())
