---
description: Partner Management, Rate Limiting & User Quotas
globs: backend/src/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# Partner Management, Rate Limiting & User Quotas

**Rule IDs**: SARAISE-38001 to SARAISE-38010, SARAISE-39001 to SARAISE-39010, SARAISE-40001 to SARAISE-40010
**Consolidates**: `23-partner-management.md`, `23-resource-quotas.md`, `23-resource-quotas.md`

---
# SARAISE Partner Management

## SARAISE-38001 Partner Management Architecture Overview

**Purpose:** Manage partner and affiliate program relationships, including partner-specific discounts, commissions, and referrals.

**Key Principles:**
- Partners can refer tenants and earn commissions
- Partners can have custom discount codes
- Partners have tiered commission structures
- Partner referrals are tracked and audited
- Partner payouts are managed through billing system
- All partner operations are audited

## SARAISE-38002 Partner Models

### Database Schema

See [Partner Models](docs/architecture/examples/backend/models/partner-models.py).

**Key Models:**
- `Partner`: Partner information, commission configuration, payout settings
- `PartnerReferral`: Tracks tenant referrals to partners
- `PartnerCommission`: Commission records for partner referrals
- `PartnerPayout`: Payout records for partner commissions

## SARAISE-38003 Partner Service

### Implementation

See [Partner Service](docs/architecture/examples/backend/services/partner-service.py).

**Key Methods:**
- `create_partner()`: Create new partner with referral code generation
- `create_referral()`: Create partner referral for tenant
- `convert_referral()`: Convert referral to commission when tenant subscribes
- `create_payout()`: Create payout for commission period
- `process_payout()`: Process and complete payout

## SARAISE-38004 Partner API Routes

### Implementation

See [Partner Routes](docs/architecture/examples/backend/services/partner-routes.py).

**Key Endpoints:**
- `POST /partners`: Create partner (platform billing manager only)
- `POST /partners/referrals`: Create referral (tenant admin only)
- `GET /partners/stats/{partner_id}`: Get partner statistics (platform billing manager only)

## SARAISE-38005 Frontend Integration

### Partner Referral Component

See [Partner Referral Component](docs/architecture/examples/frontend/components/partners/PartnerReferral.tsx).

**Features:**
- Referral code input with validation
- Role-based access control (tenant admin only)
- Integration with React Query for state management

## SARAISE-38006 Testing Requirements

### Partner Service Tests

See [Partner Service Tests](docs/architecture/examples/backend/tests/partner-service-tests.py).

**Test Coverage:**
- Partner creation with referral code generation
- Referral creation and validation
- Referral conversion to commission
- Commission calculation accuracy

## SARAISE-38007 Audit Requirements

**REQUIRED:** All partner operations must be audited (see `11-audit-logging.md`)

- Partner creation/modification
- Referral creation
- Commission calculation
- Payout creation/processing

## SARAISE-38008 Security Requirements

- **Platform Billing Manager:** Can create/modify/delete partners
- **Tenant Admin:** Can create referrals for their tenant
- **Partner Access:** Partners can view their own statistics (future feature)
- **Referral Code Validation:** Must validate referral code before creating referral
- **Commission Calculation:** Must use partner's commission configuration
- **Payout Authorization:** Only platform billing manager can process payouts

## SARAISE-38009 Performance Targets

- Partner creation: < 100ms
- Referral creation: < 50ms
- Commission calculation: < 30ms
- Payout creation: < 200ms
- Get partner stats: < 100ms

## SARAISE-38010 Integration Points

- **Discounts:** Partners can have custom discount codes (see `18-pricing.md`)
- **Coupons:** Partner-specific coupons (see `18-pricing.md`)
- **Subscriptions:** Referrals convert when tenant subscribes
- **Billing:** Commissions are tracked and paid through billing system (see `22-billing-subscriptions.md`)
- **Tenants:** Referrals link tenants to partners

---
# SARAISE Rate Limiting

**Related Documentation:**
- API Gateway Integration: See Kong configuration in `docs/architecture/examples/infrastructure/` (Kong is optional edge gateway, not required for platform correctness)
- Subscription Plans: `docs/architecture/application-architecture.md`

## SARAISE-39001 Rate Limiting Architecture Overview

**Purpose:** Implement subscription-based API rate limiting to control API usage based on subscription tier.

**Key Principles:**
- Rate limits are based on subscription plan tier
- Rate limits apply per tenant, not per user
- Rate limits are enforced at API gateway level
- Rate limit information is included in API responses
- Rate limit violations are logged and audited
- Rate limits can be overridden for platform operations

## SARAISE-39002 Rate Limit Models

### Database Schema

See [Rate Limit Models](docs/architecture/examples/backend/models/rate-limit-models.py).

**Key Models:**
- `SubscriptionRateLimit`: Rate limit configuration per subscription plan and scope
- `RateLimitUsage`: Tracks rate limit usage per tenant and period
- `RateLimitViolation`: Logs rate limit violations with request details

## SARAISE-39003 Rate Limit Service

### Implementation

See [Rate Limit Service](docs/architecture/examples/backend/services/rate-limit-service.py).

**Key Methods:**
- `get_rate_limit()`: Get rate limit configuration for tenant's subscription
- `check_rate_limit()`: Check if request is within rate limit (uses Redis for fast tracking)
- `update_usage()`: Update rate limit usage record in database
- `log_violation()`: Log rate limit violations
- `get_usage_stats()`: Get usage statistics for analysis

