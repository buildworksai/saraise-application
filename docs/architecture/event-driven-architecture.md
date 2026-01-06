# SARAISE Event-Driven Architecture

**Status:** Authoritative — Freeze Blocking  
**Version:** 1.0.0  
**Last Updated:** January 5, 2026

This document defines the **event-driven patterns** for SARAISE. Event-driven architecture is critical for decoupling modules, enabling audit trails, and supporting eventual consistency at scale.

---

## 0) Non-Negotiable Principles

1. **Events are immutable facts.** Once published, events cannot be changed.
2. **Events are append-only.** Event stores only support create, never update or delete.
3. **Events enable audit.** Every significant state change produces an event.
4. **Events decouple modules.** Publishers don't know subscribers.
5. **Events must be idempotent.** Consumers must handle duplicate delivery.

---

## 1) Event Categories

### 1.1 Domain Events

State changes in business entities.

```
tenant.created
tenant.updated
tenant.suspended
user.created
user.role_changed
resource.created
resource.updated
resource.deleted
workflow.transitioned
```

### 1.2 Integration Events

Cross-module or external system communication.

```
module.installed
module.upgraded
payment.processed
external.webhook_received
```

### 1.3 System Events

Platform-level operations.

```
session.created
session.invalidated
policy.version_changed
cache.invalidated
health.check_failed
```

---

## 2) Event Schema

### 2.1 Envelope Schema

All events MUST use this envelope:

```json
{
  "event_id": "uuid-v4",
  "event_type": "domain.entity.action",
  "event_version": "1.0",
  "timestamp": "2026-01-05T12:00:00.000Z",
  "tenant_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "causation_id": "uuid-v4",
  "actor": {
    "type": "user|system|agent",
    "id": "uuid-v4"
  },
  "payload": {
    // Event-specific data
  },
  "metadata": {
    "source_module": "module_name",
    "source_service": "service_name",
    "environment": "production"
  }
}
```

### 2.2 Payload Rules

- Payload MUST contain all data needed to process the event
- Payload MUST NOT reference external resources that may not exist
- Payload SHOULD be self-describing
- Payload schema MUST be versioned

### 2.3 Example Events

**Domain Event: Resource Created**

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440001",
  "event_type": "inventory.product.created",
  "event_version": "1.0",
  "timestamp": "2026-01-05T12:00:00.000Z",
  "tenant_id": "tenant-123",
  "correlation_id": "req-456",
  "causation_id": "cmd-789",
  "actor": {
    "type": "user",
    "id": "user-abc"
  },
  "payload": {
    "product_id": "prod-001",
    "name": "Widget",
    "sku": "WDG-001",
    "initial_quantity": 100,
    "unit_price": 29.99
  },
  "metadata": {
    "source_module": "inventory",
    "source_service": "inventory-api",
    "environment": "production"
  }
}
```

**Audit Event: Approval Completed**

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440002",
  "event_type": "workflow.approval.completed",
  "event_version": "1.0",
  "timestamp": "2026-01-05T12:05:00.000Z",
  "tenant_id": "tenant-123",
  "correlation_id": "req-789",
  "causation_id": "approval-456",
  "actor": {
    "type": "user",
    "id": "approver-xyz"
  },
  "payload": {
    "approval_id": "approval-456",
    "workflow_id": "wf-001",
    "entity_type": "purchase_order",
    "entity_id": "po-123",
    "decision": "approved",
    "comments": "Approved per policy"
  },
  "metadata": {
    "source_module": "workflow",
    "source_service": "workflow-engine",
    "environment": "production"
  }
}
```

---

## 3) Event Storage

### 3.1 Event Store Model

Events are stored in an append-only event store.

```python
# backend/src/core/event_store_models.py

from django.db import models
import uuid

class DomainEvent(models.Model):
    """Append-only event store for domain events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    event_type = models.CharField(max_length=255, db_index=True)
    event_version = models.CharField(max_length=20, default="1.0")
    timestamp = models.DateTimeField(db_index=True)
    tenant_id = models.CharField(max_length=36, db_index=True)

    # Causation chain
    correlation_id = models.CharField(max_length=36, db_index=True)
    causation_id = models.CharField(max_length=36, db_index=True)

    # Actor
    actor_type = models.CharField(max_length=20)
    actor_id = models.CharField(max_length=36, db_index=True)

    # Event data
    payload = models.JSONField()
    metadata = models.JSONField(default=dict)

    # Stream for aggregate-based queries
    stream_id = models.CharField(max_length=255, db_index=True)
    stream_position = models.BigIntegerField()

    class Meta:
        db_table = "domain_events"
        indexes = [
            models.Index(fields=["tenant_id", "event_type", "timestamp"]),
            models.Index(fields=["stream_id", "stream_position"]),
            models.Index(fields=["correlation_id"]),
        ]
        # CRITICAL: No update or delete operations allowed
        managed = True

    def save(self, *args, **kwargs):
        if self.pk and DomainEvent.objects.filter(pk=self.pk).exists():
            raise ValueError("Events are immutable - updates forbidden")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Events are immutable - deletes forbidden")
```

