from typing import Annotated

from pydantic import BaseModel, Field

from internal.schemas import BaseListResponse


class UserLoginReqSchema(BaseModel):
    """用户登录请求"""

    username: str = Field(..., description="用户名", min_length=1, max_length=50)
    password: str = Field(..., description="密码", min_length=6, max_length=100)


class UserRegisterReqSchema(BaseModel):
    """用户注册请求"""

    username: str = Field(..., description="用户名", min_length=1, max_length=50)
    password: str = Field(..., description="密码", min_length=6, max_length=100)
    phone: str | None = Field(None, description="手机号", pattern=r"^1[3-9]\d{9}$")


class UserLoginRespSchema(BaseModel):
    """用户登录响应"""

    user: "UserDetailSchema"
    token: str = Field(..., description="访问令牌")


class UserListReqSchema(BaseModel):
    name: Annotated[..., Field(min_length=1, max_length=20)]


class UserDetailSchema(BaseModel):
    id: int
    name: str
    phone: str


class UserListResponseSchema(BaseListResponse):
    total: int
    items: list[UserDetailSchema]
