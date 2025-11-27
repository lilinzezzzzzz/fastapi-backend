import json
from datetime import datetime
from typing import Optional, Dict, Any

import pytest
from loguru import logger as loguru_logger

# 请将 pkg.logger_tool 替换为你实际的文件名/路径
from pkg.logger_tool import LogConfig, _init_logger, get_logger_by_dynamic_type, logger as global_logger


@pytest.fixture
def setup_logging(tmp_path, monkeypatch):
    """
    Fixture: 初始化测试环境
    """
    monkeypatch.setattr(LogConfig, "BASE_LOG_DIR", tmp_path)
    monkeypatch.setattr(LogConfig, "DEFAULT_DIR", tmp_path / "default")

    # 重新初始化 Logger (文件开启 JSON 序列化)
    _init_logger(write_to_file=True, write_to_console=False)

    print(f"\n---> 当前测试日志路径: {tmp_path}")

    yield tmp_path

    loguru_logger.remove()


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


# --- 关键辅助函数 ---
def find_json_log(file_path, target_message: str) -> Optional[Dict[str, Any]]:
    """
    读取日志文件（每行一个 JSON），查找包含特定 message 的记录。
    如果找到，返回解析后的 record 字典；否则返回 None。
    """
    if not file_path.exists():
        return None

    content = file_path.read_text(encoding="utf-8")

    # 逐行解析 JSON
    for line in content.strip().split('\n'):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            # Loguru serialize=True 的结构是: {"text": "...", "record": {...}}
            record = data.get("record", {})

            if record.get("message") == target_message:
                return record
        except json.JSONDecodeError:
            continue

    return None


def test_default_logging_path(setup_logging):
    """测试默认日志是否为 JSON 且包含正确字段"""
    log_dir = setup_logging
    today = get_today_str()
    msg = "This is a default system log"

    global_logger.info(msg)
    loguru_logger.complete()

    expected_file = log_dir / "default" / f"app_{today}.log"
    assert expected_file.exists(), "默认日志文件未创建"

    # 使用 JSON 解析验证
    record = find_json_log(expected_file, msg)
    assert record is not None, "未在日志中找到目标 JSON 记录"

    # 验证字段
    assert record["extra"]["type"] == "default"
    assert record["level"]["name"] == "INFO"


def test_llm_logging_path(setup_logging):
    """测试 LLM 日志是否为 JSON 且 type 正确"""
    log_dir = setup_logging
    today = get_today_str()
    msg = "This is an AI response"

    llm_logger = get_logger_by_dynamic_type("llm")
    llm_logger.info(msg)
    loguru_logger.complete()

    expected_file = log_dir / "llm" / f"{today}.log"
    assert expected_file.exists()

    record = find_json_log(expected_file, msg)
    assert record is not None

    # 验证关键的 type 字段
    assert record["extra"]["type"] == "llm"


def test_dynamic_device_logging(setup_logging):
    """测试动态设备日志 JSON 结构"""
    log_dir = setup_logging
    today = get_today_str()
    device_id = "device_camera_001"
    msg = "Device connected successfully"

    dev_logger = get_logger_by_dynamic_type(device_id)
    dev_logger.info(msg)
    loguru_logger.complete()

    expected_file = log_dir / device_id / f"{today}.log"
    assert expected_file.exists()

    record = find_json_log(expected_file, msg)
    assert record is not None

    # 验证 type 是否等于 device_id (这是我们之前的设定)
    assert record["extra"]["type"] == device_id
    # 验证时间戳存在
    assert "time" in record


def test_log_isolation(setup_logging):
    """测试日志隔离：确保设备日志不会出现在默认日志中"""
    log_dir = setup_logging
    today = get_today_str()
    device_msg = "Device Msg"

    # 写入设备日志
    # 注意：这可能会在默认日志里产生一条 "System: Registered new log sink..." 的记录
    # 但我们验证的是 "Device Msg" 不在其中
    get_logger_by_dynamic_type("device_x").info(device_msg)

    loguru_logger.complete()

    default_file = log_dir / "default" / f"app_{today}.log"

    # 如果文件存在（因为有系统注册日志），则检查内容
    if default_file.exists():
        # 这里用文本搜索依然是有效的，因为如果 JSON 里没有这个字符串，那肯定没有
        # 当然，为了严谨，你也可以遍历 JSON 检查 record['message']
        content = default_file.read_text(encoding="utf-8")
        assert device_msg not in content, "错误：设备业务日志泄露到了系统默认日志中！"


def test_new_device_on_the_fly(setup_logging):
    """测试在线新增设备场景"""
    log_dir = setup_logging
    today = get_today_str()
    new_device_id = "sensor_9999"
    msg = "Battery Low"

    logger = get_logger_by_dynamic_type(new_device_id)
    logger.warning(msg)

    loguru_logger.complete()

    expected_file = log_dir / new_device_id / f"{today}.log"
    assert expected_file.exists()

    record = find_json_log(expected_file, msg)
    assert record is not None
    assert record["level"]["name"] == "WARNING"
    assert record["extra"]["type"] == new_device_id
