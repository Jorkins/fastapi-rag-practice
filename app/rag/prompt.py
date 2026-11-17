"""Prompt 构造环节。

实践点：
1. 把检索到的上下文拼进 user message，并明确「只依据上下文回答」约束幻觉；
2. 分块编号，便于答案里引用来源；
3. 生产可进一步加 system 角色、few-shot、引用格式要求。
"""

SYSTEM_PROMPT = (
    "你是知识库问答助手。只根据提供的上下文回答；"
    "上下文没有的信息，如实回答「不知道」，不要编造。"
)


def build_prompt(question: str, contexts: list[str]) -> list[dict]:
    if not contexts:
        user = f"问题：{question}\n\n（当前知识库为空，请直接告知用户暂无相关内容。）"
    else:
        block = "\n\n---\n\n".join(
            f"[{i + 1}] {ctx}" for i, ctx in enumerate(contexts)
        )
        user = f"上下文：\n{block}\n\n问题：{question}\n\n请基于上下文回答，并标注引用编号。"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
