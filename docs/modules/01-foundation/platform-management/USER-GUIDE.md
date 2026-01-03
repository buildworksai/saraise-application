<!-- SPDX-License-Identifier: Apache-2.0 -->
# Platform Management - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Platform Management module.

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
# Platform Management Customization Guide

**Module**: Platform Management
**Category**: Foundation
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the Platform Management module. Use these customization capabilities to extend platform behavior, integrate with external systems, and implement custom business logic without modifying core code.

---

## Customization Points

### 1. PlatformSettings Model

**Description**: Platform-wide configuration settings

**Available Hooks**:
- `before_insert` - Before creating a new platform setting
- `after_insert` - After a platform setting is created
- `before_update` - Before updating an existing platform setting
- `after_update` - After a platform setting is updated

**Use Cases**:
- Validate setting values before saving
- Log setting changes for audit
- Trigger platform-wide configuration updates
- Enforce setting constraints

**Example Server Script**:
```python
# Custom validation for platform settings
def before_save(doc, method):
    """Validate platform setting values"""
    if doc.key == "max_tenants":
        max_value = doc.value.get("max_tenants", 0)
        if max_value > 10000:
            frappe.throw("Maximum tenants cannot exceed 10,000")

    if doc.key == "session_timeout_minutes":
        timeout = doc.value.get("session_timeout_minutes", 30)
        if timeout < 5 or timeout > 480:
            frappe.throw("Session timeout must be between 5 and 480 minutes")

# Log all setting changes
def after_update(doc, method):
    """Log platform setting changes for audit"""
    frappe.log_error(
        f"Platform setting '{doc.key}' updated by {frappe.session.user}",
        "PlatformSettings Audit"
    )
```

---

### 2. PlatformHealthSnapshot Model

**Description**: Platform health monitoring snapshots

**Available Hooks**:
- `before_insert` - Before creating a health snapshot
- `after_insert` - After a health snapshot is created

**Use Cases**:
- Calculate health score before saving
- Trigger alerts when health score drops below threshold
- Aggregate health metrics for reporting

**Example Server Script**:
```python
# Calculate health score before saving
def before_insert(doc, method):
    """Calculate platform health score"""
    # Health score calculation based on multiple factors
    error_rate_weight = 0.3
    response_time_weight = 0.3
    active_tenants_weight = 0.2
    active_users_weight = 0.2

    error_score = max(0, 100 - (doc.error_rate * 10))
    response_time_score = max(0, 100 - (doc.avg_response_time_ms / 10))
    tenant_score = min(100, (doc.active_tenants / doc.total_tenants) * 100)
    user_score = min(100, (doc.active_users / doc.total_users) * 100)

    doc.health_score = (
        error_score * error_rate_weight +
        response_time_score * response_time_weight +
        tenant_score * active_tenants_weight +
        user_score * active_users_weight
    )

# Alert on critical health issues
def after_insert(doc, method):
    """Send alert if health score is critical"""
    if doc.health_score < 50:
        frappe.sendmail(
            recipients=["platform-ops@company.com"],
            subject=f"⚠️ Critical Platform Health Alert - Score: {doc.health_score}",
            message=f"""
                Platform health score has dropped to {doc.health_score}!

                Details:
                - Error Rate: {doc.error_rate}%
                - Avg Response Time: {doc.avg_response_time_ms}ms
                - Active Tenants: {doc.active_tenants}/{doc.total_tenants}
                - Active Users: {doc.active_users}/{doc.total_users}
            """
        )
```

---

### 3. PlatformPerformanceSnapshot Model

**Description**: Platform performance metrics

**Available Hooks**:
- `before_insert` - Before creating a performance snapshot
- `after_insert` - After a performance snapshot is created

**Use Cases**:
- Calculate performance metrics before saving
- Detect performance degradation
- Trigger optimization workflows

**Example Server Script**:
```python
# Detect performance degradation
def after_insert(doc, method):
    """Detect performance degradation and trigger optimization"""
    # Get previous snapshot for comparison
    previous = frappe.get_all(
        "PlatformPerformanceSnapshot",
        filters={
            "module_name": doc.module_name,
            "snapshot_date": ["<", doc.snapshot_date]
        },
        order_by="snapshot_date desc",
        limit=1
    )

    if previous:
        prev_doc = frappe.get_doc("PlatformPerformanceSnapshot", previous[0].name)

        # Check if performance degraded significantly
        if doc.avg_duration_ms > prev_doc.avg_duration_ms * 1.5:
            # Trigger optimization workflow
            frappe.enqueue(
                "platform_management.workflows.optimize_module_performance",
                module_name=doc.module_name,
                queue="default"
            )
```

