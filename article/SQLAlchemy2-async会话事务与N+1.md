---
title: SQLAlchemy 2.0 async：会话、事务与 N+1
author: 小python
description: 数据层是工程的腰。这篇讲 SQLAlchemy 2.0 异步写法：会话怎么管、事务边界怎么划、async 懒加载的坑、N+1 怎么防、连接池与迁移怎么配。
---

> 系列定位：**RAG 是贯穿项目，但主角是工程栈**。前三篇讲了 RAG 的算法层，工程篇回到地基——上一篇 FastAPI 工程怎么搭，这一篇装数据层。
>
> SQLAlchemy 2.0 的 async 用法和 1.x 同步版差别不小，直接照搬老写法，轻则 `MissingGreenlet`，重则事务悄悄泄漏。
>
> 六个主题：**引擎与会话、session-per-request、事务边界、懒加载与 N+1、向量距离的 SQL 映射、连接池与迁移**。每一项都有可跑代码和测试。

## 引擎与会话：两个对象，别搞混

```python
engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
```

三个角色分清楚：

| 对象 | 生命周期 | 职责 |
|---|---|---|
| engine | 进程级单例 | 管连接池，重量级 |
| async_session_factory | 进程级单例 | 造会话的工厂 |
| AsyncSession | 请求级 | 一次工作单元，轻量 |

::: note
engine 是进程级的，不要在函数里反复 create_async_engine——每次都新建连接池，连接数瞬间打满。session 是请求级的，用完即关。这个「一次建、多次造」的节奏搞反了，是 async 下最常见的性能事故。
:::

## session-per-request：一个请求一个会话

FastAPI 的依赖注入正好承载这个模式：

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session      # 请求处理完自动关闭

@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile, db: AsyncSession = Depends(get_db)):
    ...
```

`yield` 之后的代码在响应返回后执行，`async with` 保证会话一定关闭。**路由不要自己开 session**，一律从依赖拿——可测试、可替换、不泄漏。

我用测试锁死了这个语义：一个会话 commit 后，新会话能读到；未 commit 的数据别的会话看不见：

```python
async def test_uncommitted_data_not_leaked():
    async with async_session_factory() as s1:
        s1.add(Document(filename="b.txt", content="y", status="pending"))
        # 不 commit，直接退出（触发回滚）

    async with async_session_factory() as s2:
        rows = (await s2.execute(select(Document))).scalars().all()
        assert rows == []        # 未提交 → 不可见
```

## 事务边界：commit 是你划的，不是 ORM 替你划的

SQLAlchemy 的会话是**工作单元**模式：所有改动攒着，`commit()` 一次性落库，`rollback()` 一次性放弃。边界在哪，是业务决定的：

```python
doc = Document(filename=file.filename, content=content, status="pending")
db.add(doc)
await db.commit()      # 落库点：文档记录必须先在，才能入队索引
await dispatch_index(doc.id)
```

两个原则：

- **一个请求一个业务事务**：别在循环里 commit，也别把一个用例拆成多次 commit；
- **异常要回滚，别让脏会话带病复用**：回滚后会话可继续用，我专门测了这点：

```python
async def test_rollback_on_error():
    async with async_session_factory() as session:
        session.add(Document(filename="d.txt", content="w", status="pending"))
        await session.rollback()
        rows = (await session.execute(select(Document))).scalars().all()
        assert rows == []                        # 回滚生效

        session.add(Document(filename="e.txt", content="v", status="pending"))
        await session.commit()                   # 回滚后会话仍可用
```

::: warning
async 会话里忘了 commit，数据就静默丢失——没有任何报错。这是同步转 async 最容易漏的地方。我的做法是：业务上明确「谁负责 commit」，并用测试断言落库结果，不靠自觉。
:::

## expire_on_commit=False：async 下的刚需

```python
async_sessionmaker(engine, expire_on_commit=False)
```

这一行不是优化，是**async 正确性**的要求。

默认 `expire_on_commit=True` 时，commit 后 ORM 会把对象属性标记为过期，下次访问属性就触发**懒加载**去查库。在同步代码里这是隐形查询，在 async 里它直接抛 `MissingGreenlet`——因为懒加载是阻塞 IO，跑不进事件循环。

测试锁死了这个行为：

```python
async def test_expire_on_commit_false_keeps_attributes():
    async with async_session_factory() as session:
        doc = Document(filename="c.txt", content="z", status="pending")
        session.add(doc)
        await session.commit()
        assert doc.filename == "c.txt"      # commit 后直接访问，不查库
        assert doc.id is not None
