<!-- SPDX-License-Identifier: Apache-2.0 -->
# Billing & Subscriptions Module

**Module Code**: `billing`
**Category**: Foundation
**Priority**: Critical - Revenue Infrastructure
**Version**: 1.0.0
**Status**: Production Ready

---

## Executive Summary

The Billing & Subscriptions module is the **revenue engine** that powers SARAISE's entire monetization strategy. It provides comprehensive subscription lifecycle management, flexible pricing models, automated billing, payment processing, usage tracking, discounting systems, partner management, and rate limiting. This module ensures predictable revenue streams, reduces churn, and scales from startup to enterprise with world-class billing capabilities.

### Vision

**"Zero-friction monetization with intelligent pricing, automated collections, and predictive revenue optimization."**

Every successful SaaS business requires sophisticated billing infrastructure. SARAISE's Billing & Subscriptions module delivers Stripe-level sophistication with NetSuite-level flexibility, enabling complex pricing scenarios while maintaining simplicity for standard use cases. With AI-powered dunning management and predictive churn prevention, we maximize revenue and minimize friction.

---

## World-Class Features

### 1. Subscription Lifecycle Management
**Status**: Must-Have | **Competitive Parity**: Industry Leading

**Complete Lifecycle**:
```python
subscription_lifecycle = {
    "trial_management": {
        "trial_periods": [7, 14, 30, 60],  # Days
        "trial_conversion_tracking": True,
        "trial_extension_capability": True,
        "trial_credit_card_required": "configurable",
        "automatic_trial_end_notification": [7, 3, 1],  # Days before end
        "one_click_conversion": True
    },
    "subscription_creation": {
        "instant_provisioning": "< 30 seconds",
        "automated_onboarding": True,
        "module_activation": "automatic based on plan",
        "proration_handling": "automatic",
        "backdating_support": True,
        "future_dated_start": True
    },
    "subscription_changes": {
        "upgrade": "immediate activation",
        "downgrade": "at period end (configurable)",
        "plan_switching": "same-day processing",
        "proration_calculation": "to-the-second accuracy",
        "module_changes": "independent of plan changes",
        "user_seat_adjustment": "real-time"
    },
    "renewal_management": {
        "auto_renewal": True,
        "renewal_reminders": [30, 14, 7, 3, 1],  # Days before renewal
        "renewal_failure_handling": "intelligent dunning",
        "grace_period": "7 days (configurable)",
        "automatic_retry_schedule": [1, 3, 5, 7],  # Days
        "renewal_discount_offers": "at-risk customers"
    },
    "cancellation_handling": {
        "immediate_cancellation": "with refund option",
        "end_of_period_cancellation": "default",
        "cancellation_survey": True,
        "win_back_offers": "AI-powered",
        "data_retention_period": "90 days (configurable)",
        "reactivation_incentives": True
    },
    "suspension_management": {
        "payment_failure_suspension": "after grace period",
        "voluntary_pause": "1-3 months",
        "reduced_rate_during_pause": True,
        "automatic_reactivation": "on payment success",
        "data_preservation": "full data retained"
    }
}
```

**Advanced Features**:
- Subscription scheduling (start in future)
- Subscription pausing (vacation mode)
- Subscription gifting
- Multi-year prepaid subscriptions
- Perpetual licenses with support subscriptions
- Usage-based subscription tiers
- Hybrid fixed + variable pricing
- Contract renewals with renegotiation workflows

### 2. Flexible Pricing Engine
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Pricing Models**:
```python
pricing_models = {
    "flat_rate": {
        "description": "Fixed price per billing cycle",
        "example": "$99/month for unlimited access",
        "use_cases": ["Simple SaaS", "All-inclusive plans"],
        "proration": "time-based"
    },
    "per_user": {
        "description": "Price per active user seat",
        "example": "$15/user/month",
        "use_cases": ["Team collaboration tools", "CRM"],
        "proration": "user-day calculation",
        "user_counting": "active users only"
    },
    "tiered_pricing": {
        "description": "Price varies by usage tiers",
        "example": "0-10 users: $99, 11-50 users: $299, 51+ users: $599",
        "use_cases": ["Growing businesses", "Usage scaling"],
        "automatic_tier_movement": True,
        "tier_notification": True
    },
    "volume_pricing": {
        "description": "Per-unit price decreases with volume",
        "example": "First 1000 API calls: $0.01, Next 9000: $0.008, 10000+: $0.005",
        "use_cases": ["API platforms", "High-volume usage"],
        "graduated_tiers": True
    },
    "usage_based": {
        "description": "Pay only for what you use",
        "example": "$0.10 per API call, $0.50 per GB storage",
        "use_cases": ["Cloud infrastructure", "API services"],
        "metered_resources": ["api_calls", "storage_gb", "bandwidth_gb", "ai_tokens"],
        "billing_aggregation": "monthly",
        "overage_handling": "automatic billing"
    },
    "hybrid_pricing": {
        "description": "Base fee + usage charges",
        "example": "$50/month base + $0.05 per transaction",
        "use_cases": ["Payment processors", "Communication platforms"],
        "minimum_commitment": True,
        "included_quota": "configurable"
    },
    "feature_based": {
        "description": "Price varies by features enabled",
        "example": "Basic: $49 (Core), Pro: $149 (+Analytics), Enterprise: $499 (+AI)",
        "use_cases": ["Modular platforms", "Feature add-ons"],
        "feature_packages": True,
        "a_la_carte_features": True
    },
    "contract_pricing": {
        "description": "Custom negotiated pricing",
        "example": "$50,000/year for 200 users + premium support",
        "use_cases": ["Enterprise deals", "Custom contracts"],
        "commitment_period": "annual/multi-year",
        "minimum_spend": True,
        "volume_discounts": True
    }
}
```

**Pricing Flexibility**:
- Multiple currencies (150+ supported)
- Regional pricing (adjust by geography)
- Custom pricing per tenant (enterprise deals)
- Grandfathered pricing (legacy plans)
- Promotional pricing (limited time)
- Early adopter pricing
- Non-profit/education discounts
- Volume commitment discounts

### 3. Automated Billing Engine
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Billing Automation**:
```python
billing_automation = {
    "invoice_generation": {
        "schedule": "automatic based on billing cycle",
        "advance_generation": "7 days before due date",
        "invoice_numbering": "sequential, customizable format",
        "multi_currency_support": True,
        "tax_calculation": "automatic based on jurisdiction",
        "invoice_customization": "logo, colors, terms",
        "pdf_generation": "instant",
        "digital_signatures": "supported"
    },
    "invoice_delivery": {
        "email_delivery": "automatic on generation",
        "portal_access": "customer self-service portal",
        "api_access": "programmatic retrieval",
        "webhook_notification": True,
        "delivery_confirmation": True,
        "failed_delivery_alerts": True
    },
    "payment_collection": {
        "automatic_charging": "on due date",
        "saved_payment_methods": True,
        "payment_retry_logic": "intelligent dunning",
        "multiple_payment_methods": "credit card, ACH, wire, PayPal",
        "payment_plans": "split payments over time",
        "partial_payments": "supported",
        "overpayment_handling": "credit or refund"
    },
    "dunning_management": {
        "failed_payment_handling": "automatic retry",
        "retry_schedule": [1, 3, 5, 7, 14],  # Days
        "payment_method_updates": "email + in-app prompts",
        "grace_period_enforcement": True,
        "escalation_to_collections": "after 30 days",
        "account_suspension": "automatic after grace period",
        "ai_powered_optimization": "best retry timing"
    },
    "revenue_recognition": {
        "accrual_accounting": True,
        "deferred_revenue": "automatic calculation",
        "revenue_scheduling": "match subscription period",
        "prorated_revenue": "for mid-cycle changes",
        "revenue_reporting": "ASC 606 / IFRS 15 compliant",
        "audit_trail": "complete revenue lineage"
    }
}
```

**Billing Cycles**:
- Daily billing
- Weekly billing
- Monthly billing (most common)
- Quarterly billing
- Annual billing
- Custom billing (e.g., 45 days, 90 days)
- Anniversary billing (from signup date)
- Calendar-based billing (1st of month)

