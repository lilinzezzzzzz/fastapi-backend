import os
import sys
from pathlib import Path
from typing import Any
from datetime import timezone

import loguru

# 确保这里的导入路径与你的项目结构一致
from pkg import BASE_DIR, orjson_dumps


class LoggerManager:
    """
    日志管理器
    集成了配置、初始化、动态Sink注册和自定义格式化功能。
    """

    # --- 1. 核心常量定义 ---
    SYSTEM_LOG_TYPE: str = "system"

    # --- 2. 配置部分 ---
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # 路径配置
    BASE_LOG_DIR: Path = BASE_DIR / "logs"
    SYSTEM_LOG_DIR: Path = BASE_LOG_DIR / SYSTEM_LOG_TYPE

    # 轮转与保留配置
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"

    def __init__(self):
        self._logger = loguru.logger
        self._registered_types: dict[str, dict[str, Any]] = {}
        self._is_initialized = False

    def setup(
            self,
            *,
            write_to_file: bool = True,
            write_to_console: bool = True,
            force_use_utc: bool = True
    ) -> "loguru.Logger":
        """
        初始化系统日志 (System Logger)
        """
        self._logger.remove()
        self._registered_types.clear()

        # 1. 准备基础配置
        config_params: dict[str, Any] = {
            "extra": {"trace_id": "-", "type": self.SYSTEM_LOG_TYPE, "json_content": None}
        }

        # 2. 根据参数决定是否挂载 UTC 补丁
        if force_use_utc:
            config_params["patcher"] = self._utc_time_patcher

        self._logger.configure(**config_params)

        # 3. Console 输出
        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                format=self._console_formatter,  # 使用动态 Console 格式化器
                level=self.LEVEL,
                enqueue=True,
                colorize=True,
                diagnose=True
            )

        # 4. File 输出 (System Log)
        if write_to_file:
            self._ensure_dir(self.SYSTEM_LOG_DIR)

            self._logger.add(
                sink=self.SYSTEM_LOG_DIR / "{time:YYYY-MM-DD}.log",
                level=self.LEVEL,
                rotation=self.ROTATION,
                retention=self.RETENTION,
                compression=self.COMPRESSION,
                enqueue=True,
                format=self._file_formatter,  # <--- 修改这里：使用动态文件格式化器
                filter=self._filter_system
            )

            # 记录 System 类型配置
            self._registered_types[self.SYSTEM_LOG_TYPE] = {"save_json": False}

        mode_str = "UTC" if force_use_utc else "Local Time"
        self._logger.info(f"Logger initialized successfully ({mode_str} Mode).")
        self._is_initialized = True
        return self._logger

    def get_dynamic_logger(
            self,
            log_type: str,
            *,
            write_to_file: bool = True,
            write_to_console: bool = False,
            save_json: bool = True
    ) -> "loguru.Logger":
        """获取动态类型的 Logger"""
        if not self._is_initialized:
            raise RuntimeError("LoggerManager is not initialized! Call setup() first.")

        if log_type in self._registered_types:
            existing_config = self._registered_types[log_type]
            if existing_config.get("save_json") != save_json:
                raise ValueError(f"Configuration conflict for '{log_type}'.")
            return self._logger.bind(type=log_type)

        try:
            log_dir = self.BASE_LOG_DIR / log_type
            self._ensure_dir(log_dir)
            sink_path = log_dir / "{time:YYYY-MM-DD}.log"

            def _specific_filter(record):
                return record["extra"].get("type") == log_type

            if write_to_console:
                self._logger.add(
                    sink=sys.stderr,
                    format=self._console_formatter,
                    level=self.LEVEL,
                    enqueue=True,
                    colorize=True,
                    filter=_specific_filter
                )

            if write_to_file:
                # <--- 修改这里：如果 save_json 为 False，使用 _file_formatter
                log_format = self._json_formatter if save_json else self._file_formatter

                self._logger.add(
                    sink=sink_path,
                    level=self.LEVEL,
                    rotation=self.ROTATION,
                    retention=self.RETENTION,
                    compression=self.COMPRESSION,
                    enqueue=True,
                    format=log_format,
                    serialize=False,  # 注意：这里如果是 JSON 格式化器内部处理序列化，这里 False 是对的
                    filter=_specific_filter
                )

            self._registered_types[log_type] = {"save_json": save_json}
            self._logger.info(f"System: Registered new log sink for type '{log_type}'")

        except Exception as e:
            self._logger.error(f"System: Failed to register sink for '{log_type}'. Error: {e}")
            return self._logger.bind(type=self.SYSTEM_LOG_TYPE, original_type=log_type)

        return self._logger.bind(type=log_type)

    # --- 格式化器更新 ---
    @staticmethod
    def _console_formatter(record: Any) -> str:
        """
        动态控制台格式化器
        如果 extra 中包含非空的 json_content，则将其追加显示
        """
        # 基础格式
        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<magenta>{extra[trace_id]}</magenta> | "
            "<yellow>{extra[type]}</yellow> - <level>{message}</level>"
        )

        # 检查 json_content 是否存在且不为 None
        if record["extra"].get("json_content") is not None:
            # 换行并以青色显示 JSON 内容
            # loguru 会自动调用字典的 __str__ 或 __repr__
            # 如果你想在控制台看漂亮的 JSON，可以在这里把 json_content 先 dumps 一下
            fmt += "\n<cyan>{extra[json_content]}</cyan>"
        return fmt + "\n"

    @staticmethod
    def _file_formatter(record: Any) -> str:
        """
        File 文本动态格式化器 (save_json=False 时使用)
        """
        fmt = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{extra[trace_id]} | "
            "{extra[type]} - {message}"
        )

        # 检查并追加 json_content
        if record["extra"].get("json_content") is not None:
            # 这里选择换行追加，保持与 Console 视觉一致，且避免单行过长
            # 如果希望单行，可以将 \n 替换为 | 或 -
            fmt += "\n{extra[json_content]}"

        return fmt + "\n"

    @staticmethod
    def _json_formatter(record: Any) -> str:
        """JSON Lines 格式化器 (save_json=True 时使用)"""
        extra_data = record["extra"].copy()
        json_content = extra_data.pop("json_content", None)

        if not isinstance(json_content, (dict, list, str, type(None))):
            raise TypeError(f"json_content must be a dict, list, str, or None. Got {type(json_content)}")

        log_record = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f"),
            "level": record["level"].name,
            "name": record["name"],
            "function": record["function"],
            "line": record["line"],
            "text": "",
            "message": record["message"],
            "extra": extra_data
        }

        if json_content is not None:
            log_record["json_content"] = json_content

        serialized = orjson_dumps(log_record, default=str)
        record["extra"]["serialized_json"] = serialized
        return "{extra[serialized_json]}\n"

    # --- 辅助方法 ---

    @staticmethod
    def _utc_time_patcher(record: Any):
        record["time"] = record["time"].astimezone(timezone.utc)

    @staticmethod
    def _filter_system(record: Any) -> bool:
        return record["extra"].get("type") == LoggerManager.SYSTEM_LOG_TYPE

    @staticmethod
    def _ensure_dir(path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


# 实例化
logger_manager = LoggerManager()
logger = logger_manager.setup(force_use_utc=True)
get_dynamic_logger = logger_manager.get_dynamic_logger
