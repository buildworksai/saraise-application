# SARAISE Application — Agent Instructions

**SPDX-License-Identifier: Apache-2.0**  
**Version**: 4.0.0  
**Last Updated**: January 7, 2026

---

## Authority Source

**CRITICAL: All agent rules, architecture, and standards are in the documentation repository.**

```
AUTHORITATIVE SOURCE: saraise-documentation/
├── AGENTS.md                  ← Master agent instructions
├── architecture/              ← System architecture (FROZEN)
├── rules/                     ← Compliance rules (MANDATORY)
├── standards/                 ← Coding standards (REQUIRED)
└── modules/                   ← Module specifications
```

**Before ANY operation, agents MUST read `saraise-documentation/AGENTS.md`.**

---

## This Repository: saraise-application

**License:** Apache 2.0 (Open Source)

**Purpose:** Runtime Plane that executes business logic for end users.

---

## What This Repository Contains

```
saraise-application/
├── backend/                   # Django backend
│   ├── src/
│   │   ├── core/              # Core infrastructure
│   │   └── modules/           # Business modules
│   │       ├── foundation/    # Platform infrastructure (22)
│   │       └── core/          # Business operations (21)
│   ├── tests/
│   └── manage.py
├── frontend/                  # React frontend
│   └── src/
│       ├── modules/           # Module UIs
│       └── components/        # Shared components
├── docker-compose.dev.yml
└── monitoring/
```

---

## What This Repository Does NOT Contain

❌ Internal architecture documents → `saraise-documentation/`  
❌ Agent rules or prompts → `saraise-documentation/`  
❌ Business logic specifications → `saraise-documentation/`  
❌ Phase planning documents → `saraise-documentation/`  
❌ Internal reports → `saraise-documentation/`  
❌ Workspace file → `saraise-documentation/`  

---

## Operating Modes

This application operates in different modes based on configuration:

### Development Mode
```yaml
SARAISE_MODE: development
```
- License checks skipped
- All modules enabled
- Debug mode

### Self-Hosted Mode
```yaml
SARAISE_MODE: self-hosted
SARAISE_LICENSE_MODE: connected | isolated
```
- Single-tenant
- Built-in Django auth
- License validation required

### SaaS Mode
```yaml
SARAISE_MODE: saas
SARAISE_PLATFORM_URL: https://platform.saraise.com
```
- Multi-tenant
- Auth delegated to platform
- Full platform integration

---

## Quick Rules (Summary)

Full rules are in `saraise-documentation/rules/`.

| Rule | Enforcement |
|------|-------------|
| Tenant isolation | ALL tenant-scoped models have `tenant_id` |
| Tenant filtering | ALL queries filter by `tenant_id` |
| Session-based auth | NO JWT for interactive users |
| Full-stack modules | Backend + Frontend + Tests required |
| Test coverage | ≥90% with isolation tests |
| Quality gates | Pre-commit hooks MUST pass |

---

## Forbidden in This Repository

❌ Tenant lifecycle (SaaS mode) → Use `saraise-platform`  
❌ Platform configuration → Use `saraise-platform`  
❌ Platform UI → Use `saraise-platform/frontend`  
❌ Internal documentation → Use `saraise-documentation`  

---

## Development Commands

```bash
# Backend
cd backend
pip install -e .[dev]
python manage.py runserver 0.0.0.0:8000
pytest tests/ -v --cov=src --cov-fail-under=90

# Frontend
cd frontend
npm ci
npm run dev
npx tsc --noEmit
npx eslint src --max-warnings 0
```

---

## Cross-References

| Need | Location |
|------|----------|
| Full agent instructions | `saraise-documentation/AGENTS.md` |
| System architecture | `saraise-documentation/architecture/` |
| Compliance rules | `saraise-documentation/rules/` |
| Coding standards | `saraise-documentation/standards/` |
| Module specs | `saraise-documentation/modules/` |

---

**Classification:** Open Source (Apache 2.0)  
**Authority Source:** saraise-documentation/
