from urllib.parse import quote_plus

from pydantic import IPvAnyAddress
from pydantic.v1 import BaseSettings

from pkg import BASE_DIR


class BaseConfig(BaseSettings):
    # 基础配置
    DEBUG: bool = True
    SECRET_KEY: str = "CHANGE_ME"

    # JWT 配置
    JWT_ALGORITHM: str = "HS256"

    # CORS 配置
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # MySQL 配置
    MYSQL_USERNAME: str = "root"
    MYSQL_PASSWORD: str = "root"
    MYSQL_HOST: IPvAnyAddress | str = "127.0.0.1"
    MYSQL_PORT: str = "3306"
    MYSQL_DATABASE: str = "app_db"

    # Redis 配置
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_PORT: int = 6379

    # Token 过期时间（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    @property
    def sqlalchemy_database_uri(self) -> str:
        return f"mysql+aiomysql://{quote_plus(self.MYSQL_USERNAME)}:{quote_plus(self.MYSQL_PASSWORD)}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"

    @property
    def sqlalchemy_echo(self) -> bool:
        return self.DEBUG  # 开发环境启用 SQLAlchemy 日志

    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD == "":
            return f"redis://{quote_plus(self.REDIS_HOST)}:{self.REDIS_PORT}/{self.REDIS_DB}"
        else:
            return f"redis://:{quote_plus(self.REDIS_PASSWORD)}@{quote_plus(self.REDIS_HOST)}:{self.REDIS_PORT}/{self.REDIS_DB}"


class LocalConfig(BaseConfig):
    DEBUG: bool = True

    class Config:
        case_sensitive = True
        env_file_encoding = "utf-8"
        env_file = (BASE_DIR / "configs" / ".env.local").as_posix()


class DevelopmentConfig(BaseConfig):
    DEBUG: bool = True

    class Config:
        case_sensitive = True
        env_file = (BASE_DIR / "configs" / ".env.dev").as_posix()
        env_file_encoding = "utf-8"


class TestingConfig(BaseConfig):
    DEBUG = False

    class Config:
        case_sensitive = True
        env_file = (BASE_DIR / "configs" / ".env.test").as_posix()
        env_file_encoding = "utf-8"


class ProductionConfig(BaseConfig):
    DEBUG = False

    class Config:
        case_sensitive = True
        env_file = (BASE_DIR / "configs" / ".env.prod").as_posix()
        env_file_encoding = "utf-8"
