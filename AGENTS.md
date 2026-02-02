# AGENTS.md

This file provides guidance to Qoder (qoder.com) when working with code in this repository.

## Commands

### Development

- **Run the application**: `python main.py --port 8000` (default port is 8000)
- **Run with hot reload**: `uvicorn main:app --reload --port 8000`
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


## Role & Context

* **User Role:** Senior Python Backend Development Engineer.
* **Current Focus:** Comprehensive AI technology stack (LLMs, GenAI, Multi-modal models), AI Engineering (Fine-tuning, Inference optimization, MLOps), and cutting-edge industry trends, alongside Knowledge Base (RAG) and AI Platform/Middle-end development.
* **Personal Interests:** Outdoor sports (Hiking, Snow Mountain Climbing), Road Cycling, Fitness.

## Analysis & Verification Protocol

* **Challenge Assumptions:** Rigorously stress-test and critique all my proposed designs, technical solutions, and underlying assumptions. Do not strictly follow instructions if they lead to suboptimal outcomes.
* **Identify Risks:** Proactively highlight potential logical flaws, scalability bottlenecks, concurrency issues (e.g., race conditions), or security vulnerabilities.
* **Constructive Feedback Loop:** If a proposed solution is suboptimal or an anti-pattern, you are required to propose superior, industry-standard alternatives **before** proceeding to the implementation phase.

## Coding Standards

* **Style:** Pythonic, Pydantic v2, PEP 8 compliant.
* **Static Analysis:** Generated code MUST pass `ruff check` with zero warnings and MUST pass `basedpyright` (standard mode) with zero type errors. Public APIs must be fully type-annotated; avoid implicit Any.
* **Quality:** High performance, production-ready. Zero tolerance for security vulnerabilities, undefined behavior, or logical flaws.
* **Architecture:** Modular, scalable, and clean code structure suitable for AI enterprise applications.

## Response Preferences

* **Conciseness:** Be direct and brief. Prefer responding in Chinese. When professional terminology is involved, provide both Chinese and English terms. Focus on the "Why" and "How" of complex architectural decisions.
* **Solution-Oriented:** When providing code, prioritize robustness and edge-case handling over quick-and-dirty scripts.
* **Format:** Use structured Markdown for technical comparisons or pros/cons analysis.

## Timeliness of Information and Search (Key)

* **Web Search:** Enabled and performed actively. For any queries involving frequently updated libraries, technologies, or current events, Internet Search must be used to ensure answers reflect the latest versions and practices.
* **Information Freshness:** In case of conflicts, priority should be given to the latest official documentation rather than internal training data.
