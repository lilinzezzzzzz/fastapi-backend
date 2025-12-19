import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import dotenv_values, load_dotenv
from loguru import logger as _startup_logger  # 启动阶段使用默认 logger
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from internal import BASE_DIR
from pkg.crypto.aes import aes_decrypt

# 配置加载完成后，为启动日志添加文件 handler
# 这样后续的启动日志也能被记录到文件
_startup_log_dir = BASE_DIR / "logs"
_startup_log_dir.mkdir(exist_ok=True)
_startup_logger.add(
    _startup_log_dir / "startup.log",
    rotation="1 day",
    retention="7 days",
    level="INFO",
    enqueue=True,
)
_startup_logger.info("Startup logger file handler added.")

# 密钥文件路径（不纳入版本控制，只存放解密密钥等敏感信息）
_SECRETS_FILE_PATH: Path = BASE_DIR / "configs" / ".secrets"


def _init_env() -> Path:
    """
    初始化环境配置。

    执行顺序：
        1. 加载 .secrets 文件（获取 APP_ENV 和其他密钥）
        2. 根据 APP_ENV 确定配置文件路径
        3. 记录日志

    Returns:
        tuple[str, Path]: (APP_ENV, ENV_FILE_PATH)
    """

    def _load_secrets() -> None:
        """
        加载密钥文件到环境变量。

        密钥文件 (.secrets) 不纳入版本控制，只存放解密密钥等敏感信息。
        文件格式示例:
            AES_SECRET=your_aes_secret_key
            APP_ENV=local
        """
        _startup_logger.info("Loading secrets...")
        if _SECRETS_FILE_PATH.exists():
            load_dotenv(_SECRETS_FILE_PATH, override=False)  # 不覆盖已存在的环境变量
            _startup_logger.info(f"Secrets file loaded: {_SECRETS_FILE_PATH}")

            # 记录加载的配置项（只记录 key，不记录 value 以避免泄露密钥）
            secrets = dotenv_values(_SECRETS_FILE_PATH)
            for key, value in secrets.items():
                # 记录 key 和 value 是否存在（不记录实际值）
                _startup_logger.info(f"{key}: [{value if value else 'empty'}]")
        else:
            raise FileNotFoundError(f"Secrets file not found: {_SECRETS_FILE_PATH}")

    def _get_app_env() -> str:
        """
        从环境变量获取 APP_ENV。

        APP_ENV 必须在 .secrets 文件或系统环境变量中设置，不允许默认值。
        """
        _startup_logger.info("Getting APP_ENV...")
        app_env = os.getenv("APP_ENV")
        # 检查环境变量
        if app_env not in ["local", "dev", "test", "prod"]:
            raise ValueError("APP_ENV is not set. Please set it in .secrets file or environment variable.")
        _startup_logger.info(f"APP_ENV: {app_env}")
        return app_env.lower()

    _startup_logger.info("Initializing environment...")
    _load_secrets()
    env_file_path = BASE_DIR / "configs" / f".env.{_get_app_env()}"
    _startup_logger.info(f"Config file path: {env_file_path}")
    return env_file_path


# 模块加载时初始化环境配置
ENV_FILE_PATH = _init_env()


