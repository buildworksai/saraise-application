<!-- SPDX-License-Identifier: Apache-2.0 -->
# Billing & Subscriptions Customization Guide

**Module**: Billing & Subscriptions
**Category**: Foundation
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the Billing & Subscriptions module. Use these customization capabilities to extend billing logic, customize payment processing, implement custom pricing rules, and integrate with payment gateways.

---

## Customization Points

### 1. SubscriptionPlan Model

**Description**: Subscription plan definitions

**Available Hooks**:
- `before_insert` - Before creating a subscription plan
- `after_insert` - After a subscription plan is created
- `before_update` - Before updating a subscription plan
- `after_update` - After a subscription plan is updated

**Use Cases**:
- Validate plan configuration before saving
- Calculate plan pricing dynamically
- Enforce plan constraints
- Log plan changes for audit

**Example Server Script**:
```python
# Validate plan configuration
def before_save(doc, method):
    """Validate subscription plan configuration"""
    # Ensure price is positive
    if doc.price <= 0:
        frappe.throw("Subscription plan price must be greater than 0")

    # Validate billing cycle
    if doc.billing_cycle_days not in [7, 30, 90, 365]:
        frappe.throw("Billing cycle must be 7, 30, 90, or 365 days")

    # Validate tier
    valid_tiers = ["free", "basic", "professional", "enterprise"]
    if doc.tier not in valid_tiers:
        frappe.throw(f"Tier must be one of: {', '.join(valid_tiers)}")

# Calculate dynamic pricing
def before_insert(doc, method):
    """Calculate dynamic pricing based on features"""
    base_price = 0

    # Base price by tier
    tier_prices = {
        "free": 0,
        "basic": 29,
        "professional": 99,
        "enterprise": 299
    }
    base_price = tier_prices.get(doc.tier, 0)

    # Add feature-based pricing
    feature_prices = {
        "ai_agents": 20,
        "advanced_analytics": 15,
        "custom_integrations": 30
    }

    for feature, price in feature_prices.items():
        if doc.features.get(feature, False):
            base_price += price

    doc.price = base_price
```

---

### 2. Subscription Resource

**Description**: Tenant subscription records

**Available Hooks**:
- `before_insert` - Before creating a subscription
- `after_insert` - After a subscription is created
- `before_update` - Before updating a subscription
- `after_update` - After a subscription is updated
- `before_delete` - Before deleting a subscription

**Use Cases**:
- Validate subscription before creation
- Trigger subscription lifecycle workflows
- Calculate prorated amounts on plan changes
- Enforce subscription limits
- Log subscription events for audit

**Example Server Script**:
```python
# Calculate prorated amount on plan change
def before_update(doc, method):
    """Calculate prorated amount when changing plans"""
    if doc.has_value_changed("plan_id"):
        old_plan = frappe.get_doc("SubscriptionPlan", doc._doc_before_save.plan_id)
        new_plan = frappe.get_doc("SubscriptionPlan", doc.plan_id)

        # Calculate days remaining in current period
        days_remaining = (doc.current_period_end - frappe.utils.today()).days

        # Calculate prorated credit for old plan
        daily_rate_old = old_plan.price / old_plan.billing_cycle_days
        credit = daily_rate_old * days_remaining

        # Calculate prorated charge for new plan
        daily_rate_new = new_plan.price / new_plan.billing_cycle_days
        charge = daily_rate_new * days_remaining

        # Store prorated amount
        doc.prorated_amount = charge - credit
        doc.prorated_credit = credit
        doc.prorated_charge = charge

# Trigger subscription lifecycle workflow
def after_update(doc, method):
    """Trigger lifecycle workflow on status change"""
    if doc.has_value_changed("status"):
        if doc.status == "active":
            frappe.enqueue(
                "billing.workflows.activate_subscription",
                subscription_id=doc.name,
                queue="default"
            )
        elif doc.status == "suspended":
            frappe.enqueue(
                "billing.workflows.suspend_subscription",
                subscription_id=doc.name,
                queue="default"
            )
```

