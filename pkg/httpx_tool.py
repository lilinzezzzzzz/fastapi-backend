import mimetypes
import os
import time
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlparse

import httpx

from pkg.loguru_logger import logger


class HTTPxResult:
    def __init__(
            self, *, status_code: int, response: httpx.Response | None, error: str | None
    ):
        self._status_code: int = status_code
        self._response = response
        self._error = error

    @property
    def status_code(self) -> int:
        return self._status_code

    @property
    def response(self) -> httpx.Response | None:
        return self._response

    @property
    def error(self) -> str | None:
        return self._error

    def resp_json(self) -> dict:
        if not isinstance(self._response, httpx.Response):
            raise ValueError(f"response is not httpx.Response, is={self._response}")

        return self._response.json()

    def __repr__(self) -> str:
        return f"HTTPxResult(status_code={self.status_code}, response={self.response}, error={self.error})"


class HTTPXClient:
    """
    基于 httpx 封装的工具类，GET/POST/PUT/DELETE 均接收完整 URL,
    自动处理 JSON、form-data、文件上传,以及错误转换为 HTTPException。
    """

    def __init__(self, timeout: int = 60, headers: dict[str, str] | None = None):
        """
        :param timeout: 请求超时时间，默认 10 秒
        :param headers: 公共请求头，默认 {"Content-Type": 'application/json'}
        """
        self.timeout = timeout
        self.headers = headers or {"Content-Type": "application/json"}

    async def _stream(
            self,
            method: str,
            *,
            url: str,
            params: dict[str, Any] | None = None,
            data: dict[str, Any] | None = None,
            json: dict[str, Any] | None = None,
            files: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int | None = None,
            chunk_size: int = 1024,
    ) -> AsyncGenerator[bytes, None]:
        url = url.strip()
        logger.info(
            f"Stream Requesting: method={method}, url={url}, params={params}, json={json}, data={data}"
        )

        combined_headers = {
            **self.headers,
            **(headers or {}),
            "Content-Type": "application/json",
        }
        if files:
            combined_headers.pop("Content-Type", None)

        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                async with client.stream(
                        method=method.upper(),
                        url=url,
                        params=params,
                        data=None if files else data,
                        json=None if files else json,
                        files=files,
                        headers=combined_headers,
                ) as response:
                    response.raise_for_status()
                    logger.info(
                        f"Stream Response: success, status_code={response.status_code}"
                    )
                    async for chunk in response.aiter_bytes(chunk_size):
                        yield chunk
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_bytes = await response.aread()
                err_text = err_bytes.decode(errors="ignore")
                logger.error(
                    f"HTTPStatusError, status_code={status_code}, err={err_text}"
                )
            except Exception as e:
                logger.error("HTTPStatusError, content read failed")
                raise e

            raise exc
        except httpx.RequestError as exc:
            logger.error(f"_stream HTTPxRequestError")
            raise exc
        except Exception as exc:
            logger.error(f"_stream UnexpectedError")
            raise exc

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
            to_return: bool = False,
    ) -> tuple[int | None, httpx.Response | None, str | None]:
        """
        :param method: HTTP 方法
        :param url: 完整 URL
        :param params: 查询参数
        :param data: form-data 或普通 body
        :param json: JSON body
        :param files: 文件上传 dict
        :param headers: 单次请求头
        :param timeout: 单次请求超时
        :return: httpx.Response
        """
        url = url.strip()
        logger.info(
            f"Requesting: method={method}, url={url}, params={params}, json={json}, data={data}"
        )

        combined_headers = {
            **self.headers,
            **(headers or {}),
            "Content-Type": "application/json",
        }
        if files:
            combined_headers.pop("Content-Type", None)

        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                response: httpx.Response = await client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    data=None if files else data,
                    json=None if files else json,
                    files=files,
                    headers=combined_headers,
                )
                response.raise_for_status()
                return response.status_code, response, None
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                resp_content = exc.response.json()
            except Exception as e:
                logger.error(f"parse exc.response.json() failed, err={e}")
                resp_content = exc.response.text

            logger.error(
                f"_request HTTPxStatusError, status_code={status_code}, err={exc}, response={resp_content}"
            )

            if to_return:
                return status_code, None, resp_content

            raise exc
        except httpx.RequestError as exc:
            logger.error(f"_request HTTPxRequestError")

            if to_return:
                return None, None, str(exc)

            raise exc
        except Exception as exc:
            logger.error(f"_request UnexpectedError")

            if to_return:
                return None, None, str(exc)

            raise exc

    async def get(
            self,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int | None = None,
            to_return: bool = False,
    ) -> tuple[int | None, dict | None, str | None]:
        status_code, httpx_response, error_message = await self._request(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            to_return=to_return,
        )

        resp = (
            httpx_response.json()
            if isinstance(httpx_response, httpx.Response)
            else httpx_response
        )

        return status_code, resp, error_message

    async def post(
            self,
            url: str,
            *,
            json: dict[str, Any] | None = None,
            data: dict[str, Any] | str | None = None,
            files: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int | None = None,
            to_return: bool = False,
    ) -> tuple[int | None, dict | None, str | None]:
        status_code, httpx_response, error_message = await self._request(
            "POST",
            url,
            json=json,
            data=data,
            files=files,
            headers=headers,
            timeout=timeout,
            to_return=to_return,
        )

        resp = (
            httpx_response.json()
            if isinstance(httpx_response, httpx.Response)
            else httpx_response
        )

        return status_code, resp, error_message

    async def put(
            self,
            url: str,
            *,
            json: dict[str, Any] | None = None,
            data: dict[str, Any] | str | None = None,
            files: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int | None = None,
            to_return: bool = False,
    ) -> tuple[int | None, dict | None, str | None]:
        status_code, httpx_response, error_message = await self._request(
            "PUT",
            url,
            json=json,
            data=data,
            files=files,
            headers=headers,
            timeout=timeout,
            to_return=to_return,
        )

        resp = (
            httpx_response.json()
            if isinstance(httpx_response, httpx.Response)
            else httpx_response
        )

        return status_code, resp, error_message

    async def delete(
            self,
            url: str,
            *,
            json: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int | None = None,
            to_return: bool = False,
    ) -> tuple[int | None, dict | None, str | None]:
        status_code, httpx_response, error_message = await self._request(
            "DELETE",
            url,
            json=json,
            headers=headers,
            timeout=timeout,
            to_return=to_return,
        )

        resp = (
            httpx_response.json()
            if isinstance(httpx_response, httpx.Response)
            else httpx_response
        )

        return status_code, resp, error_message

    async def download_bytes(
            self,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int | None = None,
            to_return: bool = False,
    ) -> Any:
        download_start = time.perf_counter()
        # 走原来的 _request 拿到完整 response
        status_code, httpx_response, error_message = await self._request(
            method="GET",
            url=url,
            params=params,
            headers=headers,
            timeout=timeout,
            to_return=to_return,
        )

        if not isinstance(httpx_response, httpx.Response):
            return status_code, None, error_message

        logger.info(f"download {url} cost={time.perf_counter() - download_start:.2f}s")
        # 2. 从 URL 解析文件名
        parsed = urlparse(url)
        file_name = os.path.basename(parsed.path) or "download"

        # 3. 优先从 Content-Type 头取
        content_type = httpx_response.headers.get("Content-Type")
        if not content_type:
            # 再根据后缀猜一次
            ct, _ = mimetypes.guess_type(file_name)
            content_type = ct or "application/octet-stream"

        return file_name, httpx_response.content, content_type

    async def stream_get(
            self,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int | None = None,
            chunk_size: int = 1024,
    ) -> AsyncGenerator[bytes, None]:
        """
        流式GET请求
        """
        async for chunk in self._stream(
                "GET",
                url=url,
                params=params,
                headers=headers,
                timeout=timeout,
                chunk_size=chunk_size,
        ):
            yield chunk

    async def stream_post(
            self,
            url: str,
            *,
            json: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int | None = None,
            chunk_size: int = 1024,
    ) -> AsyncGenerator[bytes, None]:
        """
        流式POST请求
        """
        async for chunk in self._stream(
                "POST",
                url=url,
                json=json,
                headers=headers,
                timeout=timeout,
                chunk_size=chunk_size,
        ):
            yield chunk
