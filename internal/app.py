from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from internal.config.load_config import settings
from internal.core.exception import errors
from internal.core.logger import init_logger, logger
from internal.core.signature import init_signature_auth_handler
from internal.core.snowflake import init_snowflake_id_generator
from internal.infra.anyio_task import close_anyio_task_handler, init_anyio_task_handler
from internal.infra.database import close_async_db, init_async_db
from internal.infra.redis import close_async_redis, init_async_redis
from pkg.toolkit.response import error_response


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
    def _record_log_error(tag: str, err_desc: str):
        logger.error(f"{tag}: {err_desc}")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        _record_log_error("Validation Error", repr(exc))
        return error_response(error=errors.BadRequest, message=f"Validation Error: {exc}")


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
    # 初始化日志
    init_logger()
    # 初始化 DB
    init_async_db()
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
    logger.warning("Application is about to close.")
