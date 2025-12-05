from typing import Annotated, Union, Any
from datetime import datetime
from pydantic import BeforeValidator, WithJsonSchema, BaseModel


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


# ==========================================
# 1. FlexibleInt
# ==========================================
def _validate_flexible_int(v: Any) -> int:
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return v


# 定义：最终类型是 int，但在验证前执行转换，且 JSON Schema 显示为 integer
FlexibleInt = Annotated[
    int,
    BeforeValidator(_validate_flexible_int),
    WithJsonSchema({"type": "integer", "title": "FlexibleInt", "description": "Accepts int or digit string"})
]


# ==========================================
# 2. BigIntStr (原 StringId)
# ==========================================
def _validate_bigint_str(v: Any) -> str:
    # 核心逻辑：无论输入什么，强制转为字符串
    return str(v)


# 定义：最终类型是 str，但在验证前执行转换，且允许输入 Union[str, int]
BigIntStr = Annotated[
    Union[str, int],  # 关键点：这里告诉 IDE，输入 int 也是合法的！
    BeforeValidator(_validate_bigint_str),
    WithJsonSchema({
        "type": "string",
        "title": "BigIntStr",
        "description": "Large integer serialized as string",
        "example": "115603251198457884"
    })
]


# ==========================================
# 3. FlexibleDatetime
# ==========================================
def _validate_flexible_datetime(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, str):
        try:
            # 兼容带 Z 或不带 Z 的 ISO 格式
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None)
        except ValueError:
            raise ValueError("Invalid ISO 8601 datetime string")
    return v


FlexibleDatetime = Annotated[
    Union[datetime, str],
    BeforeValidator(_validate_flexible_datetime),
    WithJsonSchema({"type": "string", "format": "date-time", "example": "2025-05-07T14:30:00Z"})
]
