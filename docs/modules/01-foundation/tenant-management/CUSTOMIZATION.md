<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tenant Management Customization Guide

**Module**: Tenant Management
**Category**: Foundation
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the Tenant Management module. Use these customization capabilities to extend tenant lifecycle management, customize quota enforcement, and implement custom tenant onboarding workflows.

---

## Customization Points

### 1. TenantQuotaUsage Model

**Description**: Tenant quota usage tracking

**Available Hooks**:
- `before_insert` - Before recording quota usage
- `after_insert` - After quota usage is recorded
- `before_update` - Before updating quota usage
- `after_update` - After quota usage is updated

**Use Cases**:
- Validate quota usage before recording
- Trigger quota warning notifications
- Enforce quota limits
- Calculate quota utilization percentages

**Example Server Script**:
```python
# Validate quota usage before recording
def before_insert(doc, method):
    """Validate quota usage and check limits"""
    # Get subscription limits
    subscription = frappe.get_doc("Subscription", doc.subscription_id)
    plan = frappe.get_doc("SubscriptionPlan", subscription.plan_id)

    # Get quota limit from plan
    quota_limit = plan.features.get(f"max_{doc.quota_type}", 0)

    if quota_limit > 0 and doc.current_usage > quota_limit:
        frappe.throw(
            f"Quota usage ({doc.current_usage}) exceeds limit ({quota_limit}) for {doc.quota_type}"
        )

# Trigger quota warning notifications
def after_update(doc, method):
    """Send warning when quota usage exceeds 80%"""
    utilization = (doc.current_usage / doc.limit) * 100 if doc.limit > 0 else 0

    if utilization >= 80 and not doc.warning_sent:
        # Send warning email
        tenant = frappe.get_doc("Tenant", doc.tenant_id)
        frappe.sendmail(
            recipients=[tenant.admin_email],
            subject=f"⚠️ Quota Warning: {doc.quota_type} at {utilization:.1f}%",
            message=f"""
                Your {doc.quota_type} quota is at {utilization:.1f}% capacity.

                Current Usage: {doc.current_usage}
                Limit: {doc.limit}

                Please consider upgrading your subscription to avoid service interruption.
            """
        )

        # Mark warning as sent
        doc.warning_sent = True
        doc.warning_sent_at = frappe.utils.now_datetime()
        doc.save()
```

---

### 2. TenantQuotaViolation Model

**Description**: Tenant quota violation records

**Available Hooks**:
- `before_insert` - Before creating a quota violation
- `after_insert` - After a quota violation is created

**Use Cases**:
- Log quota violations for audit
- Trigger quota violation notifications
- Auto-suspend tenants on repeated violations

**Example Server Script**:
```python
# Auto-suspend on repeated violations
def after_insert(doc, method):
    """Auto-suspend tenant on repeated violations"""
    # Count violations in last 30 days
    violations = frappe.get_all(
        "TenantQuotaViolation",
        filters={
            "tenant_id": doc.tenant_id,
            "quota_type": doc.quota_type,
            "created_at": [">=", frappe.utils.add_days(frappe.utils.today(), -30)],
            "is_resolved": False
        }
    )

    # Auto-suspend after 3 violations
    if len(violations) >= 3:
        tenant = frappe.get_doc("Tenant", doc.tenant_id)
        tenant.is_active = False
        tenant.save()

        frappe.sendmail(
            recipients=[tenant.admin_email],
            subject="🚨 Tenant Suspended Due to Quota Violations",
            message=f"""
                Your tenant has been suspended due to repeated quota violations.

                Violations in last 30 days: {len(violations)}
                Latest violation: {doc.quota_type} - {doc.current_usage}/{doc.limit}

                Please contact support to resolve this issue.
            """
        )
```

---

### 3. TenantModule Resource

**Description**: Tenant module installation tracking

**Available Hooks**:
- `before_insert` - Before installing a module
- `after_insert` - After a module is installed
- `before_update` - Before updating module status
- `after_update` - After module status is updated

**Use Cases**:
- Validate module dependencies before installation
- Trigger module installation workflows
- Log module installation events
- Enforce module compatibility rules

**Example Server Script**:
```python
# Validate module dependencies
def before_insert(doc, method):
    """Validate module dependencies before installation"""
    # Get module manifest
    module_manifest = frappe.get_doc("Module", doc.module_name)
    required_modules = module_manifest.depends_on or []

    # Check if required modules are installed
    for required_module in required_modules:
        installed = frappe.get_all(
            "TenantModule",
            filters={
                "tenant_id": doc.tenant_id,
                "module_name": required_module,
                "status": "active"
            }
        )

        if not installed:
            frappe.throw(
                f"Module '{required_module}' is required but not installed. "
                f"Please install it before installing '{doc.module_name}'."
            )

# Trigger module installation workflow
def after_insert(doc, method):
    """Trigger module installation workflow"""
    if doc.status == "active":
        frappe.enqueue(
            "tenant_management.workflows.initialize_module",
            tenant_id=doc.tenant_id,
            module_name=doc.module_name,
            queue="default"
        )
```

