from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Union

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

# JavaScript 安全整数最大值 (2^53 - 1)
JS_MAX_SAFE_INTEGER = 9007199254740991

# ==========================================
# 1. SmartInt (智能整数)
# ==========================================

def _parse_smart_int(v: Any) -> int:
    """
    [输入处理]
    前端传 "123" 或 123，后端统一转为 int 类型，
    以便 Python 内部进行数学运算或数据库存储。
    """
    if isinstance(v, int):
        return v
    try:
        return int(float(str(v))) # 先 float 容错 "123.0" 这种情况
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid integer value: {v}") from e

def _serialize_smart_int(v: int) -> Union[int, str]:
    """
    [输出处理]
    序列化给前端时：
    - 如果数值超过 JS 安全范围，转为字符串 (保护精度)
    - 否则保留为数字 (方便前端计算)
    """
    if abs(v) > JS_MAX_SAFE_INTEGER:
        return str(v)
    return v

SmartInt = Annotated[
    int,  # Python 内部类型始终是 int
    BeforeValidator(_parse_smart_int),
    PlainSerializer(_serialize_smart_int, return_type=Union[int, str], when_used='json'),
    WithJsonSchema({
        "anyOf": [{"type": "integer"}, {"type": "string"}],
        "title": "SmartInt",
        "description": "Int in Python. Auto-converts to string in JSON if > JS safe range.",
        "example": 12345,
    }),
]


# ==========================================
# 2. SmartDecimal (智能浮点数)
# ==========================================

def _parse_smart_decimal(v: Any) -> Decimal:
    """
    [输入处理]
    前端传 string/float，后端统一转为 Decimal 以保证计算精度。
    """
    try:
        if isinstance(v, float):
            return Decimal(str(v)) # float 转 str 再转 Decimal 避免精度丢失
        return Decimal(v)
    except (InvalidOperation, TypeError, ValueError) as e:
        raise ValueError(f"Invalid decimal value: {v}") from e

def _serialize_smart_decimal(v: Decimal) -> Union[float, str]:
    """
    [输出处理]
    - 范围在 -1e15 到 1e15 且小数位 <= 6 位 -> 转 float (前端友好)
    - 否则 -> 转 str (保留高精度)
    """
    # 获取指数 (decimal 的 exponent 为负数表示小数位，例如 0.01 是 -2)
    # 注意：Decimal(10).as_tuple().exponent 是 0
    if -1e15 < v < 1e15 and v.as_tuple().exponent >= -6:
        return float(v)
    return str(v)

SmartDecimal = Annotated[
    Decimal, # Python 内部类型始终是 Decimal
    BeforeValidator(_parse_smart_decimal),
    PlainSerializer(_serialize_smart_decimal, return_type=Union[float, str], when_used='json'),
    WithJsonSchema({
        "anyOf": [{"type": "number"}, {"type": "string"}],
        "title": "SmartDecimal",
        "description": "Decimal in Python. Float in JSON if simple, String if high precision.",
        "example": 12.3456,
    }),
]


# ==========================================
# 3. FlexibleDatetime (保持原逻辑，稍作清理)
# ==========================================
def _validate_flexible_datetime(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, str):
        try:
            # 兼容带 Z 或不带 Z 的 ISO 格式
            return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as e:
            raise ValueError("Invalid ISO 8601 datetime string") from e
    return v

FlexibleDatetime = Annotated[
    datetime,
    BeforeValidator(_validate_flexible_datetime),
    # Pydantic 默认会将 datetime 序列化为 ISO 字符串，通常不需要自定义 Serializer，
    # 除非你需要特定格式
    WithJsonSchema({"type": "string", "format": "date-time", "example": "2025-05-07T14:30:00Z"})
]


# ==========================================
# 4. IntStr (强制字符串 ID)
# ==========================================
# 如果你的 Python 内部业务逻辑确实需要它就是 string，保持原样即可。
# 如果 Python 内部需要 int，但输出需要 string，建议用类似 SmartInt 的逻辑但 serializer 恒定返回 str。

IntStr = Annotated[
    str,
    BeforeValidator(lambda v: str(v)),
    WithJsonSchema({
        "type": "string",
        "title": "IntStr",
        "description": "Force serialization to string",
        "example": "115603251198457884",
    }),
]
