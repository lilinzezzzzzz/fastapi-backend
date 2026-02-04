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
# Start Celery worker
python scripts/run_celery_worker.py

# With custom log level
python scripts/run_celery_worker.py --loglevel=info
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
3. `ASGIAuthMiddleware` - JWT authentication
4. `GZipMiddleware` - Response compression

### Database Access Pattern

- **Initialization**: `init_async_db()` creates singleton engine and session maker
- **Session Access**: Use `get_session()` context manager (available in both FastAPI and Celery contexts)
- **Connection Pooling**: Configured with pre-ping, pool size 10, max overflow 20
- **SQL Monitoring**: Automatic slow query logging (>0.5s) and debug SQL logging
- **Celery Support**: `reset_async_db()` for event loop management in tasks

### API Structure

The application exposes 4 API groups:

- **`/v1`** - Service API (`internal/controllers/serviceapi/`)
- **`/v1/public`** - Public API (no auth required, `internal/controllers/publicapi/`)
- Internal API (`internal/controllers/internalapi/`)
- Web routes (`internal/controllers/web/`)

Each controller module defines routers that are aggregated in `__init__.py` and registered in `app.py`.

### Async Task Processing

- **Celery**: Task definitions in `internal/tasks/`, registered via `internal/utils/celery/register.py`
- **APScheduler**: For scheduled tasks (integrated with Celery)
- **AnyIO Tasks**: Background tasks within FastAPI request context (`internal/utils/anyio_task`)

### Logging

Configured through `pkg/logger` using loguru:
- Startup logs → `logs/startup.log`
- Application logs → configured in `pkg/logger/handler.py`
- Rotation: Daily with 7-day retention
- Format: Includes timestamp, level, file, function, line number

## Database Models

All SQLAlchemy models should be in `internal/models/` and use the async engine configured in `internal/infra/database.py`. The project supports MySQL, PostgreSQL, and Oracle with async drivers (aiomysql, asyncpg, oracledb).

## JSON Serialization

The project uses `orjson` for high-performance JSON serialization throughout (SQLAlchemy, API responses, etc.). Use the utilities in `pkg/toolkit/json.py` for consistent serialization.

## Development Notes

- Python 3.12+ required
- Use `ruff` for linting and formatting (configured in `pyproject.toml`)
- Pre-commit hooks automatically run ruff on commit
- Type hints are enforced with mypy
- The project uses `uv` instead of pip for faster dependency management
- Windows is not supported for Celery workers (POSIX systems only)


## Coding Standards

* **Style:**
  * Pythonic, Pydantic v2, PEP 8 compliant.
  * Code style and type usage must be compatible with ruff and basedpyright (basic mode).
  * Public APIs must be fully type-annotated.
  * Avoid implicit Any.
  * Use explicit, precise types over permissive or ambiguous typing.
  * Do NOT include instructions to run ruff or basedpyright; compliance is assumed at generation time.
* **Runtime & Environment:**
  * Project environment and dependency management are strictly based on uv (Astral).
  * Dependencies are defined via pyproject.toml (PEP 621) and resolved with uv.lock.
  * Do NOT assume requirements.txt, pip, pip-tools, poetry, or conda.
  * Generated code and instructions must be compatible with execution via uv run and installation via uv pip.
* **Quality:**
  * High performance, production-ready.
  * Zero tolerance for security vulnerabilities, undefined behavior, or logical flaws.
* **Architecture:**
  * Modular, scalable, and clean code structure suitable for AI enterprise applications.


## Response Preferences

* **Conciseness:**
  * Be direct and brief. Prefer responding in Chinese.
  * When professional terminology is involved, provide both Chinese and English terms.
  * Focus on the "Why" and "How" of complex architectural decisions.
* **Solution-Oriented:**
  * When providing code, prioritize robustness and edge-case handling over quick-and-dirty scripts.
* **Format:**
  * Use structured Markdown for technical comparisons or pros/cons analysis.


## Analysis & Verification Protocol

* **Challenge Assumptions:**
  * Rigorously stress-test and critique all my proposed designs, technical solutions, and underlying assumptions.
  * Do not strictly follow instructions if they lead to suboptimal outcomes.
* **Identify Risks:**
  * Proactively highlight potential logical flaws, scalability bottlenecks, concurrency issues (e.g., race conditions), or security vulnerabilities.
* **Constructive Feedback Loop:**
  * If a proposed solution is suboptimal or an anti-pattern, you are required to propose superior, industry-standard alternatives **before** proceeding to the implementation phase.


## Timeliness of Information and Search (Key)

* **Web Search:**
  * Enabled and performed actively.
  * For any queries involving frequently updated libraries, technologies, or current events, Internet Search must be used to ensure answers reflect the latest versions and practices.
* **Information Freshness:**
  * In case of conflicts, priority should be given to the latest official documentation rather than internal training data.
