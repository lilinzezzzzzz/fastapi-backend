# AGENTS.md

This file provides guidance to Qoder (qoder.com) when working with code in this repository.

## Commands

### Development

- **Run the application**: `python main.py --port 8090` (default port is 8090)
- **Run with hot reload**: `uvicorn main:app --reload --port 8090`
- **Run tests**: `pytest` (all tests) or `pytest tests/test_<name>.py` (single test file)
- **Run integration tests**: `pytest -m integration` (requires Celery Worker and Redis)
- **Lint code**: `ruff check .`
- **Format code**: `ruff format .`
- **Type check**: `mypy .`

### Celery Workers (Linux/macOS only)

- **Run Celery worker**: `python scripts/run_celery_worker.py`
- Note: Celery workers do not support Windows. Use POSIX systems (Linux/macOS).

### Dependency Management (using uv)

- **Install dependencies**: `uv sync` (syncs all dependencies from uv.lock)
- **Install dev dependencies**: `uv sync --group dev`
- **Add a new dependency**: `uv add <package-name>`
- **Remove a dependency**: `uv remove <package-name>`

### Docker

- **Build image**: `docker build -t fastapi-backend .`
- **Run container**: `docker run -p 8000:8000 fastapi-backend`

## Architecture

This is a FastAPI backend application with a layered architecture following Go-style project structure (internal/,
pkg/).

### Project Structure

```
internal/          # Application-specific code (not reusable)
├── app.py         # FastAPI app factory with lifespan, routers, middleware, exception handlers
├── config/        # Configuration management (env files: .env.{local,dev,test,prod}, .secrets)
├── controllers/   # API route handlers organized by API type:
│   ├── web/       # Web frontend APIs
│   ├── publicapi/ # Public APIs
│   ├── internalapi/ # Internal APIs
│   └── serviceapi/  # Service-to-service APIs
├── services/      # Business logic layer
├── dao/           # Data Access Objects (uses pkg/database builders)
├── models/        # SQLAlchemy ORM models
├── schemas/       # Pydantic models for request/response
├── dtos/          # Data Transfer Objects
├── middlewares/   # Custom ASGI middlewares (auth, logging)
├── core/          # Core utilities (logger, exception, signature, snowflake ID)
├── infra/         # Infrastructure integrations (database, redis, celery, apscheduler, anyio tasks, storage)
└── tasks/         # Celery task definitions

pkg/               # Reusable packages (can be extracted to separate libraries)
├── database/      # Database abstractions: QueryBuilder, UpdateBuilder, CountBuilder, BaseDao
├── crypto/        # Cryptography utilities (AES encryption/decryption)
├── oss/           # Object storage clients (Aliyun OSS, AWS S3)
├── async_*.py     # Async utilities (cache, celery, context, grpc, hasher, http client, logger, openai)
└── toolkit/       # General utilities

configs/           # Environment configuration files (.env.{env}, .secrets)
tests/             # Test files (pytest with async support)
ddl/               # Database schema definitions
dml/               # Database data manipulation scripts
scripts/           # Utility scripts (e.g., run_celery_worker.py)
```

### Key Architecture Patterns

**1. Configuration Management**

- Multi-environment support via `APP_ENV` (local, dev, test, prod)
- Configuration files: `configs/.env.{APP_ENV}` + `configs/.secrets`
- Sensitive values can be encrypted with `ENC(...)` format and are auto-decrypted using `AES_SECRET`
- Database type abstraction: supports MySQL, PostgreSQL, Oracle via `DB_TYPE` setting

**2. Database Layer (pkg/database)**

- **QueryBuilder**: Chainable query builder with soft-delete support, pagination, sorting
- **UpdateBuilder**: Chainable update builder for both ORM instances and class-based updates
- **CountBuilder**: Count queries with optional distinct and column-specific counting
- **BaseDao**: Generic DAO base class with common CRUD operations
- **execute_transaction**: Transaction helper for complex multi-step operations with proper flush/commit handling

**3. Application Lifecycle (internal/app.py:lifespan)**

- Initialization order: Logger → Database → Redis → Signature Auth → Snowflake ID → AnyIO Tasks
- Cleanup on shutdown: Database, Redis, AnyIO Tasks

**4. Middleware Stack (applied in reverse order)**

- RecordMiddleware: Request/response logging
- CORSMiddleware: CORS handling (if configured)
- AuthMiddleware: Token authentication
- GZipMiddleware: Response compression

**5. Dependency Injection**

- Database sessions use `SessionProvider` pattern for async session management
- DAOs receive `session_provider` via constructor for testability

**6. Code Style**

- Line length: 120 characters
- Target Python: 3.12+
- Enabled ruff rules: E/W (pycodestyle), F (pyflakes), I (isort), B (bugbear), UP (pyupgrade)
- Import sorting via ruff with `combine-as-imports = true`

## Important Notes

- **Windows Limitation**: Celery workers are not supported on Windows. Use WSL, Docker, or a Linux/macOS environment for
  Celery tasks.
- **Secrets Encryption**: Passwords in config files can be encrypted as `ENC(ciphertext)` and will be auto-decrypted at
  startup using `AES_SECRET`.
- **Soft Deletes**: Models inherit from `ModelMixin` which provides soft-delete support via `deleted_at` column. Use
  `querier_inc_deleted` to query deleted records.
- **Testing**: Integration tests marked with `@pytest.mark.integration` require full Celery Worker and Redis setup.

## General Rules

- **Language**: You must always communicate in Chinese (Simplified). Translate any technical explanation into Chinese
  unless asked otherwise.
- **语言**：必须始终使用简体中文回答所有问题。
