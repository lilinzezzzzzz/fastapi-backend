from collections.abc import Callable
from typing import Any

import orjson


def orjson_dumps(
    obj: Any,
    *,
    default: Callable[[Any], Any] | None = None,
    option: int | None = None
) -> str:
    """
    将 Python 对象序列化为 JSON 字符串。

    注意：orjson 原生返回 bytes，此函数将其解码为 utf-8 字符串以适配
    通常需要 str 类型接口的场景（如 Django/Flask 响应）。

    Args:
        obj: 要序列化的 Python 对象。
        default: 可选。当遇到无法序列化的对象时调用的函数。
        option: 可选。orjson 的配置选项掩码（例如 orjson.OPT_INDENT_2）。

    Returns:
        str: 序列化并解码后的 JSON 字符串。
    """
    # orjson.dumps 返回 bytes，这里解码为 str
    return orjson.dumps(obj, default=default, option=option).decode("utf-8")


orjson_loads_types = str | bytes | bytearray | memoryview


def orjson_loads(obj: orjson_loads_types) -> Any:
    """
    将 JSON 数据反序列化为 Python 对象。

    Args:
        obj: JSON 数据，支持 str, bytes, bytearray 或 memoryview。

    Returns:
        Any: 反序列化后的 Python 对象（通常是 dict 或 list）。
    """
    return orjson.loads(obj)
