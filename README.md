# FastAPI Backend

基于 FastAPI 构建的高性能后端应用，采用分层架构设计，支持异步数据库操作、分布式任务队列和定时任务调度。

## 特性

- **FastAPI** - 高性能异步 Web 框架
- **SQLAlchemy 2.0** - 异步 ORM，支持 MySQL、PostgreSQL、Oracle
- **Celery** - 分布式任务队列
- **APScheduler** - 定时任务调度
- **Redis** - 缓存与消息队列
- **Loguru** - 结构化日志
- **JWT** - 身份认证
- **uv** - 高性能依赖管理

## 环境要求

- Python 3.12+
- Redis
- MySQL / PostgreSQL / Oracle (任选其一)

## 快速开始

### 安装依赖

```bash
# 开发环境
uv sync

# 生产环境
uv sync --no-dev --frozen
```

### 配置

1. 复制配置模板：
```bash
cp configs/.secrets.example configs/.secrets
```

2. 编辑 `configs/.secrets`，设置必要的密钥：
```ini
APP_ENV=local
AES_SECRET=your-aes-secret-key
JWT_SECRET=your-jwt-secret-key
```

3. 根据环境编辑对应的配置文件 `configs/.env.{APP_ENV}`

### 启动服务

```bash
# 开发模式 (热重载)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn main:app --host 0.0.0.0 --port 8000 --loop uvloop --http httptools
```

### 启动 Celery Worker

```bash
# 使用脚本启动
python scripts/run_celery_worker.py

# 或使用 Celery CLI
celery -A internal.utils.celery.celery_app worker -l info -Q celery_queue

# 启动定时任务调度器
celery -A internal.utils.celery.celery_app beat -l info
```

## 项目结构

```
.
├── internal/                 # 核心应用代码
│   ├── app.py               # FastAPI 应用工厂
│   ├── config/              # 配置管理
│   ├── controllers/         # API 路由控制器
│   │   ├── web/            # Web 路由 (JWT 认证)
│   │   ├── publicapi/      # 公开 API (无需认证)
│   │   ├── internalapi/    # 内部 API (签名认证)
│   │   └── serviceapi/     # 服务 API (JWT 认证)
│   ├── services/            # 业务逻辑层
│   ├── dao/                 # 数据访问层
│   ├── models/              # SQLAlchemy 模型
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── middlewares/         # ASGI 中间件
│   ├── core/                # 核心工具 (异常、认证)
│   ├── infra/               # 基础设施 (数据库、Redis)
│   ├── tasks/               # Celery 任务定义
│   └── utils/               # 内部工具
├── pkg/                      # 可复用包模块
│   ├── database/            # SQLAlchemy 工具
│   ├── logger/              # 日志配置
│   ├── crypter/             # 加密工具
│   ├── toolkit/             # 通用工具集
│   └── oss/                 # 对象存储客户端
├── configs/                  # 配置文件
├── tests/                    # 测试用例
├── scripts/                  # 脚本工具
├── ddl/                      # 数据库 DDL
└── dml/                      # 数据库 DML
```

## API 结构

| 路径前缀 | 模块 | 认证方式 |
|---------|------|---------|
| `/v1` | serviceapi | JWT |
| `/v1/public` | publicapi | 无 |
| `/v1/internal` | internalapi | 签名认证 |
| Web 路由 | web | JWT |

## 代码质量

```bash
# Lint 检查
ruff check .

# 格式化
ruff format .

# 类型检查
mypy .
```

## 测试

```bash
# 运行所有测试
pytest

# 运行集成测试 (需要 Redis + Celery)
pytest -m integration

# 运行指定测试文件
pytest tests/test_anyio_task.py -v
```

## Docker

```bash
# 构建镜像
docker build -t fastapi-backend .

# 运行容器
docker run -p 8000:8000 fastapi-backend
```

## License

MIT License
