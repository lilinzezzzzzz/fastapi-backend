import datetime
from decimal import Decimal
from typing import Any, TypeAlias

import orjson

# === Configuration ===
# 综合了 AI 场景与 Web 响应的最佳实践选项：
# 1. OPT_SERIALIZE_NUMPY: 原生支持 numpy (AI 核心)
# 2. OPT_SERIALIZE_UUID: 原生支持 UUID
# 3. OPT_NON_STR_KEYS: 允许非字符串键 (兼容性)
# 4. OPT_UTC_Z / OPT_NAIVE_UTC: 强制 UTC 时区，统一时间标准
# 5. OPT_OMIT_MICROSECONDS: 减少输出体积
DEFAULT_ORJSON_OPTIONS = (
    orjson.OPT_SERIALIZE_NUMPY
    | orjson.OPT_SERIALIZE_UUID
    | orjson.OPT_NAIVE_UTC
    | orjson.OPT_UTC_Z
    | orjson.OPT_OMIT_MICROSECONDS
    | orjson.OPT_NON_STR_KEYS
)

type JsonInputType = str | bytes | bytearray | memoryview


def _enhanced_default_handler(obj: Any) -> Any:
    """
    增强版 Fallback 处理函数。
    集中处理 orjson 原生不支持的类型，确保系统各处序列化行为一致。
    """
    # 1. 处理小数：兼顾精度与前端兼容性
    if isinstance(obj, Decimal):
        # 如果是小数且在 JS 安全整数/浮点数范围内(-1e15 ~ 1e15)且精度不过高，转 float
        # 否则转 str 避免前端精度丢失
        if -1e15 < obj < 1e15 and obj.as_tuple().exponent >= -6:
            return float(obj)
        return str(obj)

    # 2. 处理二进制：尝试解码，避免直接崩溃
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "ignore")

    # 3. 处理时间间隔
    if isinstance(obj, datetime.timedelta):
        return obj.total_seconds()

    # 4. 处理集合
    if isinstance(obj, (set, frozenset)):
        return list(obj)

    # 5. 必须显式抛出异常
    raise TypeError(f"Type {type(obj)} is not JSON serializable")


def orjson_dumps_bytes(obj: Any, *, default: Any = None, option: int | None = None) -> bytes:
    """
    高性能 JSON 序列化（直接返回 bytes）。

    最佳场景：
    - HTTP Response (Starlette/FastAPI)
    - 写入 Redis/消息队列
    - 存入文件
    """
    handler = default if default is not None else _enhanced_default_handler
    final_option = option if option is not None else DEFAULT_ORJSON_OPTIONS

    try:
        return orjson.dumps(obj, default=handler, option=final_option)
    except Exception as e:
        # 包装异常，提供更清晰的上下文
        raise ValueError(f"JSON Serialization Failed: {str(e)} - Type: {type(obj)}") from e


def orjson_dumps(obj: Any, *, default: Any = None, option: int | None = None) -> str:
    """
    高性能 JSON 序列化（返回 str）。

    最佳场景：
    - 需要字符串操作的日志记录
    - 必须返回 str 接口的旧系统兼容
    """
    # 直接复用 bytes 函数并解码，逻辑收敛
    return orjson_dumps_bytes(obj, default=default, option=option).decode("utf-8")


def orjson_loads(obj: JsonInputType) -> Any:
    """
    高性能 JSON 反序列化。
    """
    try:
        return orjson.loads(obj)
    except Exception as e:
        raise ValueError(f"JSON Deserialization Failed: {str(e)}") from e