### 3.2 Event Stream Rules

- Each aggregate type has its own stream
- Stream ID format: `{aggregate_type}-{aggregate_id}`
- Stream position is monotonically increasing
- Gaps in position indicate lost events (requires investigation)

---

## 4) Event Publishing

### 4.1 Publisher Interface

```python
# backend/src/core/event_publisher.py

from abc import ABC, abstractmethod
from typing import Dict, Any
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass
class EventEnvelope:
    event_type: str
    tenant_id: str
    actor_type: str
    actor_id: str
    payload: Dict[str, Any]
    correlation_id: str = None
    causation_id: str = None
    event_version: str = "1.0"

class EventPublisher(ABC):
    """Abstract event publisher interface."""

    @abstractmethod
    def publish(self, event: EventEnvelope) -> str:
        """Publish event and return event_id."""
        pass

    @abstractmethod
    def publish_batch(self, events: list[EventEnvelope]) -> list[str]:
        """Publish multiple events atomically."""
        pass
```

### 4.2 Publishing Rules

1. Events MUST be published within the same transaction as the state change
2. Events MUST include correlation_id from the originating request
3. Events MUST include causation_id from the triggering event (if applicable)
4. Failures to publish MUST rollback the transaction

### 4.3 Outbox Pattern (Recommended)

For guaranteed delivery, use the Outbox pattern:

```python
# 1. Write event to outbox table in same transaction as state change
# 2. Background worker reads outbox and publishes to message broker
# 3. Mark outbox entry as published after successful delivery
# 4. Retry failed entries with exponential backoff
```

---

## 5) Event Consumption

### 5.1 Consumer Interface

```python
# backend/src/core/event_consumer.py

from abc import ABC, abstractmethod
from typing import Dict, Any

class EventHandler(ABC):
    """Abstract event handler interface."""

    @property
    @abstractmethod
    def handles_event_types(self) -> list[str]:
        """Return list of event types this handler processes."""
        pass

    @abstractmethod
    def handle(self, event: Dict[str, Any]) -> None:
        """Process the event. Must be idempotent."""
        pass
```

### 5.2 Consumption Rules

1. Handlers MUST be idempotent (handle duplicates gracefully)
2. Handlers MUST track processed event IDs to detect duplicates
3. Handlers MUST NOT modify the event
4. Handlers SHOULD complete within timeout (configurable, default 30s)
5. Failed handlers MUST NOT block other handlers

### 5.3 Idempotency Pattern

```python
class IdempotentEventHandler(EventHandler):
    """Base class for idempotent event handling."""

    def __init__(self):
        self.processed_events = ProcessedEventLog()

    def handle(self, event: Dict[str, Any]) -> None:
        event_id = event["event_id"]

        # Check if already processed
        if self.processed_events.exists(event_id):
            return  # Idempotent: already processed

        try:
            self._do_handle(event)
            self.processed_events.mark_processed(event_id)
        except Exception as e:
            self.processed_events.mark_failed(event_id, str(e))
            raise

    @abstractmethod
    def _do_handle(self, event: Dict[str, Any]) -> None:
        """Implement actual event processing."""
        pass
```

---

## 6) Event Sourcing (High-Risk Domains)

### 6.1 When to Use Event Sourcing

Event sourcing is REQUIRED for:
- Financial ledger entries
- Audit trails
- Compliance-sensitive data
- Any domain requiring complete history

### 6.2 Event Sourced Aggregate

