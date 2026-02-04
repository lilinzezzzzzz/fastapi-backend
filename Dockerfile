FROM python:3.12.9-slim

# 基础环境变量
ENV TZ=Etc/UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# uv 虚拟环境配置
# UV_INDEX_URL: 使用阿里云 PyPI 镜像源加速包下载
# UV_COMPILE_BYTECODE: 编译字节码加快启动速度
# UV_LINK_MODE: copy 模式更适合容器环境（避免硬链接问题）
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

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
