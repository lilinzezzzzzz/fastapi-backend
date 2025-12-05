from typing import Annotated

from pydantic import Field, BaseModel

from internal.schemas import BaseListResponse


class UserListReqSchema(BaseModel):
    name: Annotated[..., Field(min_length=1, max_length=20)]


class UserDetailSchema(BaseModel):
    id: int
    name: str
    phone: str


class UserListResponseSchema(BaseListResponse):
    total: int
    items: list[UserDetailSchema]