---

### 4. TenantHealthSnapshot Resource

**Description**: Tenant health monitoring snapshots

**Available Hooks**:
- `before_insert` - Before creating a health snapshot
- `after_insert` - After a health snapshot is created

**Use Cases**:
- Calculate tenant health score
- Detect tenant churn risk
- Trigger health improvement workflows

**Example Server Script**:
```python
# Calculate tenant health score
def before_insert(doc, method):
    """Calculate tenant health score"""
    # Health score factors
    usage_score = min(100, (doc.active_users / doc.total_users) * 100) if doc.total_users > 0 else 0
    engagement_score = min(100, doc.engagement_metrics.get("score", 0))
    support_score = 100 - (doc.support_tickets_count * 10)  # Penalize support tickets

    # Weighted average
    doc.health_score = (
        usage_score * 0.4 +
        engagement_score * 0.4 +
        support_score * 0.2
    )

# Detect churn risk
def after_insert(doc, method):
    """Detect tenant churn risk"""
    if doc.health_score < 50:
        # High churn risk
        tenant = frappe.get_doc("Tenant", doc.tenant_id)

        # Trigger retention workflow
        frappe.enqueue(
            "tenant_management.workflows.tenant_retention",
            tenant_id=doc.tenant_id,
            health_score=doc.health_score,
            queue="default"
        )
```

---

### 5. TenantActivitySnapshot Resource

**Description**: Tenant activity metrics

**Available Hooks**:
- `before_insert` - Before creating an activity snapshot
- `after_insert` - After an activity snapshot is created

**Use Cases**:
- Calculate activity metrics
- Detect unusual activity patterns
- Trigger engagement workflows

**Example Server Script**:
```python
# Detect unusual activity patterns
def after_insert(doc, method):
    """Detect unusual activity patterns"""
    # Get previous snapshots for comparison
    previous = frappe.get_all(
        "TenantActivitySnapshot",
        filters={
            "tenant_id": doc.tenant_id,
            "snapshot_date": ["<", doc.snapshot_date]
        },
        order_by="snapshot_date desc",
        limit=7  # Last 7 days
    )

    if len(previous) >= 3:
        avg_activity = sum(p.daily_active_users for p in previous) / len(previous)

        # Detect significant drop in activity
        if doc.daily_active_users < avg_activity * 0.5:
            # Trigger engagement workflow
            frappe.enqueue(
                "tenant_management.workflows.re_engage_tenant",
                tenant_id=doc.tenant_id,
                queue="default"
            )
```

---

### 6. TenantUsageSnapshot Resource

**Description**: Tenant usage metrics

**Available Hooks**:
- `before_insert` - Before creating a usage snapshot
- `after_insert` - After a usage snapshot is created

**Use Cases**:
- Calculate usage metrics
- Detect usage anomalies
- Trigger usage-based recommendations

**Example Server Script**:
```python
# Detect usage anomalies
def after_insert(doc, method):
    """Detect usage anomalies"""
    # Get subscription plan
    tenant = frappe.get_doc("Tenant", doc.tenant_id)
    subscription = frappe.get_doc("Subscription", tenant.subscription_id)
    plan = frappe.get_doc("SubscriptionPlan", subscription.plan_id)

    # Check if usage exceeds plan limits
    if doc.api_calls > plan.max_api_calls_per_month:
        # Recommend upgrade
        frappe.enqueue(
            "tenant_management.workflows.recommend_upgrade",
            tenant_id=doc.tenant_id,
            reason="API calls exceed plan limit",
            queue="default"
        )
```

---

### 7. TenantChurnRiskSnapshot Resource

**Description**: Tenant churn risk predictions

**Available Hooks**:
- `before_insert` - Before creating a churn risk snapshot
- `after_insert` - After a churn risk snapshot is created

**Use Cases**:
- Calculate churn risk score
- Trigger retention workflows
- Send churn risk alerts

