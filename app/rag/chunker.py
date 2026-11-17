"""文本切分：chunk 环节。

实践点：
1. 切分是检索质量的第一道关口——太小丢上下文，太大稀释语义；
2. 重叠（overlap）保证跨切片边界的信息不丢失；
3. 生产可按段落/语义/token 切分（tiktoken、按标题结构），这里给最小可懂实现。
"""


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """按字符切分，带重叠。

    Args:
        text: 原始文本。
        chunk_size: 每块字符数。
        overlap: 相邻块重叠字符数（应小于 chunk_size）。
    """
    text = text.strip()
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap 必须小于 chunk_size")

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = end - overlap
    return chunks
