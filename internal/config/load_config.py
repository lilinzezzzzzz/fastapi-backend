from functools import lru_cache
from typing import Literal

from loguru import logger
from pydantic import MySQLDsn, RedisDsn, SecretStr, computed_field, model_validator
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
    1. 系统环境变量 (System Environment Variables)
    2. .secrets 文件 (Secrets File)
    3. 环境配置文件 (.env.local / .env.prod 等)
    """

    # --- 核心环境配置 ---
    # 允许从环境变量覆盖，默认为 local
    APP_ENV: Literal["local", "dev", "test", "prod"] = "local"
    DEBUG: bool = False

    # --- 密钥配置 (全部使用 SecretStr 防止日志泄露) ---
    AES_SECRET: SecretStr = SecretStr("")  # 解密用的根密钥
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- CORS ---
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # --- Database (MySQL) ---
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USERNAME: str
    MYSQL_PASSWORD: str  # 原始值，可能是 ENC(...)
    MYSQL_DATABASE: str

    # --- Cache (Redis) ---
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""  # 原始值，可能是 ENC(...)
    REDIS_DB: int = 0

    # Pydantic 配置
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def decrypt_sensitive_fields(self) -> "Settings":
        """
        全字段解密验证器。
        在所有字段加载完成后执行，使用加载到的 AES_SECRET 解密特定字段。
        """
        # 需要解密的字段列表
        fields_to_decrypt = ["MYSQL_PASSWORD", "REDIS_PASSWORD"]

        # 获取 AES 密钥明文
        aes_key = self.AES_SECRET.get_secret_value()

        # 如果没有 AES 密钥，跳过解密（假设都是明文）
        if not aes_key:
            return self

        for field in fields_to_decrypt:
            # 获取当前字段值
            original_value = getattr(self, field)

            if isinstance(original_value, str) and original_value.startswith("ENC(") and original_value.endswith(")"):
                encrypted_content = original_value[4:-1]
                try:
                    # 使用内部方法解密
                    decrypted_value = aes_decrypt(encrypted_content, aes_key)
                    # 将解密后的值回写到实例中
                    setattr(self, field, decrypted_value)
                except Exception as e:
                    error_msg = f"Failed to decrypt field '{field}': {str(e)}"
                    logger.error(error_msg)
                    raise ValueError(error_msg) from e
        return self

    @computed_field
    @property
    def sqlalchemy_database_uri(self) -> str:
        """生成 SQLAlchemy 连接字符串"""
        return MySQLDsn.build(
            scheme="mysql+aiomysql",
            username=self.MYSQL_USERNAME,
            password=self.MYSQL_PASSWORD,  # 此时已是解密后的密码
            host=self.MYSQL_HOST,
            port=self.MYSQL_PORT,
            path=f"{self.MYSQL_DATABASE}",
            query="charset=utf8mb4",
        ).unicode_string()

    @computed_field
    @property
    def redis_url(self) -> str:
        """生成 Redis 连接字符串"""
        return RedisDsn.build(
            scheme="redis",
            username=None,
            password=self.REDIS_PASSWORD if self.REDIS_PASSWORD else None,
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            path=f"{self.REDIS_DB}",
        ).unicode_string()


# =========================================================
# 工厂函数与单例
# =========================================================


@lru_cache
def get_settings() -> Settings:
    """
    获取配置单例。

    逻辑：
    1. 初始化日志。
    2. 探测 APP_ENV (优先级: 环境变量 > .secrets文件)。
    3. 根据 APP_ENV 决定加载哪些 .env 文件。
    4. 实例化 Settings。
    """
    _logger = _setup_startup_logger()
    _logger.info("Loading configuration...")

    # 1. 确定 APP_ENV
    # 为了拿到 APP_ENV，我们先临时加载一下 .secrets (如果不通过系统环境变量传参)
    secrets_path = BASE_DIR / "configs" / ".secrets"
    temp_env_file = secrets_path if secrets_path.exists() else None

    # 预加载以获取 APP_ENV，不进行完整校验
    class EnvProber(BaseSettings):
        APP_ENV: Literal["local", "dev", "test", "prod"] = "local"
        model_config = SettingsConfigDict(env_file=temp_env_file, extra="ignore")

    app_env = EnvProber().APP_ENV
    _logger.info(f"Detected Environment: {app_env}")

    # 2. 构建配置文件路径列表
    # 加载顺序：.env.{env} (基础配置) -> .secrets (密钥覆盖) -> 系统环境变量 (最高优先级，自动处理)
    env_file_path = BASE_DIR / "configs" / f".env.{app_env}"

    load_files = []
    if env_file_path.exists():
        load_files.append(env_file_path)
    if secrets_path.exists():
        load_files.append(secrets_path)

    if load_files:
        _logger.info(f"Loading config files: {[f.name for f in load_files]}")

    # 3. 实例化最终配置
    try:
        _settings = Settings(_env_file=load_files)  # type: ignore
        _logger.success("Configuration loaded successfully.")
        return _settings
    except Exception as e:
        _logger.critical(f"Failed to load configuration: {e}")
        raise


# 全局入口，类似原代码的 settings，但改为调用函数
# 建议在业务代码中使用 get_settings()，如果非要保持变量名兼容：
settings = get_settings()
