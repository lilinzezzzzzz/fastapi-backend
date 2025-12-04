from pathlib import Path

from internal.config import BaseConfig, DevelopmentConfig, LocalConfig, ProductionConfig, TestingConfig
from pkg import BASE_DIR, SYS_ENV, SYS_NAMESPACE
from pkg.logger_tool import logger


def init_setting() -> BaseConfig:
    logger.info("Init setting...")
    logger.info(f"Current environment: {SYS_ENV}.")

    # 根据环境变量选择配置
    config_classes_gather = {
        "dev": DevelopmentConfig,
        "test": TestingConfig,
        "prod": ProductionConfig,
        "local": LocalConfig,
    }
    config_class = config_classes_gather.get(SYS_ENV)
    if not config_class:
        raise Exception(f"Invalid APP_ENV value: {SYS_ENV}")

    env_file_path = (BASE_DIR / "configs" / f".env.{SYS_NAMESPACE}").as_posix()
    # 检查env_file_path是否存在
    if not Path(env_file_path).exists():
        raise Exception(f"Env file not found: {env_file_path}")

    logger.info(f"Env file path: {env_file_path}.")
    s = config_class()
    logger.info("Init setting successfully.")
    logger.info("==========================")
    for k, v in s.dict().items():
        logger.info(f"{k}: {v}")
    logger.info(s.sqlalchemy_database_uri)
    logger.info(s.redis_url)
    logger.info("==========================")
    return s


setting: BaseConfig = init_setting()