---

### 4. PlatformHealingEvent Resource

**Description**: Platform self-healing events

**Available Hooks**:
- `before_insert` - Before creating a healing event
- `after_insert` - After a healing event is created

**Use Cases**:
- Validate healing actions before execution
- Log healing events for analysis
- Trigger notifications on critical healing events

**Example Server Script**:
```python
# Validate healing actions
def before_insert(doc, method):
    """Validate healing action before execution"""
    if doc.event_type == "restart_service":
        # Check if service is critical
        critical_services = ["database", "redis", "api_gateway"]
        if doc.component in critical_services:
            # Require approval for critical services
            if not doc.get("approved_by"):
                frappe.throw(
                    f"Restarting critical service '{doc.component}' requires approval"
                )

# Log healing events for analysis
def after_insert(doc, method):
    """Log healing event for analysis"""
    frappe.log_error(
        f"Healing event: {doc.event_type} on {doc.component} - Status: {doc.status}",
        "PlatformHealingEvent"
    )
```

---

### 5. PlatformScalingEvent Resource

**Description**: Platform scaling events

**Available Hooks**:
- `before_insert` - Before creating a scaling event
- `after_insert` - After a scaling event is created

**Use Cases**:
- Validate scaling actions before execution
- Log scaling events for cost analysis
- Trigger notifications on scaling events

**Example Server Script**:
```python
# Validate scaling actions
def before_insert(doc, method):
    """Validate scaling action"""
    if doc.scaling_action == "scale_up":
        # Check cost implications
        cost_per_instance = 100  # $100 per instance per month
        additional_instances = doc.target_instances - doc.previous_instances
        monthly_cost_increase = additional_instances * cost_per_instance

        if monthly_cost_increase > 1000:
            # Require approval for large cost increases
            if not doc.get("approved_by"):
                frappe.throw(
                    f"Scaling up will increase monthly costs by ${monthly_cost_increase}. "
                    "Approval required."
                )

# Log scaling events for cost analysis
def after_insert(doc, method):
    """Log scaling event for cost tracking"""
    cost_per_instance = 100
    instance_change = doc.target_instances - doc.previous_instances
    monthly_cost_change = instance_change * cost_per_instance

    frappe.log_error(
        f"Scaling event: {doc.scaling_action} {doc.component} "
        f"({doc.previous_instances} -> {doc.target_instances} instances). "
        f"Monthly cost change: ${monthly_cost_change}",
        "PlatformScalingEvent"
    )
```

---

### 6. PlatformBackupRecord Resource

**Description**: Platform backup records

**Available Hooks**:
- `before_insert` - Before creating a backup record
- `after_insert` - After a backup record is created
- `after_update` - After a backup record is updated

**Use Cases**:
- Validate backup configuration before execution
- Log backup completion for compliance
- Trigger backup verification workflows

**Example Server Script**:
```python
# Validate backup configuration
def before_insert(doc, method):
    """Validate backup configuration"""
    if doc.backup_type == "full":
        # Full backups should be scheduled during low-traffic hours
        current_hour = frappe.utils.now_datetime().hour
        if 8 <= current_hour <= 18:
            frappe.throw(
                "Full backups should be scheduled during off-peak hours (8 PM - 8 AM)"
            )

# Trigger backup verification
def after_update(doc, method):
    """Trigger backup verification after completion"""
    if doc.status == "completed" and not doc.get("verified"):
        frappe.enqueue(
            "platform_management.workflows.verify_backup",
            backup_id=doc.backup_id,
            queue="default"
        )
```

---

### 7. PlatformIncident Resource

**Description**: Platform incident records

**Available Hooks**:
- `before_insert` - Before creating an incident
- `after_insert` - After an incident is created
- `after_update` - After an incident is updated

**Use Cases**:
- Auto-assign incidents based on severity
- Trigger incident response workflows
- Send notifications on critical incidents

