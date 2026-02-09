from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from internal.config import init_settings, settings
from internal.infra.database import close_async_db, init_async_db
from internal.infra.otel import init_otel, instrument_fastapi_app, shutdown_otel
from internal.infra.redis import close_async_redis, init_async_redis
from internal.utils.anyio_task import close_anyio_task_handler, init_anyio_task_handler
from internal.utils.signature import init_signature_auth_handler
from internal.utils.snowflake import init_snowflake_id_generator
from pkg.logger import init_logger, logger


def create_app() -> FastAPI:
    debug = settings.DEBUG
    app = FastAPI(
        debug=debug,
        docs_url="/docs" if debug else None,
        redoc_url="/redoc" if debug else None,
        lifespan=lifespan,
    )

    register_router(app)
    register_exception(app)
    register_middleware(app)

    return app


def register_router(app: FastAPI):
    from internal.controllers import web

    app.include_router(web.router)
    from internal.controllers import internalapi

    app.include_router(internalapi.router)
    from internal.controllers import publicapi

    app.include_router(publicapi.router)
    from internal.controllers import serviceapi

    app.include_router(serviceapi.router)


def register_exception(app: FastAPI):
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        # 重新抛出异常，让外层中间件统一处理
        raise exc


def register_middleware(app: FastAPI):
    # 6. GZip 中间件：压缩响应，提高传输效率
    from starlette.middleware.gzip import GZipMiddleware

    app.add_middleware(GZipMiddleware)

    # 4. 认证中间件：校验 Token，确保只有合法用户访问 API
    from internal.middlewares.auth import ASGIAuthMiddleware

    app.add_middleware(ASGIAuthMiddleware)

    # 2. CORS 中间件：处理跨域请求
    if settings.BACKEND_CORS_ORIGINS:
        from starlette.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_credentials=True,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 1. 日志中间件：记录请求和响应的日志，监控 API 性能和请求流
    from internal.middlewares import ASGIRecordMiddleware

    app.add_middleware(ASGIRecordMiddleware)


# 定义 lifespan 事件处理器
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 初始化配置（必须最先执行）
    init_settings()

    # 初始化日志（使用配置中的格式）
    init_logger(log_format=settings.LOG_FORMAT, enable_otel_bridge=settings.OTEL_ENABLED)

    # 初始化 OpenTelemetry（在日志之后，以便 OTel 初始化日志能正常输出）
    if settings.OTEL_ENABLED:
        init_otel(
            service_name=settings.OTEL_SERVICE_NAME,
            environment=settings.APP_ENV,
            otlp_endpoint=settings.OTEL_OTLP_ENDPOINT,
            console_export=settings.OTEL_CONSOLE_EXPORT,
            logs_enabled=True,  # 启用 Logs 桥接
        )
        # 对已创建的 app 实例插桩，此时添加的 OpenTelemetryMiddleware
        # 会成为最外层中间件，在 ASGIRecordMiddleware 之前创建 span context
        instrument_fastapi_app(_app)

    # 初始化 DB（使用配置中的 echo）
    init_async_db(echo=settings.DB_ECHO)
    # 初始化 Redis
    init_async_redis()
    # 初始化签名认证
    init_signature_auth_handler()
    # 初始化 Snowflake ID Generator
    init_snowflake_id_generator()
    # 初始化 AnyIO Task Manager
    await init_anyio_task_handler()

    logger.info("lifespan init completed, Application will start.")

    yield

    # 关闭时的清理逻辑
    await close_async_db()
    await close_async_redis()
    await close_anyio_task_handler()
    await shutdown_otel()
    logger.warning("Application is about to close.")
