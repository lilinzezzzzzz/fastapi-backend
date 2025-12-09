from _decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Annotated, Any

from pydantic import BeforeValidator, WithJsonSchema

JS_MAX_SAFE_INTEGER = 9007199254740991


def _validate_smart_int(v: Any) -> int | str:
    """
    智能整数转换逻辑：
    1. 尝试转为 int (支持字符串输入 "123")
    2. 如果数值绝对值 > JS安全整数范围，强制转为 str (保护雪花ID精度)
    3. 否则保留为 int
    """
    try:
        # 统一转 int，处理 float 或 str 输入
        if isinstance(v, float):
            val = int(v)
        else:
            val = int(str(v))
    except (ValueError, TypeError) as e:
        # 如果无法转数字，抛出 Pydantic 验证错误
        raise ValueError(f"Invalid integer value: {v}") from e

    # 核心保护逻辑：检测雪花算法 ID
    if abs(val) > JS_MAX_SAFE_INTEGER:
        return str(val)

    return val


# ==========================================
# 1. SmartInt (智能整数 - 推荐默认使用)
# ==========================================
SmartInt = Annotated[
    int | str,
    BeforeValidator(_validate_smart_int),
    WithJsonSchema(
        {
            "anyOf": [{"type": "integer"}, {"type": "string"}],
            "title": "SmartInt",
            "description": "Auto-convert to string if integer exceeds JS safe range (2^53-1)",
            "example": 12345,
        }
    ),
]


# ==========================================
# 2. IntStr (强制字符串 ID - 依然保留)
# ==========================================
def _validate_bigint_str(v: Any) -> str:
    """无论输入什么，强制转为字符串"""
    return str(v)


IntStr = Annotated[
    str | int,
    BeforeValidator(_validate_bigint_str),
    WithJsonSchema(
        {
            "type": "string",
            "title": "IntStr",
            "description": "Force serialization to string",
            "example": "115603251198457884",
        }
    ),
]


def _validate_flexible_datetime(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, str):
        try:
            # 兼容带 Z 或不带 Z 的 ISO 格式
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None)
        except ValueError as e:
            raise ValueError("Invalid ISO 8601 datetime string") from e
    return v


# ==========================================
# 3. FlexibleDatetime
# ==========================================

FlexibleDatetime = Annotated[
    datetime | str,
    BeforeValidator(_validate_flexible_datetime),
    WithJsonSchema({"type": "string", "format": "date-time", "example": "2025-05-07T14:30:00Z"}),
]


def _validate_smart_decimal(v: Any) -> float | str:
    """
    智能转换逻辑：
    1. 范围在 -1e15 到 1e15 之间，且小数位精度 >= -6 (最多6位) -> 转 float
    2. 否则 (数值过大 或 精度过高) -> 转 str
    """
    try:
        if isinstance(v, float):
            obj = Decimal(str(v))
        else:
            obj = Decimal(v)
    except (InvalidOperation, TypeError, ValueError) as e:
        raise ValueError(f"Invalid decimal value: {v}") from e

    # 判断范围和精度
    if -1e15 < obj < 1e15 and obj.as_tuple().exponent >= -6:
        return float(obj)

    return str(obj)


# ==========================================
# 4. SmartDecimal (智能浮点数)
# ==========================================

SmartDecimal = Annotated[
    float | str,
    BeforeValidator(_validate_smart_decimal),
    WithJsonSchema(
        {
            "anyOf": [{"type": "number"}, {"type": "string"}],
            "title": "SmartDecimal",
            "description": "Float for standard precision, String for high precision/large numbers",
            "example": 12.3456,
        }
    ),
]
