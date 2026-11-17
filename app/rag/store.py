"""向量相似度计算（教学用 numpy 实现）。

实践点：
1. 生产不要用内存全量扫描 + numpy，应让向量库在库内算：
   - pgvector: `ORDER BY embedding <=> :q LIMIT :k`
   - Qdrant / Milvus: 自带 ANN 索引（HNSW 等）
2. 这里用余弦相似度做最小可懂闭环，方便读者理解检索本质。
"""
import numpy as np


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)
