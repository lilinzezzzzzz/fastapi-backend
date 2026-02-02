import json
import time
from collections.abc import AsyncGenerator, AsyncIterable, Callable
from functools import wraps
from typing import Any

import anyio
from starlette.requests import Request

from pkg.toolkit.logger import logger


def async_generator_timer(slow_threshold: float = 5.0):
    """
    异步生成器计时装饰器，用于统计 Handler.handle 方法或普通异步生成器函数的执行时间。

    Args:
        slow_threshold: 慢执行阈值（秒），超过此时间会记录警告日志

    Usage:
        @async_generator_timer(slow_threshold=5.0)
        async def handle(self, messages, **kwargs):
            ...
    """

    def decorator(func: Callable[..., AsyncGenerator[Any, None]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 支持类方法和普通函数
            if args and hasattr(args[0], "__class__"):
                handler_name = f"{args[0].__class__.__name__}.{func.__name__}"
            else:
                handler_name = func.__name__

            start_time = time.perf_counter()

            logger.info(f"Starting {handler_name}...")
            try:
                async for response in func(*args, **kwargs):
                    yield response
            finally:
                elapsed = time.perf_counter() - start_time
                if elapsed > slow_threshold:
                    logger.info(f"SLOW: {handler_name} took {elapsed:.3f}s (threshold: {slow_threshold}s)")
                else:
                    logger.info(f"Completed {handler_name} in {elapsed:.3f}s")

        return wrapper

    return decorator


async def stream_with_chunk_control[T](
    _: Request,
    generator: AsyncIterable[T],
    chunk_timeout: float,
    is_sse: bool = True,
) -> AsyncIterable[T]:
    """
    基于 AnyIO 的单 Chunk 超时控制。
    总超时由 Middleware 统一控制。
    """
    iterator = generator.__aiter__()

    while True:
        try:
            # 使用 anyio.fail_after 仅控制获取下一个 chunk 的等待时间
            with anyio.fail_after(chunk_timeout):
                item = await iterator.__anext__()

            yield item

        except StopAsyncIteration:
            break

        except TimeoutError:
            # 仅处理 Chunk 生成超时（卡顿）
            logger.warning(f"[Stream Timeout] Chunk generation timed out after {chunk_timeout}s")

            if is_sse:
                # 构造 SSE 格式的超时错误消息
                err_data = {"code": 408, "message": f"Stream chunk timed out. No data received for {chunk_timeout}s"}
                yield f"data: {json.dumps(err_data)}\n\n"

            # 单个 Chunk 超时通常意味着上游服务卡死，建议中断流
            break

        except anyio.get_cancelled_exc_class() as e:
            # 处理 Middleware 触发的总超时取消 或 客户端断连
            # 当 Middleware 的 fail_after 触发时，会向这里注入 CancelledError
            logger.info(f"Stream cancelled (Client disconnected or Global Timeout). Msg: {str(e)}")
            raise e  # 必须抛出，以便 Middleware 或 Server 正确关闭连接

        except Exception as e:
            logger.error(f"Stream generation error: {e}", exc_info=True)
            if is_sse:
                yield f"data: {json.dumps({'code': 500, 'message': str(e)})}\n\n"
            break