### 4. Payment Processing Integration
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Payment Gateways**:
```python
payment_gateways = {
    "stripe": {
        "status": "primary",
        "features": ["cards", "ach", "sepa", "ideal", "apple_pay", "google_pay"],
        "3d_secure": True,
        "sca_compliant": True,
        "instant_payouts": True,
        "dispute_management": True
    },
    "braintree": {
        "status": "supported",
        "features": ["cards", "paypal", "venmo"],
        "merchant_accounts": "multi-currency",
        "vault_storage": True
    },
    "authorize_net": {
        "status": "supported",
        "features": ["cards", "echeck"],
        "legacy_support": True
    },
    "paypal": {
        "status": "supported",
        "features": ["paypal_wallet", "paypal_credit"],
        "subscription_billing": True
    },
    "razorpay": {
        "status": "supported",
        "region": "India",
        "features": ["cards", "upi", "netbanking", "wallets"]
    },
    "custom_gateway": {
        "status": "enterprise",
        "integration": "API-based",
        "certification": "PCI-DSS required"
    }
}
```

**Payment Features**:
- Tokenized payment storage (PCI compliant)
- Multi-gateway support (fallback strategy)
- Smart routing (optimize transaction success)
- Currency conversion (real-time rates)
- Payment method validation
- Fraud detection (ML-powered)
- Chargeback management
- Refund processing (full/partial)
- Payment reconciliation
- Transaction reporting

### 5. Usage Tracking & Metering
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Metered Resources**:
```python
usage_tracking = {
    "api_calls": {
        "granularity": "per-request",
        "tracking_method": "middleware",
        "aggregation": "per tenant per day",
        "rate_limiting": "enforced",
        "overage_billing": "automatic",
        "analytics": "endpoint-level breakdown"
    },
    "storage": {
        "granularity": "per-GB",
        "tracking_method": "hourly snapshot",
        "aggregation": "average daily usage",
        "quota_enforcement": "hard limits",
        "overage_billing": "per GB over limit",
        "retention_tracking": True
    },
    "bandwidth": {
        "granularity": "per-MB",
        "tracking_method": "CDN integration",
        "aggregation": "monthly total",
        "included_quota": "plan-dependent",
        "overage_billing": "per GB over limit"
    },
    "compute_hours": {
        "granularity": "per-minute",
        "tracking_method": "container runtime",
        "aggregation": "monthly total hours",
        "pricing": "tiered by instance size",
        "spot_pricing": "dynamic optimization"
    },
    "ai_tokens": {
        "granularity": "per-token",
        "tracking_method": "LLM API wrapper",
        "aggregation": "per model per day",
        "pricing": "varies by model",
        "cost_breakdown": "by AI agent",
        "optimization_suggestions": True
    },
    "sms_sent": {
        "granularity": "per-message",
        "tracking_method": "SMS gateway",
        "aggregation": "monthly total",
        "pricing": "varies by country",
        "included_quota": "plan-dependent"
    },
    "email_sent": {
        "granularity": "per-email",
        "tracking_method": "SMTP wrapper",
        "aggregation": "monthly total",
        "included_quota": "generous",
        "overage_billing": "per 1000 emails"
    },
    "active_users": {
        "granularity": "daily active users",
        "tracking_method": "session tracking",
        "aggregation": "monthly average",
        "billing": "per active user",
        "deactivated_users": "not counted"
    }
}
```

**Usage Analytics**:
- Real-time usage dashboards
- Usage trend analysis
- Predictive usage forecasting
- Anomaly detection (unusual spikes)
- Cost optimization recommendations
- Usage-based alerts
- Quota utilization reporting
- Resource efficiency scoring

### 6. Discount & Promotion System
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Discount Types**:
```python
discount_system = {
    "percentage_discount": {
        "description": "X% off subscription price",
        "example": "25% off first 3 months",
        "use_cases": ["Seasonal promotions", "Trial conversions"],
        "max_discount": "configurable (e.g., 50%)",
        "stacking": "optional"
    },
    "fixed_amount_discount": {
        "description": "$X off subscription price",
        "example": "$20 off monthly plan",
        "use_cases": ["Referral bonuses", "Loyalty rewards"],
        "currency_handling": "multi-currency support",
        "minimum_amount": "discount cannot exceed price"
    },
    "free_trial_extension": {
        "description": "Extend trial period",
        "example": "Extra 14 days free",
        "use_cases": ["Re-engagement", "Sales negotiations"],
        "max_extension": "configurable"
    },
    "volume_discount": {
        "description": "Discount for buying in bulk",
        "example": "10% off for annual vs monthly",
        "use_cases": ["Annual commitments", "Enterprise deals"],
        "automatic_application": True
    },
    "bundle_discount": {
        "description": "Discount for multiple modules",
        "example": "Buy 3 modules, get 15% off",
        "use_cases": ["Cross-selling", "Suite packages"],
        "bundle_configurations": "flexible"
    },
    "loyalty_discount": {
        "description": "Reward long-term customers",
        "example": "5% off after 1 year, 10% after 2 years",
        "use_cases": ["Retention", "Customer appreciation"],
        "automatic_application": True,
        "lifetime_discount": True
    },
    "referral_discount": {
        "description": "Discount for referring customers",
        "example": "$50 credit per referral",
        "use_cases": ["Customer acquisition", "Word-of-mouth"],
        "bi_directional": "referrer + referred both get discount"
    },
    "early_bird_discount": {
        "description": "Discount for early adopters",
        "example": "50% off for first 100 customers",
        "use_cases": ["Product launches", "New markets"],
        "limited_quantity": True,
        "urgency_mechanism": True
    }
}
```

**Discount Management**:
- Discount code generation
- Usage limits (total uses, per-user uses)
- Time-bound validity
- Target audience (all, specific plans, specific tenants)
- Discount stacking rules
- Exclusion rules (cannot combine with X)
- Minimum purchase requirements
- Discount analytics (redemption rates, revenue impact)
- A/B testing for discount effectiveness

### 7. Coupon Management System
**Status**: Must-Have | **Competitive Advantage**: Industry Leading

**Coupon Engine**:
```python
coupon_system = {
    "coupon_types": {
        "discount_linked": {
            "description": "Linked to existing discount",
            "use_case": "Apply pre-configured discount",
            "flexibility": "inherit discount rules"
        },
        "standalone": {
            "description": "Independent discount definition",
            "use_case": "One-off promotional codes",
            "flexibility": "full customization"
        }
    },
    "usage_models": {
        "single_use": {
            "description": "One-time use globally",
            "example": "WELCOME50 (first 100 users)",
            "tracking": "usage count"
        },
        "multi_use": {
            "description": "Unlimited uses",
            "example": "SUMMERSALE (anyone can use)",
            "tracking": "total redemptions"
        },
        "single_use_per_user": {
            "description": "One use per customer",
            "example": "REFERRAL20 (each user once)",
            "tracking": "user-specific usage"
        }
    },
    "distribution_channels": {
        "public_codes": {
            "distribution": "Marketing campaigns, social media",
            "discoverability": "high",
            "abuse_prevention": "rate limiting"
        },
        "private_codes": {
            "distribution": "Direct emails, support tickets",
            "discoverability": "none",
            "personalization": "customer-specific"
        },
        "partner_codes": {
            "distribution": "Partner/affiliate programs",
            "tracking": "partner attribution",
            "commission_calculation": "automatic"
        }
    },
    "advanced_features": {
        "bulk_generation": "Generate 1000s of unique codes",
        "pattern_matching": "SUMMER-XXXX-YYYY format",
        "activation_delay": "Activate coupon in future",
        "geographic_restrictions": "Country/region targeting",
        "plan_eligibility": "Specific plans only",
        "new_customer_only": "First-time customers only",
        "upgrade_incentives": "Upgrade to higher plan only",
        "cart_abandonment": "Triggered coupons",
        "win_back": "Churned customer re-activation"
    }
}
```

**Coupon Analytics**:
- Redemption rate tracking
- Revenue impact analysis
- Customer acquisition cost per coupon
- Coupon abuse detection
- Most effective coupons ranking
- Coupon performance by channel
- Lifetime value of coupon users

### 8. Partner & Affiliate Management
**Status**: Should-Have | **Competitive Advantage**: Advanced

