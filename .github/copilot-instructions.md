# SARAISE — AI Coding Agent Instructions

**Version**: 3.0.0  
**Last Updated**: January 5, 2026

---

## Authority Order (If Conflicts)

1. `.agents/rules/*.md` — Authoritative rules (many are `alwaysApply: true`)
2. `docs/architecture/` — Frozen architecture specs
3. `docs/modules/00-MODULE-INDEX.md` — Implementation sequencing
4. `docs/architecture/examples/` — Approved reference implementations

---

## Repository Structure (Non-Negotiable)

| Location | Purpose |
|----------|---------|
| `docs/architecture/` | Architecture specifications |
| `docs/modules/` | Module specifications |
| `reports/` | Findings, reports (ONLY create docs here) |
| `scripts/` | Scripts (ONLY scripts here) |
| `.agents/rules/` | AI agent rules |
| `backend/src/modules/` | Backend module implementations |
| `frontend/src/modules/` | Frontend module implementations |

**FORBIDDEN**: Creating documents in repository root.

---

## README Discipline (Mandatory)

- Any **new folder** MUST include a `README.md` stating purpose, entrypoints, ownership
- Changes that alter a folder's intent/interfaces/conventions MUST update its `README.md`
- Link to relevant specs in `docs/architecture/` and rules in `.agents/rules/`

---

## Frozen Architecture Invariants (Non-Negotiable)

### Multi-Tenancy

- **Row-level multitenancy** (shared schema)
- ALL tenant-scoped data MUST use `tenant_id`
- ALL queries MUST filter by `tenant_id`

### Authentication

- **Interactive auth = server-managed sessions** (HTTP-only cookies)
- NO JWT for interactive users (JWT only for API/S2S)
- Sessions contain **identity snapshot only**: `roles[]`, `groups[]`, `jit_grants[]`, `policy_version`
- NO effective permissions cached in sessions

### Authorization

- **Deny-by-default**
- All authorization evaluated per-request by **Policy Engine**
- Sessions establish identity; Policy Engine makes decisions

### Modules

- **Manifest-driven** (`manifest.yaml` required)
- Modules MUST NOT implement login/logout/session management
- Full stack implementation required (backend + frontend + tests)

---

## Key Rule Files

| Rule | When to Apply |
|------|---------------|
| `.agents/rules/00-core-principles.md` | Always |
| `.agents/rules/10-session-auth.md` | Any auth work |
| `.agents/rules/12-auth-enforcement.md` | Authorization |
| `.agents/rules/15-module-architecture.md` | Module development |
| `.agents/rules/21-platform-tenant.md` | Tenant isolation |
| `.agents/rules/11-audit-logging.md` | Audit features |
| `.agents/rules/24-performance-slas.md` | Performance work |
| `.agents/rules/25-event-architecture.md` | Event patterns |

---

## Key Architecture Documents

| Document | Purpose |
|----------|---------|
| `docs/architecture/application-architecture.md` | System overview |
| `docs/architecture/security-model.md` | Security architecture |
| `docs/architecture/authentication-and-session-management-spec.md` | Session auth |
| `docs/architecture/policy-engine-spec.md` | Authorization |
| `docs/architecture/module-framework.md` | Module patterns |
| `docs/architecture/performance-slas.md` | Performance targets |
| `docs/architecture/test-architecture.md` | Test patterns |
| `docs/architecture/event-driven-architecture.md` | Event patterns |
| `docs/architecture/realtime-architecture.md` | WebSocket patterns |

---

## Implementation Sequencing

Check `docs/modules/00-MODULE-INDEX.md` for current implementation status:

- **Foundation modules** — Actively being implemented
- **Core modules** — Specification only (blocked until Foundation complete)
- **Industry modules** — Specification only (blocked until Core complete)

Do NOT implement modules out of sequence without explicit approval.

---

## Technology Stack

### Backend

- Python 3.10+, Django 5.0.6, Django REST Framework 3.15.1
- PostgreSQL 17, Redis 7+
- **Django ORM ONLY** (no SQLAlchemy)
- **Django migrations ONLY** (no Alembic)

### Frontend

- React 18, TypeScript 5, Vite 6+
- TanStack Query 5, Tailwind CSS 3.4+, Shadcn/ui

---

## Quality Gates (CI Enforced)

### Frontend

```bash
npx tsc --noEmit           # ZERO TypeScript errors
npx eslint --max-warnings 0 # ZERO ESLint warnings
npm test -- --coverage      # ≥90% coverage
```

### Backend

```bash
black src tests             # Formatting
isort src tests             # Import sorting
flake8 --max-line-length=120
mypy src                    # Type checking
pytest --cov=src --cov-fail-under=90
```

### Pre-Commit (Mandatory)

```bash
pip install pre-commit && pre-commit install
pre-commit run --all-files
```

---

## Module Development Pattern

### Template Module

Use `backend/src/modules/ai_agent_management/` as template:
- Copy structure
- Adapt to requirements
- 70% code reuse expected

### Required Components

**Backend:**
- `manifest.yaml` — Module contract
- `models.py` — Django ORM with `tenant_id`
- `api.py` — DRF ViewSets
- `serializers.py` — DRF serializers
- `urls.py` — URL routing
- `services.py` — Business logic
- `tests/` — ≥90% coverage, tenant isolation tests

**Frontend:**
- `pages/` — List, Detail, Create pages
- `components/` — Reusable components
- `services/` — API client
- `tests/` — Component and service tests

### Tenant Isolation (CRITICAL)

```python
def get_queryset(self):
    tenant_id = get_user_tenant_id(self.request.user)
    if not tenant_id:
        return Model.objects.none()
    return Model.objects.filter(tenant_id=tenant_id)
```

---

## Anti-Patterns (Forbidden)

❌ Missing `tenant_id` in tenant-scoped models  
❌ Missing tenant filtering in queries  
❌ JWT for interactive users  
❌ Modules without `manifest.yaml`  
❌ Dynamic route registration  
❌ Skipping tests (90% coverage mandatory)  
❌ Hardcoded API URLs  
❌ Circular module dependencies  
❌ Modifying audit logs  
❌ Bypassing pre-commit hooks  
❌ TypeScript `any` type  
❌ Database transactions in route handlers  
❌ Backend-only module stubs  
❌ Auth implementation in modules  

---

## Workspace Reality Check

- If runtime folders are missing, do NOT invent implementation paths
- Constrain changes to `docs/`, `.agents/`, `reports/`, `scripts/` unless explicitly asked
- Reference architecture documents before making changes
- Validate rule references still point to real files:
  ```bash
  ./scripts/validate-rule-references.sh
  ```

---

## Operational Persona

- Challenge weak designs without hesitation
- Reject shallow reasoning
- Enforce quality gates strictly
- Halt on rule conflicts
- Guide with precision
- Enforce full stack completeness

**Technical correctness is authority, not politeness.**
