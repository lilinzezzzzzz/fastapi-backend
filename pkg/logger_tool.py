import os
import sys
from pathlib import Path
from typing import Any, Set

import loguru

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

    CONSOLE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[trace_id]}</magenta> | <yellow>{extra[type]}</yellow> - <level>{message}</level>"
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

        # 设置默认 Context
        self._logger.configure(extra={"trace_id": "-", "type": "default"})

        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                format=LogConfig.CONSOLE_FORMAT,
                level=LogConfig.LEVEL,
                enqueue=True,
                colorize=True,
                diagnose=True
            )

        if write_to_file:
            self._ensure_dir(LogConfig.DEFAULT_DIR)
            # 默认日志暂保持普通格式，如需 JSON 也可按下面的方式修改
            self._logger.add(
                sink=LogConfig.DEFAULT_DIR / "app_{time:YYYY-MM-DD}.log",
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
                    format=self._json_formatter,
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
        这里使用了一个技巧：
        1. 我们在这里手动构建字典并序列化为 JSON 字符串。
        2. 将 JSON 字符串存入 record['extra'] 的临时字段中。
        3. 返回 "{extra[serialized_json]}\n" 让 Loguru 去输出这个字段。
        这样避免了 Loguru 试图去解析 JSON 字符串中的花括号从而导致 Crash。
        """
        # 1. 构建日志数据
        log_record = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f"),
            "level": record["level"].name,
            "name": record["name"],
            "function": record["function"],
            "line": record["line"],
            "trace_id": record["extra"].get("trace_id", "-"),
            "type": record["extra"].get("type", "default"),
            "text": "",
            "message": record["message"]
        }

        # 2. 尝试解析 message 为对象
        # 场景 A: bind(json_content=...)
        if "json_content" in record["extra"]:
            log_record["message"] = record["extra"]["json_content"]

        # 3. 序列化
        serialized = orjson_dumps(log_record, default=str, ensure_ascii=False)

        # 4. 将序列化后的字符串存回 extra (这是一个安全的副作用)
        record["extra"]["serialized_json"] = serialized

        # 5. 返回一个简单的模板，只引用上面存入的字段
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
