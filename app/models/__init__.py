"""模型包：汇总导出以便 create_all 注册所有表。"""
from app.models.chat import ChatMessage
from app.models.document import Chunk, Document
from app.models.task import IndexTask

__all__ = ["Document", "Chunk", "IndexTask", "ChatMessage"]
