<!-- SPDX-License-Identifier: Apache-2.0 -->
# Compliance Risk Management - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Compliance Risk Management module.

## Getting Started

<!-- TODO: Add getting started instructions -->

## Features

<!-- TODO: Add feature documentation -->

## Usage

<!-- TODO: Add usage instructions -->

## Customization

<!-- TODO: Add customization options -->

## Integrations

<!-- TODO: Add integration information -->


## Customization

<!-- SPDX-License-Identifier: Apache-2.0 -->

**Module**: `compliance_risk_management`
**Category**: Core Business (Compliance)
**Version**: 1.0.0

---

## Overview

The Compliance & Risk Management module supports extensive customization through the SARAISE Customization Framework. This guide documents all customization points, including server scripts, client scripts, webhooks, and custom API endpoints.

**Related Documentation**:
- [Customization Framework](../../01-foundation/customization-framework/README.md) - Complete customization framework documentation
- [Event System](../../../architecture/11-event-system.md) - Event-driven architecture patterns
- [Compliance & Risk Management README](./compliance-risk-management.md) - Module overview and quick start

---

## Server Scripts

Server scripts allow you to customize compliance behavior on the backend without modifying core code. Scripts run in a sandboxed environment with full access to the SARAISE API.

### Resource Scripts

Server scripts can be attached to any Compliance & Risk Management Resource to customize document lifecycle events.

#### Available Events

| Event | Trigger | Use Case |
|-------|---------|----------|
| `before_insert` | Before document is created | Validate data, set default values, calculate risk scores |
| `after_insert` | After document is created | Publish events, send notifications, initialize related records |
| `before_validate` | Before validation runs | Custom validation logic |
| `validate` | During validation | Additional business rule validation |
| `before_save` | Before any save operation | Auto-calculate fields, transform document data |
| `after_save` | After save operation | Update related records, trigger workflows |
| `before_update` | Before document update | Validate changes, check permissions |
| `after_update` | After document update | Publish events, update related records |
| `before_delete` | Before document deletion | Check for dependencies, prevent deletion |
| `on_cancel` | When workflow is cancelled | Cleanup resources, archive data |

### Compliance Framework Customizations

#### Example: Auto-Set Effective Date

```python
# Server Script: Auto-set effective date
# Event: before_save
# Resource: ComplianceFramework

def before_save(doc, method):
    """Auto-set effective date if not provided"""

    if not doc.effective_date:
        from datetime import date
        doc.effective_date = date.today()

    # Validate framework name uniqueness
    existing = frappe.db.get_value(
        "ComplianceFramework",
        {"name": doc.name, "name": ("!=", doc.name)},
        "name"
    )

    if existing:
        frappe.throw(f"Compliance Framework {doc.name} already exists")
```

### Risk Assessment Customizations

#### Example: Auto-Calculate Risk Score

```python
# Server Script: Auto-calculate risk score
# Event: before_save
# Resource: RiskAssessment

def before_save(doc, method):
    """Auto-calculate risk score from likelihood and impact"""

    if doc.likelihood and doc.impact:
        # Calculate risk score
        doc.risk_score = doc.likelihood * doc.impact

        # Determine risk level
        if doc.risk_score >= 20:
            doc.risk_level = "Critical"
        elif doc.risk_score >= 15:
            doc.risk_level = "High"
        elif doc.risk_score >= 10:
            doc.risk_level = "Medium"
        else:
            doc.risk_level = "Low"
```

#### Example: Risk Threshold Alert

```python
# Server Script: Alert on risk threshold exceeded
# Event: after_save
# Resource: RiskAssessment

def after_save(doc, method):
    """Send alert if risk threshold exceeded"""

    if doc.risk_level in ["Critical", "High"]:
        # Publish risk threshold exceeded event
        frappe.publish_realtime(
            "risk_threshold_exceeded",
            {
                "assessment_id": doc.name,
                "risk_level": doc.risk_level,
                "risk_score": doc.risk_score
            }
        )

        # Send notification to risk manager
        frappe.sendmail(
            recipients=["risk-manager@example.com"],
            subject=f"Risk Threshold Exceeded: {doc.title}",
            message=f"Risk assessment {doc.name} has exceeded threshold with level {doc.risk_level}"
        )
```

