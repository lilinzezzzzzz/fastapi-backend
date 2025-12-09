from typing import Any

from pydantic import BaseModel


class BaseResponse(BaseModel):
    code: int = 200
    message: str = ""
    data: Any = None


class BaseListResponse(BaseModel):
    code: int = 200
    message: str = ""
    data: list[Any] = []
    page: int = 1
    limit: int = 10
    total: int = 0