**Example Server Script**:
```python
# Trigger retention workflow on high churn risk
def after_insert(doc, method):
    """Trigger retention workflow on high churn risk"""
    if doc.churn_risk_score >= 70:  # High risk
        tenant = frappe.get_doc("Tenant", doc.tenant_id)

        # Send retention email
        frappe.sendmail(
            recipients=[tenant.admin_email],
            subject="We'd love to keep you!",
            message=f"""
                We noticed you might be considering other options.

                We'd love to help! Here are some ways we can assist:
                - Custom onboarding session
                - Feature training
                - Discount on upgrade

                Please reach out to discuss how we can better serve you.
            """
        )

        # Trigger retention workflow
        frappe.enqueue(
            "tenant_management.workflows.tenant_retention",
            tenant_id=doc.tenant_id,
            churn_risk_score=doc.churn_risk_score,
            queue="default"
        )
```

---

### 8. TenantValueSnapshot Resource

**Description**: Tenant value metrics

**Available Hooks**:
- `before_insert` - Before creating a value snapshot
- `after_insert` - After a value snapshot is created

**Use Cases**:
- Calculate tenant lifetime value
- Identify high-value tenants
- Trigger value-based workflows

**Example Server Script**:
```python
# Identify high-value tenants
def after_insert(doc, method):
    """Identify high-value tenants for special treatment"""
    if doc.lifetime_value > 10000:  # High-value tenant
        tenant = frappe.get_doc("Tenant", doc.tenant_id)

        # Assign dedicated account manager
        if not tenant.account_manager:
            account_managers = frappe.get_all(
                "User",
                filters={"role": "Account Manager"},
                fields=["name"]
            )
            if account_managers:
                tenant.account_manager = account_managers[0].name
                tenant.save()

        # Send VIP onboarding
        frappe.enqueue(
            "tenant_management.workflows.vip_onboarding",
            tenant_id=doc.tenant_id,
            queue="default"
        )
```

---

## Custom API Endpoints

### Example: Custom Tenant Analytics Endpoint

```python
@frappe.whitelist()
def get_tenant_usage_summary(tenant_id):
    """Get comprehensive tenant usage summary"""
    tenant = frappe.get_doc("Tenant", tenant_id)

    # Get quota usage
    quota_usage = frappe.get_all(
        "TenantQuotaUsage",
        filters={"tenant_id": tenant_id},
        fields=["quota_type", "current_usage", "limit"]
    )

    # Get recent activity
    recent_activity = frappe.get_all(
        "TenantActivitySnapshot",
        filters={"tenant_id": tenant_id},
        order_by="snapshot_date desc",
        limit=30,
        fields=["snapshot_date", "daily_active_users", "api_calls"]
    )

    # Get health score
    health = frappe.get_all(
        "TenantHealthSnapshot",
        filters={"tenant_id": tenant_id},
        order_by="snapshot_date desc",
        limit=1,
        fields=["health_score"]
    )

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "quota_usage": quota_usage,
        "recent_activity": recent_activity,
        "health_score": health[0].health_score if health else None
    }
```

---

## Client Scripts

### Example: Tenant Dashboard Enhancements

```javascript
// Client script for tenant dashboard
frappe.ui.form.on('Tenant', {
    refresh: function(frm) {
        // Add custom button to view usage
        frm.add_custom_button(__('View Usage Summary'), function() {
            frappe.call({
                method: 'tenant_management.api.get_tenant_usage_summary',
                args: {
                    tenant_id: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
                        // Show usage summary in dialog
                        frappe.msgprint({
                            title: __('Usage Summary'),
                            message: frappe.render_template('tenant_usage_summary', r.message)
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

### Example: Tenant Event Webhook

```python
# Webhook configuration for tenant events
webhook_config = {
    "name": "tenant_quota_webhook",
    "url": "https://external-system.com/webhook",
    "events": [
        "tenant_quota_usage.after_update",
        "tenant_quota_violation.after_insert"
    ],
    "method": "POST",
    "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
    }
}
```

---

## AI-Powered Code Generation

Use the Customization Advisor Agent to generate tenant management customizations:

**Example**:
```
User: "Create a server script that sends an email when a tenant exceeds 90% of their user quota"

AI Agent generates:
- Server script with after_update hook on TenantQuotaUsage
- Email notification logic
- Quota calculation
- Error handling
```

---

## Best Practices

1. **Always check subscription limits** before enforcing quotas
2. **Use frappe.enqueue()** for long-running tenant operations
3. **Log all tenant customizations** for audit and debugging
4. **Respect tenant isolation** - never access other tenants' data
5. **Test customizations** with demo tenant before production
6. **Document custom logic** for future maintenance

---

## References

- [Customization Framework Documentation](../customization-framework/README.md)
- [Hooks Development Guide](../../../development/hooks-development-guide.md)
- [Server Scripts Reference](../../../development/server-scripts-reference.md)
