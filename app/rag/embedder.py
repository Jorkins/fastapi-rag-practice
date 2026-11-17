"""Embedding 环节：把文本变成向量。

实践点：
1. 用抽象基类隔离具体实现，provider 可插拔（mock / openai / ollama）；
2. 生产要保证「入库」与「查询」用同一个 embedding 模型，否则向量空间不一致；
3. MockEmbedder 仅用于本地零依赖跑通链路，语义检索能力为 0，禁止上生产。
"""
import hashlib
from abc import ABC, abstractmethod


class Embedder(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """输入文本列表，返回等长向量列表。"""


class MockEmbedder(Embedder):
    """零依赖降级实现：基于词哈希生成确定性向量（bag-of-words 风格）。"""

    dim = 256

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in text.split():
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


def get_embedder(provider: str) -> Embedder:
    if provider == "mock":
        return MockEmbedder()
    # 预留：接入 OpenAI / Ollama 时在此分支返回对应实现
    raise NotImplementedError(
        f"embedding provider '{provider}' 尚未实现，请先用 mock"
    )
