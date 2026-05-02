# AGENTS.md

适用于 `internal/controllers/` 及其子目录。

## 层职责

本层是 HTTP API 入口，负责路由声明、请求接收、依赖注入、认证上下文读取和响应组装。

- `api/`：`/v1` 业务 API。
- `public/`：`/v1/public` 公共 API。
- `internal/`：`/v1/internal` 内部 API。

## 编码约定

- Controller 保持薄层，不承载业务规则、复杂查询、缓存编排或外部服务编排。
- 请求体、响应体使用 `internal/schemas/` 中的 Pydantic v2 model。
- `response_model` 统一使用 `BaseResponse[T]` / `BaseListResponse[T]` 声明响应信封（用于 OpenAPI schema 和响应校验）。
- 实际返回值使用 `pkg.toolkit.response` 中的工厂函数：成功调用 `success_response(data=...)`，分页调用 `success_list_response(data=..., page=..., limit=..., total=...)`，错误调用 `error_response(error, message=..., lang=...)`，Service 只返回业务数据，不关心 envelope。
- 业务逻辑调用 `internal/services/`，不要直接操作 ORM session。
- 需要读当前用户时使用上下文工具，例如 `pkg.toolkit.context.get_user_id()`，不要重新解析 token。
- 业务错误使用 `internal.core.AppException` 和 `internal.core.errors`。
- 路由 prefix、tags、summary 要与现有风格一致。
- 新增公开接口时确认认证中间件白名单或路由前缀是否符合预期。

## 代码最小正确形态

一个合格 Controller 的最小形态：

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from internal.schemas import BaseResponse
from internal.schemas.user import UserDetailSchema
from internal.services.user import UserService, new_user_service
from pkg.toolkit.response import CustomORJSONResponse, success_response

router = APIRouter(prefix="/user", tags=["api user"])

UserServiceDep = Annotated[UserService, Depends(new_user_service)]


@router.get(
    "/{user_id}",
    response_model=BaseResponse[UserDetailSchema],
    summary="获取用户详情",
)
async def get_user(
    user_id: int,
    user_service: UserServiceDep,
) -> CustomORJSONResponse:
    user = await user_service.get_user_detail(user_id=user_id)
    return success_response(data=user)
```

最低要求：

- 只声明路由、参数、依赖和 response model。
- `response_model` 统一使用 `BaseResponse[T]` 或 `BaseListResponse[T]` 包装业务 schema，保持响应信封一致。
- 参数名和 schema 字段名与 API contract 一致。
- 调用一个明确的 Service 方法完成用例，Service 返回业务数据，Controller 负责通过 `success_response` / `success_list_response` / `error_response` 包装响应。
- 直接返回响应工厂函数生成的 `CustomORJSONResponse`，不要手动构造 `BaseResponse` 实例。
- 需要当前用户时只读取上下文，不自行校验 token。

## 禁止事项

- 不要在 handler 中写 SQLAlchemy 查询、Redis 操作或循环内数据库访问。
- 不要在日志中打印完整 token、密码、密钥、连接串或第三方登录凭证。
- 不要绕过统一错误和认证中间件返回临时错误结构。

## 验证重点

- API contract：请求字段、响应字段、状态码、错误码。
- 认证行为：匿名、普通 token、内部签名路径是否符合路由前缀。
- 回归测试优先放在 `tests/api/` 或相关 service 单元测试中。
