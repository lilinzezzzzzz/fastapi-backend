import json
from datetime import datetime
from typing import Optional, Dict, Any

import pytest
from loguru import logger as loguru_logger

# 导入新的类实例
from pkg.logger_tool import LogConfig, logger_manager, logger as global_logger, get_logger


@pytest.fixture
def setup_logging(tmp_path, monkeypatch):
    """
    Fixture: 初始化测试环境
    """
    # 1. 修改配置路径
    monkeypatch.setattr(LogConfig, "BASE_LOG_DIR", tmp_path)
    monkeypatch.setattr(LogConfig, "DEFAULT_DIR", tmp_path / "default")

    # 2. 重新初始化 LoggerManager
    # 直接调用实例的 setup 方法
    logger_manager.setup(write_to_file=True, write_to_console=False)

    print(f"\n---> 当前测试日志路径: {tmp_path}")

    yield tmp_path

    # 3. 清理
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
            record = data.get("record", {})
            if record.get("message") == target_message:
                return record
        except json.JSONDecodeError:
            continue
    return None


def test_default_logging(setup_logging):
    """测试默认日志 (JSON)"""
    log_dir = setup_logging
    msg = "System start"

    # 使用 global_logger
    global_logger.info(msg)
    loguru_logger.complete()

    expected = log_dir / "default" / f"app_{get_today_str()}.log"
    assert expected.exists()

    record = find_json_log(expected, msg)
    assert record is not None
    assert record["extra"]["type"] == "default"


def test_dynamic_logger_creation(setup_logging):
    """测试动态 Logger 创建"""
    log_dir = setup_logging
    dev_id = "device_test_01"
    msg = "Connect success"

    # 使用新导出的 get_logger 方法
    dev_logger = get_logger(dev_id)
    dev_logger.info(msg)
    loguru_logger.complete()

    expected = log_dir / dev_id / f"{get_today_str()}.log"
    assert expected.exists()

    record = find_json_log(expected, msg)
    assert record["extra"]["type"] == dev_id


def test_create_failure_fallback(setup_logging, monkeypatch):
    """测试创建目录失败时的降级逻辑"""
    log_dir = setup_logging
    dev_id = "device_error"
    msg = "Should go to default"

    # 模拟 mkdir 抛出权限错误
    def mock_mkdir(*args, **kwargs):
        raise PermissionError("Mock permission denied")

    # 注意：我们要 Patch 的是 LoggerManager 内部调用的 pathlib.Path.mkdir
    # 或者简单点，Patch LoggerManager._ensure_dir
    monkeypatch.setattr(logger_manager, "_ensure_dir", mock_mkdir)

    # 触发日志
    dev_logger = get_logger(dev_id)
    dev_logger.info(msg)
    loguru_logger.complete()

    # 验证：设备目录不应该存在（因为创建失败）
    assert not (log_dir / dev_id).exists()

    # 验证：日志应该出现在 default 目录
    default_log = log_dir / "default" / f"app_{get_today_str()}.log"
    assert default_log.exists()

    record = find_json_log(default_log, msg)
    assert record is not None
    # 验证降级标记 (根据代码逻辑，我们返回的是 bind(type='default'))
    assert record["extra"]["type"] == "default"
    # 如果你加上了 original_type 字段，可以在这里断言
    # assert record["extra"]["original_type"] == dev_id
