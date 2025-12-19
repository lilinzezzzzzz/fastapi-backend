import os
from functools import lru_cache
from typing import Literal

from dotenv import dotenv_values
from loguru import logger
from pydantic import MySQLDsn, PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from internal import BASE_DIR
from pkg.crypto.aes import aes_decrypt


# =========================================================
# 日志配置 (懒加载)
# =========================================================
def _setup_startup_logger():
    """配置启动日志"""
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "startup.log",
        rotation="1 day",
        retention="7 days",
        level="INFO",
        enqueue=True,
        encoding="utf-8",
    )
    return logger


# =========================================================
# 配置定义
# =========================================================
# 支持的数据库类型
DBType = Literal["mysql", "postgresql", "oracle"]

# 数据库驱动映射
DB_DRIVER_MAP: dict[str, str] = {
    "mysql": "mysql+aiomysql",
    "postgresql": "postgresql+asyncpg",
    "oracle": "oracle+oracledb",
}


class Settings(BaseSettings):
    """
    应用全局配置。
    """

    # --- 核心环境配置 ---
    APP_ENV: Literal["local", "dev", "test", "prod"]
    DEBUG: bool = False

    # --- 密钥配置 ---
    AES_SECRET: SecretStr
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    PRINT_CONFIG: bool = False  # 是否打印配置信息 (调试用)

    # --- CORS ---
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # --- Database ---
    DB_TYPE: DBType  # 数据库类型: mysql, postgresql, oracle (必填)
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_DATABASE: str
    DB_SERVICE_NAME: str = ""  # Oracle 专用: Service Name

    # --- Redis ---
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",
        env_file_encoding="utf-8",
    )

    @field_validator("DB_TYPE", mode="before")
    @classmethod
    def validate_db_type(cls, v: str) -> str:
        """校验数据库类型"""
        if not v:
            raise ValueError("DB_TYPE is required and cannot be empty")
        allowed = list(DB_DRIVER_MAP.keys())
        if v not in allowed:
            raise ValueError(f"DB_TYPE must be one of {allowed}, got '{v}'")
        return v

    @model_validator(mode="after")
    def decrypt_sensitive_fields(self) -> "Settings":
        """解密敏感字段"""
        fields_to_decrypt = ["DB_PASSWORD", "REDIS_PASSWORD"]
        aes_key = self.AES_SECRET.get_secret_value()

        if not aes_key:
            return self

        for field in fields_to_decrypt:
            original_value = getattr(self, field)
            if isinstance(original_value, str) and original_value.startswith("ENC(") and original_value.endswith(")"):
                try:
                    decrypted_value = aes_decrypt(original_value[4:-1], aes_key)
                    setattr(self, field, decrypted_value)
                except Exception as e:
                    logger.error(f"Failed to decrypt field '{field}': {str(e)}")
                    raise ValueError(f"Failed to decrypt field '{field}'") from e
        return self

    @property
    def sqlalchemy_database_uri(self) -> str:
        """根据数据库类型动态生成连接 URI"""
        driver = DB_DRIVER_MAP.get(self.DB_TYPE)
        if not driver:
            raise ValueError(f"Unsupported database type: {self.DB_TYPE}")

        if self.DB_TYPE == "mysql":
            return str(
                MySQLDsn.build(
                    scheme=driver,
                    username=self.DB_USERNAME,
                    password=self.DB_PASSWORD,
                    host=self.DB_HOST,
                    port=self.DB_PORT,
                    path=self.DB_DATABASE,
                    query="charset=utf8mb4",
                )
            )
        elif self.DB_TYPE == "postgresql":
            return str(
                PostgresDsn.build(
                    scheme=driver,
                    username=self.DB_USERNAME,
                    password=self.DB_PASSWORD,
                    host=self.DB_HOST,
                    port=self.DB_PORT,
                    path=self.DB_DATABASE,
                )
            )
        elif self.DB_TYPE == "oracle":
            # Oracle 连接格式: oracle+oracledb://user:pass@host:port/?service_name=xxx
            password = self.DB_PASSWORD
            if password:
                from urllib.parse import quote_plus

                password = quote_plus(password)
                return f"{driver}://{self.DB_USERNAME}:{password}@{self.DB_HOST}:{self.DB_PORT}/?service_name={self.DB_SERVICE_NAME}"
            return f"{driver}://{self.DB_USERNAME}@{self.DB_HOST}:{self.DB_PORT}/?service_name={self.DB_SERVICE_NAME}"
        else:
            raise ValueError(f"Unsupported database type: {self.DB_TYPE}")

    @property
    def redis_url(self) -> str:
        return str(
            RedisDsn.build(
                scheme="redis",
                username=None,
                password=self.REDIS_PASSWORD if self.REDIS_PASSWORD else None,
                host=self.REDIS_HOST,
                port=self.REDIS_PORT,
                path=f"{self.REDIS_DB}",
            )
        )


# =========================================================
# 工厂函数 (简化版)
# =========================================================
@lru_cache
def get_settings() -> Settings:
    _logger = _setup_startup_logger()
    _logger.info("Loading configuration...")

    secrets_path = BASE_DIR / "configs" / ".secrets"

    # 1. 检查 .secrets 是否存在
    if not secrets_path.exists():
        msg = f"CRITICAL: Secrets file missing at {secrets_path}"
        _logger.critical(msg)
        raise FileNotFoundError(msg)

    # 2. 提取 APP_ENV (优先级: 系统环境变量 > .secrets 文件)
    # 不再实例化 Pydantic 类，直接读取
    app_env = os.getenv("APP_ENV")

    if not app_env:
        # 如果系统没设，从文件读
        secrets_dict = dotenv_values(secrets_path)
        app_env = secrets_dict.get("APP_ENV")

    if not app_env:
        msg = "CRITICAL: APP_ENV not found in system env or .secrets file!"
        _logger.critical(msg)
        raise ValueError(msg)

    _logger.info(f"Detected Environment: {app_env}")

    # 3. 检查对应环境文件是否存在
    env_file_path = BASE_DIR / "configs" / f".env.{app_env}"
    if not env_file_path.exists():
        msg = f"CRITICAL: Config file missing for environment '{app_env}' at {env_file_path}"
        _logger.critical(msg)
        raise FileNotFoundError(msg)

    # 4. 加载配置
    # load_files 顺序：[.env.dev, .secrets] -> 后者覆盖前者
    load_files = [env_file_path, secrets_path]
    _logger.info(f"Loading files: {[f.name for f in load_files]}")

    try:
        _settings = Settings(_env_file=load_files)  # type: ignore
        _logger.success("Configuration loaded successfully.")

        # 根据 PRINT_CONFIG 决定是否打印配置
        if _settings.PRINT_CONFIG:
            _logger.info("=" * 50)
            _logger.info("Configuration Details (PRINT_CONFIG=true):")
            for key, value in _settings.model_dump().items():
                # SecretStr 类型需要获取原始值
                if isinstance(getattr(_settings, key, None), SecretStr):
                    value = getattr(_settings, key).get_secret_value()
                _logger.info(f"  {key}: {value}")
            _logger.info("=" * 50)

        return _settings
    except Exception as e:
        _logger.critical(f"Config load failed: {e}")
        raise


settings = get_settings()
