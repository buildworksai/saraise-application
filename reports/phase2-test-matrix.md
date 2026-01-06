# Phase 2 Test & Drill Matrix — Tier-0

## Principles
- No architecture changes; tests validate hardening within existing contracts.
- Deny-by-default must remain intact under all scenarios.
- Each scenario must have success criteria and linked runbook.

## Scenarios and Success Criteria
- Session store outage (auth/runtime): runtime fails closed; sessions unavailable → deny with explicit reason; alert fires; runbook executed.
- IdP down (auth): login fails gracefully; no cached bypass; alert fires.
- Stale policy bundle (runtime/policy): requests with mismatched policy_version receive deterministic stale denial; audit event recorded.
- JIT/SoD enforcement (policy/runtime): restricted actions denied without JIT grant; SoD conflicts rejected; evidence logged.
- Request pipeline bypass attempts (runtime): policy engine invoked on every authenticated request; tests assert invocation.
- Input/validation hardening (Tier-0 services): malformed or oversized payloads rejected with 4xx; no crashes.
- Observability checks (all): required metrics/traces/logs emitted; alerts wired to runbooks; simulate alert and verify handling.

## Evidence Expectations
- Tests assert event emission for auth/policy/JIT/SoD flows.
- Chaos drills produce post-mortems with findings and fixes.
- Alert simulations recorded with confirmation of on-call handling.
