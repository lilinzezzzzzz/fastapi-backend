import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

from internal.core.exception import AppException, errors
from internal.core.logger import logger
from pkg.toolkit import context
from pkg.toolkit.exc import get_last_exec_tb
from pkg.toolkit.response import error_response


class ASGIRecordMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. 获取或生成 Trace ID
        headers = MutableHeaders(scope=scope)
        context.init(trace_id=(trace_id := headers.get("X-Trace-ID", uuid.uuid4().hex)))

        # 2. 上下文注入
        with logger.contextualize(trace_id=trace_id):
            client_host = scope.get("client", ["unknown"])[0]
            logger.info(
                f"access log, ip={client_host}, method={scope['method']}, path={scope['path']}, query_string={scope.get('query_string', b'').decode()}"
            )

            start_time = time.perf_counter()
            response_started = False

            # 3. 定义 send_wrapper (闭包)
            async def send_wrapper(message):
                nonlocal response_started

                if message["type"] == "http.response.start":
                    response_started = True
                    process_time = time.perf_counter() - start_time

                    # 注入 Header
                    resp_headers = MutableHeaders(scope=message)
                    resp_headers["X-Process-Time"] = f"{process_time:.4f}"
                    resp_headers["X-Trace-ID"] = trace_id

                    logger.info(f"response log, processing time={process_time:.4f}s")

                await send(message)

            # 4. 执行应用逻辑
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as exc:
                # 5. 异常处理
                logger.error(f"Unhandled exception, exc={get_last_exec_tb(exc)}")

                if not response_started:
                    if isinstance(exc, AppException):
                        error_resp = error_response(error=exc.error, message=exc.message)
                    else:
                        error_resp = error_response(error=errors.InternalServerError, message=str(exc))

                    # 复用 send_wrapper，错误响应也会自动注入 header
                    await error_resp(scope, receive, send_wrapper)
                else:
                    logger.critical(f"Response already started, cannot send error response. trace_id={trace_id}")
