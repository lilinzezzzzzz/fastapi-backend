import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from internal.config.load_config import APP_ENV, setting
from internal.core.exception import global_codes
from internal.core.logger import init_logger
from internal.core.signature import init_signature_auth_handler
from internal.core.snowflake import init_snowflake_id_generator
from internal.infra.anyio_task import close_anyio_task_handler, init_anyio_task_handler
from internal.infra.database import close_db, init_db
from internal.infra.redis import close_redis, init_redis
from pkg.async_logger import logger
from pkg.response import error_response, response_factory


def create_app() -> FastAPI:
    debug = setting.DEBUG
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
        logging.error(f"{tag}: {err_desc}")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        _record_log_error("Validation Error", repr(exc))
        return error_response(error=global_codes.BadRequest, message=f"Validation Error: {exc}")


def register_middleware(app: FastAPI):
    # 6. GZip 中间件：压缩响应，提高传输效率
    from starlette.middleware.gzip import GZipMiddleware

    app.add_middleware(GZipMiddleware)

    # 4. 认证中间件：校验 Token，确保只有合法用户访问 API
    from internal.middleware.auth import ASGIAuthMiddleware

    app.add_middleware(ASGIAuthMiddleware)

    # 2. CORS 中间件：处理跨域请求
    if setting.BACKEND_CORS_ORIGINS:
        from starlette.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_credentials=True,
            allow_origins=setting.BACKEND_CORS_ORIGINS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 1. 日志中间件：记录请求和响应的日志，监控 API 性能和请求流
    from internal.middleware.recorder import ASGIRecordMiddleware

    app.add_middleware(ASGIRecordMiddleware)


# 定义 lifespan 事件处理器
@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Init lifespan...")
    # 检查环境变量
    if APP_ENV not in ["local", "dev", "test", "prod"]:
        raise Exception(f"Invalid ENV: {APP_ENV}")

    cur_pid = os.getpid()
    logger.info(f"Current PID: {cur_pid}")
    # 初始化 DB
    init_db()
    # 初始化 Redis
    init_redis()
    # 初始化签名认证
    init_signature_auth_handler()
    # 初始化 Snowflake ID Generator
    init_snowflake_id_generator()
    # 初始化日志
    init_logger()
    # 初始化 AnyIO Task Manager
    await init_anyio_task_handler()

    logger.info("Application will start.")

    yield

    # 关闭时的清理逻辑
    await close_db()
    await close_redis()
    await close_anyio_task_handler()
    logger.warning("Application is about to close.")
