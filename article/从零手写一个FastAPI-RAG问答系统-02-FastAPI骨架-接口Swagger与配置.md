---
title: 从零手写一个 FastAPI RAG 问答系统（二）：FastAPI 骨架——接口、Swagger 与配置
author: 小python
description: 这篇讲框架本身：分层目录、接口设计、Swagger 自动文档、.env 配置、lifespan 与统一异常，全部来自可运行的 RAG 工程。
---

> 本系列《从零手写一个 FastAPI RAG 问答系统》，RAG 是贯穿项目，主角是工程栈。第一篇把 RAG 闭环跑通了，这一篇讲框架本身：**接口怎么设计、Swagger 文档怎么白拿、配置怎么一个口子进**。
>
> 框架三行代码能跑，工程不是。分层、配置、生命周期、异常，这四件事决定了三个月后你是在加功能还是在还债。

## 目录结构：分层是免费的，事后重构很贵

先看这个 RAG 工程的骨架：

```text
app/
├── main.py          # 入口：lifespan + 路由挂载 + 异常处理
├── core/            # 配置 / 数据库 / Celery / 异常 / 日志
├── models/          # ORM 模型
├── schemas/         # Pydantic 请求/响应模型
├── api/
│   ├── deps.py      # 可复用依赖
│   └── routes/      # 路由，按业务拆
├── rag/             # 业务逻辑：可插拔组件
├── services/        # 用例编排
└── tasks/           # 后台任务
```

每层只做一件事，依赖方向单向：

| 层 | 职责 | 不做什么 |
|---|---|---|
| routes | 参数校验、调服务、返回响应 | 不写业务逻辑 |
| services | 用例编排 | 不碰 HTTP 细节 |
| models / schemas | 数据结构定义 | 不含行为 |
| core | 基础设施（配置/DB/异常） | 不含业务 |

::: note
分层的价值不在当下，在于变化。换 ORM、换任务队列、加 gRPC 入口时，改动只落在对应层。一开始就不分层，后面每个需求都要全局搜索着改。
:::

## 配置：.env 一个口子进

配置散落在全局变量和 `os.environ` 里，是事故高发地。Pydantic v2 的 Settings 把它收拢成一个类：

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- 应用 ----
    app_name: str = "FastAPI RAG Practice"
    # ---- 数据库 ----
    database_url: str = "sqlite+aiosqlite:///./rag.db"
    # ---- Celery / Redis ----
    celery_broker_url: str = "redis://localhost:6379/0"
    # true = 本地无 Redis 也能跑（任务同步执行）；生产置 false
    celery_task_always_eager: bool = True
    # ---- RAG ----
    chunk_size: int = 500
    embedding_provider: str = "mock"   # mock | openai | ollama
    llm_provider: str = "mock"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

三个细节做对了：

- **字段名自动映射环境变量**：`database_url` 读 `DATABASE_URL`，大小写不敏感；
- **`lru_cache` 保证单例**：多处导入是同一个对象，不会重复读文件；
- **`extra="ignore"`**：.env 里多写的字段不报错，减少环境噪音。

配套的 `.env.example` 是一份「配置说明书」，团队里任何人拿到项目，看它就知道要配什么：

```bash
# ---- 数据库（本地默认 SQLite，零依赖；生产换 PostgreSQL + pgvector）----
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/rag
DATABASE_URL=sqlite+aiosqlite:///./rag.db

# ---- Redis / Celery ----
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_TASK_ALWAYS_EAGER=true

# ---- RAG ----
CHUNK_SIZE=500
EMBEDDING_PROVIDER=mock
LLM_PROVIDER=mock

# ---- 定时任务 ----
ENABLE_SCHEDULER=true
```

::: warning
.env 不进版本库，.env.example 才进。密钥（OPENAI_API_KEY 这类）只出现在前者。环境差异（本地 SQLite / 生产 PostgreSQL）全靠环境变量切换，代码里不出现 if 生产 就怎样。
:::

## 接口设计：三个接口撑起整个系统

RAG 问答系统的对外面就三个接口，加上一个健康检查：

| 接口 | 方法 | 作用 |
|---|---|---|
| `/documents/upload` | POST | 上传文档，落库 + 派发后台索引任务 |
| `/documents` | GET | 文档列表，看索引状态 |
| `/chat` | POST | 问答：检索 + 生成，返回答案与引用 |
| `/health` | GET | 健康检查，给容器编排探活用 |

上传接口的完整实现：

```python
router = APIRouter(prefix="/documents", tags=["documents"])

@router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=201,
    summary="上传文档",
    description="上传文本文件：落库为 pending 文档，并把「切分 + 向量化 + 入库」"
                "派发为后台任务。立即返回文档记录，索引状态可轮询列表接口查看。",
)
async def upload_document(
    file: UploadFile = File(..., description="UTF-8 文本文件"),
    db: AsyncSession = Depends(get_db),
) -> Document:
    content = (await file.read()).decode("utf-8", errors="ignore")
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    doc = Document(filename=file.filename or "unnamed.txt",
                   content=content, status="pending")
    db.add(doc)
    await db.commit()

    await dispatch_index(doc.id)   # 耗时活派发出去，接口立即返回
    return doc
```

