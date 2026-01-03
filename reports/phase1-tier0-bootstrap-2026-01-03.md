# Phase 1 — Tier‑0 Repo Bootstrap (CI + Governance Only)

**Date:** 2026-01-03  
**Scope:** Bootstrapped Tier‑0 repositories with **governance + CI scaffolding only**. No business logic, no modules, no auth/session implementations, no AI agents.

## Repositories created + initial `main` pushed

- https://github.com/buildworksai/saraise-auth
- https://github.com/buildworksai/saraise-runtime
- https://github.com/buildworksai/saraise-control-plane
- https://github.com/buildworksai/saraise-policy-engine
- https://github.com/buildworksai/saraise-platform-core

## What’s included (per repo)

- `.github/workflows/ci.yml` with **Node pinned to `18.19.1`**
- `.github/CODEOWNERS` (placeholder owners; must be updated to real teams)
- `.github/pull_request_template.md` (Tier‑0 PR checklist)
- `scripts/phase1-guardrails.sh` (reject obvious feature/architecture violations early)
- Minimal Python project skeleton (`pyproject.toml`, simple entrypoint, smoke test)

## Verification performed (local)

- Confirmed CI workflow exists in all repos and includes `node-version: '18.19.1'`.
- Confirmed governance/guardrail files exist in all repos:
  - `.github/CODEOWNERS`
  - `.github/pull_request_template.md`
  - `scripts/phase1-guardrails.sh`
  - `pyproject.toml`

## Manual follow-ups required (GitHub settings)

These cannot be enforced purely by repo contents and must be configured in GitHub org/repo settings:

- **Branch protection** on `main`:
  - Require PRs (no direct pushes)
  - Require CI checks to pass
  - Require **2 approvals** (Tier‑0 rule)
  - Require CODEOWNERS review
  - Disable force-push
- Replace placeholder entries in `.github/CODEOWNERS` with actual owners/teams.

## Notes

- This work intentionally avoids implementing any platform features. It is strictly a safe bootstrap to enable CI/governance enforcement before Phase‑1 functional work begins.
