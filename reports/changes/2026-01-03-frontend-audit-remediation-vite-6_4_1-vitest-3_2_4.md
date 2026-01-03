# Frontend audit remediation — Vite 6.4.1 + Vitest 3.2.4 (2026-01-03)

## Summary
- Goal: eliminate `npm audit` findings without `overrides` and keep guardrails green.
- Outcome: `npm audit` reports **0 vulnerabilities** after upgrading to Vite 6.4.1 and Vitest 3.2.4, with TypeScript, ESLint, and tests passing.

## Why
- `npm audit` reported vulnerabilities in the toolchain dependency graph (Vite/esbuild + Vitest).
- Governance constraints:
  - No dependency graph overrides for core tooling.
  - Fix must be reproducible with exact pins and `npm ci`.

## Changes (exact pins)
- `vite`: `5.1.4` → `6.4.1`
- `vitest`: `1.6.0` → `1.6.1` (patch fix for critical) → `3.2.4` (final)
- `@vitest/coverage-v8`: `3.2.4` (enables coverage reporters for CI)

## Lockfile
- Regenerated `frontend/package-lock.json` from scratch under the new pins.

## Proof (local)
Commands run from `frontend/`:
- `npm audit` → `found 0 vulnerabilities`
- `npm run typecheck` → pass
- `npm run lint` → pass (`--max-warnings 0`)
- `npm test` → pass

Resolved versions evidence:
- `vite@6.4.1` pulls `esbuild@0.25.12` (>= 0.25.0).

## Config impact
- No config changes required for this minimal scaffold.
- Existing `vite.config.ts` and `vitest.config.ts` continued to work.

## CI compatibility addendum
- Removed Jest-only `--watchAll=false` from CI test commands (Vitest rejects this flag).
- Added explicit Vitest 3 coverage configuration and dependency so CI receives `coverage/coverage-summary.json`.

## Rollback
- Revert `frontend/package.json` and `frontend/package-lock.json` to the last known good versions.

## Production/runtime note
- `vite` and `vitest` are `devDependencies` only.
- Production images should ship built static assets (`dist/`) and must not install devDependencies in the runtime stage.