```

## 懒加载与 N+1：lazy="raise" 把问题提前炸出来

N+1 问题：查 1 个文档 + 它的 20 个切片，不是 1 条 SQL，而是 1 + 20 条。ORM 默认的懒加载在遍历时逐个查库，量一上来延迟爆炸。

async 下还有更狠的：懒加载在事件循环里跑不起来，直接抛 `MissingGreenlet`。所以**默认懒加载在 async 里是双重错误**——既慢又炸。

正确姿势是声明期就关掉懒加载，把问题显式化：

```python
class Document(Base):
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="raise"
    )
```

`lazy="raise"` 的语义是：**没预加载就访问，直接抛错**。不是偷偷查库，不是莫名其妙崩，而是在查询侧把问题暴露出来。测试验证：

```python
async def test_lazy_relationship_raises_explicitly():
    async with async_session_factory() as session:
        doc = (await session.execute(select(Document))).scalars().first()
        with pytest.raises(InvalidRequestError):
            _ = doc.chunks        # 未预加载 → 显式抛错
```

要访问关联，就在查询时显式预加载，一条 SQL 搞定：

```python
stmt = select(Document).options(selectinload(Document.chunks))
docs = (await session.execute(stmt)).scalars().all()
docs[0].chunks      # 不再查库
```

预加载策略选型：

| 策略 | 行为 | 适用 |
|---|---|---|
| selectin | 子查询 IN，批量取 | 一对多，最常用 |
| joined | JOIN 一次取 | 多对一、一对一 |
| raise | 未预加载就报错 | async 默认防护 |

::: note
lazy="raise" 是 async 项目的默认选择。它把「隐式 N+1」变成「显式报错」，代价是查询必须写全 options，收益是性能问题不会潜伏到生产。
:::

## 向量距离的 SQL 映射：相似度是这么算的

这是 RAG 工程特有的映射——`Chunk.embedding` 不是普通字段，是向量。查询也不只是 WHERE 过滤，而是**按距离排序取 top-k**。SQL 长这样：

```sql
SELECT id, content
FROM pg_chunks
ORDER BY embedding <=> :query_vec   -- <=> 是余弦距离算子
LIMIT 5
```

pgvector 提供三个距离算子：

| 算子 | 含义 | 方向 |
|---|---|---|
| `<->` | L2（欧氏）距离 | 越小越近 |
| `<=>` | 余弦距离 | 越小越近 |
| `<#>` | 负内积 | 越小越近（内积取负） |

SQLAlchemy 2.0 的映射写法——`Vector` 列类型 + 距离方法，ORM 替你拼算子：

```python
from pgvector.sqlalchemy import Vector

class PgChunk(PgBase):
    __tablename__ = "pg_chunks"
    embedding = mapped_column(Vector(1536), nullable=False)

def build_cosine_search(query_vec: list[float], k: int = 5):
    return (
        select(PgChunk.id, PgChunk.content)
        .order_by(PgChunk.embedding.cosine_distance(query_vec))  # <-=
        .limit(k)
    )
```

三个细节值得较真：

- **维度要在发查询前校验**。`query_vec` 长度和列定义的 `Vector(1536)` 不一致，PostgreSQL 会报维度错误——但错误发生在数据库往返之后。发之前 `len(query_vec) != VECTOR_DIM` 就 raise，省一次白跑的 IO。
- **距离升序就是相似度降序**。`<=>` 算出的是「距离」，越小越近，`ORDER BY` 默认升序正好。别看着「相似度」三个字就写 `DESC`——方向写反，top-k 变成最不相关的 k 条，还不报错。我用数值断言锁死了这个方向：余弦距离升序与余弦相似度降序给出同一排序。
- **编译期就能验证 SQL 形状**。`stmt.compile(dialect=postgresql.dialect())` 不需要真起数据库，断言 `<=>`、`ORDER BY`、`LIMIT` 都在。测试便宜，就能常跑。

