import json
from datetime import datetime
from typing import Any, Dict, Optional

import pytest
from loguru import logger as loguru_logger

# 1. 导入调整：LogConfig 已移除，get_logger 变更为 get_dynamic_logger
from pkg.toolkit.async_logger import LoggerManager, get_dynamic_logger, logger as global_logger, logger_manager


@pytest.fixture
def setup_logging(tmp_path):
    """
    Fixture: 初始化测试环境
    """
    # 2. 修改配置路径
    # 注意：直接修改类属性。由于 SYSTEM_LOG_DIR 是在类加载时计算的，
    # 修改 BASE_LOG_DIR 后必须手动更新 SYSTEM_LOG_DIR。
    LoggerManager.BASE_LOG_DIR = tmp_path / "logs"
    LoggerManager.SYSTEM_LOG_DIR = LoggerManager.BASE_LOG_DIR / LoggerManager.SYSTEM_LOG_TYPE

    # 3. 重新初始化 LoggerManager
    logger_manager.setup(write_to_file=True, write_to_console=False)

    print(f"\n---> 当前测试日志路径: {LoggerManager.BASE_LOG_DIR}")

    yield LoggerManager.BASE_LOG_DIR

    # 4. 清理
    loguru_logger.remove()


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


def find_json_log(file_path, target_message: str) -> Optional[Dict[str, Any]]:
    """JSON 日志查找辅助函数"""
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8")
    for line in content.strip().split('\n'):
        if not line.strip(): continue
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

    # 使用 global_logger (System logger)
    global_logger.info(msg)
    loguru_logger.complete()

    # 路径变更：default -> system, 文件名不再包含 app_ 前缀
    expected = base_log_dir / "system" / f"{get_today_str()}.log"

    assert expected.exists(), f"系统日志文件未创建: {expected}"

    # 验证文本内容
    assert find_text_log(expected, msg), "未在文本日志中找到目标消息"


def test_dynamic_logger_creation(setup_logging):
    """测试动态 Logger 创建 (默认为 JSON)"""
    base_log_dir = setup_logging
    dev_id = "device_test_01"
    msg = "Connect success"

    # 使用新导出的 get_dynamic_logger 方法
    # 默认 save_json=True
    dev_logger = get_dynamic_logger(dev_id)
    dev_logger.info(msg)
    loguru_logger.complete()

    # 路径：logs/device_test_01/YYYY-MM-DD.log
    expected = base_log_dir / dev_id / f"{get_today_str()}.log"
    assert expected.exists(), f"设备日志文件未创建: {expected}"

    # 验证 JSON 内容
    record = find_json_log(expected, msg)
    assert record is not None
    # 验证 extra 中的 type
    assert record["extra"]["type"] == dev_id
    # 验证 text 字段为空 (符合之前需求)
    assert record["text"] == ""


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
    dev_logger = get_dynamic_logger(dev_id)
    dev_logger.info(msg)
    loguru_logger.complete()

    # 验证：设备目录不应该存在（因为创建失败）
    assert not (base_log_dir / dev_id).exists()

    # 验证：日志应该出现在 system 目录
    system_log = base_log_dir / "system" / f"{get_today_str()}.log"
    assert system_log.exists()

    # 注意：降级到 system log 后，格式变成了文本格式 (因为 System Logger 是文本)
    # 同时 context type 会变成 "system"
    assert find_text_log(system_log, msg), "未在系统降级日志中找到消息"

    # 如果你想验证它是作为 "system" 类型记录的，需要去 parse 文本日志的格式
    # 文本格式包含: ... | {extra[type]} - {message}
    content = system_log.read_text(encoding="utf-8")
    assert f"system - {msg}" in content or f"| system - {msg}" in content
