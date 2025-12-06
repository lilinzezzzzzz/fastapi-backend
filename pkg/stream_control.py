import json
from collections.abc import AsyncIterable
from typing import TypeVar

import anyio
from fastapi import Request

from pkg.loguru_logger import logger

T = TypeVar("T")


async def stream_with_chunk_control(
        _: Request,
        generator: AsyncIterable[T],
        chunk_timeout: float,
        is_sse: bool = True
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
                err_data = {
                    "code": 408,
                    "message": f"Stream chunk timed out. No data received for {chunk_timeout}s"
                }
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
