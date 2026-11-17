"""文档相关 schema。

实践点：请求/响应用 Pydantic v2 模型，与 ORM 模型分离（API 边界清晰）。
"""
from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: str
