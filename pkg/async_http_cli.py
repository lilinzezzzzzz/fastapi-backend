import mimetypes
import os
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import anyio
import httpx

from pkg.async_logger import logger


@dataclass
class RequestResult:
    status_code: int = 0
    response: httpx.Response | None = None
    error: str | None = None
    _json: Any = field(init=False, default=None)

    @property
    def success(self) -> bool:
        """判断请求是否逻辑成功 (2xx 且无异常错误)"""
        return self.error is None and 200 <= self.status_code < 300

    def json(self) -> Any:
        """安全的获取 JSON，带缓存"""
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

    def raise_for_status(self):
        """如果请求失败，主动抛出异常，类似 httpx 原生行为"""
        if not self.success:
            raise httpx.HTTPStatusError(
                message=f"Request failed with {self.status_code}: {self.error}",
                request=self.response.request if self.response else None,
                response=self.response,
            )


class AsyncHttpClient:
    """
    基于 httpx 封装的单例/长连接客户端。
    建议配合 async with 使用，或全局初始化一次。
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
        # 初始化一个长效的 client，复用 TCP 连接
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
        """关闭客户端连接池"""
        await self.client.aclose()

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
        """
        核心请求方法，统一异常捕获
        """
        url = url.strip()
        # 合并 Header 逻辑：files 上传时通常不需要手动设 Content-Type，httpx 会自动处理 boundary
        req_headers = headers or {}

        # 记录日志
        logger.info(f"Req: {method} {url} | params={params}")

        try:
            # 复用 self.client
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

            # 尝试捕获 HTTP 协议层面的错误状态 (如 404, 500)
            # 注意：这里我们不直接 raise，而是封装到 Result 中，由调用方决定
            err_msg = None
            if response.is_error:
                try:
                    # 尝试读取错误体
                    await response.aread()
                    err_msg = response.text
                except Exception as e:
                    err_msg = f"HTTP {response.status_code}, error: {e}"

            return RequestResult(
                status_code=response.status_code, response=response, error=err_msg
            )

        except httpx.HTTPStatusError as exc:
            # 这种情况通常由 response.raise_for_status() 触发，
            # 但上面的逻辑没有调用它，所以主要捕获 connect error 等
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

    async def download_bytes(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> tuple[str, bytes | None, str]:
        """
        下载小文件。如果是大文件，建议单独写一个 stream_download 方法。
        返回: (filename, content_bytes, content_type)
        """
        start_time = time.perf_counter()
        result = await self.get(url, params=params, timeout=timeout)

        if not result.success or not result.response:
            logger.error(f"Download failed: {result.error}")
            return "", None, ""

        cost = time.perf_counter() - start_time
        logger.info(f"Download success: {url} | cost={cost:.2f}s")

        # 解析文件名
        parsed = urlparse(url)
        file_name = os.path.basename(parsed.path) or "download_file"

        # 解析 Content-Type
        content_type = result.response.headers.get("Content-Type", "")
        if not content_type:
            ct, _ = mimetypes.guess_type(file_name)
            content_type = ct or "application/octet-stream"

        return file_name, result.response.content, content_type

    async def download_file(
        self,
        url: str,
        save_path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        chunk_size: int = 1024 * 64,  # 64KB
        on_progress: Any | None = None,  # Callable[[int, int | None], None]
    ) -> tuple[bool, str]:
        """
        流式下载大文件，边下载边写入磁盘，避免内存溢出。

        Args:
            url: 下载地址
            save_path: 保存路径
            params: URL 查询参数
            headers: 请求头
            timeout: 超时时间
            chunk_size: 分块大小（默认 64KB）
            on_progress: 进度回调 (downloaded_bytes, total_bytes)

        Returns:
            (success, error_message)
        """
        start_time = time.perf_counter()
        logger.info(f"Download file: {url} -> {save_path}")

        try:
            async with self.client.stream(
                "GET",
                url,
                params=params,
                headers=headers,
                timeout=timeout or self.timeout,
            ) as response:
                if response.is_error:
                    err_msg = f"HTTP {response.status_code}"
                    logger.error(f"Download failed: {err_msg}")
                    return False, err_msg

                # 获取文件总大小（可能为 None）
                total_size = response.headers.get("Content-Length")
                total_size = int(total_size) if total_size else None

                # 确保父目录存在
                parent_dir = os.path.dirname(save_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)

                downloaded = 0
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

        except httpx.HTTPStatusError as exc:
            err_msg = f"HTTPStatusError: {exc.response.status_code}"
            logger.error(err_msg)
            return False, err_msg
        except httpx.RequestError as exc:
            err_msg = f"Network Error: {exc}"
            logger.error(err_msg)
            return False, err_msg
        except Exception as exc:
            err_msg = f"Download Error: {exc}"
            logger.exception(err_msg)
            return False, err_msg

    async def stream_request(
        self, method: str, url: str, chunk_size: int = 1024, **kwargs
    ) -> AsyncGenerator[bytes, None]:
        """
        通用流式请求
        """
        logger.info(f"Stream Req: {method} {url}")

        try:
            # stream 需要特殊的上下文管理
            async with self.client.stream(method, url, **kwargs) as response:
                response.raise_for_status()
                logger.info(f"Stream Start: {response.status_code}")
                async for chunk in response.aiter_bytes(chunk_size):
                    yield chunk
        except httpx.HTTPStatusError as exc:
            logger.error(f"Stream HTTPStatusError: {exc.response.status_code}")
            # 这里如果不 yield 出错误信息，调用方可能直接断开
            raise exc
        except Exception as exc:
            logger.error(f"Stream Error: {exc}")
            raise exc


# 使用示例
"""
async def main():
    # 方式1：上下文管理器（推荐，自动关闭连接）
    async with HTTPXClient() as client:
        res = await client.get("https://httpbin.org/get")
        if res.success:
            print(res.json())
        else:
            print("Error:", res.error)

    # 方式2：全局单例（FastAPI常用）
    # global_client = HTTPXClient()
    # ... on_shutdown: await global_client.close()
"""
