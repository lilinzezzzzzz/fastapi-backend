import json
import pytest
import sys
from pathlib import Path

# 确保能导入 pkg (视你的目录结构而定，如果已在 pythonpath 可忽略)
sys.path.append(str(Path(__file__).parent.parent))

from pkg.logger_tool import LoggerManager, LogConfig

@pytest.fixture
def logger_setup(tmp_path):
    """
    Fixture: 初始化 LoggerManager，并将日志目录重定向到临时文件夹。
    tmp_path 是 pytest 内置 fixture，会在测试结束后自动清理。
    """
    # 1. 临时修改配置中的路径，避免污染项目真实日志目录
    # 注意：这里修改的是类属性，会影响单例行为，所以测试是独立的
    LogConfig.BASE_LOG_DIR = tmp_path / "logs"
    LogConfig.DEFAULT_DIR = LogConfig.BASE_LOG_DIR / "default"

    # 2. 初始化管理器
    manager = LoggerManager()
    # 强制重新 setup，写入文件但不写控制台(保持测试输出干净)
    manager.setup(write_to_file=True, write_to_console=False)

    return manager, LogConfig.BASE_LOG_DIR


def test_dynamic_logger_json_structure(logger_setup):
    """
    测试核心需求：
    1. text 为空
    2. message 为 JSON 对象
    3. 文件成功写入
    """
    manager, base_dir = logger_setup
    log_type = "payment_gateway"

    # 获取动态 logger
    logger = manager.get_dynamic_logger(log_type)

    # 构造测试数据 (字典)
    test_data = {
        "transaction_id": "TXN_9999",
        "amount": 100.50,
        "status": "success",
        "meta": {
            "user_id": 123,
            "ip": "127.0.0.1"
        }
    }

    # 1. 写入日志
    logger.info(test_data)

    # 重要：因为 Loguru 配置了 enqueue=True (异步写入)，
    # 我们需要调用 complete() 等待所有日志写入磁盘，否则读取文件时可能是空的。
    logger.complete()

    # 2. 验证文件是否存在
    target_dir = base_dir / log_type
    assert target_dir.exists(), f"目录未创建: {target_dir}"

    # 查找生成的日志文件 (文件名含日期，使用 glob 匹配)
    log_files = list(target_dir.glob("*.log"))
    assert len(log_files) > 0, "没有生成日志文件"
    log_file = log_files[0]

    # --- 输出日志路径 ---
    print(f"\n>>> [test_dynamic_logger_json_structure] 生成的日志文件路径: {log_file.absolute()}")

    # 3. 读取并验证内容
    with open(log_file, "r", encoding="utf-8") as f:
        line = f.readline()
        assert line, "日志文件内容为空"

        # 尝试解析 JSON
        try:
            log_json = json.loads(line)
        except json.JSONDecodeError:
            pytest.fail(f"日志不是有效的 JSON 格式: {line}")

        # --- 核心断言 ---

        # 验证 A: text 字段必须为空字符串
        assert "text" in log_json
        assert log_json["text"] == "", f"Expected text to be empty, got '{log_json['text']}'"

        # 验证 B: type 字段
        assert log_json["type"] == log_type

        # 验证 C: message 字段必须是对象(dict)，且内容一致
        assert isinstance(log_json["message"], dict), "Message 字段应该是 dict 对象，而不是字符串"
        assert log_json["message"]["transaction_id"] == "TXN_9999"
        assert log_json["message"]["amount"] == 100.50
        assert log_json["message"]["meta"]["ip"] == "127.0.0.1"


def test_dynamic_logger_with_bind(logger_setup):
    """
    测试使用 bind 方法传递 json_content 的场景
    (适用于不想依赖字符串反解析的复杂场景)
    """
    manager, base_dir = logger_setup
    log_type = "audit_log"
    logger = manager.get_dynamic_logger(log_type)

    complex_data = {"action": "delete", "target": "user", "is_admin": True}

    # 使用 bind 传递
    logger.bind(json_content=complex_data).info("这一段文本会被忽略")

    logger.complete()

    # 读取文件验证
    target_dir = base_dir / log_type
    log_file = list(target_dir.glob("*.log"))[0]

    # --- 输出日志路径 ---
    print(f"\n>>> [test_dynamic_logger_with_bind] 生成的日志文件路径: {log_file.absolute()}")

    with open(log_file, "r", encoding="utf-8") as f:
        log_json = json.loads(f.readline())

        # 验证 message 是否直接变成了 complex_data
        assert log_json["message"] == complex_data
        assert log_json["message"]["action"] == "delete"
        # 验证 text 依然为空
        assert log_json["text"] == ""


def test_fallback_for_non_dict_message(logger_setup):
    """
    测试边界情况：如果用户传入的不是字典，程序不应该崩，
    message 应该回退为普通字符串。
    """
    manager, base_dir = logger_setup
    log_type = "system_error"
    logger = manager.get_dynamic_logger(log_type)

    plain_msg = "这是一条普通文本日志"
    logger.error(plain_msg)

    logger.complete()

    target_dir = base_dir / log_type
    log_file = list(target_dir.glob("*.log"))[0]

    # --- 输出日志路径 ---
    print(f"\n>>> [test_fallback_for_non_dict_message] 生成的日志文件路径: {log_file.absolute()}")

    with open(log_file, "r", encoding="utf-8") as f:
        log_json = json.loads(f.readline())

        # 这里 message 应该是字符串
        assert log_json["message"] == plain_msg
        assert log_json["level"] == "ERROR"
        assert log_json["text"] == ""