三个设计点：

- **上传只做轻活**：落库 + 派发，切分向量化是重活，扔给 Celery（第四篇展开）；
- **`response_model` 是契约**：过滤字段（`content` 大字段不出网）、校验输出、生成文档，三件事一次做完；
- **状态码按语义给**：创建 201、参数错 400、未找到 404。别什么都 200。

## Swagger：白拿的文档，别浪费

FastAPI 基于 OpenAPI 规范，`/docs` 页面自动生成。但「自动生成」不等于「可读」——默认出来的文档只有函数名，消费方看不懂。让文档可用的四个手段：

**1. tags 分组。** `APIRouter(prefix="/documents", tags=["documents"])` 一行，/docs 页面按业务分组，chat 和 documents 各归各。

**2. summary + description 写在路由上。** 就是上面 upload 接口那样，summary 出现在接口列表里，description 出现在展开详情里。写给人看的话，不是写给自己的注释。

**3. Field/Parameter 带描述和约束。** 请求模型的字段说明直接进文档：

```python
class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="用户问题")
    session_id: str | None = Field(default=None, max_length=36,
                                   description="多轮会话分组 id，同一会话传同一个值")
```

min_length/max_length 自动变成 Swagger 上的校验说明，前端联调时不用再问你「最长多少字」。

**4. response_model 让响应结构可读。** `/chat` 返回 `ChatResponse`，文档里自动列出 answer 和 sources 字段，前端照着建类型，不用抓包猜。

::: note
Swagger 不只是文档，还是免费的调试台。/docs 页面上每个接口都能 Try it out 直接发请求——上传一个文件试 /documents/upload、发一句「这个项目用什么 ORM」试 /chat，接口通不通当场见分晓。
:::

## 依赖注入：Depends 是框架的心脏

数据库会话的获取方式，最能体现 FastAPI 的依赖注入思想：

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session      # 请求结束自动关闭

# 路由只声明「我要一个 DB 会话」
@router.get("", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[Document]:
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars().all())
```

路由不关心会话从哪来、怎么关——`async with` 保证一定关，FastAPI 保证每个请求拿到独立的会话。将来要换连接方式、加读写分离，只改 `get_db` 一个函数，所有路由不动。

## lifespan：资源的生老病死

启动建连接池、启动调度器，关闭优雅退出——这些资源有生命周期，用 lifespan 管理：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()                                    # 启动：建表
    scheduler = create_scheduler() if settings.enable_scheduler else None
    if scheduler is not None:
        scheduler.start()
    yield                                              # ← 服务运行期
    if scheduler is not None:
        shutdown_scheduler(scheduler)                  # 关闭：优雅退出

app = FastAPI(title=settings.app_name, lifespan=lifespan)
```

::: warning
别再用 @app.on_event("startup")，它已弃用。lifespan 是唯一受支持的写法，而且启动和关闭的对称逻辑放在一处，不会出现「启动写了、关闭忘了」。另外 ENABLE_SCHEDULER=false 可以一键关掉进程内调度器——生产上定时任务交给 Celery Beat 容器，避免每个副本都跑一份。
:::

## 统一异常处理：一个格式，别让前端猜

每个 endpoint 手写 try/except 是灾难。正确姿势是异常分层 + 统一 handler：

```python
class AppError(Exception):
    def __init__(self, message, code="APP_ERROR", status_code=400):
        self.message, self.code, self.status_code = message, code, status_code

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_, exc): ...          # 业务异常 → 业务错误码

    @app.exception_handler(HTTPException)
    async def _http_error(_, exc): ...         # HTTP 异常 → 同构格式

    app.add_exception_handler(500, _internal)  # 未捕获 → 兜底 500
```

所有错误统一成一种结构，前端只认一个：

```json
{"error": {"code": "RULE_VIOLATION", "message": "业务规则不满足"}}
```

这里有个实测踩过的坑，值得单独讲：

::: warning
未捕获异常的兜底必须用 app.add_exception_handler(500, handler)。只注册 @app.exception_handler(Exception) 是兜不住的——Starlette 的 build_middleware_stack 只把 key == 500 的 handler 交给 ServerErrorMiddleware，Exception 类型的 handler 会被忽略，异常原样抛出。
:::

## 总结

FastAPI 工程骨架四件事，按依赖顺序做：

1. **分层**：routes / services / models / core，依赖单向；
2. **配置**：Pydantic Settings + .env，一个口子进，环境差异全走变量；
3. **接口 + Swagger**：response_model 当契约，tags/summary/description 让 /docs 真正可读可调；
4. **统一异常**：三类异常一个格式，500 兜底用状态码 handler。

> 下一篇装数据层：RAG 系统要哪几张表、ORM 怎么写映射、问答记录怎么落库，以及向量距离在 SQL 里长什么样。

::: note
文中代码全部来自可运行工程，接口可直接用 Swagger 调试。工程源码见文末引用。
:::
