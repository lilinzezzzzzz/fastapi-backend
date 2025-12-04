from pathlib import Path
from typing import Type

from internal.config import BaseConfig, DevelopmentConfig, LocalConfig, ProductionConfig, TestingConfig
from pkg import BASE_DIR, SYS_ENV, SYS_NAMESPACE
from pkg.logger_tool import logger


def init_setting() -> BaseConfig:
    """
    加载配置。
    此函数只在模块首次被导入时执行一次。
    """
    logger.info("Init setting...")
    logger.info(f"Current environment: {SYS_ENV}.")

    # 1. 策略模式选择配置类
    config_classes_gather: dict[str, Type[BaseConfig]] = {
        "dev": DevelopmentConfig,
        "test": TestingConfig,
        "prod": ProductionConfig,
        "local": LocalConfig,
    }

    config_class = config_classes_gather.get(SYS_ENV)
    if not config_class:
        raise ValueError(f"Invalid APP_ENV value: {SYS_ENV}")

    # 2. 确定 env 文件路径
    env_file_path = (BASE_DIR / "configs" / f".env.{SYS_NAMESPACE}").as_posix()

    # 3. 检查文件是否存在 (可选，视你的部署策略而定)
    if not Path(env_file_path).exists():
        logger.warning(f"Env file not found: {env_file_path}. Relying on system environment variables.")
    else:
        logger.info(f"Loading env file: {env_file_path}")

    # 4. 实例化配置
    # Pydantic BaseSettings 会自动处理环境变量覆盖逻辑
    # 如果 Config 类内部指定了 env_file，这里直接实例化即可；
    # 也可以显式传参: s = config_class(_env_file=env_file_path)
    s = config_class()

    # 5. 打印关键信息 (注意脱敏)
    logger.info("Init setting successfully.")
    logger.info("==========================")
    for k, v in s.dict().items():
        logger.info(f"{k}: {v}")
    logger.info(s.sqlalchemy_database_uri)
    logger.info(s.redis_url)
    logger.info("==========================")
    return s


# =========================================================
# 单例模式：模块加载时立即执行，生成全局唯一的配置对象
# =========================================================
setting: BaseConfig = init_setting()
