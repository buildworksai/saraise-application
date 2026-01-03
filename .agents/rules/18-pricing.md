---
description: Pricing, Discounts & Coupons
globs: backend/src/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# Pricing, Discounts & Coupons

**Rule IDs**: SARAISE-36001 to SARAISE-36010, SARAISE-37001 to SARAISE-37010
**Consolidates**: `18-pricing.md`, `18-pricing.md`

---


# 🎟️ SARAISE Discounts & Offers

**⚠️ CRITICAL**: All discount and offer operations MUST follow these patterns for security, accuracy, and compliance.

**Related Documentation:**
- Billing & Subscriptions: See `22-billing-subscriptions.md` (SARAISE-34001-34010)
- Subscription Plans: See `22-billing.md` (SARAISE-35001-35010)
- Coupon Management: See `18-pricing.md` (SARAISE-37001-37010)

## SARAISE-36001 Discount Overview

### Core Principles
- **Discount Types**: Percentage or fixed amount discounts
- **Scope**: Can target subscription plans, addons, services, or all
- **Stacking**: Support for discount stacking with exclusions
- **Usage Limits**: Per-discount and per-user usage limits
- **Validation**: Must validate eligibility before application
- **Audit Logging**: All discount operations must be audited

## SARAISE-36002 Discount Model

### Discount Definition

**Key Fields:**
- `discount_type`: `percentage` or `fixed_amount`
- `discount_value`: Discount amount (percentage or fixed)
- `scope`: `subscription_plan`, `addon`, `service`, or `all`
- `target_plan_id`: Optional plan-specific targeting
- `valid_from` / `valid_until`: Validity period
- `max_uses` / `max_uses_per_user`: Usage limits
- `can_stack`: Whether discount can stack with others
- `excludes_discount_ids`: Discounts that cannot be used together
- `min_subscription_amount`: Minimum subscription amount required
- `is_public`: Whether discount is publicly visible

## SARAISE-36003 Discount Service

### Core Operations

**Key Methods:**
- `create_discount()` - Create new discount (platform billing manager only)
- `validate_discount()` - Validate discount eligibility
- `apply_discount()` - Apply discount to subscription
- `get_active_offers()` - Get available offers for tenant

**Validation Rules:**
- Check validity period (valid_from, valid_until)
- Check usage limits (max_uses, max_uses_per_user)
- Check scope and target plan eligibility
- Check minimum subscription amount
- Check stacking rules and exclusions

## SARAISE-36004 Discount Routes

See [Discount Routes](docs/architecture/examples/backend/services/discount-routes.py).

**Key Endpoints:**
- `POST /discounts` - Create discount (RequirePlatformBillingManager)
- `POST /discounts/apply` - Apply discount to subscription (tenant user)
- `GET /discounts/offers` - Get active offers (public or tenant-specific)

**Key Points:**
- Platform billing manager can create/modify/delete discounts
- Tenant users can view and apply public discounts
- All operations are audited
- Subscription validation ensures tenant isolation

## SARAISE-36005 Frontend Integration

See [Discount Management Component](docs/architecture/examples/frontend/components/discount-manager.tsx).

**Key Features:**
- Discount code input and application
- Discount listing for platform billing managers
- Real-time validation feedback
- Integration with subscription management

## SARAISE-36006 Testing Requirements

See [Discount Service Tests](docs/architecture/examples/backend/tests/discount-service-tests.py) for complete test examples.

**Required Tests:**
- Discount creation
- Discount validation (success, expired, invalid)
- Discount application
- Usage limit enforcement
- Stacking rules validation

## SARAISE-36007 Audit Requirements

**REQUIRED:** All discount operations must be audited (see `11-audit-logging.md`)

- Discount creation/modification
- Discount application
- Discount removal
- Offer creation/modification

## SARAISE-36008 Security Requirements

- **Platform Billing Manager:** Can create/modify/delete discounts
- **Tenant Billing Manager:** Can view and apply discounts to their tenant
- **Tenant Users:** Can view public discounts and apply them
- **Discount Code Validation:** Must validate discount eligibility before application
- **Usage Limits:** Must enforce max_uses and max_uses_per_user
- **Stacking Rules:** Must respect can_stack and excludes_discount_ids

## SARAISE-36009 Performance Targets

- Discount validation: < 50ms
- Discount application: < 100ms
- Get active offers: < 200ms
- Discount calculation: < 30ms

## SARAISE-36010 Integration Points

- **Subscription Plans:** Discounts can target specific plans
- **Subscriptions:** Discounts are applied to subscriptions
- **Billing:** Discount amounts affect invoice calculations
- **Coupons:** Discounts can be used with coupon codes (see `18-pricing.md`)
- **Partners:** Partner-specific discounts (see `23-partner-management.md`)

