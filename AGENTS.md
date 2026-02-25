# AGENTS.md

This file provides guidance to Qoder (qoder.com) when working with code in this repository.

## Project Overview

FastAPI backend application built with Python 3.12+ using a layered architecture pattern. The project uses `uv` for dependency management and includes Celery for async task processing, Redis for caching, and SQLAlchemy for database operations with support for MySQL, PostgreSQL, and Oracle.

## Commands

### Development Setup
```bash
# Install dependencies (development)
uv sync

# Install production dependencies only
uv sync --no-dev --frozen
```

### Code Quality
```bash
# Run linter and formatter (pre-commit hooks)
ruff check .
ruff format .

# Type checking
mypy .
```

### Testing
```bash
# Run all tests
pytest

# Run tests with specific markers
pytest -m integration  # Integration tests (requires Celery + Redis)

# Run specific test file
pytest tests/test_anyio_task.py
```

### Running the Application
```bash
# Development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production server (with uvloop and httptools)
uvicorn main:app --host 0.0.0.0 --port 8000 --loop uvloop --http httptools

# Using Docker
docker build -t fastapi-backend .
docker run -p 8000:8000 fastapi-backend
```

### Celery Worker
```bash
# Start Celery worker (recommended method)
python scripts/run_celery_worker.py

# Start worker with Celery CLI (development)
celery -A internal.utils.celery.celery_app worker -l info -c 1 -Q default,celery_queue

# Start Celery Beat (for scheduled tasks)
celery -A internal.utils.celery.celery_app beat -l info

# Production worker with memory limits
celery -A internal.utils.celery.celery_app worker \
    -l info -c 4 \
    --max-tasks-per-child 1000 \
    --max-memory-per-child 120000 \
    -Q default,celery_queue
```

## Architecture

### Directory Structure

- **`internal/`** - Core application code (business logic layer)
  - `app.py` - FastAPI application factory with lifespan management
  - `controllers/` - API route handlers organized by API type
    - `api/` - Main API routes (`/v1`), requires JWT authentication
    - `public/` - Public API routes (`/v1/public`), no authentication required
    - `internal/` - Internal API routes (`/v1/internal`), requires signature authentication
  - `services/` - Business logic layer
  - `dao/` - Data Access Objects (database operations)
  - `models/` - SQLAlchemy ORM models
  - `schemas/` - Pydantic schemas for request/response validation
  - `dtos/` - Data Transfer Objects for internal data structures
  - `middlewares/` - ASGI middleware (auth, logging, etc.)
  - `config/` - Configuration management with environment-based loading
  - `core/` - Core utilities (auth, exceptions)
  - `infra/` - Infrastructure layer (database, redis connection management)
  - `tasks/` - Shared task logic (reusable by Celery and APScheduler)
  - `utils/` - Internal utilities
    - `celery/` - Celery app initialization and task registration
    - `apscheduler/` - APScheduler configuration
    - `redis/` - Redis utilities
    - `vector/` - Vector database utilities
    - `anyio_task.py` - AnyIO task handler
    - `signature.py` - Signature authentication
    - `snowflake.py` - Snowflake ID generator

- **`pkg/`** - Reusable package modules (can be extracted to separate packages)
  - `database/` - SQLAlchemy utilities (engine, session, DAO base classes, query builders)
  - `logger/` - Loguru-based logging configuration
  - `crypter/` - Encryption utilities (AES)
  - `toolkit/` - Common utilities (response formatting, JWT, JSON, etc.)
  - `decorators/` - Reusable decorators
  - `oss/` - Object storage clients (Aliyun OSS, S3)
  - `third_party_auth/` - Third-party login strategies (WeChat, etc.)

- **`configs/`** - Configuration files
  - `.env.{APP_ENV}` - Environment-specific configs (local, dev, test, prod)
  - `.secrets` - Sensitive credentials (contains APP_ENV, AES_SECRET, JWT_SECRET, etc.)

- **`tests/`** - Test suite with pytest
- **`scripts/`** - Utility scripts (Celery worker launcher, etc.)
- **`ddl/`** - Database DDL scripts
- **`dml/`** - Database DML scripts

### Configuration System

The application uses a sophisticated multi-environment configuration system:

