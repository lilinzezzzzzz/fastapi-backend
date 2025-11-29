import logging
import os
import sys
import json
import ast  # 用于将字典字符串安全还原为对象
from pathlib import Path
from typing import Any, Set

import loguru

from pkg import BASE_DIR


class LogConfig:
    """日志配置中心"""
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    BASE_LOG_DIR: Path = BASE_DIR / "logs"
    DEFAULT_DIR: Path = BASE_LOG_DIR / "default"

    # 通用配置
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"

    # Console 格式
    CONSOLE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[trace_id]}</magenta> | <yellow>{extra[type]}</yellow> - <level>{message}</level>"
    # File 使用 JSON 序列化，FORMAT 参数在 serialize=True 时会被 loguru 忽略或作为 text 字段，此处保留供参考
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

        # 3. 配置控制台输出
        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                format=LogConfig.CONSOLE_FORMAT,
                level=LogConfig.LEVEL,
                enqueue=True,
                colorize=True,
                diagnose=True
            )

        # 4. 配置文件输出 (Default)
        # 如果你也希望默认日志也是这种 JSON 格式，可以将这里的 format 改为 self._json_formatter
        # 并去掉 serialize=True (因为 _json_formatter 内部已经做了序列化)
        if write_to_file:
            self._ensure_dir(LogConfig.DEFAULT_DIR)
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
        """
        获取动态类型的 Logger，写入 JSON 文件
        """
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
                # --- 关键修改 ---
                self._logger.add(
                    sink=sink_path,
                    level=LogConfig.LEVEL,
                    rotation=LogConfig.ROTATION,
                    retention=LogConfig.RETENTION,
                    compression=LogConfig.COMPRESSION,
                    enqueue=True,
                    # 使用自定义 JSON 格式化器，而不使用 serialize=True
                    format=self._json_formatter,
                    # serialize 必须设为 False，否则 Loguru 会再次把我们的 JSON 字符串转义
                    serialize=False,
                    filter=_specific_filter
                )

            self._registered_types.add(log_type)

            # 记录系统日志
            self._logger.info(f"System: Registered new log sink for type '{log_type}'")

        except Exception as e:
            # 降级处理：注册失败时，回退到 default，并记录错误
            self._logger.error(f"System: Failed to register sink for '{log_type}'. Error: {e}")
            return self._logger.bind(type="default", original_type=log_type)

        return self._logger.bind(type=log_type)

    @staticmethod
    def _json_formatter(record: Any) -> str:
        """
        自定义 JSON 格式化器。
        将日志记录转换为符合要求的 JSON 字符串。
        :param record: 字典
        """
        # 1. 提取基础信息
        log_record = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f"),
            "level": record["level"].name,
            "name": record["name"],
            "function": record["function"],
            "line": record["line"],
            "trace_id": record["extra"].get("trace_id", "-"),
            "type": record["extra"].get("type", "default"),

            # 要求：text 字段为空字符串
            "text": "",

            # 默认 message 为字符串
            "message": record["message"]
        }

        # 2. 处理 message 字段，使其成为 JSON 对象
        # 场景 A: 用户使用 logger.bind(json_content={...}).info(...)
        if "json_content" in record["extra"]:
            log_record["message"] = record["extra"]["json_content"]

        # 场景 B: 用户直接使用 logger.info({'a': 1})
        # Loguru 会将字典转换为字符串 "{'a': 1}" (注意是单引号，这是 Python 的 repr)
        # 我们尝试将其解析回字典对象
        else:
            try:
                # 使用 ast.literal_eval 安全地解析 Python 字典字符串
                # 如果 message 看起来像字典或列表，尝试转换
                val = ast.literal_eval(record["message"])
                if isinstance(val, (dict, list)):
                    log_record["message"] = val
            except (ValueError, SyntaxError):
                # 解析失败，保持原样（普通字符串日志）
                pass

        # 3. 序列化为 JSON 字符串并添加换行符
        return json.dumps(log_record, default=str, ensure_ascii=False) + "\n"

    @staticmethod
    def _filter_default(record: Any) -> bool:
        return record["extra"].get("type") == "default"

    @staticmethod
    def _remove_uvicorn_handlers():
        logging.getLogger("uvicorn.access").handlers = []
        logging.getLogger("uvicorn.error").handlers = []
        logging.getLogger("uvicorn").handlers = []

    @staticmethod
    def _ensure_dir(path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


# 1. 实例化管理器
logger_manager = LoggerManager()
# 2. 执行初始化 (模块加载时执行)
logger = logger_manager.setup()
# 3. 导出常用的动态 logger 获取方法，保持 API 简洁
get_dynamic_logger = logger_manager.get_dynamic_logger
