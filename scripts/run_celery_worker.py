from internal.celery_tasks.__init__ import default_celery_client, default_queue
import os
import sys


def main() -> None:
    # 显式禁止 Windows 环境运行
    if os.name == "nt":
        print("Error: This worker script does not support Windows. Please use a POSIX system (Linux/macOS).")
        sys.exit(1)

    # 可用环境变量覆盖，括号内为默认值
    queues = default_queue
    loglevel = "debug"

    pool = "prefork"
    concurrency = "4"

    # 允许通过命令行追加更多 Celery 参数（优先级最高）
    # 用法示例：python tools/run_celery_worker.py --logfile=worker.log
    extra_cli_args = sys.argv[1:]

    argv = [
        "worker",
        "-l", loglevel,
        "-Q", queues,
        "--pool", pool,
        "--concurrency", str(concurrency),
        # 移除了 minimal_flags (*minimal_flags)，因为 Linux 下通常需要 gossip/heartbeat
        *extra_cli_args,
    ]

    # 用 worker_main 更稳（避免 Click 解析 "celery" 命令名的问题）
    default_celery_client.app.worker_main(argv)


if __name__ == "__main__":
    main()