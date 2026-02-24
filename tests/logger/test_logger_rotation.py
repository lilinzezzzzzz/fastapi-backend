import os
import time as time_module
from datetime import UTC, time, timedelta

from pkg.logger import LoggerHandler


class TestLogRotationRetention:

    def test_retention_cleans_old_files(self, tmp_path):
        """
        测试 Retention: 验证旧文件被删除
        注意：loguru 的 retention 在轮转时触发，不是写日志时
        """
        # 1. 准备路径和旧文件
        base_log_dir = tmp_path / "logs"
        base_log_dir.mkdir(parents=True, exist_ok=True)
        log_dir = base_log_dir / "default"
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
        manager = LoggerHandler(
            base_log_dir=base_log_dir,
            use_subdir=True,  # 使用子目录
            timezone="UTC",
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
        manager = LoggerHandler(
            base_log_dir=base_log_dir,
            use_subdir=True,  # 使用子目录
            timezone="UTC",
            rotation=timedelta(seconds=1),  # <--- 注入 1秒 轮转
            enqueue=False
        )

        logger = manager.setup(write_to_console=False)
        log_dir = base_log_dir / "default"
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
        from zoneinfo import ZoneInfo

        # 1. 默认情况: timezone=UTC, rotation 无时区 -> 自动使用 UTC
        mgr1 = LoggerHandler(timezone="UTC", rotation=time(0, 0, 0))
        assert mgr1.rotation.tzinfo.key == "UTC"

        # 2. 非UTC时区: timezone=Asia/Shanghai, rotation 无时区 -> 自动使用 Asia/Shanghai
        mgr2 = LoggerHandler(timezone="Asia/Shanghai", rotation=time(0, 0, 0))
        assert mgr2.rotation.tzinfo == ZoneInfo("Asia/Shanghai")

        # 3. 混合: timezone=UTC, rotation 已带 UTC 时区 -> 正常
        custom_utc = time(12, 0, 0, tzinfo=UTC)
        mgr3 = LoggerHandler(timezone="UTC", rotation=custom_utc)
        assert mgr3.rotation == custom_utc

        # 4. 验证 timezone 属性 (使用 timedelta rotation 避免时区检查)
        mgr4 = LoggerHandler(timezone="Asia/Shanghai", rotation=timedelta(days=1))
        assert mgr4.timezone == ZoneInfo("Asia/Shanghai")

        # 5. 验证字符串和 ZoneInfo 对象都可以
        mgr5 = LoggerHandler(timezone=ZoneInfo("America/New_York"), rotation=timedelta(days=1))
        assert mgr5.timezone == ZoneInfo("America/New_York")

    def test_rotation_timezone_must_match(self):
        """
        测试 rotation 时区必须与 timezone 一致
        """
        from zoneinfo import ZoneInfo

        import pytest

        # rotation 时区与 timezone 不一致应该抛出 ValueError
        with pytest.raises(ValueError, match="rotation timezone .* must match timezone"):
            LoggerHandler(timezone="UTC", rotation=time(0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

        # timezone=Asia/Shanghai, rotation 带 UTC 时区 -> 抛出异常
        with pytest.raises(ValueError, match="rotation timezone .* must match timezone"):
            LoggerHandler(timezone="Asia/Shanghai", rotation=time(0, 0, 0, tzinfo=UTC))

        # rotation 无时区，自动使用 timezone -> 正常
        mgr = LoggerHandler(timezone="Asia/Shanghai", rotation=time(8, 0, 0))
        assert mgr.rotation.tzinfo == ZoneInfo("Asia/Shanghai")
        assert mgr.rotation.hour == 8

    def test_datetime_utc_support(self):
        """
        测试 datetime.UTC 作为 timezone 参数
        """
        from datetime import UTC
        from zoneinfo import ZoneInfo

        # datetime.UTC 应该被正确转换为 ZoneInfo("UTC")
        mgr = LoggerHandler(timezone=UTC, rotation=timedelta(days=1))
        assert mgr.timezone == ZoneInfo("UTC")

        # 与 rotation 搭配使用
        mgr2 = LoggerHandler(timezone=UTC, rotation=time(0, 0, 0))
        assert mgr2.rotation.tzinfo.key == "UTC"

    def test_use_subdir_parameter(self, tmp_path):
        """
        测试 use_subdir 参数
        """
        base_log_dir = tmp_path / "logs"
        base_log_dir.mkdir(parents=True, exist_ok=True)

        # 1. use_subdir=True: 日志按 namespace 存放在子目录
        mgr1 = LoggerHandler(
            base_log_dir=base_log_dir,
            use_subdir=True,  # 显式指定使用子目录
            rotation=timedelta(days=1),
            enqueue=False
        )
        logger1 = mgr1.setup(write_to_console=False)
        logger1.info("test")

        # 默认日志应该在 base_log_dir/default 下
        default_log_dir = base_log_dir / "default"
        assert default_log_dir.exists()
        assert len(list(default_log_dir.glob("*.log"))) >= 1

        # 2. use_subdir=False: 所有日志在 base_log_dir 下
        base_log_dir2 = tmp_path / "logs2"
        base_log_dir2.mkdir(parents=True, exist_ok=True)

        mgr2 = LoggerHandler(
            base_log_dir=base_log_dir2,
            use_subdir=False,
            rotation=timedelta(days=1),
            enqueue=False
        )
        logger2 = mgr2.setup(write_to_console=False)
        logger2.info("test")

        # 系统日志应该直接在 base_log_dir 下
        assert not (base_log_dir2 / "default").exists()
        assert len(list(base_log_dir2.glob("*.log"))) >= 1

        # 3. 动态 logger 的子目录行为
        mgr3 = LoggerHandler(
            base_log_dir=tmp_path / "logs3",
            use_subdir=True,
            rotation=timedelta(days=1),
            enqueue=False
        )
        mgr3.setup(write_to_console=False, write_to_file=False)
        dynamic_logger = mgr3.get_dynamic_logger("my_module")
        dynamic_logger.info("test dynamic")

        # 动态日志应该在 base_log_dir/my_module 下
        my_module_dir = tmp_path / "logs3" / "my_module"
        assert my_module_dir.exists(), f"目录不存在: {my_module_dir}"

        # 4. use_subdir=False 时的动态 logger
        mgr4 = LoggerHandler(
            base_log_dir=tmp_path / "logs4",
            use_subdir=False,
            rotation=timedelta(days=1),
            enqueue=False
        )
        mgr4.setup(write_to_console=False, write_to_file=False)
        dynamic_logger2 = mgr4.get_dynamic_logger("another_module")
        dynamic_logger2.info("test dynamic")

        # 动态日志也应该在 base_log_dir 下（不创建子目录）
        another_module_dir = tmp_path / "logs4" / "another_module"
        assert not another_module_dir.exists(), f"不应存在子目录: {another_module_dir}"
        assert len(list((tmp_path / "logs4").glob("*.log"))) >= 1
