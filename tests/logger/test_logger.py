import json
from datetime import UTC, datetime
from typing import Any

import pytest
from loguru import logger as loguru_logger

from pkg.logger import LoggerHandler

# 全局变量用于存储测试期间的 manager 实例
_test_manager: LoggerHandler | None = None


@pytest.fixture
def setup_logging(tmp_path):
    """
    Fixture: 初始化测试环境
    """
    global _test_manager
    base_log_dir = tmp_path / "logs"
    base_log_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在

    # 创建新的 LoggerHandler 实例
    _test_manager = LoggerHandler(
        base_log_dir=base_log_dir,
    )
    _test_manager.setup(write_to_file=True, write_to_console=False)

    print(f"\n---> 当前测试日志路径: {base_log_dir}")

    yield base_log_dir

    # 清理
    loguru_logger.remove()
    _test_manager = None


def get_today_str():
    return datetime.now(UTC).strftime("%Y-%m-%d")


def find_json_log(file_path, target_message: str) -> dict[str, Any] | None:
    """JSON 日志查找辅助函数"""
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8")
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            # 5. 结构调整：新格式没有外层的 "record" 包装，直接是扁平字典
            if data.get("message") == target_message:
                return data
        except json.JSONDecodeError:
            continue
    return None


def find_text_log(file_path, target_message: str) -> bool:
    """文本日志查找辅助函数 (用于 System Log)"""
    if not file_path.exists():
        return False
    content = file_path.read_text(encoding="utf-8")
    return target_message in content


def test_default_logging(setup_logging):
    """
    测试默认日志 (Default Log)
    注意：根据最新代码，Default Log 固定为文本格式，不是 JSON。
    """
    base_log_dir = setup_logging
    msg = "Default logger start sequence"

    # 使用测试 manager 的 logger
    assert _test_manager is not None
    _test_manager._logger.info(msg)
    loguru_logger.complete()

    expected = base_log_dir / f"{get_today_str()}.log"

    assert expected.exists(), f"默认日志文件未创建: {expected}"

    # 验证文本内容
    assert find_text_log(expected, msg), "未在文本日志中找到目标消息"


def test_text_formatter_only_shows_current_span():
    handler = LoggerHandler()

    record = {
        "time": datetime(2026, 4, 20, 2, 51, 41, 837000, tzinfo=UTC),
        "level": type("Level", (), {"name": "ERROR"})(),
        "name": "pkg.logger.span",
        "function": "__aexit__",
        "line": 211,
        "message": "span.error",
        "extra": {
            "trace_id": "019da8cd058b76ed8a4a52141c1c6b38",
            "span_seq": 2,
            "span_name": "middleware.auth.token",
            "span_path": "1:middleware.request|2:middleware.auth.token",
            "json_content": {
                "elapsed_ms": 0.554,
                "error_type": "AppException",
            },
        },
    }

    formatted = handler._text_formatter(record)

    assert formatted == (
        "{extra[_formatted_time]} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{extra[_formatted_trace_id]}{extra[_formatted_span_segment]} | "
        "{message} | {extra[_text_json]}\n"
    )
    assert record["extra"]["_formatted_time"] == "2026-04-20T02:51:41.837Z"
    assert record["extra"]["_formatted_trace_id"] == "019da8cd058b76ed8a4a52141c1c6b38"
    assert record["extra"]["_formatted_span_segment"] == " | 2:middleware.auth.token"
    assert "1:middleware.request|2:middleware.auth.token" not in record["extra"]["_formatted_span_segment"]


def test_text_formatter_keeps_braces_in_dynamic_values():
    handler = LoggerHandler()

    record = {
        "time": datetime(2026, 4, 20, 2, 51, 41, 837000, tzinfo=UTC),
        "level": type("Level", (), {"name": "INFO"})(),
        "name": "pkg.logger.span",
        "function": "__aenter__",
        "line": 181,
        "message": "span.start",
        "extra": {
            "trace_id": "trace-{raw}",
            "span_seq": 2,
            "span_name": "span-{raw}",
            "span_path": "1:outer|2:span-{raw}",
            "json_content": None,
        },
    }

    formatted = handler._text_formatter(record)

    assert formatted == (
        "{extra[_formatted_time]} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{extra[_formatted_trace_id]}{extra[_formatted_span_segment]} | "
        "{message}\n"
    )
    assert record["extra"]["_formatted_trace_id"] == "trace-{raw}"
    assert record["extra"]["_formatted_span_segment"] == " | 2:span-{raw}"
