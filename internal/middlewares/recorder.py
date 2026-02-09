import time
from dataclasses import dataclass, field

from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from internal.core.exception import AppException, errors
from pkg.logger import logger
from pkg.toolkit import context
from pkg.toolkit.exc import get_business_exec_tb, get_unexpected_exec_tb
from pkg.toolkit.otel import get_current_trace_id
from pkg.toolkit.response import error_response
from pkg.toolkit.string import uuid6_unique_str_id


@dataclass
class _RequestContext:
    """请求上下文，封装中间件处理过程中的状态变量"""

    path: str
    method: str
    client_host: str
    query_string: str
    headers: MutableHeaders
    start_time: float = field(default_factory=time.perf_counter)
    trace_id: str = field(default_factory=uuid6_unique_str_id)
    receive: Receive | None = None
    response_started: bool = False
    _process_time: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        # trace_id 优先级：OTel context > 请求头 X-Trace-ID > uuid6
        otel_trace_id = get_current_trace_id()
        if otel_trace_id:
            self.trace_id = otel_trace_id
        else:
            header_trace_id = self.headers.get("X-Trace-ID")
            if header_trace_id:
                self.trace_id = header_trace_id

    @property
    def process_time(self) -> float:
        """返回请求处理耗时。如果已记录则返回记录值，否则返回当前实时值。"""
        if self._process_time is not None:
            return self._process_time
        return time.perf_counter() - self.start_time

    def create_send_wrapper(self, send: Send, scope: Scope):
        """
        创建 send 包装器，用于在响应头中注入追踪信息

        Args:
            send: 原始 send 函数
            scope: ASGI scope

        Returns:
            包装后的 send 函数
        """

        async def send_wrapper(message: Message):
            if message["type"] == "http.response.start":
                self.response_started = True
                headers_list = MutableHeaders(scope=message)
                headers_list["X-Process-Time"] = str(self.process_time)
                headers_list["X-Trace-ID"] = self.trace_id
            await send(message)

        return send_wrapper


class ASGIRecordMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    @staticmethod
    def _log_exception(exc: Exception) -> None:
        """
        记录异常日志，根据异常类型使用不同的日志级别

        Args:
            exc: 捕获的异常
        """
        if isinstance(exc, AppException):
            logger.warning(f"Business exception, exc={get_business_exec_tb(exc)}")
        elif isinstance(exc, RequestValidationError):
            logger.warning(f"Validation Error: {exc}")
        else:
            logger.error(f"Unexpected exception, exc={get_unexpected_exec_tb(exc)}")

    @staticmethod
    def _build_error_response(exc: Exception) -> Response:
        """
        根据异常类型构造错误响应

        Args:
            exc: 捕获的异常

        Returns:
            FastAPI Response 对象
        """
        if isinstance(exc, AppException):
            return error_response(error=exc.error, message=exc.message)
        elif isinstance(exc, RequestValidationError):
            return error_response(error=errors.BadRequest, message=f"Validation Error: {exc}")
        else:
            return error_response(error=errors.InternalServerError, message=str(exc))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 初始化请求上下文
        req_ctx = _RequestContext(
            path=scope["path"],
            method=scope["method"],
            client_host=scope.get("client", ["unknown"])[0],
            query_string=scope.get("query_string", b"").decode(),
            headers=MutableHeaders(scope=scope),
            receive=receive,
        )

        # 全局异常捕获,覆盖整个请求处理流程
        try:
            # 1. 初始化上下文
            context.init(trace_id=req_ctx.trace_id)

            send_wrapper = req_ctx.create_send_wrapper(send, scope)
            # 2. 记录访问日志
            with logger.contextualize(trace_id=req_ctx.trace_id):
                logger.info(
                    f"access log, ip={req_ctx.client_host}, method={req_ctx.method}, "
                    f"path={req_ctx.path}, query_string={req_ctx.query_string}"
                )

                # 3. 创建 send 包装器并执行应用逻辑
                await self.app(scope, receive, send_wrapper)

                # 4. 记录响应日志
                logger.info(f"response log, processing time={req_ctx.process_time:.4f}s")

        except Exception as exc:
            # 5. 统一异常处理
            self._log_exception(exc)

            if not req_ctx.response_started:
                error_resp = self._build_error_response(exc)
                await error_resp(scope, receive, send_wrapper)
            else:
                logger.critical(f"Response already started, cannot send error response. trace_id={req_ctx.trace_id}")
