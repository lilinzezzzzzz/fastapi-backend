import time
import uuid
from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.datastructures import MutableHeaders

from internal.core.exception import get_last_exec_tb
from pkg.context_tool import context
from pkg.logger_tool import logger
from pkg.resp_tool import error_code, response_factory


class ASGIRecordMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. 获取或生成 Trace ID
        # ASGI headers 是 list of (bytes, bytes) tuple
        headers = MutableHeaders(scope=scope)
        context.init(trace_id := headers.get("X-Trace-ID", uuid.uuid4().hex))

        # 2. 上下文注入
        with logger.contextualize(trace_id=trace_id):
            # 注意：在纯 ASGI 中获取 body 或 params 比较麻烦，
            # 这里仅记录路径和方法，避免为了读 body 而消耗掉 receive stream
            client_host = scope.get("client", ["unknown"])[0]
            logger.info(
                f"access log, ip={client_host}, method={scope['method']}, path={scope['path']}, query_string={scope.get('query_string', b'').decode()}"
            )

            start_time = time.perf_counter()
            response_started = False
            # 定义 send_wrapper 来拦截响应，注入 Header
            async def send_wrapper(message):
                nonlocal response_started
                if message["type"] == "http.response.start":
                    response_started = True
                    process_time = time.perf_counter() - start_time

                    # 注入响应头 (需要修改 message 中的 headers)
                    # 注意：headers 是 mutable list，直接修改
                    headers_list = MutableHeaders(scope=message)
                    headers_list["X-Process-Time"] = str(process_time)
                    headers_list["X-Trace-ID"] = trace_id

                    logger.info(f'response log, processing time={process_time:.2f}s')

                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as exc:
                # 3. 异常处理
                # 注意：在 ASGI 层捕获异常非常危险，通常建议让异常冒泡给 FastAPI 的 ExceptionHandlers 处理。
                # 如果你必须在这里拦截所有未处理异常并返回 JSON，需要手动发送 ASGI 消息。

                logger.error(f"Unhandled exception, exc={get_last_exec_tb(exc)}")
                if not response_started:
                    # 手动构建错误响应
                    error_resp = response_factory.response(
                        code=error_code.InternalServerError,
                        message=f"Unhandled Exception: {exc}"
                    )

                    # 使用 Starlette Response 对象来帮助我们发送 ASGI 消息 (比手写容易)
                    await error_resp(scope, receive, send)
                else:
                    logger.error(f"Response already started, cannot send 500 error response for trace_id={trace_id}")
                    pass
