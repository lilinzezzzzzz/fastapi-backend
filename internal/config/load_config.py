import os
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pkg import SYS_ENV, BASE_DIR
from pkg.logger_tool import logger


class BaseConfig(BaseSettings):
    """基础配置类，定义所有环境共享的配置项"""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量
    )

    # 基础配置
    DEBUG: bool
    SECRET_KEY: SecretStr

    # JWT 配置
    JWT_ALGORITHM: str

    # CORS 配置
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # MySQL 配置
    MYSQL_USERNAME: str
    MYSQL_PASSWORD: SecretStr
    MYSQL_HOST: str
    MYSQL_PORT: int
    MYSQL_DATABASE: str

    # Redis 配置
    REDIS_HOST: str
    REDIS_PASSWORD: SecretStr
    REDIS_DB: int
    REDIS_PORT: int

    # Token 过期时间（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        password = self.MYSQL_PASSWORD.get_secret_value()
        return f"mysql+aiomysql://{quote_plus(self.MYSQL_USERNAME)}:{quote_plus(password)}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_echo(self) -> bool:
        return self.DEBUG  # 开发环境启用 SQLAlchemy 日志

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        password = self.REDIS_PASSWORD.get_secret_value()
        if password == "":
            return f"redis://{quote_plus(self.REDIS_HOST)}:{self.REDIS_PORT}/{self.REDIS_DB}"
        else:
            return f"redis://:{quote_plus(password)}@{quote_plus(self.REDIS_HOST)}:{self.REDIS_PORT}/{self.REDIS_DB}"


# 配置文件路径
ENV_FILE_PATH: Path = BASE_DIR / "configs" / f".env.{os.getenv('APP_ENV', 'local')}"


class Settings(BaseConfig):
    # 自动根据环境变量 APP_ENV 加载对应的 .env 文件
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=ENV_FILE_PATH.as_posix(),
        env_file_encoding="utf-8",
        extra="ignore"
    )


def init_setting() -> Settings:
    """
    加载配置。
    此函数只在模块首次被导入时执行一次。
    """
    logger.info("Init setting...")
    logger.info(f"Current environment: {SYS_ENV}.")

    # 检查配置文件是否存在
    if not ENV_FILE_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {ENV_FILE_PATH}")

    # 实例化配置
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
