---
title: FastAPI 工程起盘：从目录结构到统一异常
author: 小python
description: RAG 只是外壳，这篇讲 FastAPI 工程怎么搭：分层结构、Pydantic v2 配置、lifespan、依赖注入、统一异常处理，每个套路都带可跑代码。
---

> 系列重申一句定位：**RAG 是贯穿项目，但主角是工程栈**。前三篇讲了 RAG 的算法层，这一篇回到地基——FastAPI 工程本身怎么搭。
>
> 框架三行代码能跑，工程不是。分层、配置、生命周期、异常、测试，这五件事决定了三个月后你是在加功能还是在还债。

## 目录结构：分层是免费的，事后重构很贵

先看这个 RAG 工程的骨架：

```text
app/
├── main.py          # 入口：lifespan + 路由挂载 + 异常处理
├── core/            # 配置 / 数据库 / 异常 / 日志
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

## 配置：Pydantic v2 Settings，一个口子进

配置散落在全局变量和 os.environ 里，是事故高发地。集中到一个 Settings 类：

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FastAPI RAG Practice"
    database_url: str = "sqlite+aiosqlite:///./rag.db"
    celery_broker_url: str = "redis://localhost:6379/0"
    chunk_size: int = 500

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

三个细节做对了：

- **字段名自动映射环境变量**：`database_url` 读 `DATABASE_URL`，大小写不敏感；
- **`lru_cache` 保证单例**：多处导入是同一个对象，测试时可 `get_settings.cache_clear()` 重载；
- **`extra="ignore"`**：.env 里多写的字段不报错，减少环境噪音。

测试里覆盖配置只需在 import 前设环境变量，这个套路在 conftest 里：

```python
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["ENABLE_SCHEDULER"] = "false"
```

## lifespan：资源的生老病死

启动建连接池、启动调度器、关闭释放资源——这些不是「顺手写在 import 时」的，它们有生命周期。用 lifespan 上下文管理器：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()                                    # 启动：建表 / 连接池
    scheduler = create_scheduler() if settings.enable_scheduler else None
    if scheduler is not None:
        scheduler.start()
    yield                                              # ← 服务运行期
    if scheduler is not None:
        shutdown_scheduler(scheduler)                  # 关闭：优雅退出

app = FastAPI(title=settings.app_name, lifespan=lifespan)
```

::: warning
别再用 @app.on_event("startup")，它已弃用。lifespan 是唯一受支持的写法，而且它把启动和关闭的对称逻辑放在一处，不会出现「启动写了、关闭忘了」。
:::

lifespan 里只放**重量级资源**（DB、调度器、客户端池）。轻量的东西走 import 即可，别把启动搞慢。

## 依赖注入：FastAPI 可测试性的来源

依赖注入（Depends）是 FastAPI 最值得学透的机制。它解决的问题是：**代码要什么，就声明什么；测试要替换，就覆盖什么**。

数据库会话是最典型的例子：

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session      # 请求结束自动关闭

@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile, db: AsyncSession = Depends(get_db)):
    ...
```

路由只声明「我要一个 DB 会话」，不关心它从哪来、怎么关。测试里替换它：

```python
app.dependency_overrides[get_db] = lambda: fake_session
```

当前用户、限流器、权限校验都做成依赖，好处是同一套机制：生产注入真的，测试注入假的。

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

这里有个**实测踩过的坑**，值得单独讲：

::: warning
未捕获异常的兜底必须用 app.add_exception_handler(500, handler)。只注册 @app.exception_handler(Exception) 是兜不住的——Starlette 的 build_middleware_stack 只把 key == 500 的 handler 交给 ServerErrorMiddleware，Exception 类型的 handler 会被忽略，异常原样抛出。
:::

还有第二个坑：**ServerErrorMiddleware 在调用 handler 返回响应后，仍会 re-raise 异常**（Starlette 的设计，便于 ASGI 服务器记日志）。所以测试里验证 500 响应时，传输层要设 `raise_app_exceptions=False`，否则异常会被抛进测试：

```python
transport = ASGITransport(app=app, raise_app_exceptions=False)
```

这两个坑不看源码、不实际跑一遍，很难发现。测试跑通才是证据。

## API 设计：响应模型是契约

```python
@router.get("", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[Document]:
    ...
```

`response_model` 做三件事：**过滤字段**（`content` 大字段不出网）、**校验输出**（结构不符直接 500 暴露问题）、**生成 OpenAPI 文档**（`/docs` 自动更新）。请求进来是 schema，出去也是 schema，ORM 模型不外泄。

状态码按语义给：创建 201、删除 204、参数错 400、未找到 404。别什么都 200。

## 测试套路：AsyncClient + 隔离数据库

FastAPI 测试的标准姿势：

```python
@pytest.mark.asyncio
async def test_upload_and_chat():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/documents/upload", files=...)
        assert resp.status_code == 201
```

三个配套：

- **内存 SQLite**：`sqlite+aiosqlite:///:memory:`，测试零依赖、零残留；
- **每个测试建表清表**：conftest 用 autouse fixture，保证隔离；
- **ASGITransport 不触发 lifespan**：所以表要手动初始化，这个坑第一次写测试必踩。

::: note
测试是工程的证据，不是负担。这套结构下，加一个接口只需写路由和服务，测试自动获得内存库、依赖覆盖、统一异常——基础设施一次搭好，长期摊薄成本。
:::

## 总结

FastAPI 工程起盘五件事，按依赖顺序做：

1. **分层**：routes / services / models / core，依赖单向；
2. **配置**：Pydantic v2 Settings，一个口子进，lru_cache 单例；
3. **lifespan**：管理资源生命周期，别用已弃用的 on_event；
4. **依赖注入**：声明式要依赖，测试可覆盖；
5. **统一异常**：三类异常一个格式，500 兜底用状态码 handler。

五件事都不难，难在一开始就做对。后面两篇在这个骨架上装数据层和任务队列。

> 下一篇讲数据层：SQLAlchemy 2.0 的 async 会话怎么管、事务边界怎么划、N+1 怎么防，以及为什么 `expire_on_commit=False` 在 async 下是刚需。

::: note
文中代码全部来自可运行工程，统一异常与测试套路带单元测试。工程源码见文末引用。
:::
