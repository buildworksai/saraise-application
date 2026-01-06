# Phase 2 Implementation Tasks — Tier-0 Repos

## Status: READY FOR EXECUTION

---

## saraise-auth

### Observability (P1)
- Add metrics: session_issue_total, session_rotate_total, session_invalid_total, session_store_latency_ms (p50/p95/p99), session_store_errors_total.
- Add structured JSON logs: login/logout/rotate outcomes, session store errors, auth failures.
- Trace session lifecycle end-to-end (include policy_version in trace context).
- Test: assert metrics/logs/traces emitted in session flow tests.

### Security Hardening (P2)
- Session tamper test: validate that modified session tokens are rejected.
- Session store outage resilience: test graceful failure when store unavailable.
- Input validation: test login/rotate payloads for malformed/oversized inputs.

### Compliance Evidence (P2)
- Emit auditable auth events: login, logout, rotate, store errors.
- Define auth event schema (timestamp, user_id, tenant_id, action, result).
- Test: assert events emitted and retrievable.

### Chaos Drill: Session Store Outage (P3)
- Simulated store outage; auth should fail closed with explicit reason.
- Metrics confirm elevated error rate and latency spike.
- Alert fires; on-call confirmed and runbook executed.
- Post-mortem: findings, recovery time, fixes.

---

## saraise-runtime

### Observability (P1)
- Add metrics: requests_total (by outcome/tenant/module), policy_eval_latency_ms (p50/p95/p99), policy_denies_total (by reason), auth_missing_total.
- Add structured JSON logs: request outcome with policy_version, decision_reason, module.
- Trace request → policy evaluation → decision path.
- Test: assert metrics/logs/traces present in request flow tests.

### Security Hardening (P2)
- Policy evaluation guarantee: test that policy engine is invoked on every authenticated request.
- Stale policy handling: test request with stale policy_version receives deterministic deny.
- Input/path validation: test malformed module/action paths rejected.

### Compliance Evidence (P2)
- Emit policy decision events: policy_version, decision_reason, jit_grant_id (if applicable), sod_conflict (if applicable).
- Define decision event schema.
- Test: assert events emitted for allow/deny outcomes.

### Chaos Drills (P3)
- Stale policy bundle: control plane bumps policy version; runtime fetch/apply; requests with old version denied.
- Metrics show stale_denies spike; alert fires.
- Post-mortem: time to detect, propagate, and enforce.

---

## saraise-policy-engine

### Observability (P1)
- Add metrics: policy_eval_total (by decision), policy_bundle_version_gauge, policy_stale_denies_total, policy_eval_latency_ms (p50/p95/p99).
- Add structured JSON logs: evaluation decision with rule hit, bundle_version, stale_reason.
- Trace evaluation internals: rule hits, final decision path.
- Test: assert metrics/logs/traces in evaluation tests.

### Security Hardening (P2)
- Deny-by-default regression: confirm that missing/invalid policies default to deny.
- Stale vs current bundle: test that policy_version mismatch triggers stale deny.
- SoD/JIT enforcement: test restricted actions denied without JIT grant.

### Compliance Evidence (P2)
- Emit evaluation events: bundle_version, decision, stale_reason, jit_check, sod_check.
- Define evaluation event schema.
- Test: assert events present for all decision paths.

### No Chaos Drill (tight coupling to runtime; covered in runtime stale policy drill).

---

## saraise-control-plane

### Observability (P1)
- Add metrics: tenant_create_total, tenant_suspend_total, policy_version_bump_total, shard_assign_latency_ms (p50/p95/p99).
- Add structured JSON logs: tenant lifecycle changes, policy version bumps, shard assignments.
- Trace policy bump propagation.
- Test: assert metrics/logs in lifecycle tests.

### Security Hardening (P2)
- Shard metadata integrity: test that shard id matches tenant deterministically.
- Policy version bump idempotence: test repeated bump of same version is safe.

### Compliance Evidence (P2)
- Emit lifecycle events: create, suspend, delete, policy_bump.
- Define lifecycle event schema (timestamp, tenant_id, action, result, new_policy_version).
- Test: assert events emitted for all lifecycle ops.

### No Chaos Drill (control plane is not in critical hot path; observability + compliance sufficient).

---

## saraise-platform-core

### Contract Stability (P1)
- Verify IdentitySnapshot, TenantContext, PolicyDecision, AuditEvent contracts remain unchanged.
- Add optional event emission schema reference.
- Test: assert contract_signature unchanged in CI.

### No Hardening (platform-core is contract library; hardening in services).

---

## Alert Simulations (SRE/Platform) (P3)

- Session store error rate alert: simulate and verify firing + on-call response.
- Stale policy denies spike: simulate and verify firing + on-call response.
- Auth failure rate: simulate and verify firing + on-call response.
- Verify each alert maps to an existing runbook and execution can proceed.

---

## Board Sign-Off (P4)
- Collect results, regressions, chaos drill post-mortems, alert validations.
- Confirm all Phase 2 exit criteria met.
- Present to Board for Phase 3 approval.
