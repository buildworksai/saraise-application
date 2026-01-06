# SARAISE Operational Runbooks (Day-2 Operations)

**Status:** Draft v0.1 (authoritative, enforced)

This document defines **how SARAISE is operated under stress**: incidents, failures, saturation, security events, and human error.

Architecture prevents many failures. Runbooks prevent panic when failures still occur.

---

## 0) Ruthless Operational Principles

1. **No improvisation during incidents.** Follow the runbook or stop.
2. **Fail closed beats partial recovery.** Safety > availability.
3. **Automation first, humans last.** Humans approve, systems execute.
4. **Every incident teaches the platform.** Fixes become rules.
5. **If it’s not written here, it’s not allowed.**

---

## 1) Incident Severity Levels

| Level | Description | Examples |
|-----|-------------|----------|
| SEV-1 | Platform-wide risk | Cross-tenant data exposure, auth bypass, session store outage |
| SEV-2 | Multi-tenant outage | Shard failure, migration deadlock, AI saturation cascade |
| SEV-3 | Tenant-level impact | Isolated shard overload |
| SEV-4 | Degraded service | Latency breach, quota throttling |

Severity determines response authority and escalation path.

---

## 2) Shard Saturation Response

### Triggers
- Any saturation signal > threshold (see Shard Sizing spec)

### Automated Actions
1. Block new tenant placement
2. Throttle background jobs
3. Reduce non-critical workloads

### Human-Approved Actions
- Initiate shard split
- Isolate top offenders

### Forbidden
- Raising shard limits
- Manual tenant reshuffling

---

## 3) Runtime Failure Runbook

### Detection
- Health probes fail
- Error rate spike

### Response
1. Mark shard unhealthy
2. Reroute traffic if possible
3. Freeze migrations
4. Notify control plane

### Recovery
- Restore from backup or replica
- Post-mortem mandatory

---

## 4) Migration Failure Runbook

### Detection
- Lock budget violation
- Backfill stalls

### Response
1. Pause migration
2. Switch affected modules to read-only
3. Block dependent modules

### Forbidden
- Manual schema edits
- Forced retries

---

## 4A) Database Failover Runbook

### Detection
- Primary DB health check failures
- Replication lag breaches
- Connection pool failures

### Response
1. Freeze writes at control plane
2. Promote replica (if pre-approved)
3. Redirect runtime connections
4. Verify data consistency checks

### Recovery
- Rebuild failed primary
- Audit failover event
- Post-mortem mandatory

---

## 4B) Policy Lag Runbook

### Detection
- Policy version drift between runtime and control plane
- Authorization decisions using stale policy version

### Response
1. Fail closed for affected policy scopes
2. Force policy cache refresh
3. Block policy writes until consistency restored

### Recovery
- Validate policy version convergence
- Re-enable authorization traffic
- Post-mortem mandatory

---

## 5) Tenant Isolation Runbook

### Triggers
- Isolation thresholds breached
- Compliance escalation

### Steps
1. Mark tenant as `isolating`
2. Provision target shard
3. Migrate tenant data
4. Switch routing
5. Resume access

All steps are auditable.

---

## 6) Security Incident Runbook

### Triggers
- Policy bypass attempt
- Unauthorized access
- Cross-region access violation

### Response
1. Fail closed (block access)
2. Activate kill switches
3. Preserve evidence
4. Notify security leads

### Post-Incident
- Root cause analysis
- Policy or platform update

---

## 6A) Authentication Outage Runbook

Authentication failures are treated as **platform-wide risk events**.

### Scenarios Covered
- Identity Provider (OIDC / SAML) outage
- Session store (Redis / DB) outage
- Partial federation failure (some tenants or IdPs impacted)

---

### A) Identity Provider (IdP) Outage

#### Detection
- Spike in login failures
- IdP health checks failing

#### Response
1. Disable new login attempts for affected IdP
2. Preserve existing valid sessions
3. Notify impacted tenant admins
4. Escalate to IdP provider

#### Forbidden
- Falling back to weaker authentication
- Issuing temporary credentials

---

### B) Session Store Outage

#### Detection
- Session validation failures
- Elevated auth error rates

#### Response
1. Fail closed for new requests
2. Preserve audit logs
3. Attempt session store restore
4. Invalidate all sessions if corruption is suspected

Session store outages are **SEV-1** events.

---

### C) Partial Federation Failure

#### Detection
- Auth failures limited to specific tenants or IdPs

#### Response
1. Isolate affected tenants
2. Disable impacted federation configs
3. Maintain unaffected tenant access
4. Communicate status transparently

---

### Post-Incident Requirements
- Root cause analysis
- Session integrity verification
- Preventive control update

---

## 7) AI Agent Incident Runbook

### Triggers
- Agent runaway execution
- Unauthorized tool invocation

### Response
1. Terminate agent
2. Revoke agent permissions
3. Freeze affected workflows

### Forbidden
- Letting agent continue “to finish task"

---

## 7A) AI Capacity & Saturation Runbook

This runbook governs **AI-specific capacity exhaustion** to ensure AI workloads never destabilize core transactional operations.

### Triggers (Any One)
- AI agent concurrency > 70% of shard ceiling
- LLM token throughput > 65% of shard budget for 5 minutes
- Tool invocation backlog growth
- AI-induced API latency degradation

---

### Automated Response (Immediate)
1. Throttle new AI agent executions
2. Queue non-critical agent requests
3. Reduce AI token allocation per tenant
4. Emit saturation and audit events

AI throttling MUST NOT impact non-AI API traffic.

---

### Escalation Path (If Sustained > 15 minutes)
1. Identify top AI-consuming tenants
2. Apply per-tenant AI quota clamps
3. Freeze AI execution for offending tenants
4. Flag tenants for isolation review

---

### Human-Approved Actions
- Force tenant AI isolation
- Provision AI-dedicated shard
- Adjust commercial AI quotas

---

### Forbidden Actions
- Disabling AI quotas globally
- Increasing shard AI ceilings under pressure
- Allowing AI workloads to degrade transactional latency

---

### Post-Incident Requirements
- AI usage and token analysis
- Cost impact assessment
- Update AI quota baselines if justified
- Mandatory post-mortem for SEV-1 / SEV-2

---

## 8) Quota Abuse Runbook

### Detection
- Repeated quota violations

### Response
1. Throttle tenant
2. Notify tenant admin
3. Flag for isolation review

---

## 9) Control Plane Failure Runbook

### Detection
- Control plane unavailable

### Response
- Runtime continues last known-good config
- Freeze lifecycle actions
- Restore control plane ASAP

---

## 10) Post-Incident Discipline

Every SEV-1 / SEV-2 requires:
- Written post-mortem
- Concrete preventive action
- Runbook update if needed

No blame. Only fixes.

---

## 11) What Is Explicitly Forbidden

- Ad-hoc fixes in production
- Silent data correction
- Skipping post-mortems
- “Temporary” policy bypasses

Violations are treated as platform failures.

---

## 12) Final Warning

Systems do not fail catastrophically.

People panic catastrophically.

These runbooks exist to prevent that.

---

**End of document**

---
