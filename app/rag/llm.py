"""LLM 调用环节：生成最终答案。

实践点：
1. 抽象基类隔离实现，provider 可插拔；
2. MockLLM 仅用于打通链路，把检索到的上下文回显出来，证明「检索」这一步生效了；
3. 生产接入 OpenAI 兼容接口（DeepSeek / 通义 / Ollama 都兼容 /v1/chat/completions）。
"""
from abc import ABC, abstractmethod


class LLM(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict]) -> str:
        """输入 messages，返回文本答案。"""


class MockLLM(LLM):
    async def chat(self, messages: list[dict]) -> str:
        user = messages[-1]["content"]
        if "上下文：" in user and "\n\n问题：" in user:
            ctx = user.split("上下文：", 1)[1].split("\n\n问题：", 1)[0]
            return (
                "[mock 模式] 检索到以下上下文，接入真实 LLM 后将基于它生成答案：\n\n" + ctx
            )
        return "[mock 模式] 当前知识库为空，暂无相关内容。"


def get_llm(provider: str) -> LLM:
    if provider == "mock":
        return MockLLM()
    # 预留：接入 OpenAI / Ollama 时在此分支返回对应实现
    raise NotImplementedError(f"llm provider '{provider}' 尚未实现，请先用 mock")
