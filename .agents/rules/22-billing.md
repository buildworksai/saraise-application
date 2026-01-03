---
description: Billing & Subscription Plans
globs: backend/src/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# Billing & Subscription Plans

**Rule IDs**: SARAISE-34001 to SARAISE-34010, SARAISE-35001 to SARAISE-35010
**Consolidates**: `22-billing-subscriptions.md`, `22-billing.md`

---


# 💳 SARAISE Billing & Subscription Management

**⚠️ CRITICAL**: All billing and subscription operations MUST follow these patterns for security, accuracy, and compliance.

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Module Framework: `docs/architecture/module-framework.md`

## SARAISE-34001 Billing Overview

### Core Principles
- **Subscription-Based**: All billing is subscription-based
- **Tenant-Scoped**: Billing is scoped to tenants
- **Audit Logging**: All billing operations must be audited
- **Payment Processing**: Secure payment processing integration

## SARAISE-34002 Subscription Model

### Subscription Definition

See [Billing Models](docs/architecture/examples/backend/models/billing-models.py).

**Key Models:**
- `SubscriptionStatus` - Subscription status enum
- `Subscription` - Subscription model with tenant_id, plan_id, status, period dates
- `InvoiceStatus` - Invoice status enum
- `Invoice` - Invoice model with subscription_id, tenant_id, amount, status

## SARAISE-34003 Subscription Service

### Subscription Management Service

See [Subscription Service](docs/architecture/examples/backend/services/subscription-service.py).

**Key Methods:**
- `create_subscription()` - Create subscription for tenant
- `update_subscription()` - Update subscription plan
- `cancel_subscription()` - Cancel subscription
- `get_subscription()` - Get subscription by ID
- `get_tenant_subscription()` - Get tenant subscription (platform-level query)

## SARAISE-34004 Invoice Management

### Invoice Model

See [Billing Models](docs/architecture/examples/backend/models/billing-models.py).

**Key Models:**
- `InvoiceStatus` - Invoice status enum
- `Invoice` - Invoice model with subscription_id, tenant_id, amount, status, due_date

## SARAISE-34005 Payment Processing

### Payment Service

See [Payment Service](docs/architecture/examples/backend/services/payment-service.py).

**Key Methods:**
- `process_payment()` - Process payment for invoice
- `_charge_payment()` - Charge payment via payment gateway (placeholder for integration)

## SARAISE-34006 Billing Routes

### Billing API Routes

See [Billing Routes](docs/architecture/examples/backend/services/billing-routes.py).

**Key Endpoints:**
- `GET /subscriptions/{subscription_id}` - Get subscription (tenant billing manager only)
- `POST /subscriptions/{subscription_id}/cancel` - Cancel subscription (tenant billing manager only)
- `POST /invoices/{invoice_id}/pay` - Process payment for invoice (tenant billing manager only)

## SARAISE-34007 Subscription Lifecycle

### Subscription Lifecycle Management

See [Subscription Lifecycle Service](docs/architecture/examples/backend/services/subscription-lifecycle-service.py).

**Key Methods:**
- `process_subscription_renewals()` - Process subscription renewals
- `_renew_subscription()` - Renew subscription with invoice creation

## SARAISE-34008 Usage Tracking

### Usage Tracking Service

See [Usage Tracking Service](docs/architecture/examples/backend/services/usage-tracking-service.py).

**Key Methods:**
- `record_usage()` - Record resource usage for tenant
- `get_usage_summary()` - Get usage summary for tenant

## SARAISE-34009 Billing Testing

### Billing Test Patterns

See [Billing Tests](docs/architecture/examples/backend/tests/test_billing.py) for complete test examples.

**Required Tests:**
- Subscription creation
- Subscription renewal
- Payment processing
- Usage tracking

## SARAISE-34010 Billing Compliance

### Compliance Requirements
- **Audit Logging**: All billing operations must be audited
- **Data Retention**: Billing data must be retained for compliance
- **Privacy**: Payment data must be encrypted and secured
- **Reporting**: Financial reports must be accurate and auditable

---

**Next Steps**: Use these patterns to implement billing and subscription management. Ensure all billing operations are properly secured, audited, and compliant with regulations.

---


# 📦 SARAISE Subscription Plans

**⚠️ CRITICAL**: All subscription plan operations MUST follow these patterns for consistency, flexibility, and scalability.

## SARAISE-35001 Subscription Plan Overview

### Core Principles
- **Plan Tiers**: Multiple plan tiers (Free, Basic, Professional, Enterprise)
- **Feature-Based**: Plans include specific features and limits
- **Pricing**: Flexible pricing models (monthly, annual, usage-based)
- **Upgrade/Downgrade**: Support for plan changes

## SARAISE-35002 Subscription Plan Model

### Plan Definition

See [Subscription Plan Model](docs/architecture/examples/backend/models/subscription-plan-model.py).

## SARAISE-35003 Plan Service

### Plan Management Service

See [Plan Service](docs/architecture/examples/backend/services/plan-service.py).

## SARAISE-35004 Plan Features

### Feature Management

See [Plan Feature Service](docs/architecture/examples/backend/services/plan-feature-service.py).

## SARAISE-35005 Plan Routes

### Plan API Routes

See [Plan Routes](docs/architecture/examples/backend/services/plan-routes.py).

## SARAISE-35006 Plan Upgrade/Downgrade

### Plan Change Service

See [Plan Change Service](docs/architecture/examples/backend/services/plan-change-service.py).

## SARAISE-35007 Plan Testing

### Plan Test Patterns

See [Plan Testing Examples](docs/architecture/examples/backend/tests/test_plans.py) for complete test examples.

---

**Next Steps**: Use these patterns to implement subscription plan management. Ensure all plan operations support flexible pricing, feature management, and upgrade/downgrade workflows.

---


**Audit**: Version 7.0.0; Consolidated 2025-12-23
