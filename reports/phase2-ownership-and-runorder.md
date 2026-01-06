# Phase 2 Ownership and Run Order — Tier-0

## Ownership (assign names/teams)
- Auth: hardening + session store outage drills + auth evidence hooks.
- Runtime: policy invocation guarantees + stale policy handling + chaos drills.
- Policy engine: stale vs current bundle handling + deny reasons + evidence emission.
- Control plane: policy version bump flows + shard metadata integrity + audit evidence.
- Platform core: contract stability monitoring + evidence schema references.
- Observability/Alerts: shared SRE/Platform team for metrics/traces/logs/alerts.

## Run Order (recommended sequence)
1) Finalize owners and success criteria per scenario (see phase2-test-matrix).
2) Wire observability signals and alert simulations (baseline first) per service.
3) Security hardening tests: SoD/JIT, stale policy, session tamper, input validation.
4) Compliance evidence hooks: emit and validate auth/policy/JIT/SoD events.
5) Chaos drills (with post-mortems):
   - Session store outage (auth/runtime)
   - IdP down (auth)
   - Stale policy bundle / policy lag (runtime/policy)
6) Alert simulations mapped to runbooks; verify firing and handling.
7) Consolidate findings, fix regressions, rerun critical paths, and prepare Board sign-off.
