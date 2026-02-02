import os
import time as time_module
from datetime import UTC, time, timedelta

from pkg.logger import LoggerManager


class TestLogRotationRetention:

    def test_retention_cleans_old_files(self, tmp_path):
        """
        测试 Retention: 验证旧文件被删除
        注意：loguru 的 retention 在轮转时触发，不是写日志时
        """
        # 1. 准备路径和旧文件
        base_log_dir = tmp_path / "logs"
        base_log_dir.mkdir(parents=True, exist_ok=True)
        log_dir = base_log_dir / "system"
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"log_dir: {log_dir}")

        old_file = log_dir / "2023-01-01.log"
        old_file.write_text("Old logs...")

        # 修改为 40 天前
        days_ago_40 = time_module.time() - (40 * 24 * 3600)
        os.utime(old_file, (days_ago_40, days_ago_40))

        new_file = log_dir / "2023-12-01.log"
        new_file.write_text("New logs...")

        # 2. 实例化 Manager (直接注入配置)
        # 使用 1 byte 轮转触发 retention 检查
        manager = LoggerManager(
            base_log_dir=base_log_dir,
            system_subdir="system",  # 指定子目录
            use_utc=True,
            rotation=1,  # <--- 1 byte 轮转，达到后立即轮转
            retention=timedelta(days=30),  # <--- 30天保留
            enqueue=False  # 测试环境通常不需要多进程队列
        )

        # 3. 启动
        logger = manager.setup(write_to_console=False)

        # 4. 触发多次日志写入以触发轮转
        logger.info("Trigger action 1")
        logger.info("Trigger action 2")  # 超过 1 byte，触发轮转
        time_module.sleep(0.2)  # 等待 retention 执行

        # 5. 验证
        # 注意：retention 可能在后台线程执行，需要等待
        for _ in range(10):
            if not old_file.exists():
                break
            time_module.sleep(0.1)

        assert not old_file.exists(), f"旧文件未被删除: {old_file}"
        assert new_file.exists(), f"新文件不应被删除: {new_file}"

    def test_rotation_creates_new_files(self, tmp_path):
        """
        测试 Rotation: 验证文件切割
        """
        # 确保基础目录存在
        base_log_dir = tmp_path / "logs"
        base_log_dir.mkdir(parents=True, exist_ok=True)

        # 1. 实例化 (注入 1秒 轮转策略)
        manager = LoggerManager(
            base_log_dir=base_log_dir,
            system_subdir="system",  # 指定子目录
            use_utc=True,
            rotation=timedelta(seconds=1),  # <--- 注入 1秒 轮转
            enqueue=False
        )

        logger = manager.setup(write_to_console=False)
        log_dir = base_log_dir / "system"
        print(f"log_dir: {log_dir}")

        # 2. 第一条日志
        logger.info("Log entry 1")
        files_step_1 = list(log_dir.glob("*.log*"))
        assert len(files_step_1) >= 1

        # 3. 等待超时
        time_module.sleep(1.2)

        # 4. 第二条日志
        logger.info("Log entry 2")

        files_step_2 = list(log_dir.glob("*.log*"))
        assert len(files_step_2) > len(files_step_1)

    def test_init_sets_correct_timezone(self):
        """
        测试构造函数的时区逻辑
        """
        # 1. 默认情况: 传入 UTC=True, rotation=Naive Time -> 自动转 UTC
        mgr1 = LoggerManager(use_utc=True, rotation=time(0, 0, 0))
        assert mgr1.rotation.tzinfo == UTC

        # 2. 显式本地: 传入 UTC=False -> 保持 Naive
        mgr2 = LoggerManager(use_utc=False, rotation=time(0, 0, 0))
        assert mgr2.rotation.tzinfo is None

        # 3. 混合: 传入 UTC=True, 但 rotation 已经是 UTC -> 保持 UTC
        custom_utc = time(12, 0, 0, tzinfo=UTC)
        mgr3 = LoggerManager(use_utc=True, rotation=custom_utc)
        assert mgr3.rotation == custom_utc
