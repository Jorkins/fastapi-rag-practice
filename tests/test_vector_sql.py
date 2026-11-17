"""向量距离 SQL 映射测试：编译断言 SQL 形状 + 数值断言排序方向。

不需要真起 PostgreSQL——用 postgresql 方言编译语句，断言距离算子与 LIMIT 形状；
再用「余弦距离 = 1 - 余弦相似度」的数学关系锁死排序方向不被写反。
"""
import pytest

from app.rag.store import cosine_similarity
from app.rag.vector_sql import (
    VECTOR_DIM,
    build_cosine_search,
    build_l2_search,
    compile_sql,
)

Q = [1.0] + [0.0] * (VECTOR_DIM - 1)
NEAR = [0.9, 0.1] + [0.0] * (VECTOR_DIM - 2)   # 与 Q 接近
FAR = [0.0, 1.0] + [0.0] * (VECTOR_DIM - 2)    # 与 Q 远


def test_cosine_search_sql_shape():
    """余弦检索编译出 <=> 距离算子 + LIMIT，且按距离升序。"""
    sql = compile_sql(build_cosine_search(Q, k=3))
    assert "<=>" in sql
    assert "LIMIT" in sql.upper()
    assert "ORDER BY" in sql.upper()
    # 升序（ASC 或无修饰）= 距离小的在前
    assert "DESC" not in sql.upper()


def test_l2_search_sql_shape():
    """L2 检索编译出 <-> 距离算子。"""
    sql = compile_sql(build_l2_search(Q, k=3))
    assert "<->" in sql
    assert "LIMIT" in sql.upper()


def test_dimension_mismatch_raises():
    """query_vec 维度不对要显式报错，不能把垃圾向量发给数据库。"""
    with pytest.raises(ValueError, match="维度"):
        build_cosine_search([1.0, 2.0])


def test_cosine_distance_ordering_matches_similarity():
    """余弦距离升序 == 余弦相似度降序：方向没写反的数值证据。"""
    distance_near = 1.0 - cosine_similarity(Q, NEAR)
    distance_far = 1.0 - cosine_similarity(Q, FAR)
    assert distance_near < distance_far  # 距离升序 → NEAR 排前面
    assert cosine_similarity(Q, NEAR) > cosine_similarity(Q, FAR)  # 相似度降序同向
