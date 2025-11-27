from datetime import datetime

import pytest
from loguru import logger as loguru_logger

# 请将 core_logger 替换为你实际的文件名/路径
from pkg.logger_tool import LogConfig, _init_logger, get_logger_by_dynamic_type, logger as global_logger


@pytest.fixture
def setup_logging(tmp_path, monkeypatch):
    """
    Fixture: 初始化测试环境
    1. 将日志目录重定向到 pytest 的临时目录
    2. 重新初始化 logger 以应用新路径
    """
    # 1. 修改 LogConfig 中的路径配置
    # 注意：LogConfig.BASE_LOG_DIR 是类属性，需要 patch 类
    monkeypatch.setattr(LogConfig, "BASE_LOG_DIR", tmp_path)
    monkeypatch.setattr(LogConfig, "DEFAULT_DIR", tmp_path / "default")

    # 2. 重新初始化 Logger
    # 我们关闭控制台输出，只测试文件写入，保持测试输出干净
    _init_logger(write_to_file=True, write_to_console=False)

    print(f"\n---> 当前测试日志路径: {tmp_path}")

    # 3. 返回临时目录路径供测试使用
    yield tmp_path

    # 4. 清理：移除所有 handler，防止干扰其他测试
    loguru_logger.remove()


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


def test_default_logging_path(setup_logging):
    """测试默认日志是否写入 /logs/default/"""
    log_dir = setup_logging
    today = get_today_str()

    # 触发默认日志
    global_logger.info("This is a default system log")

    # 强制等待写入 (loguru enqueue=True 是异步的)
    loguru_logger.complete()

    expected_file = log_dir / "default" / f"app_{today}.log"

    assert expected_file.exists(), "默认日志文件未创建"
    assert "This is a default system log" in expected_file.read_text(encoding="utf-8")


def test_llm_logging_path(setup_logging):
    """测试 LLM 日志是否写入 /logs/llm/"""
    log_dir = setup_logging
    today = get_today_str()

    # 触发 LLM 日志 (使用你代码中的 get_logger_by_type 或 bind)
    llm_logger = get_logger_by_dynamic_type("llm")
    llm_logger.info("This is an AI response")

    loguru_logger.complete()

    expected_file = log_dir / "llm" / f"{today}.log"

    assert expected_file.exists(), "LLM 日志文件未创建"
    assert "This is an AI response" in expected_file.read_text(encoding="utf-8")


def test_dynamic_device_logging(setup_logging):
    """测试动态设备日志是否自动创建文件夹并写入"""
    log_dir = setup_logging
    today = get_today_str()
    device_id = "device_camera_001"

    # 触发动态设备日志
    dev_logger = get_logger_by_dynamic_type(device_id)
    dev_logger.info("Device connected successfully")

    loguru_logger.complete()

    # 期望路径: /tmp_path/device_camera_001/YYYY-MM-DD.log
    expected_dir = log_dir / device_id
    expected_file = expected_dir / f"{today}.log"

    assert expected_dir.exists(), f"设备目录 {device_id} 未自动创建"
    assert expected_file.exists(), "设备日志文件未创建"
    assert "Device connected successfully" in expected_file.read_text(encoding="utf-8")


def test_log_isolation(setup_logging):
    """测试日志隔离：确保设备日志不会出现在默认日志中"""
    log_dir = setup_logging
    today = get_today_str()

    # 写入一条设备日志
    get_logger_by_dynamic_type("device_x").info("Device Msg")

    loguru_logger.complete()

    # 检查默认日志文件
    default_file = log_dir / "default" / f"app_{today}.log"

    # 如果默认日志文件甚至没创建，那也是一种成功（说明没混进去）
    if default_file.exists():
        content = default_file.read_text(encoding="utf-8")
        assert "Device Msg" not in content, "错误：设备日志泄露到了默认日志文件中！"


def test_new_device_on_the_fly(setup_logging):
    """测试在线新增设备场景"""
    log_dir = setup_logging
    today = get_today_str()

    # 模拟系统运行中突然出现新设备
    new_device_id = "sensor_9999"
    logger = get_logger_by_dynamic_type(new_device_id)
    logger.warning("Battery Low")

    loguru_logger.complete()

    expected_file = log_dir / new_device_id / f"{today}.log"
    assert expected_file.exists()
    assert "Battery Low" in expected_file.read_text(encoding="utf-8")
