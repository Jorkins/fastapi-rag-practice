# FastAPI RAG Practice

一个手写的 **FastAPI + RAG + SQLAlchemy + Celery + Redis** 闭环实践工程，用于讲解 FastAPI 生产级项目结构。

参考结构：Mini-RAG Project（FastAPI + Celery + pgvector/Qdrant）与 RAG-Code-Solution（FastAPI + SQLAlchemy async + Celery + LangGraph）。

## 核心闭环

```
上传文档 → 落库 + 入队(Celery) → 切分(chunk) → 向量化(embedding) → 入库
                                                                    ↓
提问 → 向量化 → 检索(top_k) → 拼 Prompt → LLM → 答案 + 引用来源
```

## 技术栈

| 模块 | 选型 |
|---|---|
| Web 框架 | FastAPI（async） |
| 配置 | Pydantic v2 + pydantic-settings |
| ORM | SQLAlchemy 2.0 async |
| 数据库 | SQLite（默认零依赖）/ PostgreSQL + pgvector（生产） |
| 异步任务 | Celery + Redis |
| 定时任务 | APScheduler（进程内）+ Celery Beat（分布式） |
| 向量相似度 | numpy 余弦（教学）/ pgvector `<=>`（生产） |
| 包管理 | uv |

## 快速开始（本地零外部依赖）

```bash
cd fastapi-rag-practice
uv sync                      # 安装依赖
cp .env.example .env         # 默认 mock + eager 模式，无需 Redis / API Key

# 启动
uv run uvicorn app.main:app --reload
```

打开 http://127.0.0.1:8000/docs 测试：

```bash
# 上传一个 .txt 文件
curl -X POST http://127.0.0.1:8000/documents/upload \
  -F "file=@README.md"

# 提问
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "这个项目用什么 ORM？"}'
```

## 运行测试

```bash
uv run pytest -v
```

## Docker Compose 一键起生产形态

一条命令拉起 **PostgreSQL(pgvector) + Redis + API + Celery Worker + Beat** 全套：

```bash
docker compose up -d --build
```

启动后访问 http://127.0.0.1:8000/docs，`/health` 健康检查已内置。

## 切换到生产模式

1. 数据库换 PostgreSQL + pgvector，并把 `Chunk.embedding` 换成 `vector` 列；
2. `CELERY_TASK_ALWAYS_EAGER=false`，启动 Redis + worker + beat：
   ```bash
   celery -A app.core.celery_app:celery_app worker -l info
   celery -A app.core.celery_app:celery_app beat -l info
   ```
3. `EMBEDDING_PROVIDER` / `LLM_PROVIDER` 换成真实模型（OpenAI 兼容接口即可）。

## 目录结构

```
app/
├── main.py            # 入口 + lifespan
├── core/              # 配置、DB、Celery、日志
├── models/            # ORM 模型（Document / Chunk / IndexTask）
├── schemas/           # Pydantic 请求/响应模型
├── api/               # 路由 + 依赖注入
├── rag/               # chunker / embedder / store / retriever / prompt / llm
├── services/          # 业务编排（RAG 链路组装）
├── tasks/             # Celery 异步任务（文档索引 + 定时清理）
└── scheduler.py       # APScheduler 进程内定时任务
```

更详细的逐模块讲解见 `article/` 下的系列文章（《从零手写一个 FastAPI-RAG 问答系统》01~07，涵盖目录结构、SQLAlchemy async、Celery、pgvector 混合检索、RAGAS 评测与 Docker 部署）。
