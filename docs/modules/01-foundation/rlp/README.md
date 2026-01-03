# Resource-Level Permissions (RLP)

## Overview

Resource-Level Permissions (RLP) provides row-level security (RLS) and field-level security (FLS) for SARAISE. RLP automatically filters queries and masks sensitive fields based on ownership, assignment, hierarchy, sharing, and custom rules.

## Architecture

### Components

1. **RLPQueryFilter** (`backend/src/modules/security/rlp/query_filter.py`)
   - Core component that applies row-level and field-level security
   - Supports ownership, assigned, hierarchy, team, sharing, and custom rules
   - Integrates with ABAC for complex custom rules

2. **RLPMiddleware** (`backend/src/modules/security/rlp/middleware.py`)
   - Django middleware that automatically injects RLP filters
   - Uses Django ORM QuerySet filtering for transparent security enforcement

3. **RLPRuleEngine** (`backend/src/modules/security/rlp/rule_engine.py`)
   - Fetches applicable RLP rules for users and resource types
   - Filters rules by role, tenant, and active status

4. **RecordSharingManager** (`backend/src/modules/security/rlp/sharing_manager.py`)
   - Manages explicit record sharing (user/team/role)
   - Handles temporary shares with expiration

5. **HierarchyManager** (`backend/src/modules/security/rlp/hierarchy_manager.py`)
   - Manages user reporting hierarchies
   - Uses PostgreSQL LTREE for efficient hierarchy queries

6. **RLPQueryCacheManager** (`backend/src/modules/security/rlp/query_cache.py`)
   - Redis + database caching for RLP rule evaluations
   - Target: <5ms overhead per query

## Database Schema

### Tables

- `rlp_row_security_rules` - Row-level security rule definitions
- `rlp_field_security_rules` - Field-level security rule definitions
- `rlp_record_shares` - Explicit record sharing grants
- `rlp_user_hierarchies` - User reporting hierarchy (LTREE)
- `rlp_access_denials` - Audit log of access denials
- `rlp_query_cache` - Performance cache for RLP filters

See migration: `backend/src/modules/security_access_control/migrations/004_rlp_architecture.py`

## Rule Types

### Row-Level Security Rules

1. **Ownership** - User can access records they created
   ```json
   {
     "type": "ownership",
     "field": "created_by"
   }
   ```

2. **Assigned** - User can access records assigned to them
   ```json
   {
     "type": "assigned",
     "field": "assigned_to"
   }
   ```

3. **Hierarchy** - User can access records created by their direct reports
   ```json
   {
     "type": "hierarchy",
     "field": "created_by"
   }
   ```

4. **Team** - User can access records belonging to their team
   ```json
   {
     "type": "team",
     "field": "team_id"
   }
   ```

5. **Sharing** - User can access explicitly shared records
   ```json
   {
     "type": "sharing"
   }
   ```

6. **Custom** - Complex rules evaluated via ABAC
   ```json
   {
     "type": "custom",
     "condition": {
       "type": "equals",
       "attribute": "resource.status",
       "value": "Active"
     }
   }
   ```

### Field-Level Security Rules

- **Read Roles** - Roles that can read the field
- **Write Roles** - Roles that can write the field
- **Masking** - Mask sensitive values (SSN, credit card, email, etc.)
- **Compliance Classification** - PII, PHI, PCI, Confidential

## Usage

### Enable RLP for Session

```python
from src.core.database import get_db_with_rlp
from src.core.auth_decorators import get_current_user_from_session

@router.get("/opportunities")
async def list_opportunities(
    current_user: User = Depends(get_current_user_from_session),
    db: AsyncSession = Depends(get_db_with_rlp)
):
    # RLP is automatically enabled for authenticated sessions
    # All queries are automatically filtered
    result = await db.execute(select(Opportunity))
    # User sees ONLY opportunities they have access to
    return result.scalars().all()
```

### Manual RLP Application

```python
from src.modules.security.rlp.query_filter import RLPQueryFilter

rlp_filter = RLPQueryFilter(session, tenant_id, user_id)
query = await rlp_filter.apply_row_security(query, "Opportunity", "read")
```

### Field-Level Security

```python
records = await db.execute(select(Employee))
employees = records.scalars().all()

# Apply field-level security (masks/removes sensitive fields)
filtered = await rlp_filter.apply_field_security(employees, "Employee", "read")
```

## API Endpoints

### Row Security Rules

- `POST /api/v1/rlp/row-security-rules` - Create row security rule
- `GET /api/v1/rlp/row-security-rules` - List row security rules

### Field Security Rules

- `POST /api/v1/rlp/field-security-rules` - Create field security rule
- `GET /api/v1/rlp/field-security-rules` - List field security rules

### Record Sharing

- `POST /api/v1/rlp/shares` - Share record with user/team/role
- `DELETE /api/v1/rlp/shares/{share_id}` - Revoke share
- `GET /api/v1/rlp/shares/by-user/{user_id}` - Get user's shares

### Hierarchy Management

- `POST /api/v1/rlp/hierarchies` - Set user's manager
- `GET /api/v1/rlp/hierarchies/subordinates/{manager_id}` - Get subordinates

### Access Testing

- `POST /api/v1/rlp/test-access` - Test if user can access record

### Audit Logs

- `GET /api/v1/rlp/access-denials` - Query access denial audit log

## Integration Patterns

### ABAC Integration

Custom RLP rules use ABAC for complex condition evaluation:

```python
# Custom rule with ABAC condition
rule_expression = {
    "type": "custom",
    "condition": {
        "type": "AND",
        "conditions": [
            {"type": "equals", "attribute": "resource.status", "value": "Active"},
            {"type": "greater_than", "attribute": "resource.amount", "value": 10000}
        ]
    }
}
```

