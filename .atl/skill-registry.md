# Skill Registry - back-cv-analyzer

**Generated**: Sat Apr 04 2026
**Mode**: engram

## User-Level Skills

### SDD Phases

| Skill | Description | Trigger |
|-------|-------------|---------|
| sdd-explore | Explore and investigate ideas | When the orchestrator launches you to think through a feature, investigate the codebase, or clarify requirements |
| sdd-propose | Create change proposal | When the orchestrator launches you to create or update a proposal for a change |
| sdd-spec | Write specifications | When the orchestrator launches you to write or update specs for a change |
| sdd-design | Create technical design | When the orchestrator launches you to write or update the technical design for a change |
| sdd-tasks | Break down into tasks | When the orchestrator launches you to create or update the task breakdown for a change |
| sdd-apply | Implement tasks | When the orchestrator launches you to implement one or more tasks from a change |
| sdd-verify | Validate implementation | When the orchestrator launches you to verify a completed (or partially completed) change |
| sdd-archive | Archive completed change | When the orchestrator launches you to archive a change after implementation and verification |
| sdd-onboard | Guided SDD walkthrough | When the orchestrator launches you to onboard a user through the full SDD cycle |
| sdd-init | Initialize SDD context | When user wants to initialize SDD in a project |

### Utilities

| Skill | Description | Trigger |
|-------|-------------|---------|
| issue-creation | Create GitHub issues | Creating a GitHub issue, reporting a bug, or requesting a feature |
| branch-pr | Create PRs and branches | Creating a pull request, opening a PR, or preparing changes for review |
| judgment-day | Adversarial code review | "judgment day", "judgment-day", "review adversarial", "dual review", "doble review", "juzgar", "que lo juzguen" |
| skill-creator | Create new AI skills | Creating a new skill, adding agent instructions, or documenting patterns for AI |

### Domain-Specific

| Skill | Description | Trigger |
|-------|-------------|---------|
| go-testing | Go testing patterns | Writing Go tests, using teatest, or adding test coverage |

## Project Conventions

- **AGENTS.md**: Not found
- **CLAUDE.md**: Not found
- **No project-specific skills detected**

## Compact Rules

**Python / FastAPI**:
- Use async/await for all database and I/O operations
- Pydantic models for validation and settings (BaseSettings with .env file)
- SQLAlchemy 2.0 async models with mapped_column (declarative)
- Dependency injection via FastAPI's Depends() for database sessions
- Pydantic v2 schemas (not v1)
- HTTP exception handling with FastAPI's HTTPException
- UUID primary keys for all entities
- Separate concerns: routes.py, services.py, models.py, schemas.py per module
- Use type hints (from __future__ import annotations)
- Factory pattern for app creation (create_app())
- Lifespan context manager for startup/shutdown hooks
- Request logging middleware for observability
- JWT-based auth with access + refresh tokens
- Token blacklisting for logout support
- Single-use tokens for password resets
- Alembic for database migrations
- CORS middleware for cross-origin requests
- Email via aiosmtplib (SMTP)
- Multiple AI provider abstraction (base class with provider implementations)

**Testing**:
- No test framework currently installed
- Strict TDD Mode: disabled (no test runner detected)
- To enable TDD, add: pytest, pytest-asyncio, pytest-cov, httpx

**Code Quality**:
- .ruff_cache exists but ruff not in requirements.txt - consider adding ruff for linting
- Consider adding mypy for type checking
- Consider adding black for code formatting
- Use descriptive variable names
- Add docstrings to all functions and classes
- Follow Python PEP 8 conventions
