from starlette.datastructures import MutableHeaders
from starlette.types import Scope


class BaseMiddlewareContext:
    """中间件上下文基类，封装从 scope 提取的公共字段。"""

    __slots__ = ("_path", "_method", "_headers")

    def __init__(self, scope: Scope) -> None:
        self._path: str = scope["path"]
        self._method: str = scope.get("method", "GET")
        self._headers = MutableHeaders(scope=scope)

    @property
    def path(self) -> str:
        return self._path

    @property
    def method(self) -> str:
        return self._method

    @property
    def headers(self) -> MutableHeaders:
        return self._headers
