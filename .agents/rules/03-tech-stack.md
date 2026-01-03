---
description: Technology stack standards and approved dependencies for SARAISE multi-tenant application
globs: **/*
alwaysApply: true
---

# SARAISE Technology Stack (Aligned — Current Application)

**⚠️ CRITICAL**: All technology versions, package names, and Docker images are defined here.
Other files MUST reference these variables, not hardcode tech versions.

## SARAISE-12000 Central Tech Stack Registry (SINGLE SOURCE OF TRUTH)

### Environment Variables for Tech Stack

See [Tech Stack Environment Variables](docs/architecture/examples/config/tech-stack-env-vars.sh) for complete list.

### Docker Image Registry

See [Docker Image Registry](docs/architecture/examples/config/docker-image-registry.sh) for complete list.

### Python Helper Functions

See [Python Tech Stack Helpers](docs/architecture/examples/backend/core/tech-stack-helpers.py).

**Key Functions:**
- `get_postgres_image()`, `get_redis_image()`, `get_django_version()`, `get_python_version()`
- `get_kong_image()`, `get_loki_image()`, `get_grafana_image()`, `get_prometheus_image()`
- `get_celery_image()`, `get_flower_image()`, `get_tech_requirements()`

### TypeScript Helper Functions

See [TypeScript Tech Stack Helpers](docs/architecture/examples/frontend/lib/tech-stack-helpers.ts).

**Key Functions:**
- `getTechVersions()` - Get all tech versions from environment
- `getPackageJsonDependencies()` - Get package.json dependency strings

### Tech Stack Configuration Reference
- **Docker Compose**: Uses `${TECH_VARIABLE:-default}` syntax
- **Package Files**: Uses helper functions from this file
- **CI/CD**: Uses environment variables with fallbacks
- **Documentation**: References this file for tech versions

### Non-Negotiable Version Pinning Rules

- **BANNED:** `latest`, `stable`, `*`, `>=`, `+`, caret (`^`) ranges, tilde (`~`) ranges
- **REQUIRED:** exact versions for:
  - Docker images (include tag)
  - Python dependencies
  - Node.js runtime
  - Frontend dependencies

All version values MUST be sourced from the central registry (env vars + helper functions) and MUST be reproducible.

All references to major-only versions (e.g. "18", "5", "x") are forbidden.
Exact patch versions are mandatory.

### Files That Reference This Central Registry
- `09-infrastructure-config.md` - Docker images and versions
- `08-secrets-management.md` - Tech-specific environment variables
- `06-automated-enforcement.md` - Testing and quality tools
- `01-getting-started.md` - Tech examples and setup
- `04-backend-standards.md` - Python-specific tech
- `05-frontend-standards.md` - TypeScript-specific tech
- `02-quality-enforcement.md` - Tech stack overview

## SARAISE-12001 Allowed Stack (authoritative)

- **Framework**: Django 5.0.6, Django REST Framework (DRF) 3.15.1, Gunicorn 23.0.0
- **Database**: PostgreSQL 17.x (exact image tag resolved via get_postgres_image()),
  Django ORM (built-in), psycopg 3.2.1

  Optional Extension (Phase 4+ only): pgvector (for embedding storage)
  - PostgreSQL remains the system of record
  - pgvector does NOT replace PostgreSQL
  - Vector usage must remain tenant-scoped and quota-governed
- **Authentication**: Pure session-based with Redis (server), django-redis 5.4.0, bcrypt 4.3.0
  - **MFA / OTP (TOTP)**:
    - django-otp 1.3.0
    - django-otp-totp 1.1.2

  MFA uses RFC 6238 (TOTP) and is compatible with:
  - Microsoft Authenticator
  - Google Authenticator
- **Validation**: DRF Serializers (built-in), django-environ 0.11.2
- **Email**: MailHog (development/testing), Django email backend (built-in)
- **Caching Client**: django-redis 5.4.0
- **Task Queue**: Celery 5.3.4, Flower 2.0.1 (task monitoring)
- **AI/ML (Phase 4+ Only)**:
  - All AI/agent dependencies MUST be enabled only when executing AI workstreams.
  - Versions MUST be pinned via the central registry (no “latest”).
- **Observability**: OpenTelemetry SDK 1.33.0, OTLP Exporter 1.33.0

  All metrics, logs, and traces MUST include the following dimensions where applicable:
  - tenant_id
  - request_id
  - policy_version
  - decision_id
  - session_id (hashed/redacted)

  Missing these dimensions is a correctness bug, not an observability issue.

- **MCP**: MCP 1.9.0 (Model Context Protocol)
- **HTTP Client**: httpx 0.28.1, httpx-sse 0.4.0
- **DB Driver**: psycopg 3.2.1
- **API Documentation**: drf-spectacular 0.27.2 (OpenAPI/Swagger generation)
- **CORS**: django-cors-headers 4.3.1
- **Testing**: pytest-django 4.8.0, pytest 8.3.5, pytest-cov 6.1.1, django.test (built-in)
- **Code Quality**: Black 25.1.0, Flake8 7.2.0, django-stubs 5.0.2 (mypy type stubs)

### Frontend (Vite/React)
- **Build Tool**: Vite 5.1.4
- **Framework**: React 18.2.0, TypeScript 5.3.3
- **Routing**: React Router DOM 6.22.0
- **Styling**: Tailwind CSS 3.4.17, Tailwind CSS Animate 1.0.7
- **UI Components**:
  - Radix UI (comprehensive component library)
  - shadcn/ui (component patterns)
  - Lucide React 0.454.0 (icons)
- **Forms**: React Hook Form 7.54.1, Hookform Resolvers 3.9.1
- **Validation**: Zod 3.24.1
- **State Management**:
  - Zustand (pinned exact)
  - TanStack Query (pinned exact)

  The Redux ecosystem is entirely forbidden, including redux, Redux Toolkit, redux-saga, and redux-thunk.
  Zustand is the only allowed client state container.

- **Workflows**: ReactFlow (@xyflow/react 12.6.0)
- **Drag & Drop**: React Beautiful DnD 13.1.1
- **Charts**: Recharts 2.15.0
- **Markdown**: React Markdown 10.1.0, Remark GFM 4.0.1
- **Code Highlighting**: React Syntax Highlighter 15.6.1
- **Theming**: Custom theme provider (no Next Themes dependency)
- **Notifications**: Sonner 1.7.1
- **Date Handling**: date-fns 2.28.0, React Day Picker 8.10.1
- **AI Integration (Phase 4+ Only)**:
  - OpenAI SDK (pinned exact via central registry)
  - AI/agent dependencies are forbidden in Phase 1–3 unless explicitly enabled by the phase plan
- **Animations**: Framer Motion (pinned exact, optional)
- **Development**: ESLint 9.34.0, Prettier (pinned exact), Vitest (pinned exact)

### Infrastructure & DevOps
- **Containerization**: Docker, Docker Compose
- **Database**: PostgreSQL 17.x (Alpine) — image tag pinned via get_postgres_image()
- **Caching**: Redis Server (Alpine) — image tag pinned via get_redis_image()
- **Object Storage**: MinIO (S3-compatible)
- **Search**: OpenSearch 2.11.1 (Elasticsearch-compatible, Apache 2.0 licensed)
- **API Gateway**: Kong 3.4 (Alpine) — image tag pinned via get_kong_image()

  Kong is an OPTIONAL edge gateway.
  - Disabled by default in local development and Phase 1 execution
  - Enabled only in staging / performance testing / production profiles

  Kong MUST NOT perform:
  - authentication
  - authorization
  - session issuance

  Kong is not required for platform correctness.

- **Logging**: Loki 2.9.0
- **Monitoring**: Prometheus (pinned exact via get_prometheus_image()), Grafana 10.2.0
- **Email Testing**: MailHog (pinned exact via get_mailhog_image())
- **Secrets Management**: Vault (pinned exact via get_vault_image())
- **Environment**: Python (pinned exact via get_python_version()), Node.js 18.19.1
- **Package Management**: pip (Python), npm/yarn (Node.js)

## SARAISE-12007 Service-to-Stack Mapping (Authoritative)

- saraise-auth: Django + DRF service, owns login/logout and session issuance
- saraise-runtime: Django + DRF service, validates sessions and enforces policy (deny-by-default)
- saraise-policy-engine: Python service/library, performs policy + ABAC evaluation
- saraise-control-plane: Django service, manages tenants, shards, policies (NO request-time auth)
- Redis: Region-local session store (never authorization cache)
- PostgreSQL: Primary system of record (tenant-scoped)

## SARAISE-12002 Banned Technologies (by exclusion)
- Any tech not listed above is banned for this repository unless formally approved via Architecture Change Proposal (ACP).
- **Specifically banned**:
  - Node.js backend (use Python/Django)
  - FastAPI (use Django + DRF)
  - SQLAlchemy (use Django ORM)
  - Alembic (use Django migrations)
  - Prisma (use Django ORM)
  - tRPC (use DRF APIs)
  - Express.js (use Django)
  - ClickHouse (use PostgreSQL/OpenSearch)
  - Elasticsearch (use OpenSearch - Apache 2.0 licensed)
  - Redux Toolkit (use Zustand for client state)
  - Custom authentication (use Django + session-based auth)
  - JWT tokens (use session-based auth only)

## SARAISE-12002A Critical Routing Rules
**THIS PROJECT USES REACT ROUTER!**

See [React Router Examples](docs/architecture/examples/frontend/components/react-router-examples.tsx) for correct and forbidden patterns.

## SARAISE-12003 Migration & Exceptions
- Any deviation requires:
  - Rationale, risk assessment, and plan
  - Architecture Change Proposal (ACP) approval
  - Cross-reference to this rule ID in PR description

## SARAISE-12004 Accessibility & Theming Guardrails
- Use semantic colors from `13-branding-visual.md` (no hardcoded hex in components)
- Enforce keyboard/ARIA patterns for Radix UI components
- Follow SARAISE brand colors defined in Tailwind config (deepBlue, gold, teal, green)

## SARAISE-12005 AI Agent Development Standards

AI and agent-related dependencies are NOT part of the core platform tech stack.
They are phase-gated (Phase 4+) and may only be enabled when explicitly allowed by the active phase plan.
Inclusion of any AI dependency does NOT imply architectural commitment.

- Use OpenAI SDK (pinned exact via central registry) for AI model integration and agent development (Phase 4+ only)
- Implement A2A protocol for agent interoperability
- Use LangGraph for complex workflow management
- Follow CrewAI patterns for multi-agent systems
- Implement proper MCP server integration
- Use LiteLLM for model abstraction and switching

- Vector storage MUST use PostgreSQL + pgvector unless an Architecture Change Proposal (ACP)
  explicitly approves a dedicated vector database for a specific workload.

All AI tooling listed below is OPTIONAL, non-authoritative, and subject to replacement
without architecture changes, provided safety and governance contracts remain intact.

## SARAISE-12005B MFA & Authentication Assurance Rules

- MFA is implemented using TOTP only (RFC 6238).
- MFA is enforced AFTER primary login and BEFORE sensitive actions.
- MFA state MUST NOT be treated as authorization.
- MFA contributes only to authentication assurance level.
- MFA enforcement decisions are evaluated via policy engine (ABAC-aware).
- Custom OTP implementations are forbidden.
- External MFA SaaS dependencies are forbidden.

Approved MFA Libraries (Authoritative):
- django-otp 1.3.0
- django-otp-totp 1.1.2

## SARAISE-12005A Workstream-Specific Technologies

**⚠️ NOTE**: This tech stack covers general application development standards.

**Hard Rule:** Workstream dependencies are forbidden in Phase 1–3 unless the phase plan explicitly enables them.

**Documentation Status:** Workstream architecture documentation is not yet available. These dependencies are listed for reference only and should not be used until Phase 4+ and proper documentation is available.

### Additional Workstream Dependencies (Reference Only)

These are documented in architecture docs and required for workstream features:

**Agent Orchestration**:
- temporalio (pinned exact via central registry) - Long-running workflows with saga pattern
- instructor (pinned exact via central registry) - Structured LLM outputs with Pydantic validation
- pydantic-ai (pinned exact via central registry) - Type-safe agent development

**Governance & Quality**:
- guardrails-ai (pinned exact via central registry) - Output validation and governance enforcement
- ragas (pinned exact via central registry) - RAG quality metrics and evaluation
- langsmith (pinned exact via central registry) - Agent execution tracing and debugging

**Cost Optimization**:
- portkey-ai (pinned exact via central registry) - LLM gateway (caching, fallbacks, cost tracking, observability)
- dspy-ai (pinned exact via central registry) - Prompt optimization and automatic tuning

**Implementation Note**: Add these dependencies to `backend/pyproject.toml` only if implementing workstream features. For standard application development, the core tech stack above is sufficient.

## SARAISE-12006 Service Integration Examples

See [Service Integration Examples](docs/architecture/examples/backend/services/service-integrations.py) for:
- MailHog Email Testing
- MinIO Object Storage
- Celery Task Queue
- Redis Caching
