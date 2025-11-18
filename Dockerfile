FROM python:3.12.9-slim

ENV TZ=Etc/UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/root/.local/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT=".venv"

# 先拷贝依赖声明文件，提高缓存命中率
# 如果你有 uv.lock，就顺便一起 COPY
COPY pyproject.toml uv.lock ./

# 使用 uv 安装依赖到项目本地虚拟环境 .venv
RUN uv sync --frozen --no-cache --no-default-groups

# 再拷贝业务代码（避免改代码就重新装依赖）
COPY . .

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ss -lnt | grep -q 8000 || exit 1

# 使用 uv run 启动 FastAPI 应用（会自动在 .venv 里跑）
ENTRYPOINT ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop", "--http", "httptools", "--access-log"]