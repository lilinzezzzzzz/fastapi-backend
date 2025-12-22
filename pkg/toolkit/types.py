from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

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
    仅支持整数或纯数字字符串，其他类型返回错误。
    """
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError as e:
            raise ValueError(f"Invalid integer value: {v}") from e
    raise TypeError(f"Expected int or str, got {type(v).__name__}, {v}")


def _serialize_smart_int(v: int) -> int | str:
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
    PlainSerializer(_serialize_smart_int, return_type=int | str, when_used="json"),
    WithJsonSchema(
        {
            "anyOf": [{"type": "integer"}, {"type": "string"}],
            "title": "SmartInt",
            "description": "Int in Python. Auto-converts to string in JSON if > JS safe range.",
            "example": 12345,
        }
    ),
]


# ==========================================
# 2. SmartDecimal (智能浮点数)
# ==========================================


def _parse_smart_decimal(v: Any) -> Decimal:
    """
    [输入处理]
    前端传 string/float，后端统一转为 Decimal 以保证计算精度。
    仅支持 Decimal、int、float、str 类型，其他类型返回错误。
    """
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, str):
        try:
            return Decimal(v)
        except InvalidOperation as e:
            raise ValueError(f"Invalid decimal value: {v}") from e
    raise TypeError(f"Expected Decimal, int, float or str, got {type(v).__name__}")


def _serialize_smart_decimal(v: Decimal) -> float | str:
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
    Decimal,  # Python 内部类型始终是 Decimal
    BeforeValidator(_parse_smart_decimal),
    PlainSerializer(_serialize_smart_decimal, return_type=float | str, when_used="json"),
    WithJsonSchema(
        {
            "anyOf": [{"type": "number"}, {"type": "string"}],
            "title": "SmartDecimal",
            "description": "Decimal in Python. Float in JSON if simple, String if high precision.",
            "example": 12.3456,
        }
    ),
]


# ==========================================
# 3. SmartDatetime (智能时间类型)
# ==========================================


def _parse_smart_datetime(v: Any) -> datetime:
    """
    [输入处理] Input -> Python (Naive UTC datetime)
    1. 接收 ISO 格式字符串 (如 "2023-01-01T12:00:00Z" 或 "2023-01-01T20:00:00+08:00")
    2. 接收 datetime 对象
    3. 统一转换为 UTC 时间，再去除时区信息 (转为 Naive datetime)
    """
    if isinstance(v, datetime):
        # 如果有时区信息，先转换到 UTC，再去除时区信息
        if v.tzinfo is not None:
            v = v.astimezone(UTC)
        return v.replace(tzinfo=None)

    if isinstance(v, str):
        try:
            # 兼容带 Z 或不带 Z 的 ISO 格式
            # (Python 3.11+ 原生支持 Z，这里保留 replace 是为了兼容性更强)
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            # 如果有时区信息，先转换到 UTC，再去除时区信息
            if dt.tzinfo is not None:
                dt = dt.astimezone(UTC)
            return dt.replace(tzinfo=None)
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 datetime string: {v}") from e

    raise ValueError(f"Invalid datetime type: {type(v)}")


def _serialize_smart_datetime(v: datetime) -> str | None:
    """
    [输出处理] Python -> JSON (ISO String)
    将 datetime 对象转为标准的 ISO 8601 字符串格式（UTC 时间）
    - 如果是 naive datetime（无时区），默认视为 UTC
    - 如果带有时区信息，先转换为 UTC
    """
    if v is None:
        return None
    # 如果带有时区信息，先转换为 UTC
    if v.tzinfo is not None:
        v = v.astimezone(UTC)
    else:
        # naive datetime 默认视为 UTC
        v = v.replace(tzinfo=UTC)
    # 返回标准 ISO 格式，例如: "2025-05-07T14:30:00+00:00"
    return v.isoformat()


SmartDatetime = Annotated[
    datetime,  # <--- Python 内部类型明确为 datetime
    BeforeValidator(_parse_smart_datetime),
    PlainSerializer(_serialize_smart_datetime, return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "format": "date-time",
            "example": "2025-05-07T14:30:00",
            "title": "SmartDatetime",
            "description": "Auto-converts ISO string to Naive datetime on input; Serializes to ISO string on output.",
        }
    ),
]
# ==========================================
# 4. IntStr (强制字符串 ID)
# ==========================================
# 如果你的 Python 内部业务逻辑确实需要它就是 string，保持原样即可。
# 如果 Python 内部需要 int，但输出需要 string，建议用类似 SmartInt 的逻辑但 serializer 恒定返回 str。

IntStr = Annotated[
    str,
    BeforeValidator(lambda v: str(v)),
    WithJsonSchema(
        {
            "type": "string",
            "title": "IntStr",
            "description": "Force serialization to string",
            "example": "115603251198457884",
        }
    ),
]


# ==========================================
# 5. LazyProxy (懒加载代理)
# ==========================================


class LazyProxy:
    """
    通用懒加载代理，用于延迟初始化的单例对象。

    解决问题：
    - 模块导入时对象还未初始化 (None)
    - 需要在运行时动态获取实际对象

    用法示例:
        _redis_client: Redis | None = None

        def init_redis():
            global _redis_client
            _redis_client = Redis(...)

        def _get_redis() -> Redis:
            if _redis_client is None:
                raise RuntimeError("Redis not initialized")
            return _redis_client

        redis = LazyProxy(_get_redis)  # 导出代理对象

        # 使用时自动转发到真实对象
        redis.get("key")  # 等价于 _get_redis().get("key")
    """

    __slots__ = ("_getter",)

    def __init__(self, getter: "Callable[[], Any]"):
        object.__setattr__(self, "_getter", getter)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._getter(), name)

    def __repr__(self) -> str:
        try:
            return repr(self._getter())
        except RuntimeError:
            return "<LazyProxy: uninitialized>"