---

### 3. SubscriptionInvoice Resource

**Description**: Subscription invoice records

**Available Hooks**:
- `before_insert` - Before creating an invoice
- `after_insert` - After an invoice is created
- `after_update` - After an invoice is updated

**Use Cases**:
- Calculate invoice amounts before saving
- Apply discounts and coupons
- Validate payment terms
- Trigger invoice generation workflows
- Send invoice notifications

**Example Server Script**:
```python
# Apply discounts and coupons
def before_insert(doc, method):
    """Apply discounts and coupons to invoice"""
    subscription = frappe.get_doc("Subscription", doc.subscription_id)
    plan = frappe.get_doc("SubscriptionPlan", subscription.plan_id)

    base_amount = plan.price

    # Apply discounts
    discounts = frappe.get_all(
        "DiscountApplication",
        filters={
            "subscription_id": doc.subscription_id,
            "status": "active"
        },
        fields=["discount_id", "applied_amount"]
    )

    total_discount = sum(d.applied_amount for d in discounts)

    # Apply coupons
    coupons = frappe.get_all(
        "CouponApplication",
        filters={
            "subscription_id": doc.subscription_id,
            "status": "active"
        },
        fields=["coupon_id", "discount_amount"]
    )

    total_coupon_discount = sum(c.discount_amount for c in coupons)

    # Calculate final amount
    doc.amount = base_amount - total_discount - total_coupon_discount
    doc.discount_amount = total_discount
    doc.coupon_discount_amount = total_coupon_discount

# Send invoice notifications
def after_insert(doc, method):
    """Send invoice notification email"""
    tenant = frappe.get_doc("Tenant", doc.tenant_id)

    frappe.sendmail(
        recipients=[tenant.admin_email],
        subject=f"Invoice #{doc.invoice_number} - {doc.amount} {doc.currency}",
        message=f"""
            Invoice #{doc.invoice_number} has been generated.

            Amount: {doc.amount} {doc.currency}
            Due Date: {doc.due_date}

            Please make payment before the due date to avoid service interruption.
        """,
        attachments=[{
            "fname": f"invoice_{doc.invoice_number}.pdf",
            "fcontent": generate_invoice_pdf(doc)
        }]
    )
```

---

### 4. SubscriptionPayment Resource

**Description**: Subscription payment records

**Available Hooks**:
- `before_insert` - Before processing a payment
- `after_insert` - After a payment is processed
- `after_update` - After a payment is updated

**Use Cases**:
- Validate payment before processing
- Process payment through gateway
- Update invoice status on payment
- Trigger payment confirmation workflows
- Log payment events for audit

**Example Server Script**:
```python
# Process payment through gateway
def before_insert(doc, method):
    """Process payment through payment gateway"""
    invoice = frappe.get_doc("SubscriptionInvoice", doc.invoice_id)

    # Process payment via Stripe (example)
    import stripe
    stripe.api_key = frappe.conf.stripe_secret_key

    try:
        charge = stripe.Charge.create(
            amount=int(doc.amount * 100),  # Convert to cents
            currency=doc.currency.lower(),
            source=doc.payment_method_id,
            description=f"Invoice {invoice.invoice_number}"
        )

        doc.payment_gateway_id = charge.id
        doc.status = "succeeded"
        doc.processed_at = frappe.utils.now_datetime()

    except stripe.error.CardError as e:
        doc.status = "failed"
        doc.failure_reason = str(e)
        frappe.throw(f"Payment failed: {str(e)}")

# Update invoice status on payment
def after_insert(doc, method):
    """Update invoice status when payment succeeds"""
    if doc.status == "succeeded":
        invoice = frappe.get_doc("SubscriptionInvoice", doc.invoice_id)
        invoice.status = "paid"
        invoice.paid_date = doc.processed_at
        invoice.save()
```