## SARAISE-39004 Rate Limit Middleware

### Implementation

See [Rate Limit Middleware](docs/architecture/examples/backend/middleware/rate-limit-middleware.py).

**Features:**
- Enforces rate limits at middleware level
- Skips rate limiting for platform operations
- Adds rate limit headers to responses
- Returns 429 status when limit exceeded

## SARAISE-39005 Rate Limit API Routes

### Implementation

See [Rate Limit Routes](docs/architecture/examples/backend/services/rate-limit-routes.py).

**Key Endpoints:**
- `GET /rate-limits/usage`: Get rate limit usage statistics (tenant admin)
- `GET /rate-limits/violations`: Get rate limit violations (tenant admin)

## SARAISE-39006 Frontend Integration

### Rate Limit Display Component

See [Rate Limit Indicator Component](docs/architecture/examples/frontend/components/rate-limits/RateLimitIndicator.tsx).

**Features:**
- Displays rate limit usage from API response headers
- Visual progress indicator with warning/critical states
- Updates automatically based on API responses

## SARAISE-39007 Testing Requirements

### Rate Limit Service Tests

See [Rate Limit Service Tests](docs/architecture/examples/backend/tests/rate-limit-service-tests.py).

**Test Coverage:**
- Successful rate limit check
- Rate limit exceeded scenarios
- Redis-based tracking
- Usage statistics calculation

## SARAISE-39008 Audit Requirements

**REQUIRED:** All rate limit violations must be audited (see `11-audit-logging.md`)

- Rate limit violations are logged in `rate_limit_violations` table
- Violations include tenant, user, endpoint, and request details
- Violations can be queried for analysis and alerting

## SARAISE-39009 Security Requirements

- **Platform Operator:** Can view all rate limit usage and violations
- **Tenant Admin:** Can view their tenant's rate limit usage and violations
- **Rate Limit Enforcement:** Must be enforced at API gateway level
- **Override Protection:** Rate limit overrides require platform operator role
- **Violation Logging:** All violations must be logged with full context

## SARAISE-39010 Performance Targets

- Rate limit check: < 10ms (Redis lookup)
- Rate limit update: < 5ms (Redis increment)
- Get usage stats: < 200ms (database query)
- Get violations: < 100ms (database query)

## SARAISE-39011 Integration Points

- **Subscriptions:** Rate limits are based on subscription plan tier (see `22-billing.md`)
- **Tenants:** Rate limits are enforced per tenant
- **API Gateway:** Rate limits should be enforced at Kong gateway level (see `19-service-monitoring.md`)
- **Monitoring:** Rate limit violations should trigger alerts (see `19-service-monitoring.md`)
- **Billing:** Rate limit usage can affect billing calculations (see `22-billing-subscriptions.md`)

---
# SARAISE User Quotas

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Module Framework: `docs/architecture/module-framework.md`

## SARAISE-40001 User Quotas Architecture Overview

**Purpose:** Manage user limits based on subscription tier, enforcing subscription-based user quotas.

**Key Principles:**
- User quotas are based on subscription plan tier
- User quotas are enforced per tenant
- User quotas can be soft (warnings) or hard (blocks)
- User quota information is displayed to tenant admins
- User quota violations are logged and audited
- User quotas can be overridden for platform operations

## SARAISE-40002 User Quota Models

### Database Schema

See [User Quota Models](docs/architecture/examples/backend/models/user-quota-models.py).

**Key Models:**
- `SubscriptionQuota` - Quota configuration per subscription plan
- `TenantQuotaUsage` - Usage tracking per tenant
- `QuotaViolation` - Violation logging

## SARAISE-40003 User Quota Service

### Implementation

See [User Quota Service](docs/architecture/examples/backend/services/user-quota-service.py).

**Key Methods:**
- `get_quota()` - Get quota configuration for tenant's subscription
- `get_current_usage()` - Get current usage (explicit tenant_id filtering provides tenant isolation)
- `check_quota()` - Check if action is within quota limits
- `update_usage()` - Update quota usage record
- `log_violation()` - Log quota violations
- `get_quota_stats()` - Get quota usage statistics

## SARAISE-40004 User Quota API Routes

### Implementation

See [User Quota Routes](docs/architecture/examples/backend/services/user-quota-routes.py).

**Key Endpoints:**
- `GET /quotas/usage` - Get quota usage statistics (tenant admin)
- `GET /quotas/check/{quota_type}` - Check quota before action (tenant admin)
- `GET /quotas/violations` - Get quota violations (tenant admin)

## SARAISE-40005 Frontend Integration

### User Quota Display Component

See [Quota Display Component](docs/architecture/examples/frontend/components/quotas/QuotaDisplay.tsx).

**Key Features:**
- Display quota usage statistics with progress bars
- Warning indicators for high usage (>80%)
- Critical indicators for near-limit usage (>95%)
- Violation badges and warning notifications

## SARAISE-40006 Testing Requirements

### User Quota Service Tests

See [User Quota Service Tests](docs/architecture/examples/backend/tests/user-quota-service-tests.py) for complete test examples.

**Required Tests:**
- Quota check success (usage < limit)
- Quota check exceeded (usage >= limit)
- Soft vs hard enforcement
- Warning threshold validation
- Violation logging

## SARAISE-40007 Audit Requirements

**REQUIRED:** All quota violations must be audited (see `11-audit-logging.md`)

- Quota violations are logged in `quota_violations` table
- Violations include tenant, user, quota type, and attempted action
- Violations can be queried for analysis and alerting
