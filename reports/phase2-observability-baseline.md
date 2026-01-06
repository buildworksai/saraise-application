# Phase 2 Observability Baseline — Tier-0

## Constraints
- No architecture changes; reuse existing services and contracts.
- Alerts must map to existing runbooks; no new on-call process.
- Deny-by-default behavior must remain visible in signals.

## Metrics (per service)
- Auth: session_issue_total, session_rotate_total, session_invalid_total, session_store_latency_ms (p50/p95/p99), session_store_errors_total.
- Runtime: requests_total (by outcome/tenant/module), policy_eval_latency_ms (p50/p95/p99), policy_denies_total (by reason), auth_missing_total.
- Policy engine: policy_eval_total (by decision), policy_bundle_version_gauge, policy_stale_denies_total, policy_eval_latency_ms.
- Control plane: tenant_create_total, tenant_suspend_total, policy_version_bump_total, shard_assign_latency_ms.
- Platform core: contract_signature_version_gauge, identity_snapshot_seen_total.

## Traces
- Trace auth → runtime → policy evaluation path; include tenant_id (scrubbed), policy_version, decision reason.
- Trace session store interactions in auth/runtime for latency and error attribution.
- Trace control-plane policy bump propagation to runtime fetch/apply.

## Logs
- Structured JSON logs with tenant_id, policy_version, decision_reason; no secrets.
- Auth: login/logout/rotate outcomes, session store errors.
- Runtime: request outcome with decision_reason, module name, policy_version.
- Policy: evaluation decision with rule hit; stale/bundle errors.
- Control plane: tenant lifecycle changes, policy version bumps.

## Alerts (map to runbooks)
- Session store elevated error rate or p95 latency > SLO (Auth/Runtime) → runbook: session store outage.
- Stale policy denies spike or policy fetch failures (Runtime/Policy) → runbook: policy lag.
- Auth failure rate spike or IdP errors → runbook: IdP outage.
- Unusual deny mix (policy_denies_total by reason shifts) → runbook: authorization anomaly investigation.
- Tenant lifecycle failures (Control plane) → runbook: tenant provisioning remediation.

## Validation Tasks
- Emit metrics/traces/logs in tests; assert presence and required labels.
- Simulate alerts (session store outage, stale policy, IdP down) and verify alert firing + runbook execution.
- Ensure CI includes lint/check for structured logging schema where applicable.
