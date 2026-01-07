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

## Pre-Commit Hooks & Quality Gates

**MANDATORY: All commits MUST pass pre-commit hooks before being pushed.**

### Setup Pre-Commit Hooks

```bash
# Install pre-commit (Python tool)
pip install pre-commit

# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### Pre-Commit Checks (SARAISE-04001, SARAISE-04002)

The following checks are **MANDATORY** and **BLOCKING**:

| Check | Rule | Enforcement |
|-------|------|-------------|
| TypeScript | `tsc --noEmit` — ZERO errors | Block commit |
| ESLint | `npm run lint` — ZERO warnings | Block commit |
| Python: Black | Formatting required | Block commit |
| Python: Flake8 | Linting required | Block commit |
| Python: MyPy | Type checking | Block commit |
| File Quality | Trailing whitespace, EOF, YAML/JSON validation | Block commit |
| Security | Secret detection — No hardcoded secrets | Block commit |

**No exceptions. No bypasses. All checks must pass.**

---

## GitHub Workflows

**MANDATORY: All workflows must pass before merge.**

### Quality Guardrails Workflow

- Runs on: Push to `main`, `develop`, `release/*`, `hotfix/*` and all PRs
- Enforces: TypeScript (zero errors), ESLint (zero warnings), Python quality checks, Tests (≥90% coverage)
- **Status**: Blocking — PR cannot be merged if this fails

### CI/CD Workflow

- Runs on: All pushes and PRs
- Includes: Quality checks, Tests, Build, Security scan
- **Status**: Blocking — PR cannot be merged if this fails

---

## Phase Completion & PR Process

**CRITICAL: After successful completion of every phase, follow this process:**

### 1. Testing (MANDATORY)

Before creating a PR, **ALL tests must pass**:

```bash
# Backend tests
cd backend
pytest tests/ -v --cov=src --cov-fail-under=90

# Frontend tests
cd frontend
npm run typecheck     # TypeScript (must pass with zero errors)
npm run lint          # ESLint (must pass with zero warnings)
npm run build         # Build must succeed
```

**If any check fails, fix the issues before proceeding.**

### 2. Pre-Commit Validation

Ensure pre-commit hooks pass:

```bash
pre-commit run --all-files
```

**All hooks must pass. No exceptions.**

### 3. Create Pull Request

Once **ALL tests pass** and **ALL pre-commit hooks pass**:

1. **Commit changes** with descriptive commit messages
2. **Push to feature branch**
3. **Create Pull Request** in GitHub targeting `main` or `develop`
4. **Wait for CI/CD workflows** to complete and pass
5. **Request review** from team members
6. **Merge only after** all checks pass and approval received

**DO NOT create PRs with failing tests or pre-commit hooks.**

**DO NOT merge PRs that fail CI/CD workflows.**

---

## Quality Standards

| Standard | Requirement | Enforcement |
|----------|-------------|-------------|
| TypeScript Errors | ZERO | Pre-commit + CI |
| ESLint Warnings | ZERO | Pre-commit + CI |
| Python Formatting | Black compliant | Pre-commit + CI |
| Test Coverage | ≥90% | CI |
| Build Success | Must build without errors | CI |
| Security | No secrets, no vulnerabilities | Pre-commit + CI |

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