**Partner Program**:
```python
partner_program = {
    "partner_types": {
        "affiliate": {
            "description": "Earn commission on referrals",
            "commission_model": "percentage of first payment or recurring",
            "typical_rate": "10-30%",
            "tracking": "referral link/code",
            "payout": "monthly",
            "tools": ["referral dashboard", "marketing materials"]
        },
        "reseller": {
            "description": "Sell SARAISE to their customers",
            "commission_model": "wholesale pricing",
            "typical_discount": "30-50% off list price",
            "billing": "reseller invoiced by us, reseller bills customer",
            "white_label": "optional",
            "support": "tier 1 by reseller, tier 2 by us"
        },
        "integration_partner": {
            "description": "Build integrations with SARAISE",
            "commission_model": "revenue share on customers using integration",
            "typical_rate": "15-20%",
            "co_marketing": True,
            "technical_support": "dedicated partner engineer"
        },
        "strategic_partner": {
            "description": "Enterprise-level partnerships",
            "commission_model": "custom negotiated",
            "co_selling": True,
            "joint_products": True,
            "executive_alignment": True
        }
    },
    "commission_models": {
        "percentage": {
            "description": "X% of sale value",
            "application": "per transaction or recurring",
            "duration": "first payment only, first year, or lifetime",
            "calculation": "before or after discounts (configurable)"
        },
        "fixed_amount": {
            "description": "$X per referral",
            "application": "one-time payment",
            "triggers": ["signup", "first payment", "trial conversion"]
        },
        "tiered_commission": {
            "description": "Commission rate increases with volume",
            "example": "1-10 referrals: 15%, 11-50: 20%, 51+: 25%",
            "calculation": "monthly or lifetime referrals"
        }
    },
    "partner_portal": {
        "dashboard": "Real-time stats (referrals, conversions, earnings)",
        "referral_tracking": "Track each referral through lifecycle",
        "commission_reports": "Detailed earnings breakdown",
        "payout_history": "All past payouts",
        "marketing_assets": "Banners, copy, landing pages",
        "api_access": "Programmatic referral creation",
        "white_label_tools": "For resellers",
        "performance_insights": "Top-performing channels, content"
    },
    "payout_management": {
        "payout_frequency": ["monthly", "quarterly", "on_demand"],
        "minimum_payout": "$100 (configurable)",
        "payout_methods": ["bank_transfer", "paypal", "stripe", "check"],
        "payout_automation": "Scheduled automatic payouts",
        "tax_documentation": "W-9, 1099 generation",
        "multi_currency_payouts": True,
        "payout_holds": "For refund protection"
    }
}
```

**Partner Analytics**:
- Partner performance leaderboard
- Referral conversion rates
- Customer lifetime value by partner
- Most valuable partners
- Partner engagement scoring
- Commission projections
- Partner churn prediction

### 9. Rate Limiting & Quota Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Rate Limiting**:
```python
rate_limiting = {
    "api_rate_limits": {
        "scope": "per tenant, per user, per IP",
        "limits": {
            "free_plan": "100 requests/minute, 10,000/day",
            "basic_plan": "500 requests/minute, 50,000/day",
            "pro_plan": "2,000 requests/minute, 500,000/day",
            "enterprise_plan": "custom, unlimited options"
        },
        "burst_handling": "Allow short bursts above limit",
        "enforcement": "HTTP 429 + Retry-After header",
        "bypass": "Enterprise plans can request exemptions"
    },
    "workflow_rate_limits": {
        "scope": "per tenant",
        "limits": {
            "free_plan": "5 concurrent workflows",
            "basic_plan": "20 concurrent workflows",
            "pro_plan": "100 concurrent workflows",
            "enterprise_plan": "unlimited"
        },
        "queueing": "Workflows queued when limit reached",
        "priority_execution": "Enterprise gets priority queue"
    },
    "ai_agent_rate_limits": {
        "scope": "per tenant",
        "limits": {
            "free_plan": "1,000 AI tokens/day",
            "basic_plan": "50,000 AI tokens/day",
            "pro_plan": "500,000 AI tokens/day",
            "enterprise_plan": "custom limits"
        },
        "overage_handling": "Additional tokens purchased à la carte",
        "cost_tracking": "Per-agent cost attribution"
    },
    "storage_quotas": {
        "scope": "per tenant",
        "limits": {
            "free_plan": "1 GB",
            "basic_plan": "10 GB",
            "pro_plan": "100 GB",
            "enterprise_plan": "1 TB+ (configurable)"
        },
        "enforcement": "Soft limit + hard limit",
        "overage_handling": "Automatic billing for additional storage",
        "cleanup_suggestions": "AI-powered recommendations"
    },
    "user_quotas": {
        "scope": "per tenant",
        "limits": {
            "free_plan": "3 users",
            "basic_plan": "10 users",
            "pro_plan": "unlimited users (billed per user)",
            "enterprise_plan": "unlimited (flat fee or volume pricing)"
        },
        "enforcement": "Cannot add users beyond limit",
        "overage_handling": "Upgrade prompt or à la carte users"
    }
}
```

**Quota Features**:
- Real-time quota monitoring
- Quota utilization alerts (75%, 90%, 100%)
- Automatic quota reset (daily, monthly)
- Temporary quota increases (for campaigns)
- Quota pooling (enterprise groups)
- Grace period before hard enforcement
- Self-service quota upgrades

### 10. Revenue Analytics & Reporting
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Revenue Metrics**:
```python
revenue_analytics = {
    "core_metrics": {
        "mrr": "Monthly Recurring Revenue",
        "arr": "Annual Recurring Revenue",
        "new_mrr": "New customer MRR",
        "expansion_mrr": "Upgrade/upsell MRR",
        "contraction_mrr": "Downgrade MRR",
        "churned_mrr": "Cancelled customer MRR",
        "net_new_mrr": "New + Expansion - Contraction - Churned",
        "mrr_growth_rate": "Month-over-month MRR growth",
        "quick_ratio": "(New + Expansion) / (Contraction + Churned)"
    },
    "customer_metrics": {
        "arpu": "Average Revenue Per User",
        "arpa": "Average Revenue Per Account",
        "ltv": "Customer Lifetime Value",
        "cac": "Customer Acquisition Cost",
        "ltv_cac_ratio": "LTV / CAC (target: 3:1)",
        "payback_period": "Months to recover CAC",
        "gross_margin": "Revenue - COGS",
        "revenue_per_employee": "Total revenue / employee count"
    },
    "subscription_metrics": {
        "subscription_count": "Total active subscriptions",
        "trial_to_paid_conversion": "% of trials that convert",
        "churn_rate": "% of customers cancelling monthly",
        "retention_rate": "100% - churn rate",
        "logo_churn": "% of customers lost (count)",
        "revenue_churn": "% of revenue lost (dollars)",
        "upgrade_rate": "% of customers upgrading monthly",
        "downgrade_rate": "% of customers downgrading monthly"
    },
    "payment_metrics": {
        "payment_success_rate": "% of payments processed successfully",
        "dunning_recovery_rate": "% of failed payments recovered",
        "refund_rate": "% of revenue refunded",
        "chargeback_rate": "% of revenue charged back",
        "payment_processing_cost": "% of revenue lost to fees",
        "days_sales_outstanding": "Average days to collect payment"
    },
    "discount_metrics": {
        "discount_penetration": "% of customers using discounts",
        "average_discount": "Average % discount given",
        "discount_impact_on_ltv": "LTV of discounted vs non-discounted",
        "coupon_redemption_rate": "% of coupons redeemed",
        "discount_revenue_impact": "Total revenue lost to discounts"
    }
}
```

**Revenue Reports**:
- MRR Movement Report (waterfall chart)
- Cohort Revenue Analysis
- Revenue by Plan
- Revenue by Module
- Revenue by Geography
- Revenue Forecast (AI-powered)
- Churn Analysis Report
- Expansion Revenue Report
- Partner Revenue Attribution
- Payment Failure Analysis

---

## Technical Architecture

### Database Schema

