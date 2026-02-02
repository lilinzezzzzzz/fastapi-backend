import json
from datetime import UTC, datetime
from typing import Any

import pytest
from loguru import logger as loguru_logger

from pkg.logger import LoggerManager

# 全局变量用于存储测试期间的 manager 实例
_test_manager: LoggerManager | None = None


@pytest.fixture
def setup_logging(tmp_path):
    """
    Fixture: 初始化测试环境
    """
    global _test_manager
    base_log_dir = tmp_path / "logs"
    base_log_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在

    # 创建新的 LoggerManager 实例
    _test_manager = LoggerManager(
        base_log_dir=base_log_dir,
        system_subdir="system",
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


def test_system_logging(setup_logging):
    """
    测试系统默认日志 (System Log)
    注意：根据最新代码，System Log 固定为文本格式，不是 JSON。
    """
    base_log_dir = setup_logging
    msg = "System start sequence"

    # 使用测试 manager 的 logger
    assert _test_manager is not None
    _test_manager._logger.info(msg)
    loguru_logger.complete()

    # 路径变更：default -> system, 文件名不再包含 app_ 前缀
    expected = base_log_dir / "system" / f"{get_today_str()}.log"

    assert expected.exists(), f"系统日志文件未创建: {expected}"

    # 验证文本内容
    assert find_text_log(expected, msg), "未在文本日志中找到目标消息"


def test_dynamic_logger_creation(setup_logging):
    """测试动态 Logger 创建 (格式由 LoggerManager 的 log_format 参数决定)"""
    base_log_dir = setup_logging
    dev_id = "device_test_01"
    msg = "Connect success"

    # 使用测试 manager 的 get_dynamic_logger 方法
    assert _test_manager is not None
    dev_logger = _test_manager.get_dynamic_logger(dev_id)
    dev_logger.info(msg)
    loguru_logger.complete()

    # 路径：logs/device_test_01/YYYY-MM-DD.log
    expected = base_log_dir / dev_id / f"{get_today_str()}.log"
    assert expected.exists(), f"设备日志文件未创建: {expected}"

    # 验证文本内容（默认 log_format="text"）
    assert find_text_log(expected, msg), "未在日志文件中找到目标消息"


def test_create_failure_fallback(setup_logging, monkeypatch):
    """测试创建目录失败时的降级逻辑"""
    base_log_dir = setup_logging
    dev_id = "device_error"
    msg = "Should fallback to system log"

    # 模拟 mkdir 抛出权限错误
    # 注意：我们要 Patch 的是 LoggerManager 内部调用的静态方法 _ensure_dir
    def mock_ensure_dir(path):
        # 只针对 device_error 的路径抛错，避免影响 system log 的创建
        if dev_id in str(path):
            raise PermissionError("Mock permission denied")
        # 其他路径正常创建 (比如 system log)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(LoggerManager, "_ensure_dir", mock_ensure_dir)

    # 触发日志
    assert _test_manager is not None
    dev_logger = _test_manager.get_dynamic_logger(dev_id)
    dev_logger.info(msg)
    loguru_logger.complete()

    # 验证：设备目录不应该存在（因为创建失败）
    assert not (base_log_dir / dev_id).exists()

    # 验证：日志应该出现在 system 目录
    system_log = base_log_dir / "system" / f"{get_today_str()}.log"
    assert system_log.exists()

    # 注意：降级到 system log 后，格式与 System Logger 一致
    # 同时 context log_namespace 会变成 "system"
    assert find_text_log(system_log, msg), "未在系统降级日志中找到消息"

    # 如果你想验证它是作为 "system" 命名空间记录的，需要去 parse 文本日志的格式
    # 文本格式包含: ... | {extra[log_namespace]} - {message}
    content = system_log.read_text(encoding="utf-8")
    assert f"system - {msg}" in content or f"| system - {msg}" in content