---

### 5. Discount Resource

**Description**: Discount definitions

**Available Hooks**:
- `before_insert` - Before creating a discount
- `after_insert` - After a discount is created
- `before_update` - Before updating a discount
- `after_update` - After a discount is updated

**Use Cases**:
- Validate discount rules before saving
- Enforce discount constraints
- Calculate discount eligibility
- Log discount changes for audit

**Example Server Script**:
```python
# Validate discount rules
def before_save(doc, method):
    """Validate discount configuration"""
    # Validate discount value
    if doc.discount_type == "percentage":
        if doc.discount_value < 0 or doc.discount_value > 100:
            frappe.throw("Percentage discount must be between 0 and 100")
    elif doc.discount_type == "fixed_amount":
        if doc.discount_value <= 0:
            frappe.throw("Fixed amount discount must be greater than 0")

    # Validate date range
    if doc.valid_until and doc.valid_from > doc.valid_until:
        frappe.throw("Valid until date must be after valid from date")
```

---

### 6. Coupon Resource

**Description**: Coupon code definitions

**Available Hooks**:
- `before_insert` - Before creating a coupon
- `after_insert` - After a coupon is created
- `before_update` - Before updating a coupon
- `after_update` - After a coupon is updated

**Use Cases**:
- Validate coupon code format
- Enforce coupon usage limits
- Calculate coupon eligibility
- Log coupon changes for audit

**Example Server Script**:
```python
# Validate coupon code format
def before_insert(doc, method):
    """Validate coupon code format"""
    import re

    # Coupon code must be alphanumeric, 6-20 characters
    if not re.match(r'^[A-Z0-9]{6,20}$', doc.code):
        frappe.throw(
            "Coupon code must be 6-20 characters, uppercase alphanumeric only"
        )

    # Check for duplicate codes
    existing = frappe.get_all(
        "Coupon",
        filters={"code": doc.code},
        limit=1
    )
    if existing:
        frappe.throw(f"Coupon code '{doc.code}' already exists")
```

---

### 7. Partner Resource

**Description**: Partner and affiliate records

**Available Hooks**:
- `before_insert` - Before creating a partner
- `after_insert` - After a partner is created
- `before_update` - Before updating a partner
- `after_update` - After a partner is updated

**Use Cases**:
- Validate partner configuration
- Calculate commission rates
- Enforce partner constraints
- Log partner changes for audit

**Example Server Script**:
```python
# Calculate commission rates
def before_insert(doc, method):
    """Calculate commission rates based on partner tier"""
    tier_commission_rates = {
        "bronze": 0.10,  # 10%
        "silver": 0.15,  # 15%
        "gold": 0.20,    # 20%
        "platinum": 0.25 # 25%
    }

    doc.commission_rate = tier_commission_rates.get(doc.tier, 0.10)
```

---

### 8. PartnerReferral Resource

**Description**: Partner referral records

**Available Hooks**:
- `before_insert` - Before creating a referral
- `after_insert` - After a referral is created
- `after_update` - After a referral is updated

**Use Cases**:
- Validate referral code before creation
- Track referral conversions
- Calculate referral commissions
- Trigger referral workflows

**Example Server Script**:
```python
# Track referral conversions
def after_update(doc, method):
    """Track referral conversion and calculate commission"""
    if doc.has_value_changed("converted") and doc.converted:
        partner = frappe.get_doc("Partner", doc.partner_id)
        subscription = frappe.get_doc("Subscription", doc.subscription_id)
        plan = frappe.get_doc("SubscriptionPlan", subscription.plan_id)

        # Calculate commission
        commission_amount = plan.price * partner.commission_rate

        # Create commission record
        commission = frappe.new_doc("PartnerCommission")
        commission.partner_id = doc.partner_id
        commission.referral_id = doc.name
        commission.subscription_id = doc.subscription_id
        commission.amount = commission_amount
        commission.status = "pending"
        commission.save()
```