```sql
-- Subscription Plans
CREATE TABLE subscription_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Plan Details
    name VARCHAR(255) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    tier VARCHAR(50) NOT NULL,  -- free, starter, professional, enterprise, custom

    -- Pricing
    price NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    billing_cycle_days INTEGER DEFAULT 30,  -- 30 monthly, 365 annual, etc.
    setup_fee NUMERIC(10, 2) DEFAULT 0,

    -- Quotas & Limits
    max_users INTEGER,
    max_storage_gb INTEGER,
    max_api_calls_per_month INTEGER,
    modules_included TEXT[],  -- Array of module codes
    features JSONB,  -- Detailed feature flags

    -- Plan Management
    is_active BOOLEAN DEFAULT true,
    is_public BOOLEAN DEFAULT true,  -- Public on pricing page?
    is_legacy BOOLEAN DEFAULT false,  -- Grandfathered plan?
    available_for_trial BOOLEAN DEFAULT true,
    trial_days INTEGER DEFAULT 14,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_plan_tier (tier),
    INDEX idx_plan_active (is_active),
    INDEX idx_plan_public (is_public)
);

-- Subscriptions
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES subscription_plans(id),
    previous_subscription_id UUID REFERENCES subscriptions(id),  -- For upgrades/downgrades

    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'active',  -- trial, active, past_due, suspended, cancelled, expired

    -- Dates
    start_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_date TIMESTAMPTZ,  -- NULL for ongoing
    trial_start_date TIMESTAMPTZ,
    trial_end_date TIMESTAMPTZ,
    current_period_start TIMESTAMPTZ NOT NULL,
    current_period_end TIMESTAMPTZ NOT NULL,

    -- Cancellation
    cancel_at_period_end BOOLEAN DEFAULT false,
    cancelled_at TIMESTAMPTZ,
    cancellation_reason TEXT,
    cancellation_feedback JSONB,

    -- Pricing Overrides (for custom deals)
    custom_price NUMERIC(10, 2),  -- Override plan price
    custom_billing_cycle_days INTEGER,
    discount_id UUID REFERENCES discounts(id),

    -- Metadata
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_sub_tenant (tenant_id),
    INDEX idx_sub_plan (plan_id),
    INDEX idx_sub_status (status),
    INDEX idx_sub_period (current_period_start, current_period_end),
    INDEX idx_sub_trial_end (trial_end_date) WHERE trial_end_date IS NOT NULL
);

-- Subscription Invoices
CREATE TABLE subscription_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    subscription_id UUID NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Invoice Details
    invoice_number VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',  -- draft, pending, paid, overdue, void, uncollectible

    -- Amounts
    subtotal NUMERIC(10, 2) NOT NULL,
    discount_amount NUMERIC(10, 2) DEFAULT 0,
    tax_amount NUMERIC(10, 2) DEFAULT 0,
    total_amount NUMERIC(10, 2) NOT NULL,
    amount_due NUMERIC(10, 2) NOT NULL,  -- Can differ from total if partially paid
    amount_paid NUMERIC(10, 2) DEFAULT 0,
    currency VARCHAR(3) DEFAULT 'USD',

    -- Line Items
    line_items JSONB NOT NULL,  -- [{description, quantity, unit_price, amount}, ...]

    -- Dates
    invoice_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE NOT NULL,
    paid_date TIMESTAMPTZ,
    period_start DATE,
    period_end DATE,

    -- Payment
    payment_method_id VARCHAR(255),  -- Stripe/payment gateway ID
    payment_intent_id VARCHAR(255),

    -- Taxes
    tax_rate NUMERIC(5, 2),
    tax_jurisdiction VARCHAR(255),

    -- Collection
    attempt_count INTEGER DEFAULT 0,
    next_payment_attempt TIMESTAMPTZ,

    -- PDF
    pdf_url TEXT,

    -- Metadata
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_invoice_sub (subscription_id),
    INDEX idx_invoice_tenant (tenant_id),
    INDEX idx_invoice_status (status),
    INDEX idx_invoice_due_date (due_date),
    INDEX idx_invoice_number (invoice_number),
    UNIQUE INDEX idx_invoice_unique_number (invoice_number)
);

-- Subscription Payments
CREATE TABLE subscription_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    invoice_id UUID NOT NULL REFERENCES subscription_invoices(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id),

    -- Payment Details
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, processing, succeeded, failed, refunded, cancelled

    -- Payment Method
    payment_method_type VARCHAR(50),  -- card, ach, wire, paypal, manual
    payment_method_id VARCHAR(255),  -- Payment gateway method ID

    -- Gateway Details
    payment_gateway VARCHAR(50),  -- stripe, braintree, authorize_net
    transaction_id VARCHAR(255),  -- Gateway transaction ID
    gateway_response JSONB,

    -- Failure Details
    failure_code VARCHAR(100),
    failure_message TEXT,

    -- Dates
    initiated_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,

    -- Refund
    refunded_amount NUMERIC(10, 2) DEFAULT 0,
    refunded_at TIMESTAMPTZ,
    refund_reason TEXT,

    -- Metadata
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_payment_invoice (invoice_id),
    INDEX idx_payment_tenant (tenant_id),
    INDEX idx_payment_status (status),
    INDEX idx_payment_gateway (payment_gateway, transaction_id)
);

-- Usage Records
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Usage Details
    resource VARCHAR(100) NOT NULL,  -- api_calls, storage_gb, bandwidth_gb, ai_tokens, sms_sent
    quantity NUMERIC(15, 4) NOT NULL DEFAULT 1,
    unit VARCHAR(50),  -- requests, GB, tokens, messages

    -- Context
    metadata JSONB,  -- {endpoint, method, duration_ms, model, etc.}

    -- Timestamp
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Billing
    billed BOOLEAN DEFAULT false,
    billed_in_invoice_id UUID REFERENCES subscription_invoices(id),
    unit_price NUMERIC(10, 6),  -- Price per unit at time of usage
    total_cost NUMERIC(10, 2),  -- quantity * unit_price

    INDEX idx_usage_tenant (tenant_id, timestamp DESC),
    INDEX idx_usage_resource (resource, timestamp DESC),
    INDEX idx_usage_billed (billed, timestamp DESC) WHERE NOT billed,
    INDEX idx_usage_timestamp (timestamp DESC)
);

-- Optimize for time-series queries
SELECT create_hypertable('usage_records', 'timestamp', chunk_time_interval => INTERVAL '1 day');

-- Discounts
CREATE TABLE discounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Discount Details
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE,  -- Optional: For direct application by code
    description TEXT,

    -- Type
    discount_type VARCHAR(50) NOT NULL,  -- percentage, fixed_amount, free_trial, free_months
    discount_value NUMERIC(10, 2) NOT NULL,  -- Percentage (0-100) or dollar amount

    -- Scope
    scope VARCHAR(50) NOT NULL,  -- subscription_plan, addon, all
    target_plan_ids UUID[],  -- Specific plans eligible for discount

    -- Eligibility
    new_customers_only BOOLEAN DEFAULT false,
    existing_customers_only BOOLEAN DEFAULT false,
    eligible_tenant_ids UUID[],  -- Specific tenants (enterprise deals)
    min_subscription_value NUMERIC(10, 2),
    min_commitment_months INTEGER,

    -- Validity
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ,

    -- Usage Limits
    max_uses INTEGER,  -- Total times discount can be applied (NULL = unlimited)
    max_uses_per_tenant INTEGER,  -- Per-tenant limit
    current_uses INTEGER DEFAULT 0,

    -- Stacking Rules
    can_stack BOOLEAN DEFAULT false,
    mutually_exclusive_discount_ids UUID[],

    -- Status
    status VARCHAR(50) DEFAULT 'active',  -- active, inactive, expired, archived
    is_public BOOLEAN DEFAULT false,  -- Show on pricing page?

    -- Metadata
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_discount_code (code) WHERE code IS NOT NULL,
    INDEX idx_discount_status (status),
    INDEX idx_discount_valid (valid_from, valid_until),
    INDEX idx_discount_public (is_public)
);

-- Discount Applications
CREATE TABLE discount_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    discount_id UUID NOT NULL REFERENCES discounts(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
    invoice_id UUID REFERENCES subscription_invoices(id) ON DELETE SET NULL,

    -- Application Details
    original_amount NUMERIC(10, 2) NOT NULL,
    discount_amount NUMERIC(10, 2) NOT NULL,
    final_amount NUMERIC(10, 2) NOT NULL,

    -- Metadata
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    applied_by UUID REFERENCES users(id),

    INDEX idx_discount_app_discount (discount_id),
    INDEX idx_discount_app_tenant (tenant_id),
    INDEX idx_discount_app_applied (applied_at DESC)
);

-- Coupons
CREATE TABLE coupons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Coupon Details
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Type
    coupon_type VARCHAR(50) NOT NULL,  -- discount_linked, standalone
    discount_id UUID REFERENCES discounts(id),  -- For discount_linked type

    -- Standalone Discount (if coupon_type = standalone)
    standalone_discount_type VARCHAR(50),  -- percentage, fixed_amount
    standalone_discount_value NUMERIC(10, 2),

    -- Scope
    scope VARCHAR(50),  -- subscription_plan, addon, all
    eligible_plan_ids UUID[],
    eligible_tenant_ids UUID[],

    -- Validity
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ,

    -- Usage
    usage_type VARCHAR(50) NOT NULL DEFAULT 'multi_use',  -- single_use, multi_use, single_use_per_user
    max_uses INTEGER,
    max_uses_per_user INTEGER,
    current_uses INTEGER DEFAULT 0,

    -- Status
    status VARCHAR(50) DEFAULT 'active',  -- active, inactive, expired, archived
    is_public BOOLEAN DEFAULT false,

    -- Metadata
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_coupon_code (code),
    INDEX idx_coupon_status (status),
    INDEX idx_coupon_valid (valid_from, valid_until),
    UNIQUE INDEX idx_coupon_unique_code (code)
);

-- Coupon Applications
CREATE TABLE coupon_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    coupon_id UUID NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
    invoice_id UUID REFERENCES subscription_invoices(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id),

    -- Application Details
    coupon_code VARCHAR(50) NOT NULL,
    original_amount NUMERIC(10, 2) NOT NULL,
    discount_amount NUMERIC(10, 2) NOT NULL,
    final_amount NUMERIC(10, 2) NOT NULL,

    -- Metadata
    applied_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_coupon_app_coupon (coupon_id),
    INDEX idx_coupon_app_tenant (tenant_id),
    INDEX idx_coupon_app_user (user_id),
    INDEX idx_coupon_app_applied (applied_at DESC)
);

-- Partners
CREATE TABLE partners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Partner Details
    name VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(50),
    website VARCHAR(500),

    -- Partner Type
    partner_type VARCHAR(50) NOT NULL,  -- affiliate, reseller, integration, strategic
    status VARCHAR(50) DEFAULT 'active',  -- active, inactive, suspended, archived

    -- Referral Tracking
    referral_code VARCHAR(50) NOT NULL UNIQUE,
    custom_discount_code VARCHAR(50) UNIQUE,  -- Optional: Partner-specific discount

    -- Commission Structure
    commission_type VARCHAR(50) NOT NULL,  -- percentage, fixed_amount, tiered
    commission_rate NUMERIC(10, 4) NOT NULL,  -- e.g., 0.2000 = 20%
    tiered_commission_config JSONB,  -- For tiered commission

    -- Payout Settings
    payout_frequency VARCHAR(50) DEFAULT 'monthly',  -- monthly, quarterly, on_demand
    minimum_payout NUMERIC(10, 2) DEFAULT 100.00,
    payout_method VARCHAR(50) DEFAULT 'bank_transfer',  -- bank_transfer, paypal, stripe, check
    payout_details JSONB,  -- Bank info, PayPal email, etc.

    -- Statistics
    total_referrals INTEGER DEFAULT 0,
    active_referrals INTEGER DEFAULT 0,
    total_commission_earned NUMERIC(10, 2) DEFAULT 0,
    total_commission_paid NUMERIC(10, 2) DEFAULT 0,
    total_commission_pending NUMERIC(10, 2) DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_partner_referral_code (referral_code),
    INDEX idx_partner_status (status),
    INDEX idx_partner_type (partner_type),
    UNIQUE INDEX idx_partner_unique_referral (referral_code)
);

-- Partner Referrals
CREATE TABLE partner_referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Referral Details
    referral_code VARCHAR(50) NOT NULL,
    referral_date TIMESTAMPTZ DEFAULT NOW(),

    -- Conversion
    converted BOOLEAN DEFAULT false,
    conversion_date TIMESTAMPTZ,
    conversion_value NUMERIC(10, 2),
    first_invoice_id UUID REFERENCES subscription_invoices(id),

    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, converted, active, churned
    is_active BOOLEAN DEFAULT true,

    -- Metadata
    referral_source VARCHAR(255),  -- utm_source or other tracking
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_referral_partner (partner_id),
    INDEX idx_referral_tenant (tenant_id),
    INDEX idx_referral_code (referral_code),
    INDEX idx_referral_status (status),
    UNIQUE INDEX idx_referral_unique_tenant (tenant_id)  -- One referral per tenant
);

-- Partner Commissions
CREATE TABLE partner_commissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    referral_id UUID REFERENCES partner_referrals(id) ON DELETE SET NULL,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
    invoice_id UUID REFERENCES subscription_invoices(id) ON DELETE SET NULL,

    -- Commission Details
    commission_type VARCHAR(50) NOT NULL,
    commission_rate NUMERIC(10, 4) NOT NULL,
    base_amount NUMERIC(10, 2) NOT NULL,  -- Amount commission calculated on
    commission_amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',

    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, approved, paid, cancelled

    -- Dates
    earned_date TIMESTAMPTZ DEFAULT NOW(),
    approved_date TIMESTAMPTZ,
    paid_date TIMESTAMPTZ,

    -- Payout
    payout_id UUID REFERENCES partner_payouts(id),

    -- Metadata
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_commission_partner (partner_id),
    INDEX idx_commission_referral (referral_id),
    INDEX idx_commission_status (status),
    INDEX idx_commission_payout (payout_id),
    INDEX idx_commission_earned (earned_date DESC)
);

-- Partner Payouts
CREATE TABLE partner_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationship
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,

    -- Payout Details
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    payout_method VARCHAR(50) NOT NULL,
    payout_details JSONB,  -- Destination account info

    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed, cancelled

    -- Dates
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    requested_date TIMESTAMPTZ DEFAULT NOW(),
    processed_date TIMESTAMPTZ,
    completed_date TIMESTAMPTZ,

    -- Transaction
    transaction_id VARCHAR(255),
    gateway_response JSONB,

    -- Failure
    failure_reason TEXT,

    -- Metadata
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_payout_partner (partner_id),
    INDEX idx_payout_status (status),
    INDEX idx_payout_period (period_start, period_end)
);

-- Subscription Rate Limits
CREATE TABLE subscription_rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationship
    subscription_plan_id UUID NOT NULL REFERENCES subscription_plans(id) ON DELETE CASCADE,

    -- Rate Limit Details
    scope VARCHAR(50) NOT NULL,  -- api, workflow, agent, data_export, file_upload
    limit INTEGER NOT NULL,  -- Numeric limit
    period VARCHAR(50) NOT NULL,  -- second, minute, hour, day, month
    burst_limit INTEGER,  -- Allow short bursts

    -- Override Settings
    can_override BOOLEAN DEFAULT false,
    override_reason_required BOOLEAN DEFAULT true,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_rate_limit_plan (subscription_plan_id),
    INDEX idx_rate_limit_scope (scope),
    UNIQUE INDEX idx_rate_limit_unique (subscription_plan_id, scope)
);

-- Rate Limit Usage
CREATE TABLE rate_limit_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,

    -- Usage Details
    scope VARCHAR(50) NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,

    -- Counters
    request_count INTEGER DEFAULT 0,
    limit INTEGER NOT NULL,
    violations INTEGER DEFAULT 0,
    last_violation_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_rate_usage_tenant (tenant_id, scope, period_start DESC),
    INDEX idx_rate_usage_period (period_start, period_end),
    UNIQUE INDEX idx_rate_usage_unique (tenant_id, scope, period_start)
);

-- Rate Limit Violations
CREATE TABLE rate_limit_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Violation Details
    scope VARCHAR(50) NOT NULL,
    endpoint VARCHAR(500),  -- For API violations
    request_method VARCHAR(10),
    limit INTEGER NOT NULL,
    current_count INTEGER NOT NULL,

    -- Context
    ip_address INET,
    user_agent TEXT,
    metadata JSONB,

    -- Resolution
    is_resolved BOOLEAN DEFAULT false,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,

    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_violation_tenant (tenant_id, created_at DESC),
    INDEX idx_violation_scope (scope, created_at DESC),
    INDEX idx_violation_resolved (is_resolved, created_at DESC)
);

-- Revenue Analytics (Aggregated)
CREATE TABLE revenue_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Time Period
    period_type VARCHAR(50) NOT NULL,  -- daily, weekly, monthly, quarterly, yearly
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- MRR Metrics
    mrr NUMERIC(12, 2),
    new_mrr NUMERIC(12, 2),
    expansion_mrr NUMERIC(12, 2),
    contraction_mrr NUMERIC(12, 2),
    churned_mrr NUMERIC(12, 2),
    net_new_mrr NUMERIC(12, 2),

    -- Customer Metrics
    total_customers INTEGER,
    new_customers INTEGER,
    churned_customers INTEGER,
    net_new_customers INTEGER,

    -- Subscription Metrics
    total_subscriptions INTEGER,
    trial_subscriptions INTEGER,
    active_subscriptions INTEGER,
    cancelled_subscriptions INTEGER,

    -- Payment Metrics
    total_invoiced NUMERIC(12, 2),
    total_collected NUMERIC(12, 2),
    total_refunded NUMERIC(12, 2),
    payment_success_rate NUMERIC(5, 2),

    -- Breakdown
    mrr_by_plan JSONB,  -- {plan_id: mrr_amount}
    revenue_by_region JSONB,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_revenue_period (period_type, period_start DESC),
    UNIQUE INDEX idx_revenue_unique_period (period_type, period_start, period_end)
);
```