The condition is translated to SQL WHERE clause when possible, or evaluated via ABAC PDP.

### JIT Integration

JIT-granted permissions can bypass RLP:

- `rlp.bypass` - Bypass all RLP
- `rlp.bypass.{resource_type}` - Bypass RLP for specific resource type

```python
# User with JIT permission
user._cached_jit_permissions = ["rlp.bypass.Opportunity"]

# RLP is automatically bypassed for Opportunity queries
```

### SoD Integration

RLP detects and logs SoD violations when rules conflict with SoD policies:

```python
# When RLP rule applies to role that conflicts with user's existing roles
# SoD violation is logged to audit service
```

### Resource Integration

RLP checks Resource metadata for `rlp_enabled` flag:

```python
# Resource permissions
{
    "rlp_enabled": true  # Enable RLP for this Resource
}
```

If `rlp_enabled` is `false` or not set, RLP is not applied (defaults to `true`).

## Performance

### Caching

RLP uses Redis + database caching for rule evaluations:

- **Cache Key**: `rlp:filter:{tenant_id}:{user_id}:{resource_type}:{action}`
- **TTL**: 5 minutes (300 seconds)
- **Target**: <5ms overhead per query

### Cache Invalidation

Cache is invalidated when:
- RLP rules are created/updated/deleted
- Record shares are created/revoked
- User hierarchies are updated

## Security Considerations

### Deny-by-Default

- If no RLP rules are found, access is **denied** (deny-by-default)
- This ensures sensitive resources are protected even without explicit rules

### Audit Logging

All access denials are logged to `rlp_access_denials` table:
- User ID
- Resource type/ID
- Action attempted
- Denial reason
- Applicable rule ID
- IP address, user agent
- Suspicious activity flag

### Multi-Tenant Isolation

- All RLP rules are tenant-scoped
- Users can only access records within their tenant
- Cross-tenant access is prevented

## Troubleshooting

### RLP Not Applied

1. Check if RLP is enabled for session:
   ```python
   assert session.info.get("rlp_enabled") == True
   ```

2. Check if RLP is enabled for Resource:
   ```python
   resource.permissions.get("rlp_enabled", True)
   ```

3. Check if user has JIT bypass:
   ```python
   "rlp.bypass" in user._cached_jit_permissions
   ```

### Access Denied Unexpectedly

1. Check access denial log:
   ```bash
   GET /api/v1/rlp/access-denials?user_id={user_id}&resource_type={resource_type}
   ```

2. Verify applicable rules:
   ```python
   rules = await rule_engine.get_applicable_rules(resource_type, user_id, "read")
   ```

3. Test access:
   ```bash
   POST /api/v1/rlp/test-access
   {
     "user_id": "...",
     "resource_type": "...",
     "resource_id": "...",
     "action": "read"
   }
   ```

### Performance Issues

1. Check cache hit rate:
   ```python
   # Cache should be hit for repeated queries
   ```

2. Verify indexes are present:
   ```sql
   SELECT * FROM pg_indexes WHERE tablename LIKE 'rlp_%';
   ```

3. Monitor query performance:
   ```python
   # RLP should add <5ms overhead
   ```

## Examples

### Example 1: Ownership Rule

```python
# Create rule: Users can only see opportunities they created
POST /api/v1/rlp/row-security-rules
{
    "rule_name": "Own Opportunities Only",
    "resource_type": "Opportunity",
    "rule_type": "ownership",
    "rule_expression": {
        "type": "ownership",
        "field": "created_by"
    },
    "applies_to_roles": ["Sales Rep"],
    "priority": 100
}
```

### Example 2: Field Masking

```python
# Create rule: Mask SSN field for non-HR users
POST /api/v1/rlp/field-security-rules
{
    "rule_name": "SSN Confidentiality",
    "resource_type": "Employee",
    "field_name": "ssn",
    "read_roles": ["HR Manager", "CEO"],
    "is_masked": true,
    "mask_pattern": "ssn",
    "compliance_classification": "PII"
}
```

### Example 3: Record Sharing

```python
# Share opportunity with sales rep
POST /api/v1/rlp/shares
{
    "resource_type": "Opportunity",
    "resource_id": "opp-123",
    "shared_with_user_id": "user-456",
    "access_level": "read",
    "expires_at": "2025-12-31T23:59:59Z",
    "share_reason": "Temporary collaboration"
}
```

### Example 4: Hierarchy Access

```python
# Set manager hierarchy
POST /api/v1/rlp/hierarchies
{
    "user_id": "user-456",
    "manager_id": "user-123",
    "effective_from": "2025-01-01T00:00:00Z"
}

# Manager can now see records created by their direct reports
```

## Testing

### Unit Tests

```bash
pytest backend/src/modules/security/rlp/tests/test_query_filter.py
pytest backend/src/modules/security/rlp/tests/test_middleware.py
pytest backend/src/modules/security/rlp/tests/test_rule_engine.py
```

### Integration Tests

```bash
pytest backend/src/modules/security/rlp/tests/test_integration.py
```

## References

- [AGENT_A-RLP.md](../../../../planning/development_agents/AGENT_A-RLP.md) - Full implementation plan
- [ABAC Integration](../abac/README.md) - ABAC policy engine
- [JIT Access](../../../../planning/development_agents/AGENT_A-JIT.md) - Just-In-Time access
- [SoD Enforcement](../../../../planning/development_agents/AGENT_A-SoD.md) - Segregation of Duties
