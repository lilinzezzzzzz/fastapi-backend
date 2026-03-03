#!/bin/bash
# Celery Worker 启动脚本
#
# 使用方式：
#   ./scripts/run_celery_worker.sh
#   CELERY_CONCURRENCY=8 ./scripts/run_celery_worker.sh
#   ./scripts/run_celery_worker.sh --max-tasks-per-child=1000
#
# 环境变量：
#   CELERY_LOG_LEVEL   日志级别，默认 info
#   CELERY_CONCURRENCY 并发数，默认 4
#   CELERY_QUEUES      队列列表，默认 default,celery_queue,cron_queue

set -e

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 默认配置
LOG_LEVEL=${CELERY_LOG_LEVEL:-info}
CONCURRENCY=${CELERY_CONCURRENCY:-4}
QUEUES=${CELERY_QUEUES:-default,celery_queue,cron_queue}

# 检查 celery 是否可用
if ! command -v celery &> /dev/null; then
    echo "Error: celery not found. Please install it first:"
    echo "  uv sync  # or: pip install celery"
    exit 1
fi

# 启动 Worker
exec celery -A internal.utils.celery.celery_app worker \
    -l "$LOG_LEVEL" \
    -c "$CONCURRENCY" \
    -Q "$QUEUES" \
    --pool prefork \
    "$@"