---

### 9. RateLimitUsage Resource

**Description**: Rate limit usage tracking

**Available Hooks**:
- `before_insert` - Before recording rate limit usage
- `after_insert` - After rate limit usage is recorded
- `before_update` - Before updating rate limit usage
- `after_update` - After rate limit usage is updated

**Use Cases**:
- Track API usage per tenant
- Enforce rate limits
- Trigger rate limit warnings
- Log rate limit violations

**Example Server Script**:
```python
# Enforce rate limits
def before_insert(doc, method):
    """Enforce rate limits"""
    subscription = frappe.get_doc("Subscription", doc.subscription_id)
    plan = frappe.get_doc("SubscriptionPlan", subscription.plan_id)

    # Get current usage for this period
    period_start = frappe.utils.get_first_day(doc.usage_date)
    period_end = frappe.utils.get_last_day(doc.usage_date)

    current_usage = frappe.db.sql("""
        SELECT SUM(request_count) as total
        FROM `tabRateLimitUsage`
        WHERE subscription_id = %s
          AND usage_date BETWEEN %s AND %s
    """, (doc.subscription_id, period_start, period_end), as_dict=True)[0].total or 0

    # Check if limit exceeded
    if current_usage + doc.request_count > plan.max_api_calls_per_month:
        frappe.throw(
            f"Rate limit exceeded. Current: {current_usage}, "
            f"Limit: {plan.max_api_calls_per_month}"
        )
```

---

### 10. UsageRecord Resource

**Description**: Resource usage records

**Available Hooks**:
- `before_insert` - Before recording usage
- `after_insert` - After usage is recorded

**Use Cases**:
- Validate usage data before recording
- Calculate usage-based billing
- Aggregate usage metrics
- Trigger usage alerts

**Example Server Script**:
```python
# Calculate usage-based billing
def after_insert(doc, method):
    """Calculate usage-based billing charges"""
    subscription = frappe.get_doc("Subscription", doc.subscription_id)
    plan = frappe.get_doc("SubscriptionPlan", subscription.plan_id)

    # Get usage-based pricing from plan
    usage_pricing = plan.features.get("usage_pricing", {})

    if doc.resource_type in usage_pricing:
        unit_price = usage_pricing[doc.resource_type]
        charge = doc.quantity * unit_price

        # Create usage charge record
        usage_charge = frappe.new_doc("UsageCharge")
        usage_charge.subscription_id = doc.subscription_id
        usage_charge.usage_record_id = doc.name
        usage_charge.resource_type = doc.resource_type
        usage_charge.quantity = doc.quantity
        usage_charge.unit_price = unit_price
        usage_charge.amount = charge
        usage_charge.status = "pending"
        usage_charge.save()
```

---

## Custom API Endpoints

### Example: Custom Invoice Explanation Endpoint

```python
@frappe.whitelist()
def explain_invoice(invoice_id):
    """Explain invoice charges in natural language (Ask Amani entry point)"""
    invoice = frappe.get_doc("SubscriptionInvoice", invoice_id)
    subscription = frappe.get_doc("Subscription", invoice.subscription_id)
    plan = frappe.get_doc("SubscriptionPlan", subscription.plan_id)

    explanation = f"""
        Invoice #{invoice.invoice_number} for {plan.name} subscription.

        Base Amount: ${plan.price} {plan.currency}
        Discount: ${invoice.discount_amount or 0} {invoice.currency}
        Coupon Discount: ${invoice.coupon_discount_amount or 0} {invoice.currency}
        Total: ${invoice.amount} {invoice.currency}

        Due Date: {invoice.due_date}
        Status: {invoice.status}
    """

    return {
        "invoice_id": invoice_id,
        "explanation": explanation,
        "breakdown": {
            "base_amount": plan.price,
            "discount": invoice.discount_amount or 0,
            "coupon_discount": invoice.coupon_discount_amount or 0,
            "total": invoice.amount
        }
    }
```

