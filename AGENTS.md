# SARAISE Application — Agent Instructions

**BuildWorks.AI | Innovation, Automation, Transformation, Architecture & AI Practice**

**SPDX-License-Identifier: Apache-2.0**
**Version**: 5.1.0
**Last Updated**: July 13, 2026

---

## Authority Source

**CRITICAL: All agent rules, architecture, and standards are in the documentation repository.**

```
AUTHORITATIVE SOURCE: saraise-documentation/
├── AGENTS.md                  ← Master agent instructions (SUPREME)
├── architecture/              ← System architecture (FROZEN)
├── rules/                     ← Compliance rules (MANDATORY)
├── standards/                 ← Coding standards (REQUIRED)
├── modules/                   ← Module specifications
├── .agents/data/              ← Machine-readable rules (FAST ACCESS)
└── .cursor/skills/            ← Agent skills (BuildWorks Chief Practice)
```

**Before ANY operation, agents MUST read `saraise-documentation/AGENTS.md`.**

**Engineering Philosophy (Kaizen, Monozukuri, Jidoka, Ordnung, Vorsprung durch Technik, Stabilitat) and Operational Disciplines (Shokunin, Nemawashi, Marveling, First-Principles) are defined in the master AGENTS.md and enforced here.**

---

## Adopted Engineering Principles (Cross-Lab Agent Contract)

Inherited from `saraise-documentation/AGENTS.md` § *Adopted Engineering Principles* — NON-NEGOTIABLE in this repository:

1. **Mirror rule** — `AGENTS.md` is the only editable agent guide. Any `CLAUDE.md` is a verbatim generated mirror (`cp AGENTS.md CLAUDE.md` after edits); divergence is a defect.
2. **Scoped authority** — this file governs saraise-application only; on conflict, the master file in `saraise-documentation/` wins.
3. **Declared flows only** — this app calls `license-server` and `module-registry` through their published APIs only. It never implements platform control-plane behavior and never calls platform internals directly. *(Ordnung)*
4. **False confidence is worse than absence** — stub or mock code that returns fabricated success data is a defect, not progress. Development-mode shortcuts (skipped license checks, relaxed auth) must be impossible to enable in production and visibly marked. *(Jidoka)*
5. **Artifact discipline** — built artifacts (JS bundles, wheels, coverage output) never enter git history; documents over ~30 MB move to Git LFS. *(Ordnung)*
6. **Jidoka engagement** — plan before multi-step work; delegate independent workstreams to parallel subagents; stop the line on any red check and fix before continuing. Completion claims require passing evidence (test/build output). *(Shokunin)*
7. **Indexed knowledge first** — query `rules-index.json`, module `contracts.ts`, and `manifest.yaml` before falling back to grep or full-file reads. *(Vorsprung durch Technik)*

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

- Internal architecture documents → `saraise-documentation/` *(Ordnung)*
- Agent rules or prompts → `saraise-documentation/` *(Ordnung)*
- Business logic specifications → `saraise-documentation/` *(Ordnung)*
- Phase planning documents → `saraise-documentation/` *(Ordnung)*
- Internal reports → `saraise-documentation/` *(Ordnung)*

---

## Operating Modes

### Development Mode
```yaml
SARAISE_MODE: development
```
License checks skipped. All modules enabled. Debug mode.

### Self-Hosted Mode
```yaml
SARAISE_MODE: self-hosted
SARAISE_LICENSE_MODE: connected | isolated
```
Single-tenant. Built-in Django auth. License validation required.

### SaaS Mode
```yaml
SARAISE_MODE: saas
SARAISE_PLATFORM_URL: https://platform.saraise.com
```
Multi-tenant. Auth delegated to platform. Full platform integration.

---

## Quick Rules (Summary)

Full rules in `saraise-documentation/rules/`. Machine-readable: `saraise-documentation/.agents/data/rules-index.json`.

| Rule | Enforcement | Principle |
|------|-------------|-----------|
| Tenant isolation | ALL tenant-scoped models have `tenant_id` | Stabilität |
| Tenant filtering | ALL queries filter by `tenant_id` | Jidoka |
| Session-based auth | NO JWT for interactive users | Stabilität |
| Full-stack modules | Backend + Frontend + Tests required | Monozukuri |
| Test coverage | >=90% with isolation tests | Monozukuri |
| Quality gates | Pre-commit hooks MUST pass | Shokunin |
| Module contracts | ALL modules have `contracts.ts` | Ordnung |
| Endpoint registry | Use ENDPOINTS constant, NO hardcoded URLs | Ordnung |
| Circuit breakers | ALL external HTTP calls use circuit breakers | Jidoka |
| Graceful degradation | Dependency failures handled, not fatal | Stabilität |
| Structured logging | All logs structured JSON with `correlation_id` | Ordnung |

---

## Module Contracts Architecture (CRITICAL — Ordnung)

**Every frontend module MUST have a `contracts.ts` file.**

```
frontend/src/modules/{module_name}/
├── contracts.ts          # REQUIRED - Types & Endpoints
├── .cursorrules          # REQUIRED - Module-specific rules
├── pages/
├── components/
└── services/
```

### Before Writing Frontend Code (Nemawashi)

