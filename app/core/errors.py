"""统一异常处理：业务异常带错误码，HTTP 响应格式一致。

实践点：
1. AppError 携带 code + status_code，handler 统一转 JSON，前端只认一种错误结构；
2. HTTPException 也统一覆盖，避免 {"detail": ...} 与业务错误两种格式混用；
3. 未捕获异常兜底 500，不把堆栈泄到响应体（详情进日志）。

注意：覆盖 HTTPException handler 会改变错误响应体结构（对外行为变化），
升级时需同步通知前端。
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """业务异常基类。"""

    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__(message, code="NOT_FOUND", status_code=404)


def _error_payload(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    """把三类异常统一成 {"error": {"code", "message"}} 结构。

    注意：未捕获异常的兜底必须注册为状态码 500 的 handler。
    Starlette 的 build_middleware_stack 只把 key == 500 的 handler 交给
    ServerErrorMiddleware；只注册 Exception 类型是兜不住的（会原样抛出）。
    """

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message),
        )

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = f"HTTP_{exc.status_code}"
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return JSONResponse(status_code=exc.status_code, content=_error_payload(code, message))

    async def _internal_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_error_payload("INTERNAL_ERROR", "服务内部错误"),
        )

    # 两条都注册：500 走 ServerErrorMiddleware（真正兜底），Exception 兼容
    app.add_exception_handler(500, _internal_error)
    app.add_exception_handler(Exception, _internal_error)