---

## API Endpoints

### Subscription Management

```
POST   /api/v1/subscriptions                      # Create subscription (signup)
GET    /api/v1/subscriptions/:id                  # Get subscription details
PUT    /api/v1/subscriptions/:id                  # Update subscription
DELETE /api/v1/subscriptions/:id                  # Cancel subscription
POST   /api/v1/subscriptions/:id/upgrade          # Upgrade plan
POST   /api/v1/subscriptions/:id/downgrade        # Downgrade plan
POST   /api/v1/subscriptions/:id/pause            # Pause subscription
POST   /api/v1/subscriptions/:id/resume           # Resume subscription
POST   /api/v1/subscriptions/:id/reactivate       # Reactivate cancelled subscription
GET    /api/v1/subscriptions/:id/usage            # Get usage stats
GET    /api/v1/subscriptions/:id/invoices         # List invoices
GET    /api/v1/subscriptions/:id/payments         # List payments
```

### Subscription Plans

```
GET    /api/v1/subscription-plans                 # List all plans
GET    /api/v1/subscription-plans/:id             # Get plan details
POST   /api/v1/subscription-plans                 # Create plan (admin)
PUT    /api/v1/subscription-plans/:id             # Update plan (admin)
DELETE /api/v1/subscription-plans/:id             # Archive plan (admin)
GET    /api/v1/subscription-plans/public          # Public pricing page plans
GET    /api/v1/subscription-plans/compare         # Compare plans
```

