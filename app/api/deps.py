"""API 依赖：统一在这里管理可复用的 Depends。

实践点：依赖注入（DI）是 FastAPI 的核心机制，
session、当前用户、限流器等都可做成依赖，测试时易替换。
"""
from app.core.db import get_db

__all__ = ["get_db"]
