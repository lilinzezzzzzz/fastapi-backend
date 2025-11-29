import json
import pytest
import sys
from pathlib import Path

# ----------------------------------------------------------------------
# 1. 环境准备
# 确保能导入项目根目录下的 pkg 包
# ----------------------------------------------------------------------
sys.path.append(str(Path(__file__).parent.parent))

from pkg.logger_tool import LoggerManager, LogConfig


# ----------------------------------------------------------------------
# 2. Pytest Fixture
# ----------------------------------------------------------------------
@pytest.fixture
def logger_setup(tmp_path):
    """
    初始化 LoggerManager，并将日志输出重定向到 pytest 的临时目录。
    """
    # 临时修改配置路径
    LogConfig.BASE_LOG_DIR = tmp_path / "logs"
    LogConfig.DEFAULT_DIR = LogConfig.BASE_LOG_DIR / "default"

    manager = LoggerManager()
    # 初始化：只写文件，不写控制台（保持测试输出由于）
    manager.setup(write_to_file=True, write_to_console=False)

    return manager, LogConfig.BASE_LOG_DIR


# ----------------------------------------------------------------------
# 3. 测试用例
# ----------------------------------------------------------------------
def test_final_logging_requirements(logger_setup):
    manager, base_dir = logger_setup
    log_type = "final_check"

    # 获取动态 logger
    logger = manager.get_dynamic_logger(log_type)

    # ==========================================
    # 场景 A: 使用 bind(json_content=...)
    # 预期: message 是 JSON 对象
    # ==========================================
    complex_data = {
        "user_id": 888,
        "tags": ["vip", "active"],
        "meta": {"source": "ios"}
    }
    logger.bind(json_content=complex_data).info("这段文字会被忽略")

    # ==========================================
    # 场景 B: 直接使用 logger.info(dict)
    # 预期: message 是 字符串 (不再自动解析)，text 为空
    # ==========================================
    simple_dict = {"status": 200, "msg": "ok"}
    logger.info(simple_dict)

    # ==========================================
    # 场景 C: 普通字符串日志
    # 预期: message 是 字符串
    # ==========================================
    logger.info("系统启动成功")

    # 等待异步写入完成
    logger.complete()

    # ==========================================
    # 4. 验证结果
    # ==========================================
    target_dir = base_dir / log_type
    log_files = list(target_dir.glob("*.log"))
    assert len(log_files) > 0, "未生成日志文件"
    log_file = log_files[0]

    print(f"\n>>> 测试日志路径: {log_file}")

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 3, "日志行数不符合预期"

        # --- 验证 场景 A (Bind) ---
        log_a = json.loads(lines[0])
        print(f"Log A: {log_a}")
        assert log_a["text"] == "", "场景A: text 字段必须为空"
        assert isinstance(log_a["message"], dict), "场景A: message 必须是字典对象"
        assert log_a["message"]["user_id"] == 888
        assert log_a["message"]["tags"] == ["vip", "active"]

        # --- 验证 场景 B (Direct Dict) ---
        log_b = json.loads(lines[1])
        print(f"Log B: {log_b}")
        assert log_b["text"] == "", "场景B: text 字段必须为空"
        assert isinstance(log_b["message"], str), "场景B: message 必须是字符串 (不能被解析)"
        # 验证内容包含 key/value (注意 Python 字典转字符串通常是单引号)
        assert "'status': 200" in log_b["message"]

        # --- 验证 场景 C (String) ---
        log_c = json.loads(lines[2])
        print(f"Log C: {log_c}")
        assert log_c["text"] == "", "场景C: text 字段必须为空"
        assert log_c["message"] == "系统启动成功"


def test_orjson_serialization_check(logger_setup):
    """
    额外测试：验证 orjson 是否工作正常（不需要 ensure_ascii）
    """
    manager, base_dir = logger_setup
    logger = manager.get_dynamic_logger("utf8_test")
    # 测试中文和特殊字符
    data = {"name": "张三", "emoji": "🚀"}
    logger.bind(json_content=data).info("-")

    logger.complete()

    log_file = list((base_dir / "utf8_test").glob("*.log"))[0]
    print(f"\n>>> 测试日志路径: {log_file}")
    with open(log_file, "r", encoding="utf-8") as f:
        log_data = json.loads(f.readline())

        # 验证没有被转义为 \uXXXX
        # 如果 orjson 工作正常，这里读出来的就是原字符
        assert log_data["message"]["name"] == "张三"
        assert log_data["message"]["emoji"] == "🚀"
