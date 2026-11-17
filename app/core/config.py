"""集中配置：Pydantic Settings。

实践点：
1. 所有配置走环境变量，.env 文件由 pydantic-settings 自动加载；
2. 用 lru_cache 保证全局单例，测试时可注入覆盖；
3. 字段名自动映射为大写环境变量（case-insensitive），例如 DATABASE_URL -> database_url。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 应用 ----
    app_name: str = "FastAPI RAG Practice"
    debug: bool = True

    # ---- 数据库 ----
    database_url: str = "sqlite+aiosqlite:///./rag.db"

    # ---- Celery / Redis ----
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    # true 时任务同步执行，本地无 Redis 也能跑通；生产置 false
    celery_task_always_eager: bool = True

    # ---- RAG ----
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 4
    embedding_provider: str = "mock"  # mock | openai | ollama
    llm_provider: str = "mock"        # mock | openai | ollama
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o-mini"

    # ---- 定时任务 ----
    enable_scheduler: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