**Example Server Script**:
```python
# Auto-assign incidents
def before_insert(doc, method):
    """Auto-assign incidents based on severity"""
    if doc.severity == "critical":
        # Assign to platform owner
        platform_owners = frappe.get_all(
            "User",
            filters={"role": "Platform Owner"},
            fields=["name"]
        )
        if platform_owners:
            doc.assigned_to = platform_owners[0].name

    elif doc.severity == "high":
        # Assign to platform operator
        platform_operators = frappe.get_all(
            "User",
            filters={"role": "Platform Operator"},
            fields=["name"]
        )
        if platform_operators:
            doc.assigned_to = platform_operators[0].name

# Send notifications on critical incidents
def after_insert(doc, method):
    """Send notifications on critical incidents"""
    if doc.severity in ["critical", "high"]:
        frappe.sendmail(
            recipients=["platform-ops@company.com"],
            subject=f"🚨 Platform Incident: {doc.incident_type} - {doc.severity}",
            message=f"""
                A {doc.severity} incident has been detected:

                Type: {doc.incident_type}
                Component: {doc.component}
                Description: {doc.description}
                Detected At: {doc.detected_at}
            """
        )
```

---

## Custom API Endpoints

### Example: Custom Platform Analytics Endpoint

```python
# Custom API endpoint for platform analytics
@frappe.whitelist()
def get_custom_platform_analytics(period="30d"):
    """Get custom platform analytics with additional metrics"""
    from datetime import datetime, timedelta

    # Calculate date range
    if period == "30d":
        start_date = datetime.now() - timedelta(days=30)
    elif period == "7d":
        start_date = datetime.now() - timedelta(days=7)
    else:
        start_date = datetime.now() - timedelta(days=365)

    # Get platform health snapshots
    snapshots = frappe.get_all(
        "PlatformHealthSnapshot",
        filters={"snapshot_date": [">=", start_date]},
        fields=["health_score", "error_rate", "avg_response_time_ms", "snapshot_date"],
        order_by="snapshot_date asc"
    )

    # Calculate trends
    if len(snapshots) >= 2:
        first_half = snapshots[:len(snapshots)//2]
        second_half = snapshots[len(snapshots)//2:]

        avg_health_first = sum(s.health_score for s in first_half) / len(first_half)
        avg_health_second = sum(s.health_score for s in second_half) / len(second_half)

        health_trend = "improving" if avg_health_second > avg_health_first else "degrading"
    else:
        health_trend = "stable"

    return {
        "period": period,
        "snapshots": snapshots,
        "health_trend": health_trend,
        "average_health_score": sum(s.health_score for s in snapshots) / len(snapshots) if snapshots else 0
    }
```

---

## Client Scripts

### Example: Platform Dashboard Enhancements

```javascript
// Client script for platform dashboard
frappe.ui.form.on('PlatformSettings', {
    refresh: function(frm) {
        // Add custom button to dashboard
        frm.add_custom_button(__('Run Health Check'), function() {
            frappe.call({
                method: 'platform_management.api.run_health_check',
                callback: function(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: __('Health check completed'),
                            indicator: 'green'
                        });
                    }
                }
            });
        });
    }
});
```

---

## Webhooks

### Example: Platform Event Webhook

```python
# Webhook configuration for platform events
webhook_config = {
    "name": "platform_health_webhook",
    "url": "https://external-monitoring.com/webhook",
    "events": [
        "platform_health_snapshot.after_insert",
        "platform_incident.after_insert"
    ],
    "method": "POST",
    "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
    }
}
```

---

## AI-Powered Code Generation

The Customization Framework includes AI-powered code generation for Platform Management customizations. Use the Customization Advisor Agent to generate server scripts, client scripts, and API endpoints based on natural language descriptions.

**Example**:
```
User: "Create a server script that sends an alert when platform health score drops below 70"

AI Agent generates:
- Server script with before_insert hook
- Email notification logic
- Error handling
- Documentation
```

---

## Best Practices

1. **Always validate inputs** in server scripts to prevent security issues
2. **Use frappe.enqueue()** for long-running operations
3. **Log all customizations** for debugging and audit
4. **Test customizations** in development before deploying to production
5. **Document custom logic** for future maintenance
6. **Use hooks appropriately** - don't overload hooks with complex logic

---

## References

- [Customization Framework Documentation](../customization-framework/README.md)
- [Hooks Development Guide](../../../development/hooks-development-guide.md)
- [Server Scripts Reference](../../../development/server-scripts-reference.md)
- [Client Scripts Reference](../../../development/client-scripts-reference.md)

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
