"""检索质量指标：Recall@k / Hit Rate@k / MRR。

对应《检索好不好，别靠感觉》一文的代码出处。设计原则：
1. 纯 Python 实现，零外部依赖，可单测（见 tests/test_metrics.py）；
2. 单条查询的指标与批量聚合分开：单条便于定位失败案例，聚合用于回归对比；
3. 评测数据集用 EvalCase 显式建模，避免「query 和答案靠位置对齐」的脆弱写法。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


@dataclass(frozen=True)
class EvalCase:
    """一条评测样本。

    query: 用户问题
    relevant_ids: 标注的正确切片 id（黄金集）
    reference_answer: 参考答案（生成层评测用，检索层可不填）
    """

    query: str
    relevant_ids: frozenset[str] = field(default_factory=frozenset)
    reference_answer: str = ""


def recall_at_k(retrieved: list[str], relevant: frozenset[str], k: int) -> float:
    """Recall@k = 命中的正确切片数 / 正确切片总数。

    衡量「该找到的，找到了多少」。relevant 为空时无从判断，返回 0.0。
    """
    if k <= 0:
        raise ValueError("k 必须为正数")
    if not relevant:
        return 0.0
    hit = len(set(retrieved[:k]) & relevant)
    return hit / len(relevant)


def hit_rate_at_k(retrieved: list[str], relevant: frozenset[str], k: int) -> float:
    """Hit Rate@k：top_k 里是否至少有一个正确切片（1.0 / 0.0）。

    单条查询的命中与否；批量平均后就是「多少比例的查询至少答对一次」。
    """
    if k <= 0:
        raise ValueError("k 必须为正数")
    return 1.0 if set(retrieved[:k]) & relevant else 0.0


def mrr(retrieved: list[str], relevant: frozenset[str]) -> float:
    """MRR（单条查询的倒数排名）= 1 / 第一个正确切片的排名，未命中记 0。

    对「正确答案排第几」敏感，是排序质量的核心指标。
    """
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def evaluate_retrieval(
    cases: list[EvalCase], results: list[list[str]], k: int = 5
) -> dict[str, float]:
    """批量评测：cases[i] 对应 results[i]（检索返回的 doc_id 列表）。

    返回均值指标，并附带 worst_case 便于定位失败样本——只看均值会掩盖长尾。
    """
    if len(cases) != len(results):
        raise ValueError("cases 与 results 数量不一致")
    if not cases:
        return {"recall_at_k": 0.0, "hit_rate_at_k": 0.0, "mrr": 0.0, "cases": 0}

    recalls, hits, rrs = [], [], []
    for case, retrieved in zip(cases, results):
        recalls.append(recall_at_k(retrieved, case.relevant_ids, k))
        hits.append(hit_rate_at_k(retrieved, case.relevant_ids, k))
        rrs.append(mrr(retrieved, case.relevant_ids))

    return {
        "recall_at_k": round(mean(recalls), 4),
        "hit_rate_at_k": round(mean(hits), 4),
        "mrr": round(mean(rrs), 4),
        "min_recall": round(min(recalls), 4),  # 长尾下限：最差的那条有多差
        "cases": len(cases),
        "k": k,
    }
