# Phase 2 Execution Checklist — Platform Hardening & Compliance

## Constraints
- No architecture changes; frozen domains remain in force.
- Use existing contracts and session/policy semantics; no new auth/policy surfaces.
- Tier-0 only; no business modules.

## Scope Anchors (EPIC-201/202/203)
- Security hardening: regression suite, bypass hunting, SoD/JIT enforcement checks.
- Compliance evidence: hooks and exportability for auth/policy/JIT/SoD events.
- Reliability/chaos: degraded-mode behavior (IdP down, session store down, stale policy bundle); post-mortems required.
- Observability: metrics/tracing/logs baseline; alerts mapped 1:1 to runbooks.

## Checklist
- Govern: branch protections and CODEOWNERS enforced (Phase 1); evidence captured.
- Plan: approve Phase 2 test/drill matrix and owners per repo.
- Security: add hardening tests (SoD/JIT, stale policy, session tamper, path traversal, input validation) to Tier-0 suites; gate in CI.
- Compliance: emit auditable events for auth/policy/JIT/SoD with export path; tests assert presence and schema.
- Reliability: implement degraded-mode handling for session store and policy lag; chaos drills scheduled and executed with post-mortems.
- Observability: instrument key metrics/traces/logs; wire alerts to existing runbooks; verify firing paths.
- Sign-off: board approval to enter Phase 3 after all exit criteria pass.

## Assignments
- Auth: session tamper + store outage coverage; auth event evidence.
- Runtime: per-request policy invocation checks; stale policy denial; chaos drills; observability wiring.
- Policy engine: stale vs current bundle handling; deny-by-default regressions; evidence emission.
- Control plane: policy version bump flows; shard metadata integrity; audit evidence for lifecycle changes.
- Platform core: shared contracts stability (no changes) and evidence schema references.