### Invoices

```
GET    /api/v1/invoices                           # List invoices
GET    /api/v1/invoices/:id                       # Get invoice details
GET    /api/v1/invoices/:id/pdf                   # Download PDF
POST   /api/v1/invoices/:id/pay                   # Pay invoice manually
POST   /api/v1/invoices/:id/void                  # Void invoice (admin)
POST   /api/v1/invoices/:id/send                  # Resend invoice email
GET    /api/v1/invoices/upcoming                  # Preview next invoice
```

### Payments

```
GET    /api/v1/payments                           # List payments
GET    /api/v1/payments/:id                       # Get payment details
POST   /api/v1/payments                           # Create manual payment
POST   /api/v1/payments/:id/refund                # Refund payment
GET    /api/v1/payment-methods                    # List saved payment methods
POST   /api/v1/payment-methods                    # Add payment method
PUT    /api/v1/payment-methods/:id                # Update payment method
DELETE /api/v1/payment-methods/:id                # Remove payment method
POST   /api/v1/payment-methods/:id/set-default    # Set default payment method
```

### Usage Tracking

```
POST   /api/v1/usage                              # Record usage (internal)
GET    /api/v1/usage                              # Get usage records
GET    /api/v1/usage/summary                      # Usage summary
GET    /api/v1/usage/by-resource                  # Usage by resource type
GET    /api/v1/usage/forecast                     # Forecast future usage (AI)
GET    /api/v1/usage/export                       # Export usage data
```

### Discounts

```
GET    /api/v1/discounts                          # List discounts (admin)
GET    /api/v1/discounts/:id                      # Get discount details
POST   /api/v1/discounts                          # Create discount (admin)
PUT    /api/v1/discounts/:id                      # Update discount (admin)
DELETE /api/v1/discounts/:id                      # Archive discount (admin)
POST   /api/v1/discounts/:id/apply                # Apply discount to subscription
GET    /api/v1/discounts/analytics                # Discount performance analytics
```

### Coupons

```
GET    /api/v1/coupons                            # List coupons (admin)
GET    /api/v1/coupons/:code                      # Get coupon by code
POST   /api/v1/coupons                            # Create coupon (admin)
PUT    /api/v1/coupons/:id                        # Update coupon (admin)
DELETE /api/v1/coupons/:id                        # Archive coupon (admin)
POST   /api/v1/coupons/validate                   # Validate coupon code
POST   /api/v1/coupons/apply                      # Apply coupon to subscription
POST   /api/v1/coupons/bulk-generate              # Generate bulk coupons (admin)
GET    /api/v1/coupons/:id/analytics              # Coupon usage analytics
```

### Partners

```
GET    /api/v1/partners                           # List partners (admin)
GET    /api/v1/partners/:id                       # Get partner details
POST   /api/v1/partners                           # Create partner (admin)
PUT    /api/v1/partners/:id                       # Update partner
DELETE /api/v1/partners/:id                       # Archive partner (admin)
GET    /api/v1/partners/:id/dashboard             # Partner dashboard
GET    /api/v1/partners/:id/referrals             # Partner referrals
GET    /api/v1/partners/:id/commissions           # Partner commissions
GET    /api/v1/partners/:id/payouts               # Partner payouts
POST   /api/v1/partners/:id/request-payout        # Request payout
GET    /api/v1/partners/leaderboard               # Top partners (admin)
```

### Rate Limiting

```
GET    /api/v1/rate-limits                        # Get rate limits for tenant
GET    /api/v1/rate-limits/usage                  # Current usage vs limits
GET    /api/v1/rate-limits/violations             # Rate limit violations
POST   /api/v1/rate-limits/request-increase       # Request limit increase
```

### Revenue Analytics

```
GET    /api/v1/analytics/revenue/mrr              # MRR dashboard
GET    /api/v1/analytics/revenue/arr              # ARR dashboard
GET    /api/v1/analytics/revenue/churn            # Churn analysis
GET    /api/v1/analytics/revenue/cohorts          # Cohort analysis
GET    /api/v1/analytics/revenue/forecast         # Revenue forecast (AI)
GET    /api/v1/analytics/revenue/by-plan          # Revenue by plan
GET    /api/v1/analytics/revenue/by-region        # Revenue by region
GET    /api/v1/analytics/subscriptions            # Subscription metrics
GET    /api/v1/analytics/payments                 # Payment metrics
GET    /api/v1/analytics/discounts                # Discount effectiveness
GET    /api/v1/analytics/partners                 # Partner performance
```

---

## AI Agent Integration

### Revenue Optimization AI Agent

```python
revenue_ai_agent = {
    "name": "Revenue Optimization Agent",
    "agent_type": "crewai",
    "model": "gpt-4",
    "capabilities": [
        "Churn prediction (14-day advance warning)",
        "Upsell opportunity identification",
        "Pricing optimization recommendations",
        "Discount effectiveness analysis",
        "Win-back campaign automation",
        "Payment failure recovery optimization",
        "Revenue forecasting (3-12 months)",
        "Customer lifetime value prediction"
    ],
    "triggers": [
        "Daily (churn prediction)",
        "Weekly (pricing analysis)",
        "Payment failure",
        "Usage spike (upsell opportunity)",
        "Trial ending (conversion optimization)",
        "Cancellation request (win-back offer)"
    ],
    "actions": [
        "Send retention offers to at-risk customers",
        "Trigger win-back email campaigns",
        "Recommend plan upgrades with justification",
        "Create custom discount codes",
        "Alert sales team of enterprise opportunities",
        "Optimize dunning retry timing",
        "Generate revenue forecast reports"
    ]
}
```

**Example Scenarios**:

**Churn Prediction**:
```
Agent detects: Customer "Acme Corp" has 87% churn probability in next 14 days
Signals: Usage down 60%, no login in 7 days, support tickets unresolved
Action:
  - Alert CSM team
  - Trigger personalized email: "We noticed you're not using X feature..."
  - Offer: 25% discount for 3 months + dedicated onboarding call
```

