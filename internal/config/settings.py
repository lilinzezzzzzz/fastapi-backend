"""应用配置模型定义"""

from typing import Literal

from loguru import logger
from pydantic import MySQLDsn, PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pkg.crypter.aes import aes_decrypt
from pkg.logger import LogFormat

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

    # --- 日志配置 ---
    LOG_FORMAT: LogFormat = LogFormat.TEXT  # 日志格式: TEXT 或 JSON

    # --- 密钥配置 ---
    AES_SECRET: SecretStr
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ECHO_CONFIG: bool = False  # 是否打印配置信息 (调试用)

    # --- CORS ---
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # --- Database ---
    DB_TYPE: DBType  # 数据库类型: mysql, postgresql, oracle (必填)
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USERNAME: str
    DB_PASSWORD: SecretStr
    DB_DATABASE: str
    DB_SERVICE_NAME: str = ""  # Oracle 专用: Service Name
    DB_ECHO: bool = False  # 是否输出 SQL 日志

    # --- OpenTelemetry ---
    OTEL_ENABLED: bool = True  # 是否启用 OpenTelemetry
    OTEL_SERVICE_NAME: str = "fastapi-backend"  # 服务名称（需根据实际项目修改）
    OTEL_OTLP_ENDPOINT: str = ""  # OTLP 导出端点，为空则只使用 Console 导出
    OTEL_CONSOLE_EXPORT: bool = True  # 是否启用 Console 导出（开发调试用）

    # --- Redis ---
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: SecretStr = SecretStr("")
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
            secret_value: SecretStr = getattr(self, field)
            original_value = secret_value.get_secret_value()
            if original_value.startswith("ENC(") and original_value.endswith(")"):
                try:
                    decrypted_value = aes_decrypt(original_value[4:-1], aes_key)
                    object.__setattr__(self, field, SecretStr(decrypted_value))
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

        password = self.DB_PASSWORD.get_secret_value()

        if self.DB_TYPE == "mysql":
            return str(
                MySQLDsn.build(
                    scheme=driver,
                    username=self.DB_USERNAME,
                    password=password,
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
                    password=password,
                    host=self.DB_HOST,
                    port=self.DB_PORT,
                    path=self.DB_DATABASE,
                )
            )
        elif self.DB_TYPE == "oracle":
            # Oracle 连接格式: oracle+oracledb://user:pass@host:port/?service_name=xxx
            if password:
                from urllib.parse import quote_plus

                password = quote_plus(password)
                return f"{driver}://{self.DB_USERNAME}:{password}@{self.DB_HOST}:{self.DB_PORT}/?service_name={self.DB_SERVICE_NAME}"
            return f"{driver}://{self.DB_USERNAME}@{self.DB_HOST}:{self.DB_PORT}/?service_name={self.DB_SERVICE_NAME}"
        else:
            raise ValueError(f"Unsupported database type: {self.DB_TYPE}")

    @property
    def redis_url(self) -> str:
        password = self.REDIS_PASSWORD.get_secret_value()
        return str(
            RedisDsn.build(
                scheme="redis",
                username=None,
                password=password if password else None,
                host=self.REDIS_HOST,
                port=self.REDIS_PORT,
                path=f"{self.REDIS_DB}",
            )
        )
