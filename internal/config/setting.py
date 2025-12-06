from internal.config import BaseConfig, Settings
from pkg import SYS_ENV
from pkg.logger_tool import logger


def init_setting() -> BaseConfig:
    """
    加载配置。
    此函数只在模块首次被导入时执行一次。
    """
    logger.info("Init setting...")
    logger.info(f"Current environment: {SYS_ENV}.")

    # 4. 实例化配置
    s = Settings()
    # 5. 打印关键信息 (注意脱敏)
    logger.info("Init setting successfully.")
    logger.info("==========================")
    for k, v in s.model_dump().items():
        logger.info(f"{k}: {v}")
    logger.info(s.sqlalchemy_database_uri)
    logger.info(s.redis_url)
    logger.info("==========================")
    return s


# =========================================================
# 单例模式：模块加载时立即执行，生成全局唯一的配置对象
# =========================================================
setting: BaseConfig = init_setting()