### Compliance Violation Customizations

#### Example: Auto-Generate Violation ID

```python
# Server Script: Auto-generate violation ID
# Event: before_insert
# Resource: ComplianceViolation

def before_insert(doc, method):
    """Auto-generate violation ID if not provided"""

    if not doc.violation_id:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d")
        doc.violation_id = f"VIOL-{timestamp}-{doc.name[:8]}"

    # Set default status
    if not doc.status:
        doc.status = "Open"
```

### Audit Record Customizations

#### Example: Auto-Complete Audit

```python
# Server Script: Auto-complete audit with findings
# Event: before_save
# Resource: AuditRecord

def before_save(doc, method):
    """Auto-complete audit if findings and recommendations provided"""

    if doc.findings_summary and doc.recommendations:
        if doc.status == "In Progress":
            doc.status = "Completed"

            # Publish audit completed event
            frappe.publish_realtime(
                "audit_completed",
                {
                    "audit_id": doc.name,
                    "audit_name": doc.audit_name,
                    "findings_count": len(doc.findings_summary.split("\n"))
                }
            )
```

---

## Client Scripts

Client scripts allow you to customize the user interface and add client-side logic.

### Compliance Framework Form Customizations

#### Example: Dynamic Status Indicator

```javascript
// Client Script: Dynamic status indicator
// Resource: ComplianceFramework
// Event: refresh

frappe.ui.form.on('ComplianceFramework', {
    refresh: function(frm) {
        // Add status indicator based on violations
        frappe.call({
            method: 'compliance_risk_management.api.get_violation_count',
            args: {
                framework_id: frm.doc.name
            },
            callback: function(r) {
                if (r.message && r.message.count > 0) {
                    frm.dashboard.add_indicator(
                        `${r.message.count} Open Violations`,
                        r.message.count > 5 ? 'red' : 'orange'
                    );
                }
            }
        });
    }
});
```

### Risk Assessment Form Customizations

#### Example: Real-Time Risk Score Calculation

```javascript
// Client Script: Real-time risk score calculation
// Resource: RiskAssessment
// Event: likelihood, impact

frappe.ui.form.on('RiskAssessment', {
    likelihood: function(frm) {
        calculate_risk_score(frm);
    },
    impact: function(frm) {
        calculate_risk_score(frm);
    }
});

function calculate_risk_score(frm) {
    if (frm.doc.likelihood && frm.doc.impact) {
        const risk_score = frm.doc.likelihood * frm.doc.impact;
        frm.set_value('risk_score', risk_score);

        // Determine risk level
        let risk_level = 'Low';
        if (risk_score >= 20) risk_level = 'Critical';
        else if (risk_score >= 15) risk_level = 'High';
        else if (risk_score >= 10) risk_level = 'Medium';

        frm.set_value('risk_level', risk_level);
    }
}
```

---

## Webhooks

Webhooks allow you to integrate with external systems and receive notifications.

### Compliance Violation Webhook

#### Example: Slack Notification on Violation

```python
# Webhook Handler: Slack notification on violation
# Event: compliance.violation.created

import requests

def violation_created_webhook(doc, method):
    """Send Slack notification when violation is created"""

    webhook_url = frappe.conf.get("slack_webhook_url")
    if not webhook_url:
        return

    message = {
        "text": f"New Compliance Violation: {doc.title}",
        "attachments": [
            {
                "color": "danger" if doc.violation_type == "Critical" else "warning",
                "fields": [
                    {"title": "Violation ID", "value": doc.violation_id, "short": True},
                    {"title": "Type", "value": doc.violation_type, "short": True},
                    {"title": "Framework", "value": doc.compliance_framework, "short": True},
                    {"title": "Status", "value": doc.status, "short": True}
                ]
            }
        ]
    }

    requests.post(webhook_url, json=message)
```

### Risk Threshold Webhook

#### Example: Email Alert on Risk Threshold