### Example: Custom Usage and Rate Limits Endpoint

```python
@frappe.whitelist()
def show_tenant_usage_and_rate_limits(tenant_id):
    """Show tenant usage and rate limits (Ask Amani entry point)"""
    tenant = frappe.get_doc("Tenant", tenant_id)
    subscription = frappe.get_doc("Subscription", tenant.subscription_id)
    plan = frappe.get_doc("SubscriptionPlan", subscription.plan_id)

    # Get current usage
    current_month = frappe.utils.get_first_day(frappe.utils.today())

    api_usage = frappe.db.sql("""
        SELECT SUM(request_count) as total
        FROM `tabRateLimitUsage`
        WHERE subscription_id = %s
          AND usage_date >= %s
    """, (subscription.name, current_month), as_dict=True)[0].total or 0

    return {
        "tenant_id": tenant_id,
        "subscription_plan": plan.name,
        "rate_limits": {
            "api_calls_per_month": plan.max_api_calls_per_month,
            "current_usage": api_usage,
            "remaining": plan.max_api_calls_per_month - api_usage,
            "utilization_percent": (api_usage / plan.max_api_calls_per_month) * 100
        },
        "quotas": {
            "max_users": plan.max_users,
            "max_storage_gb": plan.max_storage_gb
        }
    }
```

---

## Client Scripts

### Example: Invoice Form Enhancements

```javascript
// Client script for invoice form
frappe.ui.form.on('SubscriptionInvoice', {
    refresh: function(frm) {
        // Add "Explain Invoice" button (Ask Amani entry point)
        frm.add_custom_button(__('Explain Invoice'), function() {
            frappe.call({
                method: 'billing.api.explain_invoice',
                args: {
                    invoice_id: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: __('Invoice Explanation'),
                            message: r.message.explanation
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

### Example: Payment Gateway Webhook

```python
# Webhook handler for payment gateway events
@frappe.whitelist(allow_guest=True)
def payment_gateway_webhook():
    """Handle payment gateway webhook events"""
    data = frappe.request.get_json()
    event_type = data.get("type")

    if event_type == "payment.succeeded":
        payment_id = data.get("data", {}).get("object", {}).get("id")

        # Update payment status
        payment = frappe.get_doc("SubscriptionPayment", {"payment_gateway_id": payment_id})
        payment.status = "succeeded"
        payment.processed_at = frappe.utils.now_datetime()
        payment.save()

    elif event_type == "payment.failed":
        payment_id = data.get("data", {}).get("object", {}).get("id")

        # Update payment status
        payment = frappe.get_doc("SubscriptionPayment", {"payment_gateway_id": payment_id})
        payment.status = "failed"
        payment.failure_reason = data.get("data", {}).get("object", {}).get("failure_message")
        payment.save()

    return {"status": "ok"}
```

---

## AI-Powered Code Generation

Use the Customization Advisor Agent to generate billing customizations:

**Example**:
```
User: "Create a server script that applies a 10% discount to all enterprise subscriptions"

AI Agent generates:
- Server script with before_insert hook on SubscriptionInvoice
- Discount calculation logic
- Enterprise subscription detection
- Error handling
```

---

## Best Practices

1. **Always validate payment amounts** before processing
2. **Use frappe.enqueue()** for payment gateway calls
3. **Log all billing operations** for audit and compliance
4. **Handle payment failures gracefully** with retry logic
5. **Test customizations** with test payment methods
6. **Document custom pricing rules** for future reference
7. **Respect subscription limits** when calculating charges

---

## References

- [Customization Framework Documentation](../customization-framework/README.md)
- [Hooks Development Guide](../../../development/hooks-development-guide.md)
- [Server Scripts Reference](../../../development/server-scripts-reference.md)
- [Payment Gateway Integration Guide](../../../development/payment-gateway-integration.md)
