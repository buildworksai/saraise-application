# SARAISE Performance SLAs & Latency Targets

**Status:** Authoritative — Freeze Blocking  
**Version:** 1.0.0  
**Last Updated:** January 5, 2026

This document defines the **non-negotiable performance contracts** for SARAISE. All implementations MUST meet these targets. Performance is not optional — it is a correctness requirement.

---

## 0) Non-Negotiable Principles

1. **Performance is a feature.** Slow is broken.
2. **Latency targets are contracts.** Violations are bugs.
3. **p99 matters more than average.** Tail latency defines user experience.
4. **Performance must be measured.** If you can't measure it, you can't claim compliance.
5. **Regression is a release blocker.** Performance regressions fail the build.

---

## 1) API Latency Targets (p99)

All latency targets are measured at p99 under **1,000 concurrent users** per tenant.

### 1.1 Read Operations

| Operation Type | p50 Target | p90 Target | p99 Target | Hard Limit |
|----------------|------------|------------|------------|------------|
| Simple GET (single record) | ≤10ms | ≤25ms | ≤50ms | 100ms |
| List with pagination | ≤25ms | ≤50ms | ≤100ms | 200ms |
| List with filters | ≤30ms | ≤75ms | ≤150ms | 300ms |
| Complex aggregation | ≤50ms | ≤150ms | ≤300ms | 500ms |
| Search query | ≤50ms | ≤100ms | ≤200ms | 400ms |

### 1.2 Write Operations

| Operation Type | p50 Target | p90 Target | p99 Target | Hard Limit |
|----------------|------------|------------|------------|------------|
| Simple POST/PUT | ≤50ms | ≤100ms | ≤200ms | 400ms |
| POST with validation | ≤75ms | ≤150ms | ≤300ms | 500ms |
| Bulk create (100 records) | ≤200ms | ≤400ms | ≤800ms | 1500ms |
| DELETE | ≤30ms | ≤75ms | ≤150ms | 300ms |

### 1.3 Authentication & Authorization

| Operation Type | p50 Target | p90 Target | p99 Target | Hard Limit |
|----------------|------------|------------|------------|------------|
| Session validation | ≤1ms | ≤2ms | ≤5ms | 10ms |
| Policy Engine evaluation | ≤2ms | ≤4ms | ≤7ms | 15ms |
| Login (full flow) | ≤100ms | ≤200ms | ≤400ms | 800ms |
| Session refresh | ≤5ms | ≤10ms | ≤25ms | 50ms |

---

## 2) Database Performance Targets

### 2.1 Query Performance

| Query Type | p99 Target | Index Required | Notes |
|------------|------------|----------------|-------|
| Primary key lookup | ≤1ms | Built-in | Single row |
| Tenant-filtered list | ≤10ms | `tenant_id` | MUST be indexed |
| Multi-column filter | ≤20ms | Composite | Create composite indexes |
| JOIN (2 tables) | ≤30ms | FK indexes | Use `select_related()` |
| JOIN (3+ tables) | ≤50ms | FK indexes | Consider denormalization |

### 2.2 Connection Pool

| Metric | Target | Hard Limit |
|--------|--------|------------|
| Connection acquisition | ≤5ms | 20ms |
| Connection pool saturation | ≤80% | 95% |
| Connections per worker | 10-20 | 50 |

### 2.3 Required Indexes

All tenant-scoped tables MUST have indexes on:
- `tenant_id` (single column)
- `tenant_id, created_at` (compound, descending)
- `tenant_id, {status_field}` (compound, if status filtering is common)

---

## 3) Cache Performance Targets

### 3.1 Redis Cache

| Operation | p99 Target | Hard Limit |
|-----------|------------|------------|
| GET (single key) | ≤1ms | 5ms |
| SET (single key) | ≤2ms | 10ms |
| MGET (batch, ≤100 keys) | ≤5ms | 20ms |
| Pipeline (≤50 ops) | ≤10ms | 50ms |

### 3.2 Cache Hit Rates

| Cache Type | Minimum Hit Rate | Target Hit Rate |
|------------|-----------------|-----------------|
| Session cache | 95% | 99% |
| Policy cache | 90% | 95% |
| Application cache | 80% | 90% |

---

## 4) AI Agent Performance Targets

### 4.1 Agent Execution

| Operation | p99 Target | Hard Limit | Notes |
|-----------|------------|------------|-------|
| Tool registration lookup | ≤5ms | 20ms | Cached |
| Permission check (per tool) | ≤7ms | 15ms | Policy Engine |
| Quota validation | ≤3ms | 10ms | Redis-backed |
| Audit event emission | ≤5ms | 20ms | Async preferred |

### 4.2 Agent Limits

