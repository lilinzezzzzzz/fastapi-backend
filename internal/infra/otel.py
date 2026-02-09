"""
OpenTelemetry 基础设施模块

负责 OTel TracerProvider/LoggerProvider 的初始化、导出器配置、自动插桩，
以及与现有 loguru 日志系统的桥接辅助函数。
"""

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from pkg.logger import logger

# 全局标记
_otel_initialized = False
_tracer_provider: TracerProvider | None = None
_logger_provider: LoggerProvider | None = None


def init_otel(
    *,
    service_name: str = "fastapi-backend",
    service_version: str = "0.1.0",
    environment: str = "dev",
    otlp_endpoint: str = "",
    console_export: bool = True,
    logs_enabled: bool = True,
) -> None:
    """
    初始化 OpenTelemetry TracerProvider/LoggerProvider 及导出器。

    :param service_name: 服务名称
    :param service_version: 服务版本
    :param environment: 部署环境
    :param otlp_endpoint: OTLP HTTP 导出端点，为空则不启用
    :param console_export: 是否启用 Console 导出（开发调试用）
    :param logs_enabled: 是否启用 Logs 桥接（将 loguru 日志转发到 OTel）
    """
    global _otel_initialized, _tracer_provider, _logger_provider

    if _otel_initialized:
        logger.info("OpenTelemetry already initialized, skipping.")
        return

    # 1. 配置 Resource
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": environment,
        }
    )

    # 2. 创建 TracerProvider
    _tracer_provider = TracerProvider(resource=resource)

    # 3. 添加 Console 导出器（开发调试可即时看到 span）
    if console_export:
        console_processor = BatchSpanProcessor(ConsoleSpanExporter())
        _tracer_provider.add_span_processor(console_processor)
        logger.info("OpenTelemetry: ConsoleSpanExporter enabled.")

    # 4. 添加 OTLP HTTP 导出器（对接 Jaeger/Tempo 等后端）
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            otlp_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            _tracer_provider.add_span_processor(otlp_processor)
            logger.info(f"OpenTelemetry: OTLPSpanExporter enabled, endpoint={otlp_endpoint}")
        except Exception as e:
            logger.error(f"OpenTelemetry: Failed to initialize OTLPSpanExporter: {e}")

    # 5. 设置为全局 TracerProvider
    trace.set_tracer_provider(_tracer_provider)

    # 6. 初始化 LoggerProvider（Logs Bridge）
    if logs_enabled:
        _init_logger_provider(resource, console_export, otlp_endpoint)

    # 7. 自动插桩
    _setup_auto_instrumentation()

    _otel_initialized = True
    logger.info(
        f"OpenTelemetry initialized. service={service_name}, version={service_version}, env={environment}, logs_enabled={logs_enabled}"
    )


def instrument_fastapi_app(app) -> None:
    """
    对已创建的 FastAPI 应用实例进行 OTel 插桩。

    必须在 lifespan 中、init_otel() 之后调用，
    此时添加的 OpenTelemetryMiddleware 会成为最外层中间件（最后添加 = 最先执行），
    确保在 ASGIRecordMiddleware 之前创建 span context。

    :param app: FastAPI 应用实例
    """
    if not _otel_initialized:
        logger.warning("OpenTelemetry not initialized, skipping FastAPI app instrumentation.")
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry: FastAPI app instrumented (instance-level).")
    except Exception as e:
        logger.warning(f"OpenTelemetry: Failed to instrument FastAPI app: {e}")


def _init_logger_provider(resource: Resource, console_export: bool, otlp_endpoint: str) -> None:
    """
    初始化 LoggerProvider，用于接收 loguru 转发的日志。

    :param resource: OTel Resource
    :param console_export: 是否启用 Console 导出
    :param otlp_endpoint: OTLP 端点地址
    """
    global _logger_provider

    # 创建 LoggerProvider
    _logger_provider = LoggerProvider(resource=resource)

    # 添加 Console Log Exporter
    if console_export:
        console_log_exporter = ConsoleLogExporter()
        _logger_provider.add_log_record_processor(BatchLogRecordProcessor(console_log_exporter))
        logger.info("OpenTelemetry: ConsoleLogExporter enabled for logs.")

    # 添加 OTLP Log Exporter
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

            otlp_log_exporter = OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs")
            _logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_log_exporter))
            logger.info(f"OpenTelemetry: OTLPLogExporter enabled, endpoint={otlp_endpoint}/v1/logs")
        except Exception as e:
            logger.error(f"OpenTelemetry: Failed to initialize OTLPLogExporter: {e}")

    # 设置为全局 LoggerProvider
    set_logger_provider(_logger_provider)


def _setup_auto_instrumentation() -> None:
    """
    配置自动插桩（httpx、SQLAlchemy、Redis 等库级别的埋点）。

    注意：FastAPI 插桩不在此处进行，因为需要对已创建的 app 实例调用
    instrument_app()，由 instrument_fastapi_app() 单独处理。
    """

    # httpx 自动插桩
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.info("OpenTelemetry: HTTPX auto-instrumentation enabled.")
    except Exception as e:
        logger.warning(f"OpenTelemetry: Failed to instrument HTTPX: {e}")

    # Redis 自动插桩
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.info("OpenTelemetry: Redis auto-instrumentation enabled.")
    except Exception as e:
        logger.warning(f"OpenTelemetry: Failed to instrument Redis: {e}")

    # SQLAlchemy 自动插桩
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
        logger.info("OpenTelemetry: SQLAlchemy auto-instrumentation enabled.")
    except Exception as e:
        logger.warning(f"OpenTelemetry: Failed to instrument SQLAlchemy: {e}")


async def shutdown_otel() -> None:
    """关闭 OpenTelemetry，刷新并清理资源"""
    global _otel_initialized, _tracer_provider, _logger_provider

    if _logger_provider is not None:
        _logger_provider.shutdown()
        logger.warning("OpenTelemetry LoggerProvider shut down.")

    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        logger.warning("OpenTelemetry TracerProvider shut down.")

    _tracer_provider = None
    _logger_provider = None
    _otel_initialized = False


def is_otel_enabled() -> bool:
    """检查 OTel 是否已初始化"""
    return _otel_initialized


def get_otel_logging_handler() -> LoggingHandler | None:
    """
    获取 OTel LoggingHandler，用于桥接 loguru 日志。

    :return: LoggingHandler 实例，如果 Logs 未启用则返回 None
    """
    if not _otel_initialized or _logger_provider is None:
        return None
    return LoggingHandler(logger_provider=_logger_provider)