```python
# backend/src/modules/finance/ledger_aggregate.py

class LedgerEntryAggregate:
    """Event-sourced aggregate for ledger entries."""

    def __init__(self):
        self.events: list = []
        self.version = 0

    def apply_event(self, event: Dict[str, Any]) -> None:
        """Apply event to rebuild state."""
        handler = getattr(self, f"_apply_{event['event_type']}", None)
        if handler:
            handler(event["payload"])
        self.version += 1

    def _apply_ledger_entry_posted(self, payload: Dict[str, Any]) -> None:
        self.balance += payload["amount"]
        self.last_entry_id = payload["entry_id"]

    @classmethod
    def load(cls, stream_id: str) -> "LedgerEntryAggregate":
        """Load aggregate from event stream."""
        aggregate = cls()
        events = DomainEvent.objects.filter(
            stream_id=stream_id
        ).order_by("stream_position")

        for event in events:
            aggregate.apply_event({
                "event_type": event.event_type,
                "payload": event.payload,
            })

        return aggregate
```

### 6.3 CQRS for Event-Sourced Domains

For event-sourced domains, use CQRS:

```
Commands → Aggregate → Events → Event Store
                              ↓
Events → Projector → Read Model (Query optimized)
```

---

## 7) Message Broker Integration

### 7.1 Supported Brokers

| Broker | Use Case | When to Use |
|--------|----------|-------------|
| PostgreSQL LISTEN/NOTIFY | Simple, low-volume | < 1000 events/second |
| Redis Pub/Sub | Real-time, ephemeral | In-memory acceptable |
| Kafka/Pulsar | High-volume, durable | > 10000 events/second |

### 7.2 Topic Naming Convention

```
saraise.{environment}.{tenant_id|platform}.{domain}.{event_type}

Examples:
saraise.production.tenant-123.inventory.product.created
saraise.production.platform.session.invalidated
```

### 7.3 Partitioning Strategy

- Partition by `tenant_id` for tenant isolation
- Partition by `aggregate_id` for ordering within aggregate
- Never partition by `event_type` (breaks ordering)

---

## 8) Event Versioning

### 8.1 Schema Evolution Rules

1. Adding optional fields is always safe
2. Removing fields requires version bump
3. Changing field types requires version bump
4. Renaming fields requires version bump

### 8.2 Version Handling

```python
class EventUpgrader:
    """Upgrade old event versions to current version."""

    def upgrade(self, event: Dict[str, Any]) -> Dict[str, Any]:
        version = event.get("event_version", "1.0")

        if version == "1.0":
            event = self._upgrade_1_0_to_2_0(event)
            version = "2.0"

        return event

    def _upgrade_1_0_to_2_0(self, event: Dict[str, Any]) -> Dict[str, Any]:
        # Add default values for new fields
        event["payload"]["new_field"] = "default_value"
        event["event_version"] = "2.0"
        return event
```

---

## 9) Error Handling

### 9.1 Dead Letter Queue

Failed events go to DLQ:
- Retain for investigation
- Include failure reason
- Support replay after fix

### 9.2 Retry Policy

| Attempt | Delay | Notes |
|---------|-------|-------|
| 1 | Immediate | First retry |
| 2 | 1 second | |
| 3 | 5 seconds | |
| 4 | 30 seconds | |
| 5 | 5 minutes | Final retry |
| 6+ | DLQ | Manual investigation |

---

## 10) Observability

### 10.1 Required Metrics

- `events_published_total` (counter by event_type)
- `events_consumed_total` (counter by event_type, handler)
- `event_processing_duration_seconds` (histogram)
- `event_publish_latency_seconds` (histogram)
- `dlq_depth` (gauge)

### 10.2 Required Logs

```json
{
  "level": "info",
  "message": "Event published",
  "event_id": "...",
  "event_type": "...",
  "tenant_id": "...",
  "correlation_id": "..."
}
```

---

## 11) What Is Explicitly Forbidden

- ❌ Updating or deleting events
- ❌ Events without tenant_id (for tenant-scoped data)
- ❌ Events without correlation_id
- ❌ Non-idempotent consumers
- ❌ Synchronous event handling in request path
- ❌ Cross-tenant event leakage
- ❌ Events with external resource references

---

## 12) Implementation Timeline

| Phase | Scope | Timeline |
|-------|-------|----------|
| Phase 7 | Event store foundation, audit events | Q1 2026 |
| Phase 8 | Financial domain event sourcing | Q2 2026 |
| Phase 9 | Full CQRS for high-volume modules | Q3 2026 |

---

## 13) Final Warning

Event-driven architecture done wrong creates more problems than it solves.

Follow these patterns exactly, or do not implement event-driven features.

---

**Verification Checksum**
- Document: event-driven-architecture.md
- Purpose: Define event-driven patterns for SARAISE
- Status: Authoritative — Freeze Blocking

---

**End of document**

