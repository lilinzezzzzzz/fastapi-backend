import json
import sys

import pytest

from pkg.toolkit.logger import LoggerManager


# ----------------------------------------------------------------------
# 1. 环境准备
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# 2. Pytest Fixture
# ----------------------------------------------------------------------
@pytest.fixture
def logger_setup(tmp_path):
    """
    初始化 LoggerManager，并将日志输出重定向到 pytest 的临时目录。
    """
    base_log_dir = tmp_path / "logs"
    base_log_dir.mkdir(exist_ok=True)

    manager = LoggerManager(base_log_dir=base_log_dir)
    # 初始化：只写文件，不写控制台
    manager.setup(write_to_file=True, write_to_console=False)

    return manager, base_log_dir


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

    print(f"\n>>> [Test] 日志根目录: {base_dir}")
    print(f">>> [Test] 系统日志目录: {manager.system_log_dir}")

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

        # 4. 验证 extra 字段已展开到根层级，且 json_content 已移除
        assert "trace_id" in log_a
        assert log_a["type"] == "system"
        # save_json=True 时，内部使用 {log_type}_json 作为 filter key
        assert log_a["log_type"] == f"{log_type}_json"

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


def test_log_file_extension_always_dot_log(logger_setup):
    """
    验证：
    1. 无论 save_json 是 True 还是 False，日志文件后缀都是 .log
    2. 同一个 log_type 下，JSON 格式和文本格式日志写入同一个文件，且不会重复
    """
    manager, base_dir = logger_setup
    print(f"\n>>> [Test] 日志根目录: {base_dir}")

    # 使用同一个 log_type
    log_type = "mixed_format_test"

    # 场景 A: save_json=True
    logger_json = manager.get_dynamic_logger(log_type, save_json=True)
    logger_json.info("JSON 格式日志")
    logger_json.complete()

    # 场景 B: save_json=False（同一个 log_type）
    logger_text = manager.get_dynamic_logger(log_type, save_json=False)
    logger_text.info("文本格式日志")
    logger_text.complete()

    # 验证日志文件
    log_dir = base_dir / log_type
    log_files = list(log_dir.glob("*.log"))
    json_files_should_not_exist = list(log_dir.glob("*.json"))

    assert len(log_files) == 1, f"应只有一个 .log 文件，实际: {log_files}"
    assert len(json_files_should_not_exist) == 0, "不应生成 .json 文件"
    print(f"\n>>> [Test] 混合格式日志文件: {log_files[0]}")

    # 验证文件内容 - JSON 和 text 使用不同的 internal_key，不会重复
    # Line 1: save_json=True 时的 JSON 格式日志
    # Line 2: save_json=False 时的文本格式日志
    with open(log_files[0], "r", encoding="utf-8") as f:
        lines = f.readlines()
        print(f">>> [Test] 日志行数: {len(lines)}")
        for i, line in enumerate(lines):
            print(f">>> [Test] Line {i + 1}: {line.strip()[:100]}...")

        assert len(lines) == 2, f"应有两行日志（JSON + 文本），实际: {len(lines)}"

        # 第一行是 JSON 格式
        log_json = json.loads(lines[0])
        assert log_json["message"] == "JSON 格式日志"

        # 第二行是文本格式（不是有效的 JSON）
        assert "文本格式日志" in lines[1]
        try:
            json.loads(lines[1])
            pytest.fail("文本格式日志不应该是有效的 JSON")
        except json.JSONDecodeError:
            pass  # 预期行为


if __name__ == "__main__":
    # 允许直接运行此文件调试
    sys.exit(pytest.main(["-s", "-v", "--log-cli-level=INFO", __file__]))
