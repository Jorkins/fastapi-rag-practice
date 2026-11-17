"""向量距离的 SQL 映射（生产形态，独立于默认 SQLite 链路）。

实践点：
1. 生产把相似度下推到数据库算：pgvector 的 vector 列 + 距离算子，
   一条 SQL 完成「排序 + 截断」：`ORDER BY embedding <=> :q LIMIT :k`；
2. 本模块自带独立 Base，不进默认建表链路——教学工程跑在 SQLite 上，
   执行不了 pgvector 距离算子，混进主链路只会让 create_all 炸掉；
3. 测试用编译断言验证 SQL 形状（不需要真起 PostgreSQL），
   另用数值断言锁死「余弦距离 = 1 - 余弦相似度」的排序方向。

三个常用距离算子（pgvector）：
- `<->`  : L2（欧氏）距离
- `<=>`  : 余弦距离（文本 embedding 最常用）
- `<#>`  : 负内积（越大越近的内积，取负后变成越小越近）
"""
from __future__ import annotations

from sqlalchemy import Integer, String, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector

# 教学用小维度；生产与 embedding 模型输出维度一致（如 1536）
VECTOR_DIM = 8


class PgBase(DeclarativeBase):
    """独立元数据：pgvector 映射不混入 app.core.db 的 Base。"""


class PgChunk(PgBase):
    """切片表的生产形态映射：embedding 是 pgvector 的 vector 列。"""

    __tablename__ = "pg_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    content: Mapped[str] = mapped_column(String(2000))
    embedding = mapped_column(Vector(VECTOR_DIM), nullable=False)


def _check_dim(query_vec: list[float]) -> None:
    if len(query_vec) != VECTOR_DIM:
        raise ValueError(f"query_vec 维度应为 {VECTOR_DIM}，实际 {len(query_vec)}")


def build_cosine_search(query_vec: list[float], k: int = 5):
    """余弦距离升序取 top-k。

    编译产物：ORDER BY pg_chunks.embedding <=> :q LIMIT :k
    距离升序 = 相似度降序，方向不用自己换算。
    """
    _check_dim(query_vec)
    return (
        select(PgChunk.id, PgChunk.content)
        .order_by(PgChunk.embedding.cosine_distance(query_vec))
        .limit(k)
    )


def build_l2_search(query_vec: list[float], k: int = 5):
    """L2（欧氏）距离升序取 top-k：ORDER BY embedding <-> :q LIMIT :k。"""
    _check_dim(query_vec)
    return (
        select(PgChunk.id, PgChunk.content)
        .order_by(PgChunk.embedding.l2_distance(query_vec))
        .limit(k)
    )


def compile_sql(stmt) -> str:
    """把语句编译成 PostgreSQL SQL 字符串（测试断言 SQL 形状用）。"""
    return str(stmt.compile(dialect=postgresql.dialect()))
