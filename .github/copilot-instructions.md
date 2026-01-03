# SARAISE — Copilot coding agent instructions

## Authority order (if anything conflicts)
1. `.agents/rules/*.md` (authoritative; many are `alwaysApply: true`)
2. `docs/architecture/` (frozen specs)
3. `docs/modules/00-MODULE-INDEX.md` (implementation sequencing)
4. `docs/architecture/examples/` (approved reference implementations)

## Repo structure (don’t fight it)
- Architecture specs live in `docs/architecture/`.
- Module specifications live in `docs/modules/`.
- Reports/findings belong in `reports/` only (never create new docs in repo root).
- Scripts belong in `scripts/` only.

## README discipline (mandatory)
- Any **new folder** you create MUST include a `README.md` that states the folder’s purpose, key entrypoints, and ownership boundaries.
- If you change a folder’s contents in a way that changes its intent, interfaces, or conventions, you MUST update that folder’s `README.md` in the same change.
- Prefer concise purpose READMEs (what lives here, what must not live here, and links to the relevant specs in `docs/architecture/` and rules in `.agents/rules/`).

## Frozen architecture invariants (non-negotiable)
- **Row-level multitenancy** (shared schema): tenant-scoped data MUST use `tenant_id` and MUST be filtered by it.
- **Interactive auth = server-managed sessions** (HTTP-only cookies). No JWT for interactive users.
- Sessions contain **identity snapshot only**: `roles[]`, `groups[]`, `jit_grants[]`, `policy_version` (no effective perms, no cached decisions).
- Authorization is **deny-by-default** and evaluated per-request by the **Policy Engine**.
- Modules are **manifest-driven** (`manifest.yaml`) and MUST NOT implement login/logout/session management.

Key rule files to follow when touching runtime code:
- Session auth: `.agents/rules/10-session-auth.md`
- Module boundaries/deps: `.agents/rules/15-module-architecture.md`
- Tenant isolation: `.agents/rules/21-platform-tenant.md`
- Auth enforcement: `.agents/rules/12-auth-enforcement.md`
- Audit logging: `.agents/rules/11-audit-logging.md`

## Implementation sequencing (strict)
- Only **Foundation modules (Phase 1–5)** are approved for implementation now.
- **Core** and **Industry-Specific** modules are **specification-only** until Phase 8/8+.

## Developer workflows (don’t guess)
- Pre-commit is mandatory:
  ```bash
  pip install pre-commit && pre-commit install
  pre-commit run --all-files
  ```
- Validate that `.agents/rules` references still point to real files:
  ```bash
  ./scripts/validate-rule-references.sh
  ```
- CI guardrails are strict (see `.github/workflows/quality-guardrails.yml`):
  - Frontend: `npx tsc --noEmit` + `npx eslint --max-warnings 0` + tests with ≥90% coverage
  - Backend: `black`/`isort`/`flake8`/`mypy` + tests with ≥90% coverage

## Workspace reality check
- This branch appears docs/spec-heavy (e.g., `frontend/` is assets-only and `backend/` may be absent), while CI/rules describe the intended runtime layout.
- If runtime folders are missing, do not invent implementation paths; constrain changes to `docs/`, `.agents/`, `reports/`, and `docs/architecture/examples/` unless explicitly asked.
