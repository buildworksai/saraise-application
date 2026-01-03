# Compliance & Risk Management - Inter-Module Integrations

<!-- SPDX-License-Identifier: Apache-2.0 -->

**Module**: `compliance_risk_management`
**Category**: Core Business (Compliance)
**Version**: 1.0.0

---

## Overview

The Compliance & Risk Management module acts as a **compliance orchestration layer** integrating with QMS (GxP), Audit, Master Data Management (MDM), and Sustainability & ESG modules. This document describes the event-driven integration architecture and all inter-module integrations.

**Related Documentation**:
- [Compliance & Risk Management README](./compliance-risk-management.md) - Module overview and quick start
- [Event System](../../../architecture/11-event-system.md) - Event-driven architecture patterns
- [Integration Patterns](../../../architecture/04-integration-patterns.md) - General integration patterns

---

## Compliance Orchestration Architecture

### Design Principles

1. **Event-Driven**: All integrations use event-driven architecture via the Event Bus (Redis-based)
2. **Orchestration Layer**: Module orchestrates compliance across multiple modules
3. **Non-Intrusive**: Acts as a compliance layer without modifying core module code
4. **Tenant Isolation**: All integrations respect tenant boundaries
5. **Async Processing**: Compliance checks run asynchronously to avoid blocking operations

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│         Compliance & Risk Management Orchestration          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Compliance  │  │     Risk     │  │    Audit    │     │
│  │  Framework   │  │  Assessment  │  │  Record     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Compliance  │  │   Risk       │  │  Compliance │     │
│  │  Violation   │  │  Mitigation  │  │  Control    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Event Bus Integration Layer             │  │
│  │              (Redis-based pub/sub)                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Events
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Integrated Modules                        │
├─────────────────────────────────────────────────────────────┤
│  QMS (GxP) │ Audit │ MDM │ Sustainability & ESG          │
└─────────────────────────────────────────────────────────────┘
```

---

## QMS (GxP) Integration

### Integration Overview

Compliance & Risk Management integrates with QMS (GxP) module to sync compliance data and import audit findings.

### Events

| Event | Source | Action | Description |
|-------|--------|--------|-------------|
| `qms.compliance.updated` | QMS | Sync Compliance Status | Sync QMS compliance status to compliance framework |
| `qms.audit.completed` | QMS | Import Audit Findings | Import QMS audit findings as audit records |

### Implementation

#### Event Handler: QMS Compliance Sync

```python
# backend/src/modules/compliance_risk_management/integrations/qms_integration.py

from src.core.event_bus import event_bus, EventBusEvent
from src.modules.compliance_risk_management.integrations.qms_integration import QMSIntegration

async def setup_qms_integration(db: AsyncSession):
    """Setup QMS integration event handlers"""

    integration = QMSIntegration(db)

    # Subscribe to QMS compliance events
    await event_bus.subscribe(
        "qms.compliance.updated",
        integration.handle_qms_compliance_event
    )

    # Subscribe to QMS audit events
    await event_bus.subscribe(
        "qms.audit.completed",
        integration.handle_qms_compliance_event
    )
```

### API Endpoints

- `POST /api/v1/compliance-risk-management/integrations/qms/sync` - Manually sync QMS compliance data
- `GET /api/v1/compliance-risk-management/integrations/qms/status` - Get QMS integration status

---

## Audit Integration

### Integration Overview

Compliance & Risk Management integrates with Audit module to import audit findings and create compliance violations from critical findings.

### Events

| Event | Source | Action | Description |
|-------|--------|--------|-------------|
| `audit.completed` | Audit | Import Audit Findings | Import audit findings as audit records |
| `audit.finding.created` | Audit | Create Violation | Create compliance violation if finding is critical |

### Implementation

#### Event Handler: Audit Findings Import

```python
# backend/src/modules/compliance_risk_management/integrations/audit_integration.py

from src.core.event_bus import event_bus, EventBusEvent
from src.modules.compliance_risk_management.integrations.audit_integration import AuditIntegration

async def setup_audit_integration(db: AsyncSession):
    """Setup Audit integration event handlers"""

    integration = AuditIntegration(db)

    # Subscribe to audit events
    await event_bus.subscribe(
        "audit.completed",
        integration.handle_audit_event
    )

    await event_bus.subscribe(
        "audit.finding.created",
        integration.handle_audit_event
    )
```

### API Endpoints

- `POST /api/v1/compliance-risk-management/integrations/audit/import` - Manually import audit findings
- `GET /api/v1/compliance-risk-management/integrations/audit/status` - Get audit integration status

---

## MDM Integration

### Integration Overview

Compliance & Risk Management integrates with Master Data Management (MDM) module to check data compliance against compliance frameworks.

### Events

| Event | Source | Action | Description |
|-------|--------|--------|-------------|
| `mdm.data.quality.issue` | MDM | Check Compliance | Check data entity compliance and create violations if needed |

### Implementation

#### Event Handler: Data Compliance Check

```python
# backend/src/modules/compliance_risk_management/integrations/mdm_integration.py