::: warning
教学工程默认跑 SQLite + JSON 存向量 + numpy 算相似度，那是为了让零依赖可跑。生产必须把距离计算下推到 pgvector——把全部向量拉回进程里逐个算，是 O(n) 次 Python 循环加 O(n) 次网络传输，量一上来先死的是应用服务器不是数据库。
:::

## 连接池：默认值不是万能的

```python
engine = create_async_engine(
    settings.database_url,
    pool_size=10,          # 常驻连接数
    max_overflow=20,       # 峰值可超发的连接
    pool_pre_ping=True,    # 取连接前先探活
    pool_recycle=3600,     # 连接最大存活时间
)
```

| 参数 | 作用 | 调大后果 |
|---|---|---|
| pool_size | 常驻连接 | 占 DB 连接配额 |
| max_overflow | 突发峰值 | 打满 DB max_connections |
| pool_pre_ping | 排除死连接 | 每次取连接多一次往返 |
| pool_recycle | 防连接被服务端掐断 | 过小会频繁重建 |

::: warning
pool_size + max_overflow 不是越大越好，上限是数据库的 max_connections。多个进程/副本时要按「单进程池 × 副本数 ≤ DB 上限」算总账，否则高峰一到全体排队。
:::

## 迁移：create_all 只配教学

工程里 `init_db()` 用 `Base.metadata.create_all` 建表，是教学简化。**生产必须用 Alembic**，因为它做的是「版本化演进」——每次表结构变更是一个可回滚的迁移脚本。

```python
# alembic/env.py 核心：用模型元数据驱动迁移
from app.core.db import Base
from app import models  # 触发元数据注册

target_metadata = Base.metadata

def run_migrations_online():
    connectable = async_engine_from_config(...)   # async 迁移
    ...
```

三件事必须做：

- 迁移脚本进版本库，和代码一起 review；
- 每次改模型就生成迁移，**禁止手工改生产表**；
- 上线前 `alembic upgrade head`，回滚用 `alembic downgrade -1`。

## 常见坑清单

| 坑 | 现象 | 纠正 |
|---|---|---|
| 忘 commit | 数据静默丢失 | 明确 commit 责任方，测试断言 |
| 函数里建 engine | 连接数暴涨 | engine 进程级单例 |
| async 里懒加载 | MissingGreenlet | lazy="raise" + 预加载 |
| commit 后访问属性 | 同上 | expire_on_commit=False |
| 会话跨请求复用 | 脏数据串请求 | session-per-request |
| 手工改生产表 | 环境不一致 | Alembic 迁移 |
| 向量拉回进程算距离 | O(n) 循环 + 全量传输 | pgvector 库内 ORDER BY 距离 |
| 距离排序方向写反 | top-k 返回最不相关 | 距离升序，别写 DESC |

## 总结

SQLAlchemy 2.0 async 的正确姿势可以浓缩成一句话：**engine 进程级、session 请求级、事务业务级、懒加载全部显式化**。

具体五步：`create_async_engine` + `async_sessionmaker` 起盘，`get_db` 实现 session-per-request，`commit/rollback` 划清事务边界，`expire_on_commit=False` + `lazy="raise"` 消灭隐形查询，Alembic 管迁移。RAG 特有的向量距离也有对应映射：pgvector 的 `Vector` 列 + `<=>` 算子，top-k 一条 SQL 在库内算完。每一项都带测试，不是我说能跑，是跑过。

> 下一篇装任务队列：Celery + Redis 的任务幂等、重试策略、eager 与 worker 的切换，以及 Beat 定时任务怎么不漏跑。

::: note
文中测试覆盖会话隔离、事务回滚、expire_on_commit 行为、懒加载防护与预加载，以及向量距离的 SQL 形状与排序方向，共 10 项。工程源码见文末引用。
:::
