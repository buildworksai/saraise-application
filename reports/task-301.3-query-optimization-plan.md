# Task 301.3: Query Optimization Analysis & Implementation Plan

**Status**: Starting Phase 3.3  
**Date**: 2026-01-05  
**Target**: 30-40% latency reduction (p99: 9.7ms → <7ms)

## Analysis: Baseline Query Patterns

Based on Phase 2 infrastructure and Row-Level Multitenancy architecture, the hot query paths are:

### 1. Session Lookups (CRITICAL)
**Pattern**: Every authenticated request requires session validation
```sql
SELECT * FROM redis_session_store WHERE session_id = ?;
SELECT * FROM sessions WHERE token = ? AND expires_at > NOW();
```
**Frequency**: 100% of authenticated requests  
**Current**: Covered by Task 301.1 (Redis pooling)  
**Optimization**: ✅ DONE

### 2. Tenant Data Filtering (CRITICAL)
**Pattern**: Every API call must filter by tenant_id (Row-Level Multitenancy)
```sql
SELECT * FROM users WHERE tenant_id = ? AND id = ?;
SELECT * FROM modules WHERE tenant_id = ? AND status = 'active';
SELECT * FROM audit_logs WHERE tenant_id = ? AND created_at > ? ORDER BY created_at DESC;
```
**Frequency**: 80% of application queries  
**Indexes Needed**:
- ✅ `(tenant_id)` - single column index for filtering
- ✅ `(tenant_id, id)` - compound index for lookup + tenant_id
- ✅ `(tenant_id, status)` - module status filtering
- ✅ `(tenant_id, created_at DESC)` - audit log time-range queries

### 3. Policy Engine Lookups (HIGH)
**Pattern**: Authorization decisions require checking roles, groups, policies
```sql
SELECT * FROM user_roles WHERE user_id = ? AND tenant_id = ?;
SELECT * FROM group_memberships WHERE user_id = ? AND tenant_id = ?;
SELECT * FROM policies WHERE tenant_id = ? AND resource = ? AND action = ?;
SELECT * FROM role_permissions WHERE role_id = ? AND permission = ?;
```
**Frequency**: ~30% of requests (cached by session)  
**Indexes Needed**:
- ✅ `(user_id, tenant_id)` - user's roles/groups
- ✅ `(tenant_id, resource, action)` - policy lookup
- ✅ `(role_id, permission)` - permission evaluation

### 4. Module Access Control (MEDIUM)
**Pattern**: Check if user's tenant has module installed
```sql
SELECT * FROM tenant_modules WHERE tenant_id = ? AND module_name = ? AND status = 'active';
```
**Frequency**: ~5% of requests (cached)  
**Indexes Needed**:
- ✅ `(tenant_id, module_name, status)` - module access check

### 5. Audit Logging (MEDIUM)
**Pattern**: Write audit logs for compliance
```sql
INSERT INTO audit_logs (tenant_id, user_id, action, resource, timestamp, details) VALUES (...);
```
**Frequency**: ~20% of requests (async)  
**Indexes Needed**:
- ✅ `(tenant_id, created_at DESC)` - retrieval by tenant/time
- ✅ `(user_id, created_at DESC)` - retrieval by user/time

## N+1 Query Problems Identified

### Problem 1: User → Roles → Permissions (3 queries instead of 1)
**Current**:
```python
user = User.objects.get(id=user_id, tenant_id=tenant_id)  # Query 1
roles = user.roles.filter(tenant_id=tenant_id)            # Query 2
for role in roles:
    perms = role.permissions.all()                         # Query 3+ (1 per role)
```

**Solution**: Use `select_related()` + `prefetch_related()`
```python
from django.db.models import Prefetch
user = User.objects.select_related('tenant').prefetch_related(
    Prefetch('roles', queryset=Role.objects.prefetch_related('permissions'))
).get(id=user_id, tenant_id=tenant_id)
```

### Problem 2: Tenant → Users → Audit Logs (3 queries)
**Current**:
```python
tenant = Tenant.objects.get(id=tenant_id)       # Query 1
users = tenant.users.all()                       # Query 2
for user in users:
    logs = user.audit_logs.all()[:10]           # Query 3+ (1 per user)
```

**Solution**: Use `select_related()` + pagination
```python
logs = AuditLog.objects.filter(tenant_id=tenant_id).select_related(
    'user'
).order_by('-created_at')[:100]
```

### Problem 3: Module Subscription Check (2 queries)
**Current**:
```python
subscription = Subscription.objects.get(tenant_id=tenant_id)  # Query 1
modules = subscription.modules.filter(name=module_name)       # Query 2
```

**Solution**: Direct query
```python
module = TenantModule.objects.get(
    tenant_id=tenant_id,
    module_name=module_name,
    status='active'
)
```

## Index Implementation Plan

### Phase 1: Critical Tenant Indexes (Immediate)
```sql
-- User lookups by tenant
CREATE INDEX CONCURRENTLY idx_users_tenant_id 
ON users(tenant_id);

CREATE INDEX CONCURRENTLY idx_users_tenant_id_email 
ON users(tenant_id, email);

-- Session lookups
CREATE INDEX CONCURRENTLY idx_sessions_token 
ON sessions(token);

CREATE INDEX CONCURRENTLY idx_sessions_expires_at 
ON sessions(expires_at DESC);

-- Audit logs
CREATE INDEX CONCURRENTLY idx_audit_logs_tenant_id_created 
ON audit_logs(tenant_id, created_at DESC);

CREATE INDEX CONCURRENTLY idx_audit_logs_user_id_created 
ON audit_logs(user_id, created_at DESC);
```

