import time
from dataclasses import dataclass, field

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from internal.core.exception import AppException, errors
from internal.core.logger import logger
from pkg.toolkit import context
from pkg.toolkit.exc import get_business_exec_tb, get_unexpected_exec_tb
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

    def __post_init__(self):
        # 优先使用请求头中的 trace_id
        header_trace_id = self.headers.get("X-Trace-ID")
        if header_trace_id:
            self.trace_id = header_trace_id

    @property
    def process_time(self) -> float:
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

            # 2. 记录访问日志
            with logger.contextualize(trace_id=req_ctx.trace_id):
                logger.info(
                    f"access log, ip={req_ctx.client_host}, method={req_ctx.method}, "
                    f"path={req_ctx.path}, query_string={req_ctx.query_string}"
                )

                # 3. 创建 send 包装器并执行应用逻辑
                send_wrapper = req_ctx.create_send_wrapper(send, scope)
                await self.app(scope, receive, send_wrapper)

                # 4. 记录响应日志
                logger.info(f"response log, processing time={req_ctx.process_time:.4f}s")

        except Exception as exc:
            # 5. 统一异常处理 - 区分业务异常与系统异常
            if isinstance(exc, AppException):
                # 业务异常使用 warning 级别
                logger.warning(f"Business exception, exc={get_business_exec_tb(exc)}")
            else:
                # 系统异常使用 error 级别
                logger.error(f"Unexpected exception, exc={get_unexpected_exec_tb(exc)}")

            if not req_ctx.response_started:
                # 构造错误响应
                if isinstance(exc, AppException):
                    error_resp = error_response(error=exc.error, message=exc.message)
                else:
                    error_resp = error_response(error=errors.InternalServerError, message=str(exc))

                # 复用 send_wrapper,错误响应也会自动注入追踪头
                send_wrapper = req_ctx.create_send_wrapper(send, scope)
                await error_resp(scope, receive, send_wrapper)
            else:
                logger.critical(f"Response already started, cannot send error response. trace_id={req_ctx.trace_id}")
