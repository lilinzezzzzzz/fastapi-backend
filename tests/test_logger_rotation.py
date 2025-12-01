import os
import time
from datetime import time as dt_time

import pytest
from freezegun import freeze_time
from loguru import logger as global_logger

from pkg.logger_tool import LoggerManager


@pytest.fixture
def clean_logger(tmp_path, monkeypatch):
    """
    Fixture: 初始化测试环境
    """
    # 1. Patch 路径
    monkeypatch.setattr(LoggerManager, "BASE_LOG_DIR", tmp_path)
    monkeypatch.setattr(LoggerManager, "SYSTEM_LOG_DIR", tmp_path / LoggerManager.SYSTEM_LOG_TYPE)

    # 2. 默认配置
    monkeypatch.setattr(LoggerManager, "RETENTION", "30 days")
    # 默认每天 00:00 轮转
    monkeypatch.setattr(LoggerManager, "ROTATION", dt_time(0, 0, 0))

    manager = LoggerManager()

    # 3. 关键：测试时关闭异步 (enqueue=False)，确保 file write 立即发生
    # 这样 freezegun 的时间修改能立即生效，无需 sleep 等待
    manager.setup(write_to_console=False, write_to_file=True, enqueue=False)

    yield manager

    global_logger.remove()


def test_daily_rotation_at_midnight(clean_logger, tmp_path, monkeypatch):
    """
    【测试 1】: 测试跨天轮转 (00:00)
    策略：设置 ROTATION 为 00:00，利用 freezegun 跨越午夜，触发 Loguru 的轮转机制。
    """
    # 显式确保设置为 00:00 (虽然 Fixture 设了，这里强调一下意图)
    monkeypatch.setattr(LoggerManager, "ROTATION", dt_time(0, 0, 0))

    device_id = "device-daily-test"
    log_dir = tmp_path / device_id

    # --- Day 1 (23:55) ---
    with freeze_time("2025-01-01 23:55:00") as frozen_time:
        # 重新绑定 logger (enqueue=False 保持同步)
        logger = clean_logger.get_dynamic_logger(device_id, enqueue=False)
        logger.info("Log Day 1")

        # 验证 Day 1 文件存在
        assert (log_dir / "2025-01-01.log").exists()

        # --- Day 2 (00:05) ---
        # 时间流逝，跨越 00:00
        frozen_time.move_to("2025-01-02 00:05:00")

        # 写入日志。
        # 原理：Loguru 在添加 Sink 时计算出下一次轮转时间是 2025-01-02 00:00:00。
        # 现在时间是 00:05，超过了预定时间，因此触发轮转。
        logger.info("Log Day 2")

        # 验证
        assert (log_dir / "2025-01-02.log").exists(), "跨天轮转失败：未生成新日期的文件"

        content_day2 = (log_dir / "2025-01-02.log").read_text(encoding="utf-8")
        assert "Log Day 2" in content_day2
        assert "Log Day 1" not in content_day2

        # 验证旧文件依然存在且未被修改
        assert (log_dir / "2025-01-01.log").exists()

    print(f"\n[Time Test] Success. Files: {[f.name for f in log_dir.glob('*.log')]}")


def test_retention_cleanup(clean_logger, tmp_path, monkeypatch):
    """
    【测试 2】: 测试过期清理
    策略：将 Rotation 阈值设得极小 (100 Bytes)，强制触发轮转。
    因为 Loguru 只有在发生轮转时才会顺便检查并删除过期文件。
    """
    # 技巧：通过极小的 Size 轮转来激活 Retention 检查逻辑
    monkeypatch.setattr(LoggerManager, "ROTATION", 10)  # 100 Bytes

    device_id = "device-retention-test"
    log_dir = tmp_path / device_id
    log_dir.mkdir(parents=True, exist_ok=True)

    # 1. 伪造一个 31 天前的日志文件
    old_file = log_dir / "2020-01-01.log"
    old_file.write_text("Old log content needs to be deleted.")

    # 修改文件时间 (mtime) 到 31 天前
    days_31_ago = time.time() - (31 * 24 * 3600) - 100
    os.utime(old_file, (days_31_ago, days_31_ago))

    print(f"\n[Retention Setup] Created: {old_file}")

    # 2. 获取 Logger
    logger = clean_logger.get_dynamic_logger(device_id, enqueue=False)

    # 3. 写入足够多的数据，触发 100 Bytes 的轮转
    # 只要触发了 Rotation，Loguru 就会去扫描目录清理旧文件
    for i in range(10):
        logger.info(f"Trigger rotation data {i} " * 5)

    # 4. 验证
    assert not old_file.exists(), f"Retention 失败: 旧文件 {old_file.name} 未被删除"

    # 确认新日志还在
    assert len(list(log_dir.glob("*.log"))) > 0

    print("[Retention Test] Pass. Old file deleted.")
