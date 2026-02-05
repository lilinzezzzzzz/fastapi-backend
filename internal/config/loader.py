"""配置加载器"""

from pathlib import Path

from dotenv import dotenv_values
from loguru import logger

from internal import BASE_DIR
from internal.config.settings import Settings


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


def detect_app_env() -> str:
    """
    检测应用环境

    规则：
    - 只从 .secrets 文件读取 APP_ENV
    - 如果文件不存在或 APP_ENV 未设置，则报错终止
    """
    secrets_path = BASE_DIR / "configs" / ".secrets"

    # 检查文件是否存在
    if not secrets_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {secrets_path}")

    # 从文件读取配置
    secrets_dict = dotenv_values(secrets_path)
    app_env = secrets_dict.get("APP_ENV")

    if not app_env:
        raise ValueError(f"APP_ENV not found in {secrets_path}")

    return app_env


def _validate_secrets_file() -> tuple[Path, dict]:
    """
    验证 .secrets 文件存在并返回路径和内容

    Returns:
        tuple[Path, dict]: (文件路径, 配置字典)

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: APP_ENV 未设置
    """
    secrets_path = BASE_DIR / "configs" / ".secrets"

    # 检查文件是否存在
    if not secrets_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {secrets_path}")

    # 读取配置
    secrets_dict = dotenv_values(secrets_path)

    # 验证必需的 APP_ENV
    app_env = secrets_dict.get("APP_ENV")
    if not app_env:
        raise ValueError(f"APP_ENV not found in {secrets_path}")

    return secrets_path, secrets_dict


def load_config() -> Settings:
    """
    加载应用配置

    加载顺序：
    1. 验证 .secrets 文件并获取应用环境
    2. 检查对应环境配置文件是否存在
    3. 加载配置文件 (.env.{env} 和 .secrets)
    """
    _logger = _setup_startup_logger()
    _logger.info("Loading configuration...")

    # 1. 验证 .secrets 文件并获取应用环境
    try:
        secrets_path, secrets_dict = _validate_secrets_file()
        app_env = secrets_dict["APP_ENV"]  # 已经验证过存在
        _logger.info(f"Detected Environment: {app_env}")
    except (FileNotFoundError, ValueError) as e:
        _logger.critical(f"Configuration validation failed: {e}")
        raise

    # 2. 检查对应环境文件是否存在
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

        # 根据 ECHO_CONFIG 决定是否打印配置
        if _settings.ECHO_CONFIG:
            _logger.info("=" * 50)
            _logger.info("Configuration Details (ECHO_CONFIG=true):")
            for key, value in _settings.model_dump().items():
                # SecretStr 类型需要获取原始值
                if hasattr(_settings, key) and hasattr(getattr(_settings, key), "get_secret_value"):
                    value = getattr(_settings, key).get_secret_value()
                _logger.info(f"  {key}: {value}")

            _logger.info("=" * 50)

        return _settings
    except Exception as e:
        _logger.critical(f"Config load failed: {e}")
        raise


# 全局配置实例（私有）
_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """
    获取配置实例（线程安全的单例模式）
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = load_config()
    return _settings_instance


def init_settings() -> Settings:
    """
    初始化并返回配置实例
    在应用启动时调用此函数
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = load_config()
    return _settings_instance


def reset_settings():
    """
    重置配置实例（主要用于测试）
    """
    global _settings_instance
    _settings_instance = None