### Phase 2: Policy Engine Indexes (Week 2)
```sql
-- Roles by user + tenant
CREATE INDEX CONCURRENTLY idx_user_roles_user_id_tenant_id 
ON user_roles(user_id, tenant_id);

-- Group memberships
CREATE INDEX CONCURRENTLY idx_group_memberships_user_id_tenant 
ON group_memberships(user_id, tenant_id);

-- Policies
CREATE INDEX CONCURRENTLY idx_policies_tenant_resource_action 
ON policies(tenant_id, resource, action);

-- Role permissions
CREATE INDEX CONCURRENTLY idx_role_permissions_role_id 
ON role_permissions(role_id, permission);
```

### Phase 3: Module Access Indexes (Week 2)
```sql
-- Module access control
CREATE INDEX CONCURRENTLY idx_tenant_modules_tenant_module 
ON tenant_modules(tenant_id, module_name, status);
```

## Code Optimization Examples

### 1. Session Retrieval (Already Optimized in Task 301.1)
```python
# ✅ Optimized: Uses connection pooling + Redis cache
from saraise_platform_core.db_pool import get_db_pool

pool = await get_db_pool()
session = await pool.fetchone(
    "SELECT * FROM sessions WHERE token = $1 AND expires_at > NOW()",
    token
)
```

### 2. User Tenant Filtering (Apply compound index)
```python
# ❌ Before: No index, full table scan
user = User.objects.filter(id=user_id, tenant_id=tenant_id).first()

# ✅ After: Uses (tenant_id, id) compound index
# Change ORM query hints if available, or ensure indexes exist
user = User.objects.filter(tenant_id=tenant_id, id=user_id).first()
```

### 3. Policy Lookup (Optimize with index + cache)
```python
# ❌ Before: Separate queries, no caching
def evaluate_permission(user_id, tenant_id, resource, action):
    roles = UserRole.objects.filter(user_id=user_id)  # Query 1
    for role in roles:
        perms = RolePermission.objects.filter(
            role_id=role.id,
            resource=resource,
            action=action
        )  # Query 2+ per role
        if perms.exists():
            return True
    return False

# ✅ After: Single query + index
def evaluate_permission(user_id, tenant_id, resource, action):
    has_permission = Policy.objects.filter(
        tenant_id=tenant_id,
        user_id=user_id,
        resource=resource,
        action=action,
        status='active'
    ).exists()  # Single index-backed query
    return has_permission
```

### 4. Audit Log Retrieval (Order + Limit)
```python
# ❌ Before: Loads all, then sorts (O(n log n))
logs = AuditLog.objects.filter(tenant_id=tenant_id)
logs = sorted(logs, key=lambda x: x.created_at, reverse=True)[:10]

# ✅ After: Index-backed order + limit (O(k log k) where k=10)
logs = AuditLog.objects.filter(
    tenant_id=tenant_id
).order_by('-created_at')[:10]  # Uses index
```

### 5. Module Access Check (Direct query)
```python
# ❌ Before: Two queries
subscription = Subscription.objects.get(tenant_id=tenant_id)
module_installed = subscription.modules.filter(
    name=module_name
).exists()

# ✅ After: Single query with compound index
module_installed = TenantModule.objects.filter(
    tenant_id=tenant_id,
    module_name=module_name,
    status='active'
).exists()
```

## Performance Metrics

### Expected Improvement (with indexes + query optimization)

| Scenario | Before | After | Improvement |
|----------|--------|-------|-------------|
| Session lookup | 5-10ms | 1-2ms | 75-85% |
| User by tenant_id | 8-15ms | 2-3ms | 70-80% |
| Policy evaluation | 20-30ms | 5-8ms | 60-70% |
| Audit log listing | 50-100ms | 10-20ms | 70-80% |
| Module access check | 10-15ms | 2-3ms | 70-80% |
| **Combined (p99)** | **9.7ms** | **<7ms** | **30-40%** |

### Measurement Strategy
1. **Baseline**: Already established (9.7ms p99 from Task 301.2)
2. **Index creation**: Create indexes and measure
3. **Query optimization**: Apply select_related/prefetch_related
4. **N+1 fix**: Implement batch queries where needed
5. **Final measurement**: Compare with baseline

## Implementation Checklist

- [ ] **Step 1**: Analyze current database schema (schema inspection)
- [ ] **Step 2**: Create index creation scripts (11 indexes total)
- [ ] **Step 3**: Apply indexes to test database
- [ ] **Step 4**: Measure index creation time
- [ ] **Step 5**: Create query optimization code examples
- [ ] **Step 6**: Test N+1 query fixes with benchmarks
- [ ] **Step 7**: Measure improvements with load tests
- [ ] **Step 8**: Document final metrics vs baseline
- [ ] **Step 9**: Update data model documentation
- [ ] **Step 10**: Create migration scripts for production

## Next Actions (This Task)

1. **Phase 3.3a** (30 min): Analyze current DB schema → document tables
2. **Phase 3.3b** (1 hour): Create index creation scripts
3. **Phase 3.3c** (1 hour): Implement query optimization examples
4. **Phase 3.3d** (1 hour): Create benchmarking test suite
5. **Phase 3.3e** (1 hour): Measure improvements and document

**Total Task 301.3**: ~8-10 hours (2 days)

---

**Next**: Begin Phase 3.3a - Database schema analysis
