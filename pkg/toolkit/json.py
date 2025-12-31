from typing import Any

import orjson

# === Configuration ===
# 针对 AI 场景的默认优化选项：
# 1. OPT_SERIALIZE_NUMPY: 原生支持 numpy 数组序列化（RAG/向量必备）
# 2. OPT_NON_STR_KEYS: 允许非字符串键（兼容性）
# 3. OPT_UTC_Z: 强制所有 datetime 使用 UTC 时区（防止时区混乱）
DEFAULT_ORJSON_OPTIONS = orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS | orjson.OPT_UTC_Z

type JsonInputType = str | bytes | bytearray | memoryview


def _strict_default_handler(obj: Any) -> Any:
    """
    默认的 Fallback 处理函数。
    用于捕获无法序列化的类型，防止 orjson 静默输出 null。
    """
    if isinstance(obj, set):
        return list(obj)
    # 可以在此添加针对 AI 平台特有对象的处理，如 PyTorch Tensor
    # if hasattr(obj, "detach") and hasattr(obj, "cpu"):
    #     return obj.detach().cpu().numpy().tolist()

    # 必须显式抛出异常，否则 orjson 会将其视为 None (null)
    raise TypeError(f"Type {type(obj)} is not JSON serializable")


def orjson_dumps(obj: Any, *, default: Any = None, option: int | None = None) -> str:
    """
    高性能 JSON 序列化（输出 str）。

    Args:
        obj: 待序列化对象
        default: 自定义序列化函数。如果不传，使用内置的 _strict_default_handler 增强鲁棒性。
        option: orjson 选项掩码。如果不传，使用针对 AI 优化的默认配置。
    """
    # 优先使用用户传入的 default，否则使用增强的 strict handler
    handler = default if default is not None else _strict_default_handler

    # 合并选项：允许用户传入额外的 option，同时保留默认的基础能力
    final_option = option if option is not None else DEFAULT_ORJSON_OPTIONS

    try:
        # 性能提示：如果下游（如 FastAPI/Starlette）支持直接返回 bytes，
        # 请移除 .decode("utf-8") 并修改返回类型注解，可减少 1 次内存拷贝。
        return orjson.dumps(obj, default=handler, option=final_option).decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"JSON Serialization Failed: {str(e)} - Type: {type(obj)}") from e


def orjson_loads(obj: JsonInputType) -> Any:
    """
    高性能 JSON 反序列化。
    """
    # 性能提示：如果 obj 是 str，orjson 内部会先 encode 转换。
    # 如果数据源本身是 bytes（如 HTTP body），请直接透传 bytes。
    try:
        return orjson.loads(obj)
    except Exception as e:
        raise RuntimeError(f"JSON Deserialization Failed: {str(e)}") from e
