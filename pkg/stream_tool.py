import asyncio
import json
import time
from typing import AsyncIterable, TypeVar, Optional, Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse
from starlette.background import BackgroundTask

from pkg.logger_tool import logger

T = TypeVar("T")


async def stream_with_dual_control(
        generator: AsyncIterable[T],
        chunk_timeout: float,
        total_timeout: float,
        error_callback: Optional[Callable[[str, float], None]] = None,
        is_sse: bool = True
) -> AsyncIterable[T]:
    """
    双重超时控制生成器 (Python 3.11+ Optimized)

    Args:
        generator: 原始数据生成器
        chunk_timeout: 单次数据块最大间隔时间 (秒)
        total_timeout: 整个流最大传输时间 (秒)
        error_callback: 超时发生时的回调 (类型, 时间限制)
        is_sse: 是否为 SSE 流。如果是，超时返回特定 JSON；否则直接断开。
    """
    # 获取异步迭代器
    iterator = generator.__aiter__()
    start_time = time.time()

    while True:
        # 1. 计算剩余的总时间
        elapsed_time = time.time() - start_time
        remaining_total_time = total_timeout - elapsed_time

        # --- 预检查：总时间耗尽 ---
        if remaining_total_time <= 0:
            if error_callback:
                error_callback("total_timeout", total_timeout)

            if is_sse:
                # 构造 SSE 格式的超时错误
                err_payload = json.dumps({"code": 408, "message": "Total timeout exceeded"})
                yield f"data: {err_payload}\n\n"

            # 停止迭代
            break

        # 2. 动态计算本次等待时间
        # 取 "Chunk超时" 和 "剩余总时间" 的较小值
        current_wait_time = min(chunk_timeout, remaining_total_time)

        try:
            # --- 关键优化：使用 Python 3.11+ 上下文管理器 ---
            # asyncio.timeout 比 wait_for 更高效，不创建新的 Task
            async with asyncio.timeout(current_wait_time):
                item = await iterator.__anext__()

            yield item

        except StopAsyncIteration:
            # 生成器正常结束
            break

        except TimeoutError:
            # --- 处理超时逻辑 ---
            # 判断是哪种超时
            now = time.time()
            is_total_timeout = (now - start_time) >= total_timeout

            if is_total_timeout:
                error_type = "total_timeout"
                limit_val = total_timeout
                error_msg = f"Operation timed out after {total_timeout}s"
            else:
                error_type = "chunk_timeout"
                limit_val = chunk_timeout
                error_msg = f"Stream chunk timed out after {chunk_timeout}s"

            # 触发回调
            if error_callback:
                error_callback(error_type, limit_val)

            # 如果是 SSE，尝试向客户端发送错误信息
            if is_sse:
                err_data = {"code": 408, "message": error_msg}
                yield f"data: {json.dumps(err_data)}\n\n"

            # 无论是否发送了错误信息，超时后必须断开流
            break

        except asyncio.CancelledError:
            # --- 客户端断开连接 ---
            # 必须重新抛出异常，以便 FastAPI/Starlette 能够感知连接中断
            # 并触发 background task 的清理工作（如果有）
            logger.info("Client disconnected during streaming.")
            raise

        except Exception as e:
            # --- 捕获业务逻辑崩溃 ---
            logger.error(f"Stream generation error: {e}", exc_info=True)
            if is_sse:
                err_data = {"code": 500, "message": "Internal Stream Error"}
                yield f"data: {json.dumps(err_data)}\n\n"
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
