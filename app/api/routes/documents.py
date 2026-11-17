"""文档上传与查询。

实践点：
1. 上传只做「落库 + 入队」，耗时的切分/向量化交给 Celery 异步做，
   API 快速返回，避免请求超时；
2. 列表接口用 response_model 过滤掉 content 大字段；
3. 路由带 summary/description，Swagger 文档自动生成可读说明。
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.document import Document
from app.schemas.document import DocumentOut
from app.tasks.dispatch import dispatch_index

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=201,
    summary="上传文档",
    description="上传文本文件：落库为 pending 文档，并把「切分 + 向量化 + 入库」派发为后台任务。立即返回文档记录，索引状态可轮询列表接口查看。",
)
async def upload_document(
    file: UploadFile = File(..., description="UTF-8 文本文件"),
    db: AsyncSession = Depends(get_db),
) -> Document:
    content = (await file.read()).decode("utf-8", errors="ignore")
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    doc = Document(filename=file.filename or "unnamed.txt", content=content, status="pending")
    db.add(doc)
    await db.commit()

    # 异步入队：切分 + 向量化 + 入库（eager 模式同步，生产走 Celery）
    await dispatch_index(doc.id)
    return doc


@router.get(
    "",
    response_model=list[DocumentOut],
    summary="文档列表",
    description="按上传时间倒序列出文档，response_model 过滤掉 content 大字段，只返回 id / filename / status / created_at。",
)
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[Document]:
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars().all())
