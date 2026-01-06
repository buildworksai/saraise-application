---
description: Performance SLA enforcement rules for SARAISE
globs: ["backend/**/*.py", "frontend/**/*.ts", "frontend/**/*.tsx"]
alwaysApply: false
---

# SARAISE-24 Performance SLA Rules

**Reference**: `docs/architecture/performance-slas.md`

This rule file enforces performance standards across the SARAISE codebase.

## SARAISE-24001 API Latency Targets

All API endpoints MUST meet these p99 latency targets:

| Operation | p99 Target | Hard Limit |
|-----------|------------|------------|
| GET single record | ≤50ms | 100ms |
| GET list | ≤100ms | 200ms |
| POST/PUT | ≤200ms | 400ms |
| DELETE | ≤150ms | 300ms |
| Session validation | ≤5ms | 10ms |
| Policy Engine | ≤7ms | 15ms |

**Enforcement**: Performance tests must verify compliance before release.

## SARAISE-24002 Database Performance Rules

### Required Indexes

All tenant-scoped tables MUST have indexes on:
- `tenant_id` (single column)
- `(tenant_id, created_at)` compound index
- `(tenant_id, status)` compound index (if status filtering is common)

### Query Rules

```python
# ✅ CORRECT: Use select_related for FKs
queryset = Model.objects.select_related('tenant', 'created_by').filter(...)

# ❌ FORBIDDEN: N+1 queries
for item in items:
    print(item.tenant.name)  # N+1 query pattern

# ✅ CORRECT: Limit results
queryset = Model.objects.filter(tenant_id=tenant_id)[:100]

# ❌ FORBIDDEN: Unbounded queries
queryset = Model.objects.filter(tenant_id=tenant_id)  # No limit
```

## SARAISE-24003 Frontend Performance Rules

### Bundle Size Limits

| Bundle | Maximum (gzipped) |
|--------|------------------|
| Main bundle | 150KB |
| Vendor bundle | 200KB |
| Per-module chunk | 50KB |
| Total initial load | 400KB |

### Core Web Vitals

| Metric | Target |
|--------|--------|
| LCP | ≤2.0s |
| FID | ≤50ms |
| CLS | ≤0.05 |

### Enforcement

```typescript
// ✅ CORRECT: Lazy load modules
const Module = lazy(() => import('./modules/ModuleName'));

// ❌ FORBIDDEN: Eager load all modules
import { AllModules } from './modules';
```

## SARAISE-24004 Cache Requirements

### Session Cache

- Hit rate MUST be ≥95%
- TTL: configurable per environment

### Application Cache

- Hit rate SHOULD be ≥80%
- Use Redis for distributed cache

```python
# ✅ CORRECT: Cache expensive queries
@cache.cached(timeout=300, key_prefix='tenant_config')
def get_tenant_config(tenant_id: str):
    return TenantConfig.objects.get(tenant_id=tenant_id)
```

## SARAISE-24005 What Is Forbidden

- ❌ Deploying without performance tests
- ❌ Unbounded queries (MUST have LIMIT)
- ❌ N+1 query patterns
- ❌ Synchronous external calls in request path
- ❌ Missing indexes on `tenant_id`
- ❌ Bundle size exceeding limits
- ❌ Performance regressions shipped to production

## SARAISE-24006 Performance Testing Requirements

Before release, ALL modules MUST pass:

1. **Load test**: 1,000 concurrent users, 15 minutes
2. **Stress test**: 2x expected peak, 5 minutes
3. **Soak test**: Baseline load, 4 hours

**Performance regression definition**:
- p99 latency increases by >10%
- Throughput decreases by >5%
- Error rate increases by >0.1%

**Performance regressions block release.**

---

**Enforcement**: CI pipeline includes performance baseline checks.