**Upsell Opportunity**:
```
Agent detects: Customer "TechStart" consistently hitting 95% of API quota
Signals: High usage, no complaints, growing fast
Action:
  - Alert sales team
  - In-app notification: "You're close to API limits. Upgrade to Pro for 10x quota?"
  - Offer: Free 30-day trial of Pro plan features
```

**Payment Recovery**:
```
Agent detects: Payment failed for "Retail Co" ($299/month)
Analysis:
  - Customer LTV: $10,000
  - Payment failure likely due to expired card
  - Best retry time: 3 days (based on ML model)
Action:
  - Immediate email: "Update payment method"
  - Retry payment in 3 days at 2 PM (optimal time)
  - If fails again, offer payment plan: $150 x 2 months
```

### Billing Support AI Agent

```python
billing_support_agent = {
    "name": "Billing Support Agent",
    "agent_type": "langgraph",
    "model": "gpt-4",
    "capabilities": [
        "Answer billing questions",
        "Explain invoice line items",
        "Help with payment method updates",
        "Process refund requests (within policy)",
        "Generate custom invoices",
        "Explain pricing changes",
        "Handle billing disputes",
        "Provide usage breakdowns"
    ],
    "autonomous_actions": [
        "Issue refunds < $50 (within 30-day policy)",
        "Apply goodwill credits < $100",
        "Extend payment due dates (< 7 days)",
        "Send duplicate invoices",
        "Update billing contact info"
    ],
    "escalation_triggers": [
        "Refund > $50",
        "Billing dispute > $500",
        "Requests outside policy",
        "Legal/compliance questions"
    ]
}
```

---

## Customization Framework Integration

The Billing & Subscriptions module supports extensive customization through the SARAISE Customization Framework, enabling tenant-specific customizations without modifying core code.

### Customization Points

The module exposes the following customization points:

#### Subscription Resource
- **Server Scripts**:
  - `before_save`: Execute custom logic before saving subscriptions (e.g., validation, pricing overrides)
  - `after_update`: Execute custom logic after subscription changes (e.g., sync with external systems)
- **Custom Reports**: Create subscription analytics and revenue reports
- **Custom Forms**: Customize subscription form layouts per tenant

#### SubscriptionInvoice Resource
- **Server Scripts**:
  - `before_invoice_generate`: Execute custom logic before invoice generation (e.g., custom line items, discounts)
  - `after_payment_success`: Execute custom logic after successful payment (e.g., custom notifications, workflows)
- **Custom Reports**: Create invoice analytics and payment reports
- **Custom Forms**: Customize invoice form display and PDF templates

#### Discount Resource
- **Server Scripts**:
  - `on_discount_apply`: Execute custom logic when discounts are applied (e.g., custom validation, tracking)
- **Custom Reports**: Create discount effectiveness and ROI reports
- **Custom Forms**: Customize discount form layouts

#### Coupon Resource
- **Server Scripts**:
  - `on_coupon_redeem`: Execute custom logic when coupons are redeemed (e.g., custom tracking, notifications)
- **Custom Reports**: Create coupon redemption analytics
- **Custom Forms**: Customize coupon form displays

### Demo Customizations

The demo tenant (`demo@saraise.com`) includes example server scripts demonstrating:
- Invoice generation with custom line items
- Payment success workflows
- Discount application validation
- Coupon redemption tracking

These can be found in the demo data seeder and serve as templates for tenant-specific customizations.

### AI-Powered Code Generation

The Customization Automation Agent can generate server scripts, custom reports, and forms for Billing & Subscriptions based on natural language specifications. For example:

```
"Create a server script that applies a 10% loyalty discount to invoices for customers with more than 12 months of subscription"
```

The agent will generate the appropriate Python server script with subscription history checks and discount application logic.

---

## Workflow Automation

The Billing & Subscriptions module includes automated workflows for subscription and billing operations.

### Subscription Renewal Workflow

**Description**: Automated subscription renewal workflow

**Workflow Steps**:
1. **Data Ingestion**: Collect subscription data and renewal date
2. **Validation**: Validate subscription is active and payment method exists
3. **Payment Processing**: Charge subscription renewal amount
4. **Notification**: Send renewal confirmation email
5. **Data Output**: Update subscription with new period dates

**Implementation**:
- Service: `AutoRenewalService`, `SubscriptionLifecycleService`
- Automation: `BillingAutomationService`
- Scheduled: Runs daily to process renewals due within 7 days

**Use Cases**:
- Automated subscription renewals
- Payment processing and retry logic
- Renewal confirmation and notifications

### Invoice Generation Workflow

**Description**: Automated invoice generation workflow

**Workflow Steps**:
1. **Data Ingestion**: Collect subscription data and billing period
2. **Validation**: Validate subscription is active and billing period has ended
3. **Data Transformation**: Calculate invoice amount with discounts and taxes
4. **Data Output**: Create invoice record and send to tenant

**Implementation**:
- Service: `AutoInvoicingService`, `InvoiceService`
- Automation: `BillingAutomationService`
- Scheduled: Runs daily to generate invoices for ended billing periods

**Use Cases**:
- Automated invoice generation
- Billing period management
- Invoice delivery and tracking

---

## Ask Amani Integration

The Billing & Subscriptions module's AI agents are automatically discovered and integrated into Ask Amani (SARAISE's AI Assistant) through the module registry system.

### Dynamic Agent Discovery

Ask Amani dynamically discovers all AI agents from registered modules, including:

- **Billing Analytics Agent**: Provides revenue analytics and insights
- **Subscription Optimization Agent**: Suggests subscription plan optimizations and upsell opportunities
- **Payment Risk Agent**: Monitors payment risks and suggests recovery strategies

### Usage Example

Users can interact with these agents through Ask Amani:

```
User: "Why did my payment fail and what should I do?"

Amani: "I'll analyze your payment issue. [Uses Payment Risk Agent]
        Your payment failed due to an expired credit card.
        Recommended actions:
        1. Update your payment method (I can help with this)
        2. Retry payment in 3 days (optimal timing based on ML model)
        3. Consider setting up automatic payment method updates

        Would you like me to help you update your payment method?"
```

### Entry Point: "Explain this invoice"

Users can get detailed explanations of invoices through Ask Amani:

```
User: "Explain this invoice"

Amani: "I'll explain your invoice. [Uses Billing Analytics Agent]

        Invoice #INV-2025-001234
        Subscription: Professional Plan

        Breakdown:
        - Base Amount: $99.00
        - Discount (10% loyalty): -$9.90
        - Tax (10%): $8.91
        - Total: $98.01

        Billing Period: Jan 1 - Jan 31, 2025
        Due Date: Feb 15, 2025
        Status: Paid on Jan 31, 2025

        The discount was applied because you've been a customer for over 12 months.
        Tax is calculated based on your billing address."
```

### Agent Capabilities in Ask Amani

All Billing & Subscriptions AI agents are accessible through Ask Amani with their full capabilities:
- Revenue analytics and forecasting
- Churn prediction and prevention
- Upsell opportunity identification
- Payment failure recovery optimization
- Discount and coupon effectiveness analysis
- Invoice explanation and breakdown

---

## Security & Compliance

### Security Measures

**PCI-DSS Compliance**:
- Never store credit card numbers (use payment gateway tokens)
- PCI-compliant payment gateway integration (Stripe Level 1)
- Annual PCI audit
- Encrypted transmission of payment data (TLS 1.3)
- Regular security scanning
- Restricted access to payment systems

**Data Protection**:
- Encryption at rest for sensitive billing data (AES-256)
- Encryption in transit (TLS 1.3)
- Tokenization of payment methods
- Redacted audit logs (mask PII)
- Secure backup of billing data
- Geographic data residency (for EU customers)

**Access Control**:
- Role-based access (billing admin, finance viewer, etc.)
- MFA required for payment operations
- Audit log of all billing changes
- IP whitelisting for financial operations
- Segregation of duties (no single person can create and approve)

### Compliance

**SOC 2 Type II**:
- Revenue recognition controls
- Billing accuracy controls
- Payment processing security
- Data retention policies
- Change management procedures

**GDPR**:
- Right to access billing data
- Right to erasure (after legal retention period)
- Data portability (export billing history)
- Consent for payment processing
- Privacy-by-design in billing systems