from src.core.event_bus import event_bus, EventBusEvent
from src.modules.compliance_risk_management.integrations.mdm_integration import MDMIntegration

async def setup_mdm_integration(db: AsyncSession):
    """Setup MDM integration event handlers"""

    integration = MDMIntegration(db)

    # Subscribe to MDM data quality events
    await event_bus.subscribe(
        "mdm.data.quality.issue",
        integration.handle_mdm_event
    )
```

### API Endpoints

- `POST /api/v1/compliance-risk-management/integrations/mdm/check` - Manually check data compliance
- `GET /api/v1/compliance-risk-management/integrations/mdm/status` - Get MDM integration status

---

## Sustainability & ESG Integration

### Integration Overview

Compliance & Risk Management integrates with Sustainability & ESG module to sync ESG metrics and create compliance violations when ESG thresholds are exceeded.

### Events

| Event | Source | Action | Description |
|-------|--------|--------|-------------|
| `sustainability.esg.report.completed` | Sustainability | Sync ESG Metrics | Sync ESG metrics to compliance framework |
| `sustainability.compliance.threshold.exceeded` | Sustainability | Create Violation | Create compliance violation when ESG threshold exceeded |

### Implementation

#### Event Handler: ESG Metrics Sync

```python
# backend/src/modules/compliance_risk_management/integrations/sustainability_integration.py

from src.core.event_bus import event_bus, EventBusEvent
from src.modules.compliance_risk_management.integrations.sustainability_integration import SustainabilityIntegration

async def setup_sustainability_integration(db: AsyncSession):
    """Setup Sustainability integration event handlers"""

    integration = SustainabilityIntegration(db)

    # Subscribe to sustainability events
    await event_bus.subscribe(
        "sustainability.esg.report.completed",
        integration.handle_sustainability_event
    )

    await event_bus.subscribe(
        "sustainability.compliance.threshold.exceeded",
        integration.handle_sustainability_event
    )
```

### API Endpoints

- `POST /api/v1/compliance-risk-management/integrations/sustainability/sync` - Manually sync ESG metrics
- `GET /api/v1/compliance-risk-management/integrations/sustainability/status` - Get sustainability integration status

---

## Compliance Event APIs

The Compliance & Risk Management module publishes events that other modules can subscribe to:

### Published Events

| Event | Description | Data |
|-------|-------------|------|
| `compliance.status.changed` | Compliance status changed | `{source, compliance_status, timestamp}` |
| `compliance.risk.threshold.exceeded` | Risk threshold exceeded | `{assessment_id, risk_level, risk_score}` |
| `compliance.audit.completed` | Audit completed | `{audit_id, audit_name, findings_count}` |
| `compliance.violation.created` | Violation created | `{violation_id, violation_type, framework}` |
| `compliance.violation.remediated` | Violation remediated | `{violation_id, remediation_date}` |

### Event API Endpoints

- `POST /api/v1/compliance-risk-management/events/compliance-status-changed` - Publish compliance status changed event
- `POST /api/v1/compliance-risk-management/events/risk-threshold-exceeded` - Publish risk threshold exceeded event
- `POST /api/v1/compliance-risk-management/events/audit-completed` - Publish audit completed event

---

## Data Synchronization Patterns

### Event-Driven Synchronization

All data synchronization is event-driven using the Redis-based Event Bus:

1. **Source Module** publishes event to Event Bus
2. **Compliance Module** subscribes to event
3. **Integration Handler** processes event and syncs data
4. **Compliance Module** publishes compliance events

### Error Handling

- **Retry Logic**: Failed events are retried with exponential backoff
- **Dead Letter Queue**: Failed events after max retries are moved to DLQ
- **Error Logging**: All errors are logged with full context
- **Tenant Isolation**: Errors in one tenant don't affect others

### Tenant Isolation

All integrations respect tenant boundaries:

- Events are tenant-scoped: `events:tenant:{tenant_id}`
- Data queries filter by `tenant_id`
- Integration handlers validate tenant access
- Cross-tenant data access is prevented

---

## Testing Integration

### Integration Test Example

```python
# tests/integration/test_qms_integration.py

async def test_qms_compliance_sync(db: AsyncSession, tenant_id: str):
    """Test QMS compliance data synchronization"""

    # Create QMS compliance event
    event = EventBusEvent(
        event_type="qms.compliance.updated",
        tenant_id=tenant_id,
        data={
            "id": "qms-doc-123",
            "compliance_status": "Compliant"
        }
    )

    # Publish event
    await event_bus.publish(
        event_type="qms.compliance.updated",
        tenant_id=tenant_id,
        data=event.data
    )

    # Verify compliance status synced
    service = ComplianceMonitoringService(db)
    status = await service.get_compliance_status(tenant_id=tenant_id)

    assert status["overall_status"] == "Compliant"
```

---

## Ask Amani Integration

Ask Amani can query compliance data across modules:

- "Show compliance status from QMS module"
- "List audit findings from Audit module"
- "Check master data compliance from MDM"
- "Show ESG compliance metrics from Sustainability module"
