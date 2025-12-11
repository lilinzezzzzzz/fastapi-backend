FROM python:3.12.9-slim

ENV TZ=Etc/UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 全局激活虚拟环境
# 而且 uv sync 也会自动检测到 VIRTUAL_ENV 并在其中安装，不需要手动指定环境位置
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./

# 安装依赖
# 此时 VIRTUAL_ENV 已经生效，uv 会自动把包安装到 /app/.venv 中
RUN uv sync --frozen --no-cache --no-default-groups

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ss -lnt | grep -q 8000 || exit 1

# 启动命令
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop", "--http", "httptools", "--access-log"]
