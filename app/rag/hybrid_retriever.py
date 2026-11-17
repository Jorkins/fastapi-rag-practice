"""检索升级件：RRF 融合 + rerank 抽象 + 混合检索主干。

对应《检索精度三层升级》一文的代码出处。设计原则：
1. RRF 融合与 rerank 抽象零依赖可跑、可测（见 tests/test_hybrid_retriever.py）；
2. pgvector / BM25 两条召回路由以依赖注入接入（HybridRetriever 不绑具体向量库），
   换 Qdrant/Elasticsearch 只换路由实现，融合与重排逻辑不动；
3. cross-encoder 推理是 CPU 密集，必须 offload（asyncio.to_thread），
   别在事件循环里同步跑——阻塞会拖垮所有并发请求。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

DEFAULT_RRF_K = 60


def rrf_fuse(
    ranked_lists: Sequence[Sequence[str]],
    k: int = DEFAULT_RRF_K,
    limit: int | None = None,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion：只看排名不看分数，免调参、跨检索器鲁棒。

    score(d) = Σ 1 / (k + rank_i(d))，rank 从 1 开始。
    多个列表中都出现的文档分数累加，自然排前。
    """
    if k <= 0:
        raise ValueError("rrf_k 必须为正数")
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return fused if limit is None else fused[:limit]


class Reranker(Protocol):
    async def rerank(
        self, query: str, candidates: Sequence[str], top_n: int
    ) -> list[tuple[int, float]]:
        """返回 [(candidate_index, score), ...]，按相关度降序，长度 <= top_n。"""
        ...


@dataclass
class MockReranker:
    """零依赖重排器：按 query 与候选的词重叠度打分，用于验证链路接通。

    生产换成 CrossEncoderReranker（bge-reranker 等）或 Cohere Rerank，
    接口不变。注意交叉编码器推理是 CPU 密集，实现里必须 offload 到线程池。
    """

    async def rerank(
        self, query: str, candidates: Sequence[str], top_n: int
    ) -> list[tuple[int, float]]:
        query_terms = set(query.lower().split())
        scored: list[tuple[int, float]] = []
        for idx, cand in enumerate(candidates):
            cand_terms = set(cand.lower().split())
            overlap = len(query_terms & cand_terms)
            scored.append((idx, float(overlap)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_n]


@dataclass
class HybridRetriever:
    """双路召回 → RRF 融合 → 可选 rerank。

    vector_search / keyword_search 由调用方注入（闭包或协程函数），
    签名一致：async (query, limit) -> Sequence[str]，返回 doc_id 列表（按相关度降序）。
    """

    vector_search: callable
    keyword_search: callable
    reranker: Reranker | None = None
    rrf_k: int = DEFAULT_RRF_K
    candidates: int = 50
    top_n: int = 5
    by_id: dict = field(default_factory=dict)

    async def retrieve(self, query: str) -> list[str]:
        # 1) 双路召回
        vec_hits = await self.vector_search(query, self.candidates)
        kw_hits = await self.keyword_search(query, self.candidates)
        # 2) RRF 融合
        fused = rrf_fuse([list(vec_hits), list(kw_hits)], self.rrf_k, self.candidates)
        ids = [doc_id for doc_id, _ in fused]
        # 3) rerank（可选）：只对候选池做，绝不全库
        if self.reranker is not None and ids:
            corpus = [self.by_id.get(i, "") for i in ids]
            ranked = await self.reranker.rerank(query, corpus, self.top_n)
            return [ids[i] for i, _ in ranked]
        return ids[: self.top_n]
