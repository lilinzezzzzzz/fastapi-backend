import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

import anyio
import httpx

from pkg.async_logger import logger


@dataclass
class RequestResult:
    status_code: int | None = None
    response: httpx.Response | None = None
    error: str | None = None
    _json: Any = field(init=False, default=None)

    @property
    def success(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300

    def json(self) -> Any:
        if self._json is not None:
            return self._json
        if not self.response:
            return {}
        try:
            self._json = self.response.json()
            return self._json
        except Exception as e:
            logger.warning(f"Response is not valid JSON: {e}")
            return {}


class AsyncHttpClient:
    """
    基于 httpx 封装的单例/长连接客户端。
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: int = 60,
        headers: dict[str, str] | None = None,
        verify: bool = True,
    ):
        self.timeout = timeout
        self.default_headers = headers or {"Content-Type": "application/json"}
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=self.default_headers,
            verify=verify,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        await self.client.aclose()

    @asynccontextmanager
    async def _stream_context(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        raise_exception: bool = True,
    ):
        """
        [封装核心]：统一的流式上下文管理器。
        处理连接建立、超时合并、状态检查、日志记录。
        """
        method = method.upper()
        # 修正问题1：确保 stream 请求也能吃到默认 timeout
        req_timeout = timeout or self.timeout

        logger.info(f"Stream Start: {method} {url}")
        try:
            async with self.client.stream(
                method,
                url,
                params=params,
                headers=headers,
                timeout=req_timeout,
            ) as response:

                # 统一状态码检查逻辑
                if raise_exception:
                    # 如果需要抛出异常，利用 httpx 原生能力
                    response.raise_for_status()
                elif response.is_error:
                    # 如果不抛出异常（供 download_file 使用），记录错误并交给调用方处理
                    logger.warning(f"Stream responded with error: {response.status_code}")

                yield response

        except httpx.HTTPStatusError as exc:
            raise Exception(f"Stream HTTPStatusError: {exc.response.status_code} - {exc}") from exc
        except Exception as exc:
            raise Exception(f"Stream Connection Error: {exc}") from exc

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | str | None = None,
        json: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> RequestResult:
        url = url.strip()
        req_headers = headers or {}
        logger.info(f"Req: {method} {url} | params={params}")

        try:
            response = await self.client.request(
                method=method.upper(),
                url=url,
                params=params,
                data=data,
                json=json,
                files=files,
                headers=req_headers,
                timeout=timeout or self.timeout,
            )

            # 修正问题3：非 stream 请求 httpx 已经读取了 body，无需 await response.aread()
            err_msg = None
            if response.is_error:
                # 尝试直接从已读取的 content 中获取文本
                try:
                    err_msg = response.text
                except Exception as e:
                    logger.warning(f"Failed to get error message from response: {e}")
                    err_msg = f"HTTP {response.status_code}"

            return RequestResult(
                status_code=response.status_code, response=response, error=err_msg
            )

        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTPStatusError: {exc}")
            return RequestResult(
                status_code=exc.response.status_code,
                response=exc.response,
                error=str(exc),
            )
        except httpx.RequestError as exc:
            logger.error(f"RequestError to {url}: {exc}")
            return RequestResult(status_code=0, error=f"Network Error: {exc}")
        except Exception as exc:
            logger.exception(f"Unexpected Error in _request: {exc}")
            return RequestResult(status_code=500, error=f"Internal Error: {exc}")

    async def get(self, url: str, **kwargs) -> RequestResult:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> RequestResult:
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> RequestResult:
        return await self._request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> RequestResult:
        return await self._request("DELETE", url, **kwargs)

    async def download_file(
        self,
        url: str,
        *,
        save_path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        chunk_size: int = 1024 * 64,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> tuple[bool, str]:
        """
        使用封装后的流式上下文下载文件。
        """
        start_time = time.perf_counter()
        logger.info(f"Download file: {url} -> {save_path}")

        try:
            # 1. 使用封装的 _stream_context，不主动抛出异常以便返回 bool
            async with self._stream_context(
                url, method="GET", params=params, headers=headers, timeout=timeout, raise_exception=False
            ) as response:

                # 手动处理错误返回，保持原本的 return False 风格
                if response.is_error:
                    return False, f"HTTP {response.status_code}"

                # 2. 准备文件写入
                total_size = response.headers.get("Content-Length")
                total_size = int(total_size) if total_size else None

                parent_dir = os.path.dirname(save_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)

                downloaded = 0
                # 使用 anyio 异步写入文件
                async with await anyio.Path(save_path).open("wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress:
                            on_progress(downloaded, total_size)

                cost = time.perf_counter() - start_time
                size_mb = downloaded / (1024 * 1024)
                logger.info(f"Download complete: {save_path} | size={size_mb:.2f}MB | cost={cost:.2f}s")
                return True, ""

        except Exception as exc:
            return False, f"Download process failed: {exc}"

    async def stream_request(
        self,
        method: str,
        url: str,
        chunk_size: int = 1024,
        params: dict = None,
        headers: dict = None,
        timeout: int = None
    ) -> AsyncGenerator[bytes, None]:
        """
        通用流式请求，复用 _stream_context
        """
        # 使用封装的上下文，默认抛出异常（符合流式处理的一般逻辑：出错即中断）
        async with self._stream_context(
            method, url, params=params, headers=headers, timeout=timeout, raise_exception=True
        ) as response:
            async for chunk in response.aiter_bytes(chunk_size):
                yield chunk