class BaseConfig(BaseSettings):
    """
    基础配置类，定义所有环境共享的配置项。

    配置加载优先级（从高到低）：
        1. 系统环境变量
        2. .env 文件
        3. 代码中定义的默认值

    加载逻辑：
        - 优先读取系统环境变量
        - 如果环境变量不存在，则从 .env 文件读取
        - 如果 .env 文件也没有，则使用默认值
        - 如果以上都没有且字段无默认值，抛出 ValidationError
    """

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量
    )

    # 基础配置
    DEBUG: bool
    JWT_SECRET: SecretStr  # JWT 签名密钥

    # AES 解密密钥（用于解密配置文件中的加密字段，通过环境变量注入）
    # 如果不使用加密配置，可设置为空字符串
    AES_SECRET: SecretStr = SecretStr("")

    # JWT 配置
    JWT_ALGORITHM: str

    # CORS 配置
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # MySQL 配置
    MYSQL_USERNAME: str
    MYSQL_PASSWORD: str  # 支持加密格式: ENC(xxx)
    MYSQL_HOST: str
    MYSQL_PORT: int
    MYSQL_DATABASE: str

    # Redis 配置
    REDIS_HOST: str
    REDIS_PASSWORD: str  # 支持加密格式: ENC(xxx)
    REDIS_DB: int
    REDIS_PORT: int

    # Token 过期时间（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    @field_validator("MYSQL_PASSWORD", "REDIS_PASSWORD", mode="before")
    @classmethod
    def decrypt_password(cls, v: str, info) -> str:
        """
        自动解密以 ENC(...) 格式存储的密码。

        配置文件中的加密格式: ENC(base64_encrypted_string)
        解密密钥通过环境变量 AES_SECRET 注入。
        """
        if not isinstance(v, str):
            return v

        if v.startswith("ENC(") and v.endswith(")"):
            # 记录原始加密字符串（方便排查问题）
            _startup_logger.info(f"Decrypting field '{info.field_name}': {v}")
            # 提取加密内容
            encrypted = v[4:-1]
            # 从环境变量获取解密密钥
            aes_secret = os.getenv("AES_SECRET", "")
            if not aes_secret:
                raise ValueError(f"Field '{info.field_name}' is encrypted but AES_SECRET is not set")
            try:
                decrypted = aes_decrypt(encrypted, aes_secret)
                _startup_logger.info(f"Field '{info.field_name}' decrypted successfully.")
                return decrypted
            except Exception as e:
                _startup_logger.error(f"Failed to decrypt field '{info.field_name}': {e}")
                raise ValueError(f"Failed to decrypt field '{info.field_name}': {e}") from e

        return v  # 非加密格式直接返回

    @property
    def sqlalchemy_database_uri(self) -> str:
        password = self.MYSQL_PASSWORD
        return f"mysql+aiomysql://{quote_plus(self.MYSQL_USERNAME)}:{quote_plus(password)}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"

    @property
    def sqlalchemy_echo(self) -> bool:
        return self.DEBUG  # 开发环境启用 SQLAlchemy 日志

    @property
    def redis_url(self) -> str:
        password = self.REDIS_PASSWORD
        if password == "":
            return f"redis://{quote_plus(self.REDIS_HOST)}:{self.REDIS_PORT}/{self.REDIS_DB}"
        else:
            return f"redis://:{quote_plus(password)}@{quote_plus(self.REDIS_HOST)}:{self.REDIS_PORT}/{self.REDIS_DB}"


# 配置文件路径（根据 APP_ENV 动态确定）
# ENV_FILE_PATH 已在模块顶部加载 .secrets 后确定


class Settings(BaseConfig):
    # 自动根据环境变量 APP_ENV 加载对应的 .env 文件
    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=ENV_FILE_PATH.as_posix(), env_file_encoding="utf-8", extra="ignore"
    )


def init_setting() -> Settings:
    """
    加载配置。
    此函数只在模块首次被导入时执行一次。
    """
    _startup_logger.info("Init setting...")

    # 检查配置文件是否存在
    if not ENV_FILE_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {ENV_FILE_PATH}")

    # 实例化配置
    s = Settings()
    # 打印关键信息 (注意脱敏)
    _startup_logger.info("Init setting successfully.")
    _startup_logger.info("==========================")
    for k, v in s.model_dump().items():
        _startup_logger.info(f"{k}: {v}")
    _startup_logger.info("==========================")
    return s


# =========================================================
# 单例模式：模块加载时立即执行，生成全局唯一的配置对象
# =========================================================
setting: Settings = init_setting()
