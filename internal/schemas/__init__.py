from pydantic import BaseModel


class BaseResponse[T](BaseModel):
    """基础响应模型

    用法:
        # 定义响应schema
        class UserInfo(BaseModel):
            id: int
            name: str

        # 在controller中使用
        @router.get("/user", response_model=BaseResponse[UserInfo])
        async def get_user():
            return BaseResponse(
                code=200,
                message="success",
                data=UserInfo(id=1, name="张三")
            )

        # 错误响应
        return BaseResponse(code=400, message="参数错误", data=None)
    """
    code: int = 200
    message: str = ""
    data: T | None = None


class BaseListResponse[T](BaseModel):
    """基础列表响应模型

    用法:
        # 定义列表项schema
        class UserInfo(BaseModel):
            id: int
            name: str

        # 在controller中使用
        @router.get("/users", response_model=BaseListResponse[UserInfo])
        async def list_users(page: int = 1, limit: int = 10):
            users = [UserInfo(id=1, name="张三"), UserInfo(id=2, name="李四")]
            return BaseListResponse(
                code=200,
                message="success",
                data=users,
                page=page,
                limit=limit,
                total=100
            )
    """
    code: int = 200
    message: str = ""
    data: list[T] = []
    page: int = 1
    limit: int = 10
    total: int = 10
