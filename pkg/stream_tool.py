import json
import time
from collections.abc import AsyncIterable, Callable
from typing import TypeVar

import anyio
from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse

from pkg.logger_tool import logger

T = TypeVar("T")


async def stream_with_dual_control(
        generator: AsyncIterable[T],
        chunk_timeout: float,
        total_timeout: float,
        is_sse: bool = True
) -> AsyncIterable[T]:
    """
    基于 AnyIO 和 perf_counter 的双重超时控制
    """
    iterator = generator.__aiter__()

    # 1. 使用 perf_counter 获取单调时钟起点
    start_time = time.perf_counter()

    while True:
        # 2. 计算消耗的时间 (单调时钟差值)
        elapsed_time = time.perf_counter() - start_time
        remaining_total_time = total_timeout - elapsed_time

        # --- 预检查：总时间耗尽 ---
        if remaining_total_time <= 0:
            logger.warning(f"Total timeout exceeded. Total timeout: {total_timeout}s")
            if is_sse:
                yield f"data: {json.dumps({"code": 408, "message": 'Total timeout exceeded'})}\n\n"
            break

        # 3. 决定本次超时时间
        current_wait_time = min(chunk_timeout, remaining_total_time)

        try:
            # --- 4. 使用 anyio.fail_after ---
            # AnyIO 会自动处理 Python 版本差异，且提供更安全的取消作用域
            with anyio.fail_after(current_wait_time):
                item = await iterator.__anext__()

            yield item

        except StopAsyncIteration:
            break

        except TimeoutError:
            # 注意：AnyIO 抛出的也是标准库的 TimeoutError (Python 3.11+) 或其兼容别名

            # 重新计算时间以确认是哪种超时
            now = time.perf_counter()
            # 加上 0.01 的缓冲，避免浮点数精度导致的边界判断失误
            is_total_timeout = (now - start_time) >= (total_timeout - 0.01)

            if is_total_timeout:
                error_type = "total_timeout"
                limit_val = total_timeout
                error_msg = f"Operation timed out after {total_timeout}s"
            else:
                error_type = "chunk_timeout"
                limit_val = chunk_timeout
                error_msg = f"Stream chunk timed out after {chunk_timeout}s"

            logger.warning(f"[Timeout] Type:{error_type} Limit:{limit_val}s")

            if is_sse:
                err_data = {"code": 408, "message": error_msg}
                yield f"data: {json.dumps(err_data)}\n\n"

            break

        except anyio.get_cancelled_exc_class() as e:
            # --- 5. 处理客户端断连 ---
            logger.info(
                f"Client disconnected (AnyIO cancellation). Exception type: {type(e).__name__}, Message: {str(e)}")
            raise

        except Exception as e:
            logger.error(f"Stream generation error: {e}", exc_info=True)
            if is_sse:
                yield f"data: {json.dumps({"code": 500, "message": str(e)})}\n\n"
            break


class TimeoutControlRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            # 1. 执行原始逻辑
            response = await original_route_handler(request)

            # 2. 检查是否为流式响应
            if isinstance(response, StreamingResponse):
                # 3. 获取动态配置 (优先从 request.state 获取，没有则用默认值)
                # 你可以在具体的 path operation 函数中通过 request.state.chunk_timeout = 5 来设置
                chunk_timeout = getattr(request.state, "chunk_timeout", 60.0)  # 默认 60s
                total_timeout = getattr(request.state, "total_timeout", 300.0)  # 默认 5min

                # 4. 判断是否为 SSE 流 (根据 media_type)
                # 常见的 SSE media type 是 text/event-stream
                is_sse = "text/event-stream" in (response.media_type or "")

                # 5. 替换 iterator
                response.body_iterator = stream_with_dual_control(
                    response.body_iterator,
                    chunk_timeout=chunk_timeout,
                    total_timeout=total_timeout,
                    is_sse=is_sse
                )

            return response

        return custom_route_handler
