import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from internal.aps_tasks import apscheduler_manager
from internal.config.setting import setting
from internal.constants import REDIS_KEY_LOCK_PREFIX
from internal.infra.database import init_db, close_db
from internal.infra.default_redis import cache_client, init_redis, close_redis
from pkg import SYS_ENV, SYS_NAMESPACE
from pkg.logger_tool import logger
from pkg.resp_tool import response_factory


def create_app() -> FastAPI:
    debug = setting.DEBUG
    app = FastAPI(
        debug=debug,
        docs_url="/docs" if debug else None,
        redoc_url="/redoc" if debug else None,
        lifespan=lifespan
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
        return response_factory.resp_422(message=f"Validation Error: {exc}")


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


async def start_scheduler(pid: int):
    scheduler_lock_key = f"{REDIS_KEY_LOCK_PREFIX}:scheduler:master"
    # 只有一个 worker 能获得锁，成为 scheduler master
    lock_id = await cache_client.acquire_lock(
        scheduler_lock_key,
        expire_ms=180000,  # 3 分钟, 避免锁死
        timeout_ms=1000,  # 最多等 1 秒获取锁
        retry_interval_ms=200  # 可略调
    )
    if lock_id:
        logger.info(f"Current process {pid} acquired scheduler master lock, starting APScheduler")
        apscheduler_manager.start()
        return True
    else:
        logger.info(f"Current process {pid} did not acquire scheduler master lock, skipping scheduler")
        return False


async def shutdown_scheduler(pid: int):
    logger.info(f"Current process {pid} Shutting down APScheduler...")
    await apscheduler_manager.shutdown()
    logger.info(f"Current process {pid} Shutting down APScheduler successfully")


# 定义 lifespan 事件处理器
@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Init lifespan...")
    # 检查环境变量
    if SYS_ENV not in ["local", "dev", "test", "prod"]:
        raise Exception(f"Invalid ENV: {SYS_ENV}")

    cur_pid = os.getpid()
    logger.info(f"Current PID: {cur_pid}")
    # 初始化 DB
    init_db()
    # 初始化 Redis
    init_redis()

    is_scheduler_master = False
    if SYS_NAMESPACE in ["dev", "test", "canary", "prod"]:
        ...
        # is_scheduler_master = await start_scheduler(cur_pid)
    else:
        # dump_routes_and_middleware(app)
        ...

    logger.info("Check completed, Application will start.")

    yield

    if is_scheduler_master:
        ...
        # await shutdown_scheduler(cur_pid)
    # 关闭时的清理逻辑
    await close_db()
    await close_redis()
    logger.warning("Application is about to close.")