---


# 🎫 SARAISE Coupon Management

**⚠️ CRITICAL**: All coupon operations MUST follow these patterns for security, accuracy, and compliance.

**Related Documentation:**
- Billing & Subscriptions: See `22-billing-subscriptions.md` (SARAISE-34001-34010)
- Discounts & Offers: See `18-pricing.md` (SARAISE-36001-36010)
- Subscription Plans: See `22-billing.md` (SARAISE-35001-35010)

## SARAISE-37001 Coupon Overview

### Core Principles
- **Coupon Types**: Discount-linked or standalone coupons
- **Usage Types**: Single-use, multi-use, or single-use-per-user
- **Code-Based**: Coupons are identified by unique codes
- **Eligibility**: Can target specific tenants or plans
- **Validation**: Must validate eligibility before application
- **Audit Logging**: All coupon operations must be audited

## SARAISE-37002 Coupon Model

### Coupon Definition

**Key Fields:**
- `code`: Unique coupon code (3-50 characters)
- `coupon_type`: `discount_linked` or `standalone`
- `discount_id`: Optional link to existing discount
- `discount_type` / `discount_value`: Standalone discount details
- `scope`: `subscription_plan`, `addon`, `service`, or `all`
- `valid_from` / `valid_until`: Validity period
- `usage_type`: `single_use`, `multi_use`, or `single_use_per_user`
- `max_uses` / `max_uses_per_user`: Usage limits
- `eligible_tenant_ids`: Optional tenant-specific targeting
- `eligible_plan_ids`: Optional plan-specific targeting
- `min_subscription_amount`: Minimum subscription amount required
- `is_public`: Whether coupon is publicly visible

## SARAISE-37003 Coupon Service

### Core Operations

**Key Methods:**
- `create_coupon()` - Create new coupon (platform billing manager only)
- `get_coupon_by_code()` - Retrieve coupon by code
- `validate_coupon()` - Validate coupon eligibility
- `apply_coupon()` - Apply coupon to subscription

**Validation Rules:**
- Check validity period (valid_from, valid_until)
- Check usage limits (max_uses, max_uses_per_user)
- Check usage type (single-use enforcement)
- Check scope and target plan/tenant eligibility
- Check minimum subscription amount

## SARAISE-37004 Coupon Routes

See [Coupon Routes](docs/architecture/examples/backend/services/coupon-routes.py).

**Key Endpoints:**
- `POST /coupons` - Create coupon (RequirePlatformBillingManager)
- `POST /coupons/apply` - Apply coupon to subscription (tenant user)
- `GET /coupons/validate/{coupon_code}` - Validate coupon without applying (public)

**Key Points:**
- Platform billing manager can create/modify/delete coupons
- Tenant users can validate and apply public coupons
- All operations are audited
- Single-use coupons are archived after first use

## SARAISE-37005 Frontend Integration

See [Coupon Input Component](docs/architecture/examples/frontend/components/coupon-input.tsx).

**Key Features:**
- Coupon code input with validation
- Apply coupon to subscription
- Real-time validation feedback
- Integration with subscription management

## SARAISE-37006 Testing Requirements

See [Coupon Service Tests](docs/architecture/examples/backend/tests/coupon-service-tests.py) for complete test examples.

**Required Tests:**
- Coupon creation
- Coupon validation (success, invalid, expired)
- Coupon application
- Single-use enforcement
- Usage limit enforcement

## SARAISE-37007 Audit Requirements

**REQUIRED:** All coupon operations must be audited (see `11-audit-logging.md`)

- Coupon creation/modification
- Coupon application
- Coupon revocation
- Coupon validation

## SARAISE-37008 Security Requirements

- **Platform Billing Manager:** Can create/modify/delete coupons
- **Tenant Billing Manager:** Can view and apply coupons to their tenant
- **Tenant Users:** Can validate and apply public coupons
- **Coupon Code Validation:** Must validate coupon eligibility before application
- **Usage Limits:** Must enforce max_uses and max_uses_per_user
- **Single-Use Enforcement:** Must properly handle single-use coupons

## SARAISE-37009 Performance Targets

- Coupon validation: < 50ms
- Coupon application: < 100ms
- Get coupon by code: < 30ms
- Get coupon applications: < 200ms

## SARAISE-37010 Integration Points

- **Discounts:** Coupons can link to discounts (see `18-pricing.md`)
- **Subscriptions:** Coupons are applied to subscriptions
- **Billing:** Coupon amounts affect invoice calculations
- **Partners:** Partner-specific coupons (see `23-partner-management.md`)
- **Offers:** Coupons can be part of promotional offers (see `18-pricing.md`)

---


**Audit**: Version 7.0.0; Consolidated 2025-12-23