| Metric | Default Limit | Hard Maximum |
|--------|--------------|--------------|
| Max execution time | 5 minutes | 30 minutes |
| Max tool calls per execution | 50 | 200 |
| Max reasoning steps | 100 | 500 |
| Max concurrent agents per tenant | 10 | 50 |

---

## 5) Frontend Performance Targets

### 5.1 Core Web Vitals

| Metric | Target | Hard Limit |
|--------|--------|------------|
| First Contentful Paint (FCP) | ≤1.0s | 1.8s |
| Largest Contentful Paint (LCP) | ≤2.0s | 2.5s |
| First Input Delay (FID) | ≤50ms | 100ms |
| Cumulative Layout Shift (CLS) | ≤0.05 | 0.1 |
| Time to Interactive (TTI) | ≤3.0s | 5.0s |

### 5.2 Bundle Size Limits

| Bundle | Maximum Size (gzipped) |
|--------|----------------------|
| Main bundle | 150KB |
| Vendor bundle | 200KB |
| Per-module chunk | 50KB |
| Total initial load | 400KB |

---

## 6) Throughput Targets

### 6.1 Per-Tenant Throughput

| Tier | Requests/second | Concurrent Users |
|------|----------------|-----------------|
| Starter | 100 RPS | 50 |
| Professional | 500 RPS | 250 |
| Enterprise | 2,000 RPS | 1,000 |
| Dedicated | 10,000 RPS | 5,000 |

### 6.2 Platform Throughput

| Metric | Target | Notes |
|--------|--------|-------|
| Total platform RPS | 100,000+ | All tenants combined |
| Peak burst capacity | 3x baseline | Auto-scaling enabled |
| Cold start time | ≤5s | New container ready |

---

## 7) Error Rate Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| 5xx error rate | ≤0.01% | 0.1% |
| 4xx error rate | ≤1% | 5% |
| Timeout rate | ≤0.1% | 0.5% |
| Database error rate | ≤0.001% | 0.01% |

---

## 8) Availability Targets

| Tier | Monthly Uptime | Max Downtime/Month |
|------|---------------|-------------------|
| Starter | 99.5% | 3.6 hours |
| Professional | 99.9% | 43 minutes |
| Enterprise | 99.95% | 21 minutes |
| Dedicated | 99.99% | 4 minutes |

---

## 9) Monitoring & Alerting

### 9.1 Required Metrics

All services MUST expose:
- Request latency (histogram: p50, p90, p95, p99)
- Request rate (counter)
- Error rate (counter by status code)
- Active connections (gauge)
- Queue depth (gauge, where applicable)

### 9.2 Alerting Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| p99 latency | 150% of target | 200% of target | Page on-call |
| Error rate | 2x target | 5x target | Page on-call |
| CPU utilization | 70% | 85% | Auto-scale |
| Memory utilization | 75% | 90% | Investigate |

---

## 10) Performance Testing Requirements

### 10.1 Mandatory Tests

Before release, ALL modules MUST pass:
1. **Load test**: 1,000 concurrent users, 15 minutes
2. **Stress test**: 2x expected peak, 5 minutes
3. **Soak test**: Baseline load, 4 hours
4. **Spike test**: 0 → 5x load → 0, instantaneous

### 10.2 Test Infrastructure

- Tool: Locust or k6
- Environment: Staging (production-equivalent)
- Data: Production-like dataset size
- Frequency: Every release, weekly scheduled

### 10.3 Regression Detection

Performance regression is defined as:
- p99 latency increases by >10%
- Throughput decreases by >5%
- Error rate increases by >0.1%

**Performance regressions block release.**

---

## 11) Capacity Planning

### 11.1 Resource Ratios

| Users | API Pods | Worker Pods | DB Connections |
|-------|----------|-------------|----------------|
| 100 | 2 | 1 | 20 |
| 500 | 4 | 2 | 50 |
| 1,000 | 8 | 4 | 100 |
| 5,000 | 16 | 8 | 200 |

### 11.2 Scaling Triggers

| Metric | Scale Up | Scale Down |
|--------|----------|------------|
| CPU | >70% for 2 min | <30% for 10 min |
| Memory | >75% for 2 min | <40% for 10 min |
| Request queue | >100 for 1 min | <10 for 5 min |

---

## 12) What Is Explicitly Forbidden

- ❌ Deploying without performance tests
- ❌ Ignoring p99 latency violations
- ❌ Unbounded queries (MUST have LIMIT)
- ❌ N+1 query patterns in production
- ❌ Synchronous external calls in request path
- ❌ Missing indexes on `tenant_id`
- ❌ Performance regressions shipped to production

---

## 13) Final Warning

Performance is not an afterthought. It is a **design constraint**.

If a feature cannot meet these SLAs, it does not ship until it does.

---

**Verification Checksum**
- Document: performance-slas.md
- Purpose: Define non-negotiable performance contracts
- Status: Authoritative — Freeze Blocking

---

**End of document**

