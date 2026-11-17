"""检索指标的单元测试：正常、部分命中、未命中、边界与聚合。"""
import pytest

from app.rag.metrics import (
    EvalCase,
    evaluate_retrieval,
    hit_rate_at_k,
    mrr,
    recall_at_k,
)


def test_recall_partial_hit():
    relevant = frozenset({"a", "b"})
    assert recall_at_k(["a", "x", "y"], relevant, k=5) == 0.5  # 命中 1/2
    assert recall_at_k(["a", "b", "x"], relevant, k=2) == 1.0  # top2 全中


def test_hit_rate_all_or_nothing():
    relevant = frozenset({"a"})
    assert hit_rate_at_k(["x", "a"], relevant, k=5) == 1.0
    assert hit_rate_at_k(["x", "y"], relevant, k=5) == 0.0
    assert hit_rate_at_k(["a", "x"], relevant, k=1) == 1.0  # 排第 1


def test_mrr_rank_sensitivity():
    relevant = frozenset({"gold"})
    assert mrr(["gold", "x"], relevant) == 1.0  # 排第 1
    assert mrr(["x", "gold"], relevant) == 0.5  # 排第 2
    assert mrr(["x", "y", "gold"], relevant) == pytest.approx(1 / 3)
    assert mrr(["x", "y"], relevant) == 0.0  # 未命中


def test_metrics_edge_cases():
    assert recall_at_k([], frozenset({"a"}), k=5) == 0.0
    assert recall_at_k(["a"], frozenset(), k=5) == 0.0  # 无标注则无从判断
    with pytest.raises(ValueError):
        recall_at_k(["a"], frozenset({"a"}), k=0)


def test_evaluate_retrieval_aggregate():
    cases = [
        EvalCase(query="q1", relevant_ids=frozenset({"a"})),
        EvalCase(query="q2", relevant_ids=frozenset({"b", "c"})),
    ]
    results = [["a", "x"], ["x", "b"]]  # q1 命中第1；q2 命中第2，召回 1/2
    report = evaluate_retrieval(cases, results, k=5)
    assert report["cases"] == 2
    assert report["hit_rate_at_k"] == 1.0  # 两条都至少命中一个
    assert report["mrr"] == pytest.approx((1.0 + 0.5) / 2)
    assert report["recall_at_k"] == pytest.approx((1.0 + 0.5) / 2)
    assert report["min_recall"] == 0.5  # 长尾：q2 只召回一半


def test_evaluate_retrieval_mismatch():
    with pytest.raises(ValueError):
        evaluate_retrieval([EvalCase(query="q")], [], k=5)
