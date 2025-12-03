"""该目录重要用于定义各种schema"""
from datetime import datetime
from typing import Any, Annotated

from pydantic import GetCoreSchemaHandler, BeforeValidator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core.core_schema import CoreSchema, no_info_plain_validator_function


class FlexibleInt(int):
    """
    灵活的整数类型：
    输入：可以是 int，也可以是数字字符串（如 "123"）。
    输出（后端使用）：int 类型。
    场景：用于处理 Query Parameters 或前端传来的不规范 JSON。
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return no_info_plain_validator_function(cls.validate)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: Any) -> JsonSchemaValue:
        return {"type": "integer", "title": "FlexibleInt",
                "description": "Accepts int or digit string, converts to int"}

    @classmethod
    def validate(cls, v: Any) -> int:
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
        raise ValueError("Must be an integer or numeric string")


class BigIntStr(str):
    """
    大整数安全字符串：
    输入（后端赋值）：可以是超长 int (Snowflake/UUIDv7 int)。
    输出（前端接收）：str 类型。
    场景：用于 Response，防止 JavaScript 丢失精度。
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return no_info_plain_validator_function(cls.validate)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: Any) -> JsonSchemaValue:
        return {
            "type": "string",
            "title": "BigIntStr",
            "description": "Large integer serialized as string to prevent precision loss",
            "example": "115603251198457884"
        }

    @classmethod
    def validate(cls, v: Any) -> str:
        if v is None:
            raise ValueError("Value cannot be None")
        return str(v)


class FlexibleDatetime(datetime):
    """
    灵活的时间类型：
    输入：可以是 datetime 对象，也可以是 ISO 字符串。
    输出（后端使用）：无时区 (naive) 的 datetime 对象。
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return no_info_plain_validator_function(cls.validate)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: Any) -> JsonSchemaValue:
        return {
            "type": "string",
            "format": "date-time",
            "example": "2025-05-07T14:30:00Z"
        }

    @classmethod
    def validate(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v.replace(tzinfo=None)  # 去掉时区
        if isinstance(v, str):
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return dt.replace(tzinfo=None)  # 去掉时区信息
            except ValueError:
                raise ValueError("Must be a valid ISO 8601 datetime string")
        raise ValueError("Must be a datetime or ISO datetime string")
