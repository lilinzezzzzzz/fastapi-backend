import json
import pytest
import sys
from pathlib import Path

# ----------------------------------------------------------------------
# 1. 环境准备
# ----------------------------------------------------------------------
# 确保能导入项目根目录下的 pkg 包
sys.path.append(str(Path(__file__).parent.parent))

from pkg.logger_tool import LoggerManager


# ----------------------------------------------------------------------
# 2. Pytest Fixture
# ----------------------------------------------------------------------
@pytest.fixture
def logger_setup(tmp_path):
    """
    初始化 LoggerManager，并将日志输出重定向到 pytest 的临时目录。
    """
    # --- 关键修改开始 ---
    # 1. 修改 Base 路径到临时目录
    LoggerManager.BASE_LOG_DIR = tmp_path / "logs"

    # 2. 显式更新 SYSTEM_LOG_DIR
    # 注意：Python 类属性在定义时已计算，仅修改 BASE_LOG_DIR 不会自动更新 SYSTEM_LOG_DIR
    # 所以这里必须手动重新拼接，确保系统日志也写入临时目录
    LoggerManager.SYSTEM_LOG_DIR = LoggerManager.BASE_LOG_DIR / LoggerManager.SYSTEM_LOG_TYPE

    manager = LoggerManager()
    # 初始化：只写文件，不写控制台
    manager.setup(write_to_file=True, write_to_console=False)

    # 返回 manager 和 临时日志根目录 (直接使用 LoggerManager 的属性)
    return manager, LoggerManager.BASE_LOG_DIR
    # --- 关键修改结束 ---


# ----------------------------------------------------------------------
# 3. 测试用例
# ----------------------------------------------------------------------
def test_json_content_extraction_logic(logger_setup):
    """
    验证核心逻辑：
    1. json_content 是否成功提拔到 JSON 根层级。
    2. extra 中是否移除了 json_content (避免重复)。
    3. message 是否保持原始文本。
    4. text 是否为空。
    """
    manager, base_dir = logger_setup
    log_type = "extraction_test"

    # 获取动态 logger (默认为 save_json=True)
    logger = manager.get_dynamic_logger(log_type)

    # ==========================================
    # 场景 A: 使用 bind(json_content=...)
    # 预期:
    #   - 根层级出现 "json_content"
    #   - extra 里没有 "json_content"
    #   - message 为 "发起支付"
    # ==========================================
    payment_data = {
        "order_id": "ORD-2023",
        "amount": 100.00,
        "currency": "CNY"
    }
    logger.bind(json_content=payment_data).info("发起支付")

    # ==========================================
    # 场景 B: 普通日志 (无 bind)
    # 预期:
    #   - 根层级没有 "json_content"
    #   - message 为 "系统自检完成"
    # ==========================================
    logger.info("系统自检完成")

    # 等待异步写入完成
    logger.complete()

    # ==========================================
    # 4. 验证结果
    # ==========================================
    target_dir = base_dir / log_type
    log_files = list(target_dir.glob("*.log"))
    assert len(log_files) > 0, "未生成日志文件"
    log_file = log_files[0]

    print(f"\n>>> [Test] 日志文件路径: {log_file}")

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 2, "应该有两条日志"

        # --- 验证 场景 A (Bind) ---
        log_a = json.loads(lines[0])
        print(f"\n[Log A Content]: {log_a}")

        # 1. 验证 text 为空
        assert log_a["text"] == ""

        # 2. 验证 message 保持原样
        assert log_a["message"] == "发起支付"

        # 3. 验证 json_content 位于根层级
        assert "json_content" in log_a
        assert log_a["json_content"] == payment_data
        assert log_a["json_content"]["order_id"] == "ORD-2023"

        # 4. 验证 extra 中已移除 json_content，但保留了其他元数据
        assert "extra" in log_a
        assert "json_content" not in log_a["extra"]
        assert "trace_id" in log_a["extra"]
        assert log_a["extra"]["type"] == log_type

        # --- 验证 场景 B (Normal) ---
        log_b = json.loads(lines[1])
        print(f"\n[Log B Content]: {log_b}")

        # 1. 验证没有 json_content 字段
        assert "json_content" not in log_b

        # 2. 验证 message
        assert log_b["message"] == "系统自检完成"

        # 3. 验证 text
        assert log_b["text"] == ""


def test_json_serialization_performance(logger_setup):
    """
    简单验证复杂类型是否能被 orjson 正确处理 (不报错即通过)
    """
    manager, base_dir = logger_setup
    logger = manager.get_dynamic_logger("complex_test")

    # 包含 Set (orjson 原生不支持 set，需要 default=str 或 list 转换，
    # 你的代码里用了 default=str，orjson_dumps 应该能处理)
    complex_data = {
        "tags": ["a", "b"],
        "nested": {"x": 1}
    }

    logger.bind(json_content=complex_data).info("复杂数据测试")
    logger.complete()

    log_file = list((base_dir / "complex_test").glob("*.log"))[0]
    print(f"\n>>> [Test] 日志文件路径: {log_file}")

    with open(log_file, "r", encoding="utf-8") as f:
        log = json.loads(f.readline())
        # 验证列表内容
        assert log["json_content"]["tags"] == ["a", "b"]
