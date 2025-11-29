import os
import sys
from pathlib import Path
from typing import Any, Set

import loguru

# 引入你自定义的 helper
from pkg import BASE_DIR, orjson_dumps


class LogConfig:
    """日志配置中心"""
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    BASE_LOG_DIR: Path = BASE_DIR / "logs"
    DEFAULT_DIR: Path = BASE_LOG_DIR / "default"

    # 通用配置
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"

    # Console 格式 (保持人类可读)
    CONSOLE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[trace_id]}</magenta> | <yellow>{extra[type]}</yellow> - <level>{message}</level>"

    # File 格式 (这个参数在使用 serialize=True 时会被忽略，但我们这里是自定义 format，保留作参考)
    FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {extra[trace_id]} | {extra[type]} - {message}"


class LoggerManager:
    """日志管理器"""

    def __init__(self):
        self._logger = loguru.logger
        self._registered_types: Set[str] = set()
        self._is_initialized = False

    def setup(self, write_to_file: bool = True, write_to_console: bool = True) -> "loguru.Logger":
        self._logger.remove()
        self._registered_types.clear()

        # 1. 设置默认 Context
        # json_content 初始化为 None，这是后续判断是否使用 bind 的关键
        self._logger.configure(extra={"trace_id": "-", "type": "default", "json_content": None})

        # 2. Console 输出
        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                format=LogConfig.CONSOLE_FORMAT,
                level=LogConfig.LEVEL,
                enqueue=True,
                colorize=True,
                diagnose=True
            )

        # 3. File 输出 (Default)
        if write_to_file:
            self._ensure_dir(LogConfig.DEFAULT_DIR)
            # 默认日志暂保持普通格式，如果默认日志也要 JSON，可以把 format 改成 self._json_formatter
            self._logger.add(
                sink=LogConfig.DEFAULT_DIR / "{time:YYYY-MM-DD}.log",
                level=LogConfig.LEVEL,
                rotation=LogConfig.ROTATION,
                retention=LogConfig.RETENTION,
                compression=LogConfig.COMPRESSION,
                enqueue=True,
                format=LogConfig.FILE_FORMAT,
                filter=self._filter_default
            )
            self._registered_types.add("default")

        self._logger.info("Logger initialized successfully.")
        self._is_initialized = True
        return self._logger

    def get_dynamic_logger(
            self,
            log_type: str,
            *,
            write_to_file: bool = True,
            write_to_console: bool = False
    ) -> "loguru.Logger":

        if not self._is_initialized:
            raise RuntimeError("LoggerManager is not initialized!")

        if log_type in self._registered_types:
            return self._logger.bind(type=log_type)

        try:
            log_dir = LogConfig.BASE_LOG_DIR / log_type
            self._ensure_dir(log_dir)
            sink_path = log_dir / "{time:YYYY-MM-DD}.log"

            def _specific_filter(record):
                return record["extra"].get("type") == log_type

            if write_to_console:
                self._logger.add(
                    sink=sys.stderr,
                    format=LogConfig.CONSOLE_FORMAT,
                    level=LogConfig.LEVEL,
                    enqueue=True,
                    colorize=True,
                    filter=_specific_filter
                )

            if write_to_file:
                self._logger.add(
                    sink=sink_path,
                    level=LogConfig.LEVEL,
                    rotation=LogConfig.ROTATION,
                    retention=LogConfig.RETENTION,
                    compression=LogConfig.COMPRESSION,
                    enqueue=True,
                    # 使用自定义的 _json_formatter
                    format=self._json_formatter,
                    # 必须关闭 Loguru 自带的序列化，因为我们在 formatter 里自己做 JSON
                    serialize=False,
                    filter=_specific_filter
                )

            self._registered_types.add(log_type)
            self._logger.info(f"System: Registered new log sink for type '{log_type}'")

        except Exception as e:
            self._logger.error(f"System: Failed to register sink for '{log_type}'. Error: {e}")
            return self._logger.bind(type="default", original_type=log_type)

        return self._logger.bind(type=log_type)

    @staticmethod
    def _json_formatter(record: Any) -> str:
        """
        自定义 JSON 格式化器。
        """
        # 1. 构建日志基础结构
        log_record = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f"),
            "level": record["level"].name,
            "name": record["name"],
            "function": record["function"],
            "line": record["line"],
            "trace_id": record["extra"].get("trace_id", "-"),
            "type": record["extra"].get("type", "default"),

            # 你的核心需求：text 恒为空
            "text": "",

            # 默认 message 为 Loguru 处理后的字符串
            "message": record["message"]
        }

        # 2. 判断是否通过 bind 传入了 json_content
        # 你的核心需求：只有 bind 了 json_content，message 才是对象
        json_content = record["extra"].get("json_content")
        if json_content is not None:
            log_record["message"] = json_content

        # 3. 序列化
        # 注意：这里去掉了 ensure_ascii=False，因为 orjson 不支持该参数
        # 你的 orjson_dumps 已经包含了 .decode("utf-8")，所以这里得到的是 str
        serialized = orjson_dumps(log_record, default=str)

        # 4. 存回 extra
        record["extra"]["serialized_json"] = serialized

        # 5. 返回模板
        return "{extra[serialized_json]}\n"

    @staticmethod
    def _filter_default(record: Any) -> bool:
        return record["extra"].get("type") == "default"

    @staticmethod
    def _ensure_dir(path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


# 实例化
logger_manager = LoggerManager()
logger = logger_manager.setup()
get_dynamic_logger = logger_manager.get_dynamic_logger