1. **Read `contracts.ts` FIRST** — Contains all types and endpoints
2. **Import types from `contracts.ts`** — NOT from `@/types/api`
3. **Use `ENDPOINTS` constant** — NO hardcoded URL strings

```typescript
// CORRECT (Ordnung)
import { PlatformSetting, ENDPOINTS } from '../contracts';
const settings = await apiClient.get<PlatformSetting[]>(ENDPOINTS.SETTINGS.LIST);

// FORBIDDEN (Ordnung violation)
const settings = await apiClient.get('/api/v1/platform/settings/');
```

### After Each Edit (Shokunin + Jidoka)

```bash
cd frontend && npx tsc --noEmit src/modules/{path}.tsx
npx eslint src/modules/{path}.tsx --max-warnings 0
```

Fix errors IMMEDIATELY. Broken code does not get committed. Period.

---

## Forbidden in This Repository

| Violation | Redirect | Principle |
|-----------|----------|-----------|
| Tenant lifecycle (SaaS mode) | `saraise-platform` | Ordnung |
| Platform configuration | `saraise-platform` | Ordnung |
| Platform UI | `saraise-platform/frontend` | Ordnung |
| Internal documentation | `saraise-documentation` | Ordnung |

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

## Quality Gates (MANDATORY — Shokunin)

```bash
pre-commit run --all-files
```

| Check | Rule | Enforcement | Principle |
|-------|------|-------------|-----------|
| TypeScript | `tsc --noEmit` — ZERO errors | Block commit | Monozukuri |
| ESLint | `npm run lint` — ZERO warnings | Block commit | Monozukuri |
| Python: Black | Formatting required | Block commit | Ordnung |
| Python: Flake8 | Linting required | Block commit | Ordnung |
| Python: MyPy | Type checking | Block commit | Jidoka |
| File Quality | Trailing whitespace, EOF, YAML/JSON | Block commit | Ordnung |
| Security | Secret detection — No hardcoded secrets | Block commit | Stabilität |

**Skipping quality gates is a Shokunin violation. There is no shortcut that preserves integrity.**

---

## Phase Completion & PR Process (Monozukuri + Kaizen)

**NEVER propose next phase without completing current phase 100%. Incomplete phases are lies.**

### 1. Testing (MANDATORY)

```bash
# Backend tests
cd backend && pytest tests/ -v --cov=src --cov-fail-under=90

# Frontend tests
cd frontend
npm run typecheck     # ZERO errors
npm run lint          # ZERO warnings
npm run build         # Must succeed
```

### 2. Pre-Commit Validation

```bash
pre-commit run --all-files
```

### 3. Retrospective (Kaizen)

Write `reports/RETRO_PHASE_{N}.md` with: what worked, what failed, metrics comparison, prevention items.

### 4. Create Pull Request

Only after ALL tests pass, ALL hooks pass, AND retrospective written.

---

## Quality Standards

| Standard | Requirement | Enforcement | Principle |
|----------|-------------|-------------|-----------|
| TypeScript Errors | ZERO | Pre-commit + CI | Monozukuri |
| ESLint Warnings | ZERO | Pre-commit + CI | Monozukuri |
| Python Formatting | Black compliant | Pre-commit + CI | Ordnung |
| Test Coverage | >=90% | CI | Monozukuri |
| Build Success | Must build without errors | CI | Jidoka |
| Security | No secrets, no vulnerabilities | Pre-commit + CI | Stabilität |

---

## Cross-References

| Need | Location |
|------|----------|
| Full agent instructions | `saraise-documentation/AGENTS.md` |
| Engineering philosophy | `saraise-documentation/AGENTS.md` (Core Principles + Operational Disciplines) |
| Machine-readable rules | `saraise-documentation/.agents/data/rules-index.json` |
| System architecture | `saraise-documentation/architecture/` |
| Compliance rules | `saraise-documentation/rules/` |
| Coding standards | `saraise-documentation/standards/` |
| Module specs | `saraise-documentation/modules/` |

---

**Classification:** Open Source (Apache 2.0)
**Authority Source:** saraise-documentation/
**Engineering Philosophy:** BuildWorks.AI Principles — enforced without exception
---

## Commit Policy (MANDATORY — MACHINE-ENFORCED)

**Commits are authored by the engineer accountable for them. AI attribution is FORBIDDEN.**

| Rule | Requirement |
| ---- | ----------- |
| Author identity | `Raghunath Chava <raghunath@buildworks.ai>` — no other identity permitted |
| AI co-author trailer | **FORBIDDEN.** No `Co-Authored-By:` line naming Claude, Codex, GPT, Copilot, or any AI |
| AI generation footer | **FORBIDDEN.** No "Generated with [Claude Code]" or equivalent, in commit messages **or PR bodies** |
| AI attribution markers | **FORBIDDEN.** No 🤖 marker in commit messages |

This is enforced by a `commit-msg` git hook that **blocks the commit** on violation.

Install it after cloning (git hooks are not version-controlled):

```bash
git config user.email "raghunath@buildworks.ai"
git config user.name  "Raghunath Chava"
# Ensure .git/hooks/commit-msg is present and executable — see the ecosystem commit-msg hook.
```

Agents operating on this repository MUST NOT add AI attribution of any kind to commits or pull requests.
