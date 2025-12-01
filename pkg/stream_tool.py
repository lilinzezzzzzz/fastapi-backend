import asyncio
import json
import time
from typing import AsyncIterable, TypeVar, Optional, Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse
from starlette.background import BackgroundTask

T = TypeVar("T")


async def stream_with_dual_control(
        generator: AsyncIterable[T],
        chunk_timeout: float,
        total_timeout: float,
        error_callback: Optional[Callable] = None,
        is_sse: bool = True  # 新增：标记是否为 SSE 格式
) -> AsyncIterable[T]:
    iterator = generator.__aiter__()
    start_time = time.time()

    while True:
        elapsed_time = time.time() - start_time
        remaining_total_time = total_timeout - elapsed_time

        # 1. 检查总超时 (预先检查)
        if remaining_total_time <= 0:
            if error_callback: error_callback("total_timeout", total_timeout)
            # 只有 SSE 才返回特定格式的错误数据，否则直接截断流
            if is_sse:
                yield f"data: {json.dumps({'code': 408, 'message': 'Total timeout exceeded'})}\n\n"
            break

        # 2. 计算本次等待时间
        current_wait_time = min(chunk_timeout, remaining_total_time)

        try:
            # 3. 等待数据
            item = await asyncio.wait_for(iterator.__anext__(), timeout=current_wait_time)
            yield item

        except StopAsyncIteration:
            break

        except asyncio.TimeoutError:
            # 判断超时类型
            is_total_timeout = (time.time() - start_time) >= total_timeout

            error_type = "total_timeout" if is_total_timeout else "chunk_timeout"
            limit_val = total_timeout if is_total_timeout else chunk_timeout
            error_msg = f"Timeout: {error_type} limit {limit_val}s exceeded"

            if error_callback:
                error_callback(error_type, limit_val)

            if is_sse:
                yield f"data: {json.dumps({'code': 408, 'message': error_msg})}\n\n"
            # 如果不是 SSE，这里直接 break，相当于网络中断，客户端会收到不完整的数据
            break

        except asyncio.CancelledError:
            # 客户端断开连接，必须重新抛出，以便底层服务器清理资源
            raise

        except Exception as e:
            # 业务逻辑崩溃
            if is_sse:
                yield f"data: {json.dumps({'code': 500, 'message': str(e)})}\n\n"
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

                path = request.url.path

                # 4. 判断是否为 SSE 流 (根据 media_type)
                # 常见的 SSE media type 是 text/event-stream
                is_sse = "text/event-stream" in (response.media_type or "")

                # 5. 替换 iterator
                response.body_iterator = stream_with_dual_control(
                    response.body_iterator,
                    chunk_timeout=chunk_timeout,
                    total_timeout=total_timeout,
                    error_callback=lambda t, v: print(f"[Timeout] Type:{t} Limit:{v}s | Path:{path}"),
                    is_sse=is_sse
                )

            return response

        return custom_route_handler
