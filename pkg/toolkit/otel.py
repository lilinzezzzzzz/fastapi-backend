"""
OpenTelemetry 工具模块

提供统一的 Tracer 获取入口和相关辅助函数。
遵循项目规范：pkg/ 作为可复用工具包，避免循环依赖。
"""

from opentelemetry import trace
from opentelemetry.trace import Tracer

# 缓存已创建的 tracer 实例，避免重复创建
_TRACERS: dict[str, Tracer] = {}


def get_tracer(name: str) -> Tracer:
    """
    获取命名 tracer 实例（带缓存）。

    :param name: tracer 名称，建议用模块名如 "otel_demo"
    :return: Tracer 实例
    """
    if name not in _TRACERS:
        _TRACERS[name] = trace.get_tracer(name)
    return _TRACERS[name]


def clear_tracers() -> None:
    """
    清空 tracer 缓存（主要用于测试场景）。
    """
    _TRACERS.clear()


# ==================== 辅助函数 ====================


def get_current_trace_id() -> str | None:
    """
    获取当前 OTel 上下文中的 trace_id（32 位 hex 字符串）。
    如果不存在有效的 span context，返回 None。
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id != 0:
        from opentelemetry.trace import format_trace_id

        return format_trace_id(ctx.trace_id)
    return None


def get_current_span_id() -> str | None:
    """
    获取当前 OTel 上下文中的 span_id（16 位 hex 字符串）。
    如果不存在有效的 span context，返回 None。
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.span_id != 0:
        from opentelemetry.trace import format_span_id

        return format_span_id(ctx.span_id)
    return None
