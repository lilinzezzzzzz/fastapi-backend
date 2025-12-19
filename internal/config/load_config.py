from functools import lru_cache
from typing import Literal

from loguru import logger
from pydantic import MySQLDsn, RedisDsn, SecretStr, ValidationError, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from internal import BASE_DIR
from pkg.crypto.aes import aes_decrypt


# =========================================================
# 日志配置 (懒加载)
# =========================================================
def _setup_startup_logger():
    """配置启动日志，仅在首次获取配置时调用"""
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


class Settings(BaseSettings):
    """
    应用全局配置。

    加载优先级 (从高到低):
    1. 系统环境变量
    2. .secrets 文件 (必须存在)
    3. 环境配置文件 (.env.local / .env.prod 等) (必须存在)
    """

    # --- 核心环境配置 ---
    APP_ENV: Literal["local", "dev", "test", "prod"]
    DEBUG: bool = False

    # --- 密钥配置 (全部使用 SecretStr 防止日志泄露) ---
    AES_SECRET: SecretStr
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- CORS ---
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # --- Database (MySQL) ---
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USERNAME: str
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str

    # --- Cache (Redis) ---
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # Pydantic 配置
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def decrypt_sensitive_fields(self) -> "Settings":
        """
        全字段解密验证器。
        """
        fields_to_decrypt = ["MYSQL_PASSWORD", "REDIS_PASSWORD"]
        aes_key = self.AES_SECRET.get_secret_value()

        if not aes_key:
            return self

        for field in fields_to_decrypt:
            original_value = getattr(self, field)
            if isinstance(original_value, str) and original_value.startswith("ENC(") and original_value.endswith(")"):
                try:
                    encrypted_content = original_value[4:-1]
                    decrypted_value = aes_decrypt(encrypted_content, aes_key)
                    setattr(self, field, decrypted_value)
                except Exception as e:
                    logger.error(f"Failed to decrypt field '{field}': {str(e)}")
                    raise ValueError(f"Failed to decrypt field '{field}'") from e
        return self

    @computed_field
    @property
    def sqlalchemy_database_uri(self) -> str:
        """生成 SQLAlchemy 连接字符串"""
        return str(
            MySQLDsn.build(
                scheme="mysql+aiomysql",
                username=self.MYSQL_USERNAME,
                password=self.MYSQL_PASSWORD,
                host=self.MYSQL_HOST,
                port=self.MYSQL_PORT,
                path=f"{self.MYSQL_DATABASE}",
                query="charset=utf8mb4",
            )
        )

    @computed_field
    @property
    def redis_url(self) -> str:
        """生成 Redis 连接字符串"""
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
# 工厂函数与单例
# =========================================================


@lru_cache
def get_settings() -> Settings:
    """
    获取配置单例。
    """
    _logger = _setup_startup_logger()
    _logger.info("Loading configuration...")

    secrets_path = BASE_DIR / "configs" / ".secrets"

    # -----------------------------------------------------
    # 1. 强制检查 .secrets 文件是否存在
    # -----------------------------------------------------
    if not secrets_path.exists():
        msg = f"CRITICAL ERROR: Secrets file not found at: {secrets_path}"
        _logger.critical(msg)
        raise FileNotFoundError(msg)

    # -----------------------------------------------------
    # 2. 探测 APP_ENV
    # -----------------------------------------------------
    class EnvProber(BaseSettings):
        APP_ENV: Literal["local", "dev", "test", "prod"]
        model_config = SettingsConfigDict(env_file=secrets_path, extra="ignore")

    try:
        env_prober = EnvProber()
        app_env = env_prober.APP_ENV
        _logger.info(f"Detected Environment: {app_env}")
    except ValidationError as e:
        _logger.critical("CRITICAL: APP_ENV is missing in .secrets file or environment variables!")
        raise e

    # -----------------------------------------------------
    # 3. 强制检查环境配置文件 (.env.xxx) 是否存在
    # -----------------------------------------------------
    env_file_path = BASE_DIR / "configs" / f".env.{app_env}"

    if not env_file_path.exists():
        msg = f"CRITICAL ERROR: Environment config file not found at: {env_file_path}"
        _logger.critical(msg)
        _logger.critical(f"Please ensure .env.{app_env} exists for APP_ENV={app_env}")
        raise FileNotFoundError(msg)

    # -----------------------------------------------------
    # 4. 实例化最终配置
    # -----------------------------------------------------

    # 加载顺序：
    # 1. 基础环境配置 (.env.prod)
    # 2. 密钥配置 (.secrets) - 覆盖前者
    # 3. 系统环境变量 - 覆盖所有
    load_files = [env_file_path, secrets_path]

    _logger.info(f"Loading config files: {[f.name for f in load_files]}")

    try:
        _settings = Settings(_env_file=load_files)  # type: ignore
        _logger.success("Configuration loaded successfully.")
        return _settings
    except Exception as e:
        _logger.critical(f"Failed to load configuration: {e}")
        raise


settings = get_settings()