```python
# Webhook Handler: Email alert on risk threshold
# Event: compliance.risk.threshold.exceeded

def risk_threshold_exceeded_webhook(event_data):
    """Send email alert when risk threshold exceeded"""

    assessment_id = event_data.get("assessment_id")
    risk_level = event_data.get("risk_level")

    # Get assessment details
    assessment = frappe.get_doc("RiskAssessment", assessment_id)

    # Send email to risk manager
    frappe.sendmail(
        recipients=["risk-manager@example.com"],
        subject=f"Risk Threshold Exceeded: {assessment.title}",
        message=f"""
        Risk assessment {assessment_id} has exceeded threshold.

        Risk Level: {risk_level}
        Risk Score: {assessment.risk_score}
        Category: {assessment.risk_category}

        Please review and take appropriate action.
        """
    )
```

---

## Custom API Endpoints

You can create custom API endpoints for specific compliance operations.

### Example: Compliance Dashboard API

```python
# Custom API Endpoint: Compliance Dashboard
# Route: /api/v1/compliance-risk-management/dashboard

@router.get("/dashboard")
async def get_compliance_dashboard(
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """Get compliance dashboard data"""

    service = ComplianceMonitoringService(db)

    # Get compliance status
    status = await service.get_compliance_status(
        tenant_id=current_user.tenant_id
    )

    # Get recent violations
    violations = await service.list_violations(
        tenant_id=current_user.tenant_id,
        limit=10
    )

    # Get high-risk assessments
    risks = await service.list_assessments(
        tenant_id=current_user.tenant_id,
        risk_level="High",
        limit=10
    )

    return {
        "status": status,
        "recent_violations": violations,
        "high_risks": risks
    }
```

---

## Workflow Customization

You can customize workflows to add additional steps or modify existing behavior.

### Example: Custom Compliance Monitoring Workflow

```python
# Workflow Customization: Enhanced compliance monitoring
# Workflow: compliance_monitoring_workflow

def custom_compliance_monitoring_step(data, context):
    """Custom step for compliance monitoring"""

    # Perform additional compliance checks
    compliance_checks = perform_custom_checks(data)

    # Generate custom report
    report = generate_custom_report(compliance_checks)

    return {
        "status": "success",
        "checks": compliance_checks,
        "report": report
    }
```

---

## Event Bus Integration

You can subscribe to compliance events and perform custom actions.

### Example: Event Subscription

```python
# Event Subscription: Compliance status changed
# Event: compliance.status.changed

from src.core.event_bus import event_bus

async def handle_compliance_status_changed(event):
    """Handle compliance status changed event"""

    tenant_id = event.tenant_id
    status = event.data.get("compliance_status")

    # Perform custom action based on status
    if status == "Non-Compliant":
        # Send alert
        send_compliance_alert(tenant_id, status)

    # Update dashboard
    update_compliance_dashboard(tenant_id, status)

# Subscribe to event
event_bus.subscribe("compliance.status.changed", handle_compliance_status_changed)
```

---

## Custom Reports

You can create custom reports for compliance analysis.

### Example: Compliance Trend Report

```python
# Custom Report: Compliance Trend Analysis
# Route: /api/v1/compliance-risk-management/reports/trends

@router.get("/reports/trends")
async def get_compliance_trends(
    start_date: datetime,
    end_date: datetime,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """Get compliance trends over time"""

    service = ComplianceMonitoringService(db)

    # Get compliance data over time period
    trends = await service.get_compliance_trends(
        tenant_id=current_user.tenant_id,
        start_date=start_date,
        end_date=end_date
    )

    return {
        "trends": trends,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        }
    }
```

---

## Ask Amani Code Generation

Ask Amani can generate code for all customization points:

- **Server Scripts**: "Generate a server script that validates compliance framework data"
- **Client Scripts**: "Generate a client script that shows risk score in real-time"
- **Webhooks**: "Generate a webhook handler for compliance violation notifications"
- **Custom APIs**: "Generate a custom API endpoint for compliance dashboard"
- **Workflows**: "Generate a custom workflow step for risk assessment"
- **Event Handlers**: "Generate an event handler for compliance status changes"


## Integrations

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

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