**ASC 606 / IFRS 15** (Revenue Recognition):
- Proper revenue recognition timing
- Deferred revenue tracking
- Revenue allocation for bundles
- Contract modification accounting
- Audit trail for revenue transactions

**Tax Compliance**:
- Automated tax calculation (Avalara/TaxJar integration)
- Tax jurisdiction detection
- Tax exemption certificate management
- VAT/GST handling for international customers
- Sales tax remittance automation
- Tax reporting (1099 for partners)

---

## Implementation Roadmap

### Phase 1: Core Billing (Months 1-2) - 8 weeks
**Goal**: Basic subscription and payment processing

- [x] Subscription plan management
- [x] Subscription CRUD operations
- [x] Basic invoice generation
- [x] Payment gateway integration (Stripe)
- [x] Usage tracking infrastructure
- [x] Automated billing cycle
- [ ] Customer portal for billing

**Success Criteria**:
- Create subscription in < 5 seconds
- Generate invoice accurately
- Process payment successfully
- Track basic usage (API calls, storage)

### Phase 2: Advanced Pricing (Months 3-4) - 8 weeks
**Goal**: Flexible pricing and monetization

- [ ] Multiple pricing models (tiered, volume, usage-based)
- [ ] Proration engine
- [ ] Custom pricing per tenant
- [ ] Multi-currency support
- [ ] Tax calculation automation
- [ ] Plan upgrade/downgrade flows
- [ ] Trial management

**Success Criteria**:
- Support 5+ pricing models
- Accurate proration to the second
- Multi-currency transactions
- Automated tax calculation

### Phase 3: Discounts & Promotions (Month 5) - 4 weeks
**Goal**: Marketing and sales enablement

- [ ] Discount management system
- [ ] Coupon generation and validation
- [ ] Bulk coupon generation
- [ ] Discount stacking rules
- [ ] Promotional campaign tracking
- [ ] Discount analytics

**Success Criteria**:
- Generate 10,000 unique coupons in < 1 minute
- Apply discounts accurately
- Track coupon ROI

### Phase 4: Partner Program (Month 6) - 4 weeks
**Goal**: Enable partner ecosystem

- [ ] Partner registration and onboarding
- [ ] Referral tracking system
- [ ] Commission calculation engine
- [ ] Partner dashboard
- [ ] Automated payout processing
- [ ] Partner analytics

**Success Criteria**:
- Track referrals accurately (100% attribution)
- Calculate commissions correctly
- Process payouts on schedule
- Partner dashboard with real-time stats

### Phase 5: Advanced Features (Months 7-8) - 8 weeks
**Goal**: Enterprise-grade capabilities

- [ ] Dunning management (intelligent retry)
- [ ] Payment method management
- [ ] Refund automation
- [ ] Revenue analytics dashboard
- [ ] MRR/ARR reporting
- [ ] Cohort analysis
- [ ] Rate limiting enforcement
- [ ] Usage-based billing

**Success Criteria**:
- Recover 40%+ of failed payments via dunning
- Real-time revenue metrics
- Accurate usage billing
- Rate limit enforcement < 10ms overhead

### Phase 6: AI-Powered Optimization (Months 9-10) - 8 weeks
**Goal**: Intelligent revenue optimization

- [ ] Churn prediction AI agent
- [ ] Upsell recommendation engine
- [ ] Payment failure recovery AI
- [ ] Revenue forecasting AI
- [ ] Pricing optimization AI
- [ ] Win-back campaign automation
- [ ] Billing support AI chatbot

**Success Criteria**:
- Churn prediction accuracy > 85%
- Increase upsell conversion by 30%
- Payment recovery rate > 40%
- Revenue forecast accuracy ±5%

---

## Competitive Analysis

| Feature | SARAISE | Stripe Billing | Chargebee | Zuora | Recurly |
|---------|---------|---------------|-----------|-------|---------|
| **Pricing Models** | 7+ models | 4 models | 6 models | 8+ models | 5 models |
| **Usage-Based Billing** | ✓ Advanced | ✓ Good | ✓ Good | ✓ Advanced | ✓ Basic |
| **Proration** | ✓ Second-level | ✓ Day-level | ✓ Day-level | ✓ Second-level | ✓ Day-level |
| **Multi-Currency** | ✓ 150+ | ✓ 135+ | ✓ 100+ | ✓ 190+ | ✓ 90+ |
| **Tax Automation** | ✓ Integrated | ✓ Stripe Tax | ✓ Integrated | ✓ Integrated | ✓ Avalara |
| **Dunning** | ✓ AI-powered | ✓ Smart Retry | ✓ Advanced | ✓ Advanced | ✓ Advanced |
| **Partner Program** | ✓ Built-in | ✗ Manual | ✓ Limited | ✓ Limited | ✗ Manual |
| **Coupon System** | ✓ Advanced | ✓ Basic | ✓ Advanced | ✓ Good | ✓ Good |
| **Rate Limiting** | ✓ Built-in | ✗ Separate | ✗ Manual | ✗ Manual | ✗ Manual |
| **AI Agents** | ✓ Churn & Upsell | ✗ | ✗ | Partial | ✗ |
| **Revenue Analytics** | ✓ Advanced | ✓ Basic | ✓ Advanced | ✓ Advanced | ✓ Advanced |
| **Setup Time** | 1-2 weeks | 2-4 weeks | 2-3 weeks | 4-8 weeks | 2-4 weeks |
| **Pricing** | Usage-based | 0.5% + $0.25 | $249+/month | $2000+/month | $599+/month |

**SARAISE Advantages**:
1. **Integrated Partner Program**: Built-in vs requiring separate platform
2. **AI-Powered Optimization**: Churn prediction, upsell intelligence, payment recovery AI
3. **Rate Limiting Integration**: Billing-aware rate limits vs separate systems
4. **Faster Setup**: 1-2 weeks vs 2-8 weeks for competitors
5. **Cost-Effective**: Usage-based vs flat monthly fees starting at $249+

**Competitive Positioning**:
- **vs Stripe Billing**: More flexible pricing models, built-in partner program, AI agents
- **vs Chargebee**: Faster setup, integrated rate limiting, better AI capabilities
- **vs Zuora**: Lower cost, simpler UX, faster implementation (Zuora = enterprise overkill)
- **vs Recurly**: More advanced AI, better partner tools, integrated usage tracking

---

## Success Metrics

### Financial Metrics
- **Revenue Processing**: $1M+ MRR processed through platform
- **Payment Success Rate**: > 97% first-attempt success
- **Dunning Recovery Rate**: > 40% of failed payments recovered
- **Churn Rate**: < 3% monthly churn (vs industry average 5-7%)
- **Revenue Recognition Accuracy**: 100% compliance with ASC 606

### Operational Metrics
- **Invoice Generation Time**: < 2 seconds per invoice
- **Payment Processing Time**: < 5 seconds per transaction
- **Billing Cycle Execution**: 100% on-time billing
- **Proration Accuracy**: 100% correct proration calculations
- **Usage Tracking Lag**: < 1 minute from usage to recorded

### Customer Metrics
- **Billing Disputes**: < 0.5% of invoices disputed
- **Payment Method Update Time**: < 2 minutes self-service
- **Coupon Redemption Success**: > 95% valid redemptions
- **Customer Billing Satisfaction**: > 4.5/5 CSAT score
- **Self-Service Resolution**: > 80% of billing queries self-resolved

### AI Agent Metrics
- **Churn Prediction Accuracy**: > 85% (14-day advance)
- **Upsell Conversion Rate**: > 20% of AI recommendations convert
- **AI-Generated Revenue**: > $50K MRR from AI-driven actions
- **Payment Recovery AI**: > 40% recovery rate (vs 25% baseline)
- **AI Response Time**: < 3 seconds for billing support queries

### Technical Metrics
- **API Latency**: < 100ms p95 for billing operations
- **Uptime**: 99.99% billing system availability
- **Data Accuracy**: 100% invoice accuracy
- **Scalability**: Handle 100K transactions/day
- **Rate Limit Overhead**: < 10ms per request

---

**Document Control**:
- **Author**: SARAISE Billing Team
- **Last Updated**: 2025-11-10
- **Status**: Production - Ready for Enterprise Deployment
- **Compliance Review**: PCI-DSS Level 1, SOC 2 Type II Certified
