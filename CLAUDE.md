# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack FastAPI template with React frontend. Backend uses FastAPI + SQLModel + PostgreSQL + Alembic migrations. Frontend uses React + Vite + TanStack Router + TanStack Query + Tailwind CSS + shadcn/ui.

## Development Commands

### Backend (Python/FastAPI)

```bash
cd backend
uv sync                    # Install dependencies
fastapi dev app/main.py    # Run local dev server with hot reload
bash ./scripts/test.sh      # Run all tests
pytest                      # Run tests directly
alembic revision --autogenerate -m "description"  # Create migration
alembic upgrade head        # Apply migrations
```

### Frontend (React/Bun)

```bash
cd frontend
bun install                # Install dependencies
bun run dev               # Run local dev server (http://localhost:5173)
bun run build             # Production build
bun run lint              # Lint with biome
bun run generate-client   # Regenerate OpenAPI TypeScript client
bunx playwright test      # E2E tests
bunx playwright test --ui # E2E tests with UI
```

### Docker Compose Stack

```bash
docker compose watch      # Start stack with live reload (recommended)
docker compose up -d      # Start stack in background
docker compose logs        # View all logs
docker compose logs backend  # View backend logs
docker compose exec backend bash  # Shell into backend container
```

### Pre-commit Hooks

```bash
uv run prek install -f    # Install pre-commit hook
uv run prek run --all-files  # Run pre-commit checks manually
```

## Architecture

### Backend Structure (`backend/app/`)

- `main.py` - FastAPI app entry, CORS middleware, includes `api_router`
- `models.py` - SQLModel ORM models (User, Item) with Pydantic schemas
- `crud.py` - CRUD utilities
- `api/main.py` - API router aggregation
- `api/routes/` - Route handlers (login, users, items, utils, private)
- `api/deps.py` - Dependency injection (auth, db session, current user)
- `core/config.py` - Settings via pydantic-settings
- `core/security.py` - Password hashing, JWT token handling
- `core/db.py` - Database engine, session
- `alembic/` - Database migrations

### Frontend Structure (`frontend/src/`)

- `client/` - Auto-generated OpenAPI client (`sdk.gen.ts`, `schemas.gen.ts`)
- `components/` - UI components organized by feature (Admin, Common, Items, Pending, Sidebar, ui/)
- `routes/` - Page components (login, signup, recover-password, reset-password, layouts)
- TanStack Router for routing, TanStack Query for data fetching

### API Design

- Base prefix: `/api/v1/`
- Auth: JWT Bearer tokens
- Routes: `/login`, `/users`, `/items`, `/utils`, `/private`
- Health check: `/api/v1/utils/health-check/`

### Database

- PostgreSQL with SQLModel ORM
- Alembic for migrations (never modify tables directly, create migrations instead)
- After model changes: create migration, commit it, apply with `alembic upgrade head`

## Key Files

- `compose.yml` - Docker Compose services (backend, frontend, db, adminer, traefik)
- `compose.override.yml` - Development overrides (volume mounts, dev command)
- `compose.traefik.yml` - Production Traefik proxy config
- `.env` - Environment variables (secrets, domain, database config)
- `backend/pyproject.toml` - Python dependencies and tool config (ruff, mypy, ty)
- `frontend/package.json` - Node dependencies and scripts
- `.pre-commit-config.yaml` - Pre-commit hooks (ruff, mypy, biome, generate-client)

## URLs (Development)

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- Adminer (DB admin): <http://localhost:8080>
- Mailcatcher: <http://localhost:1080>
- Traefik UI: <http://localhost:8090>

## Notes

- Frontend TypeScript client is auto-generated from OpenAPI spec - do not edit directly
- Re-generate client when backend API changes: `bash ./scripts/generate-client.sh`
- `prestart` container runs alembic migrations before `backend` container starts
- Email templates use MJML format in `backend/app/email-templates/src/`

## AI development rules

- Inspect the existing implementation before modifying code.
- Follow the project's existing architecture, patterns, and dependencies.
- Do not perform unrelated refactoring.
- Do not upgrade or replace dependencies unless explicitly requested.
- Run relevant tests and checks after every meaningful change.
- Do not claim completion without showing actual command results.
- Reproduce failures and identify the root cause before fixing them.
- Do not continue to a new major development phase unless explicitly requested.
- Do not run git push, force reset, destructive cleanup, or production deployment.
- Do not delete database volumes or existing user data.
- Do not expose passwords, tokens, API keys, or secret values.
