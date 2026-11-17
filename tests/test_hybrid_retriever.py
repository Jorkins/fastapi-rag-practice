"""RRF 融合 + 混合检索主干的单元测试（纯 Python，零外部依赖）。"""
import pytest

from app.rag.hybrid_retriever import HybridRetriever, MockReranker, rrf_fuse


def test_rrf_fuse_ranks_overlap_first():
    """两路都命中的文档分数累加，应排第一。"""
    fused = rrf_fuse([["a", "b"], ["b", "c"]])
    order = [doc_id for doc_id, _ in fused]
    assert order[0] == "b"
    assert set(order) == {"a", "b", "c"}
    scores = dict(fused)
    # b = 1/(60+2) + 1/(60+1)，高于任一单路文档的 1/(60+1)
    assert scores["b"] > scores["a"]
    assert scores["b"] > scores["c"]


def test_rrf_fuse_uses_rank_not_score():
    """RRF 只看排名：分数尺度差异不影响融合结果。"""
    fused = rrf_fuse([["x", "y"], ["y", "x"]])
    scores = dict(fused)
    assert scores["x"] == pytest.approx(scores["y"])  # 对称输入 → 同分


def test_rrf_fuse_limit_and_validation():
    fused = rrf_fuse([["a", "b", "c"]], k=60, limit=2)
    assert len(fused) == 2
    with pytest.raises(ValueError):
        rrf_fuse([["a"]], k=0)


async def test_hybrid_retriever_fuses_and_reranks():
    async def vec(q, limit):
        return ["a", "b", "c"][:limit]

    async def kw(q, limit):
        return ["c", "d"][:limit]

    r = HybridRetriever(
        vector_search=vec,
        keyword_search=kw,
        reranker=MockReranker(),
        candidates=10,
        top_n=2,
        by_id={"a": "sqlalchemy async session", "b": "celery task", "c": "async session", "d": "redis broker"},
    )
    got = await r.retrieve("async session")
    assert len(got) == 2
    assert set(got) <= {"a", "b", "c", "d"}
    # rerank 按词重叠：a 与 c 都含 "async session"，应排在 b/d 之前
    assert got[0] in {"a", "c"}


async def test_hybrid_retriever_without_reranker():
    async def vec(q, limit):
        return ["a", "b"]

    async def kw(q, limit):
        return ["b", "c"]

    r = HybridRetriever(vector_search=vec, keyword_search=kw, top_n=2)
    got = await r.retrieve("anything")
    assert got[0] == "b"  # 双路命中 → RRF 第一
    assert len(got) == 2