1. **Environment Detection**: `APP_ENV` variable determines which environment to load (local, dev, test, prod)
2. **File Loading Order**: `.env.{APP_ENV}` → `.secrets` (later files override earlier ones)
3. **Required Files**: Both `configs/.secrets` and `configs/.env.{APP_ENV}` must exist
4. **Secret Decryption**: Passwords can be encrypted with `ENC(encrypted_value)` format and are auto-decrypted using AES_SECRET
5. **Database Support**: Dynamically generates SQLAlchemy URIs for MySQL, PostgreSQL, or Oracle based on DB_TYPE
6. **Read Replica Support**: Optional read replica configuration for database read/write splitting

Configuration is loaded via `internal/config/loader.py` and accessed through the global `settings` object.

**Important**: The `.secrets` file must contain `APP_ENV`, `AES_SECRET`, and `JWT_SECRET` at minimum. A `.secrets.example` is provided as a template.

### Application Lifecycle

The FastAPI app (`internal/app.py`) uses a lifespan context manager that initializes:

1. Settings configuration
2. Logger (loguru with file rotation)
3. Database connection pool (SQLAlchemy async engine with optional read replica)
4. Redis connection pool
5. Signature authentication handler
6. Snowflake ID generator
7. AnyIO task manager (for background tasks)

All resources are properly cleaned up on shutdown.

### Middleware Stack (Applied in Reverse Order)

1. `ASGIRecordMiddleware` - Request/response logging
2. `CORSMiddleware` - CORS handling (if configured)
3. `ASGIAuthMiddleware` - Token/Signature authentication
4. `GZipMiddleware` - Response compression

### Database Access Pattern

- **Initialization**: `init_async_db()` creates singleton engine and session maker (called in app lifespan)
- **Session Access**: Use `get_session()` context manager for write operations, `get_read_session()` for read operations
- **Connection Pooling**: Configured with pre-ping, pool size 10, max overflow 20
- **Read Replica**: Optional read-only replica with larger pool (20 connections, 30 max overflow)
- **SQL Monitoring**: Automatic slow query logging (>0.5s) and debug SQL logging
- **Celery Support**: `reset_async_db()` for event loop management in tasks (required when using async DB in Celery workers)
- **Transaction Management**: Use `execute_transaction()` from `pkg/database/dao.py` for complex multi-step transactions

**DAO Pattern**: All database access should go through DAO classes (`internal/dao/`) which extend `BaseDao` from `pkg/database/dao.py`. The DAO provides query builders, counters, and updaters with built-in soft-delete handling.

**Query Builder Pattern**: Use the fluent query builder API (`.eq_()`, `.in_()`, `.like_()`, etc.) instead of raw SQLAlchemy queries for consistency and maintainability.

**Important**: When using database operations in Celery tasks, always call `reset_async_db()` before `init_async_db()` to avoid event loop conflicts.

### API Structure

The application exposes 3 API groups with different authentication strategies:

- **`/v1`** - Main API (`internal/controllers/api/`) - Requires JWT authentication
- **`/v1/public`** - Public API (`internal/controllers/public/`) - No authentication required (whitelisted)
- **`/v1/internal`** - Internal API (`internal/controllers/internal/`) - Requires X-Signature authentication (see `internal/utils/signature.py`)

Each controller module defines routers that are aggregated in `__init__.py` and registered in `app.py`.

**Authentication Whitelist**: The auth middleware (`internal/middlewares/auth.py`) whitelists:
- Paths starting with `/v1/public`
- Specific paths: `/auth/login`, `/auth/register`, `/auth/wechat/login`, `/docs`, `/openapi.json`

### Async Task Processing

The project supports three async task strategies with distinct use cases:

- **Celery**: Distributed task queue for long-running tasks
  - Task definitions in `internal/tasks/`, registered via `internal/utils/celery/tasks.py`
  - Initialization in `internal/utils/celery/__init__.py` with worker lifecycle hooks
  - Worker startup: `python scripts/run_celery_worker.py` or use Celery CLI directly
  - Use `run_in_async()` helper to execute async code within Celery tasks (handles event loop creation)
  - Supports dynamic queue routing via `CELERY_TASK_ROUTES`

- **APScheduler**: Scheduled/periodic tasks (integrated with Celery Beat)
  - Static schedules defined in `STATIC_BEAT_SCHEDULE` in `internal/utils/celery/__init__.py`
  - Supports both cron and interval-based scheduling
  - Beat scheduler: `celery -A internal.utils.celery.celery_app beat -l info`

