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
celery -A internal.utils.celery.initialization.celery_app worker -l info -c 1 -Q default,celery_queue

# Start Celery Beat (for scheduled tasks)
celery -A internal.utils.celery.initialization.celery_app beat -l info

# Production worker with memory limits
celery -A internal.utils.celery.initialization.celery_app worker \
    -l info -c 4 \
    --max-tasks-per-child 1000 \
    --max-memory-per-child 120000 \
    -Q default,celery_queue
```

## Architecture

### Directory Structure

- **`internal/`** - Core application code (business logic layer)
  - `app.py` - FastAPI application factory with lifespan management
  - `controllers/` - API route handlers organized by API type (web, publicapi, internalapi, serviceapi)
  - `services/` - Business logic layer
  - `dao/` - Data Access Objects (database operations)
  - `models/` - SQLAlchemy ORM models
  - `schemas/` - Pydantic schemas for request/response validation
  - `middlewares/` - ASGI middleware (auth, logging, etc.)
  - `config/` - Configuration management with environment-based loading
  - `core/` - Core utilities (exceptions, etc.)
  - `infra/` - Infrastructure layer (database, redis connection management)
  - `tasks/` - Celery task definitions
  - `utils/` - Internal utilities (anyio tasks, snowflake ID, signature auth, celery registration)

- **`pkg/`** - Reusable package modules (can be extracted to separate packages)
  - `database/` - SQLAlchemy utilities (engine, session, DAO base classes, query builders)
  - `logger/` - Loguru-based logging configuration
  - `crypter/` - Encryption utilities (AES)
  - `toolkit/` - Common utilities (response formatting, etc.)
  - `decorators/` - Reusable decorators
  - `oss/` - Object storage clients (OSS, S3)

- **`configs/`** - Configuration files
  - `.env.{APP_ENV}` - Environment-specific configs (dev, test, prod)
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

Configuration is loaded via `internal/config/load_config.py` and accessed through the global `settings` object.

**Important**: The `.secrets` file must contain `APP_ENV`, `AES_SECRET`, and `JWT_SECRET` at minimum. A `.secrets.example` is provided as a template.

### Application Lifecycle

The FastAPI app (`internal/app.py`) uses a lifespan context manager that initializes:

1. Logger (loguru with file rotation)
2. Database connection pool (SQLAlchemy async engine)
3. Redis connection pool
4. Signature authentication handler
5. Snowflake ID generator
6. AnyIO task manager (for background tasks)

All resources are properly cleaned up on shutdown.

### Middleware Stack (Applied in Reverse Order)

1. `ASGIRecordMiddleware` - Request/response logging
2. `CORSMiddleware` - CORS handling (if configured)
3. `ASGIAuthMiddleware` - redis token authentication
4. `GZipMiddleware` - Response compression

### Database Access Pattern

- **Initialization**: `init_async_db()` creates singleton engine and session maker (called in app lifespan)
- **Session Access**: Use `get_session()` context manager (available in both FastAPI and Celery contexts)
- **Connection Pooling**: Configured with pre-ping, pool size 10, max overflow 20
- **SQL Monitoring**: Automatic slow query logging (>0.5s) and debug SQL logging
- **Celery Support**: `reset_async_db()` for event loop management in tasks (required when using async DB in Celery workers)
- **Transaction Management**: Use `execute_transaction()` from `pkg/database/dao.py` for complex multi-step transactions

**DAO Pattern**: All database access should go through DAO classes (`internal/dao/`) which extend `BaseDao` from `pkg/database/dao.py`. The DAO provides query builders, counters, and updaters with built-in soft-delete handling.

**Query Builder Pattern**: Use the fluent query builder API (`.eq_()`, `.in_()`, `.like_()`, etc.) instead of raw SQLAlchemy queries for consistency and maintainability.

**Important**: When using database operations in Celery tasks, always call `reset_async_db()` before `init_async_db()` to avoid event loop conflicts.

### API Structure

The application exposes 4 API groups with different authentication strategies:

- **`/v1`** - Service API (`internal/controllers/serviceapi/`) - Requires JWT authentication
- **`/v1/public`** - Public API (`internal/controllers/publicapi/`) - No authentication required (whitelisted)
- **`/v1/internal`** - Internal API (`internal/controllers/internalapi/`) - Requires X-Signature authentication (see `internal/utils/signature.py`)
- Web routes (`internal/controllers/web/`) - Requires JWT authentication

Each controller module defines routers that are aggregated in `__init__.py` and registered in `app.py`.

**Authentication Whitelist**: The auth middleware (`internal/middlewares/auth.py`) whitelists paths starting with `/v1/public` or `/test`, and specific paths like `/docs`, `/auth/login`, etc.

### Async Task Processing

The project supports three async task strategies with distinct use cases:

- **Celery**: Distributed task queue for long-running tasks
  - Task definitions in `internal/tasks/`, registered via `internal/utils/celery/register.py`
  - Initialization in `internal/utils/celery/__init__.py` with worker lifecycle hooks
  - Worker startup: `python scripts/run_celery_worker.py` or use Celery CLI directly
  - Use `run_in_async()` helper to execute async code within Celery tasks (handles event loop creation)
  - Supports dynamic queue routing via `CELERY_TASK_ROUTES`

- **APScheduler**: Scheduled/periodic tasks (integrated with Celery Beat)
  - Static schedules defined in `STATIC_BEAT_SCHEDULE` in `internal/utils/celery/__init__.py`
  - Supports both cron and interval-based scheduling
  - Beat scheduler: `celery -A internal.utils.celery.initialization.celery_app beat -l info`

- **AnyIO Tasks**: Background tasks within FastAPI request lifecycle
  - Managed by `AnyioTaskHandler` in `internal/utils/anyio_task.py`
  - Initialized during app lifespan, auto-cleaned on shutdown
  - Supports task tracking, cancellation, timeout, and concurrency limiting
  - Use for request-scoped async operations (e.g., fire-and-forget notifications)

**Pattern**: Use AnyIO for lightweight request-scoped tasks, Celery for distributed/long-running operations, and APScheduler for periodic jobs.

### Logging

Configured through `pkg/logger` using loguru:
- **Startup logs**: `logs/startup.log` (configuration loading and initialization)
- **Application logs**: Configured in `pkg/logger/handler.py` with rotation
- **Rotation**: Daily with 7-day retention
- **Format**: Includes timestamp, level, file, function, line number
- **Log Formats**: Supports both JSON and text formats (configurable via `LogFormat.JSON` or `LogFormat.TEXT`)

**Important**: Logger is initialized in the app lifespan (`internal/app.py`) and should not be reconfigured elsewhere. For Celery workers, logger is initialized in the worker startup hook.

## Database Models

All SQLAlchemy models should:
- Be placed in `internal/models/` and use the async engine configured in `internal/infra/database.py`
- Extend from `ModelMixin` (from `pkg/database/base.py`) which provides:
  - Automatic ID generation using Snowflake algorithm (64-bit distributed IDs)
  - Soft delete support (`is_deleted`, `deleted_at` columns)
  - Timestamp tracking (`created_at`, `updated_at` columns)
  - Creator tracking (`creator_id` column, optional)
  - Common utility methods (`.create()`, `.to_dict()`, etc.)

**Supported Databases**: The project supports MySQL, PostgreSQL, and Oracle with async drivers (aiomysql, asyncpg, oracledb). The connection string is automatically built based on `DB_TYPE` in configuration.

**Snowflake IDs**: All models use Snowflake IDs by default (not database auto-increment). This enables distributed ID generation without database round-trips. IDs are generated at object creation time via `ModelMixin.create()`.

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
