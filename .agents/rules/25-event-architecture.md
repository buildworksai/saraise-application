---
description: Event-driven architecture rules for SARAISE
globs: ["backend/**/*.py"]
alwaysApply: false
---

# SARAISE-25 Event Architecture Rules

**Reference**: `docs/architecture/event-driven-architecture.md`

This rule file enforces event-driven patterns across the SARAISE codebase.

## SARAISE-25001 Event Immutability

Events are immutable facts. Once published, they CANNOT be changed.

```python
# ❌ FORBIDDEN: Updating events
event = DomainEvent.objects.get(id=event_id)
event.payload['status'] = 'updated'  # FORBIDDEN
event.save()

# ❌ FORBIDDEN: Deleting events
DomainEvent.objects.filter(id=event_id).delete()  # FORBIDDEN

# ✅ CORRECT: Events are append-only
event = DomainEvent.objects.create(
    event_type='entity.status_changed',
    tenant_id=tenant_id,
    payload={'old_status': 'pending', 'new_status': 'approved'}
)
```

## SARAISE-25002 Event Schema Requirements

All events MUST use the standard envelope:

```python
event = {
    "event_id": "uuid-v4",              # REQUIRED: Unique identifier
    "event_type": "domain.entity.action", # REQUIRED: Dot-notation type
    "event_version": "1.0",             # REQUIRED: Schema version
    "timestamp": "ISO8601",             # REQUIRED: When it occurred
    "tenant_id": "uuid-v4",             # REQUIRED for tenant-scoped events
    "correlation_id": "uuid-v4",        # REQUIRED: Request trace ID
    "causation_id": "uuid-v4",          # REQUIRED: Triggering event ID
    "actor": {
        "type": "user|system|agent",    # REQUIRED: Who caused it
        "id": "uuid-v4"
    },
    "payload": {},                      # REQUIRED: Event-specific data
    "metadata": {
        "source_module": "module_name", # REQUIRED: Origin module
        "source_service": "service_name"
    }
}
```

## SARAISE-25003 Event Publishing Rules

### Within Transaction

Events MUST be published within the same transaction as the state change:

```python
# ✅ CORRECT: Event published with state change
@transaction.atomic
def create_resource(self, data: dict, tenant_id: str, user_id: str):
    resource = Resource.objects.create(**data, tenant_id=tenant_id)
    
    DomainEvent.objects.create(
        event_type='resource.created',
        tenant_id=tenant_id,
        correlation_id=get_correlation_id(),
        actor={'type': 'user', 'id': user_id},
        payload={'resource_id': str(resource.id), 'name': resource.name}
    )
    
    return resource

# ❌ FORBIDDEN: Event outside transaction
def create_resource(self, data: dict):
    resource = Resource.objects.create(**data)
    # Event published outside transaction - if this fails, state is inconsistent
    self.event_publisher.publish(...)  # FORBIDDEN
```

### Correlation ID Required

All events MUST include correlation_id from the originating request:

```python
# ✅ CORRECT: Include correlation ID
event = DomainEvent.objects.create(
    event_type='order.created',
    correlation_id=request.headers.get('X-Correlation-ID'),  # From request
    ...
)
```

## SARAISE-25004 Event Consumer Rules

### Idempotency Required

All event consumers MUST be idempotent:

```python
# ✅ CORRECT: Idempotent consumer
class OrderCreatedHandler:
    def handle(self, event: dict) -> None:
        event_id = event['event_id']
        
        # Check if already processed
        if ProcessedEvent.objects.filter(event_id=event_id).exists():
            return  # Idempotent: skip duplicate
        
        try:
            self._do_handle(event)
            ProcessedEvent.objects.create(event_id=event_id)
        except Exception:
            ProcessedEvent.objects.create(event_id=event_id, failed=True)
            raise

# ❌ FORBIDDEN: Non-idempotent consumer
class OrderCreatedHandler:
    def handle(self, event: dict) -> None:
        # No duplicate check - will process same event multiple times
        self._do_handle(event)  # FORBIDDEN
```

### Timeout

Event handlers SHOULD complete within 30 seconds.

## SARAISE-25005 Tenant Isolation

### Events MUST include tenant_id

For tenant-scoped events:

```python
# ✅ CORRECT: Include tenant_id
DomainEvent.objects.create(
    event_type='invoice.created',
    tenant_id=tenant_id,  # REQUIRED
    ...
)

# ❌ FORBIDDEN: Missing tenant_id for tenant-scoped event
DomainEvent.objects.create(
    event_type='invoice.created',
    # tenant_id missing - FORBIDDEN
    ...
)
```

### Cross-Tenant Publishing Forbidden

```python
# ❌ FORBIDDEN: Publishing to other tenant's channel
async def publish(self, channel: str, data: dict, tenant_id: str):
    channel_tenant = extract_tenant(channel)
    if channel_tenant != tenant_id:
        raise ValueError("Cross-tenant publish forbidden")
```

## SARAISE-25006 Event Versioning

### Adding Fields

Adding optional fields is always safe:

```python
# v1.0 payload
{"order_id": "123", "amount": 100}

# v1.1 payload (safe addition)
{"order_id": "123", "amount": 100, "currency": "USD"}  # New optional field
```

### Breaking Changes Require Version Bump

```python
# v1.0 → v2.0 (breaking change)
# - Renamed 'amount' to 'total_amount'
# - Changed 'order_id' type from string to UUID

# Old event consumers must be updated before v2.0 events are published
```

## SARAISE-25007 What Is Forbidden

- ❌ Updating or deleting events
- ❌ Events without tenant_id (for tenant-scoped data)
- ❌ Events without correlation_id
- ❌ Non-idempotent consumers
- ❌ Events published outside transaction
- ❌ Cross-tenant event leakage
- ❌ Events with external resource references (URLs that may expire)

## SARAISE-25008 Event Types for Audit

The following events MUST be emitted for audit trails:

| Entity | Required Events |
|--------|-----------------|
| User | created, updated, deleted, role_changed, suspended |
| Tenant | created, updated, suspended, plan_changed |
| Resource | created, updated, deleted, approved, rejected |
| Workflow | started, transitioned, completed, cancelled |
| Payment | initiated, processed, failed, refunded |

---

**Enforcement**: Code review must verify event patterns.