- **AnyIO Tasks**: Background tasks within FastAPI request lifecycle
  - Managed by `AnyioTaskHandler` in `pkg/toolkit/async_task.py`
  - Initialized during app lifespan, auto-cleaned on shutdown
  - Supports task tracking, cancellation, timeout, and concurrency limiting
  - Use for request-scoped async operations (e.g., fire-and-forget notifications)

**Pattern**: Use AnyIO for lightweight request-scoped tasks, Celery for distributed/long-running operations, and APScheduler for periodic jobs.

### Logging

Configured through `pkg/logger` using loguru:
- **Startup logs**: `logs/startup.log` (configuration loading and initialization)
- **Application logs**: Configured in `pkg/logger/handler.py` with rotation
- **Rotation**: Daily with 30-day retention (configurable)
- **Format**: Supports both JSON and text formats (configurable via `LogFormat.JSON` or `LogFormat.TEXT`)
- **Trace ID**: Automatic trace ID propagation via context

**Important**: Logger is initialized in the app lifespan (`internal/app.py`) and should not be reconfigured elsewhere. For Celery workers, logger is initialized in the worker startup hook.

## Database Models

All SQLAlchemy models should:
- Be placed in `internal/models/` and use the async engine configured in `internal/infra/database.py`
- Extend from `ModelMixin` (from `pkg/database/base.py`) which provides:
  - Automatic ID generation using Snowflake algorithm (64-bit distributed IDs)
  - Soft delete support (`deleted_at` column)
  - Timestamp tracking (`created_at`, `updated_at` columns)
  - Creator/updater tracking (`creator_id`, `updater_id` columns)
  - Common utility methods (`.create()`, `.save()`, `.update()`, `.soft_delete()`, `.to_dict()`, etc.)

**Supported Databases**: The project supports MySQL, PostgreSQL, and Oracle with async drivers (aiomysql, asyncpg, oracledb). The connection string is automatically built based on `DB_TYPE` in configuration.

**Snowflake IDs**: All models use Snowflake IDs by default (not database auto-increment). This enables distributed ID generation without database round-trips. IDs are generated at object creation time via `ModelMixin.create()`.

## Redis Integration

Redis is used for:
- **Token Storage**: User authentication tokens stored with TTL
- **Cache**: General-purpose caching via `CacheDao` in `internal/infra/redis/dao.py`
- **Celery Broker**: Message broker for Celery task queue

**Access Pattern**: Use `redis_client` from `internal/infra/redis/connection.py` for Redis operations. The client is wrapped in `RedisClient` from `pkg/toolkit/redis_client.py` for convenience.

## Third-Party Authentication

The project includes a modular third-party authentication system in `pkg/third_party_auth/`:
- **Strategy Pattern**: Each third-party login provider implements `BaseThirdPartyAuthStrategy`
- **WeChat Login**: Built-in support for WeChat login (`pkg/third_party_auth/strategies/wechat.py`)
- **Factory Pattern**: Use `ThirdPartyAuthFactory` to get the appropriate strategy for each platform

## JSON Serialization

The project uses `orjson` for high-performance JSON serialization throughout (SQLAlchemy, API responses, Celery task payloads, etc.).

**Custom JSON Types**: SQLAlchemy columns can use `pkg/database/types.py` JSON types which provide automatic serialization/deserialization with orjson. This includes support for Pydantic models, dataclasses, and nested structures.

**API Responses**: All FastAPI responses use orjson automatically. Use utilities in `pkg/toolkit/json.py` for manual JSON operations to maintain consistency.

## Development Notes

- **Python Version**: Python 3.12+ required (uses modern type hints like `type[T]` and PEP 695 generic syntax)
- **Package Manager**: Use `uv` instead of pip for faster dependency management
  - Install dependencies: `uv sync` (dev) or `uv sync --no-dev --frozen` (prod)
  - Run commands: `uv run <command>` or activate venv: `source .venv/bin/activate`
- **Code Quality Tools**:
  - `ruff` for linting and formatting (configured in `pyproject.toml`)
  - Pre-commit hooks automatically run ruff on commit (`.pre-commit-config.yaml`)
  - Type hints enforced with mypy (`mypy .`)
- **Platform Support**: Windows is not supported for Celery workers (POSIX systems only) due to Celery's Unix-only dependencies
- **Testing**: Run tests with `pytest`, integration tests marked with `@pytest.mark.integration` require Redis and Celery
