"""FastAPI 工程基础行为测试：健康检查、统一错误格式、异常兜底。"""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError, register_exception_handlers
from app.main import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_http_exception_unified_format():
    """HTTPException 统一为 {"error": {"code", "message"}}，不再返回裸 detail。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("a.txt", b"", "text/plain")},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "HTTP_400"
        assert body["error"]["message"]


@pytest.mark.asyncio
async def test_app_error_handler():
    """AppError 带业务错误码，handler 统一转 JSON。"""

    def _make_app() -> FastAPI:
        test_app = FastAPI()
        register_exception_handlers(test_app)

        @test_app.get("/boom")
        async def boom():
            raise AppError("业务规则不满足", code="RULE_VIOLATION", status_code=422)

        @test_app.get("/crash")
        async def crash():
            raise RuntimeError("不该暴露的堆栈")

        return test_app

    # raise_app_exceptions=False：ServerErrorMiddleware 处理后仍会 re-raise
    # （Starlette 设计，便于 ASGI 服务器记日志），测试里验证响应即可
    transport = ASGITransport(app=_make_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/boom")
        assert resp.status_code == 422
        assert resp.json() == {"error": {"code": "RULE_VIOLATION", "message": "业务规则不满足"}}

        # 未捕获异常兜底 500，堆栈不进响应体
        resp = await client.get("/crash")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert "堆栈" not in body["error"]["message"]
