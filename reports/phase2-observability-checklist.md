# Phase 2 Observability Implementation Checklist

## Goal: Wire metrics, traces, logs, and alerts across Tier-0 without architecture changes.

---

## Per Service: Observability Wiring

### saraise-auth
- [ ] Add session_issue_total, session_rotate_total, session_invalid_total metrics.
- [ ] Add session_store_latency_ms (p50/p95/p99) histogram.
- [ ] Add session_store_errors_total counter.
- [ ] Structured JSON logs for auth events (login, logout, rotate, errors).
- [ ] Trace context: include policy_version and tenant_id.
- [ ] Test: assert metrics emitted in session lifecycle tests.

### saraise-runtime
- [ ] Add requests_total counter (by outcome, tenant, module).
- [ ] Add policy_eval_latency_ms histogram (p50/p95/p99).
- [ ] Add policy_denies_total counter (by deny reason).
- [ ] Add auth_missing_total counter.
- [ ] Structured JSON logs for request decisions (policy_version, decision_reason, module).
- [ ] Trace context: map request → policy eval → decision.
- [ ] Test: assert metrics/traces present in request tests.

### saraise-policy-engine
- [ ] Add policy_eval_total counter (by decision).
- [ ] Add policy_bundle_version_gauge.
- [ ] Add policy_stale_denies_total counter.
- [ ] Add policy_eval_latency_ms histogram.
- [ ] Structured JSON logs for evaluation decisions (rule hit, bundle_version, stale_reason).
- [ ] Trace: evaluation path and rule matching.
- [ ] Test: assert metrics/logs in evaluation tests.

### saraise-control-plane
- [ ] Add tenant_create_total, tenant_suspend_total counters.
- [ ] Add policy_version_bump_total counter.
- [ ] Add shard_assign_latency_ms histogram.
- [ ] Structured JSON logs for lifecycle events (action, tenant_id, new_policy_version).
- [ ] Trace: policy bump propagation flow.
- [ ] Test: assert metrics in lifecycle tests.

### saraise-platform-core
- [ ] Verify contract_signature stable (no changes).
- [ ] Add optional event schema reference docs if needed.

---

## Alert Mapping & Runbook Validation

- [ ] Session store error rate > threshold → runbook: session store outage.
- [ ] Session store p95 latency > SLO → runbook: session store outage.
- [ ] Stale policy denies spike → runbook: policy lag.
- [ ] Auth failure rate spike → runbook: IdP outage.
- [ ] Tenant lifecycle failures → runbook: tenant provisioning remediation.
- [ ] For each alert: runbook exists and has documented recovery steps.

---

## Testing & Validation

- [ ] All metrics/traces/logs emitted; verify in unit/integration tests.
- [ ] Alert simulations executed; on-call response recorded.
- [ ] Dashboard queries work and tie to metrics.

---

## CI/Enforcement

- [ ] Pre-commit lint enforces structured log format where applicable.
- [ ] Metrics/traces/logs presence validated in test assertions.
- [ ] Baseline metrics captured (pre-drill).

---

## Completion Criteria
- All checklist items ✓.
- Metrics dashboard live and queryable.
- Alerts wired to runbooks and tested.
- Ready to proceed to chaos drills.
