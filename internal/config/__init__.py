from urllib.parse import quote_plus

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pkg import BASE_DIR


class BaseConfig(BaseSettings):
    """基础配置类，定义所有环境共享的配置项"""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量
    )

    # 基础配置
    DEBUG: bool = True
    SECRET_KEY: SecretStr = SecretStr("CHANGE_ME")

    # JWT 配置
    JWT_ALGORITHM: str = "HS256"

    # CORS 配置
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # MySQL 配置
    MYSQL_USERNAME: str = "root"
    MYSQL_PASSWORD: SecretStr = SecretStr("root")
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str = "app_db"

    # Redis 配置
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PASSWORD: SecretStr = SecretStr("")
    REDIS_DB: int = 0
    REDIS_PORT: int = 6379

    # Token 过期时间（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

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


class LocalConfig(BaseConfig):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",
        env_file=(BASE_DIR / "configs" / ".env.local").as_posix(),
    )


class DevelopmentConfig(BaseConfig):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",
        env_file=(BASE_DIR / "configs" / ".env.dev").as_posix(),
    )


class TestingConfig(BaseConfig):
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",
        env_file=(BASE_DIR / "configs" / ".env.test").as_posix(),
    )


class ProductionConfig(BaseConfig):
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",
        env_file=(BASE_DIR / "configs" / ".env.prod").as_posix(),
    )
