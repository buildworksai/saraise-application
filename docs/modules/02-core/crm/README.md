<!-- SPDX-License-Identifier: Apache-2.0 -->
# Customer Relationship Management (CRM) Module

---

## ⚠️ IMPLEMENTATION PHASE STATUS

**IMPLEMENTATION STATUS:** ❌ **SPECIFICATION ONLY - NOT FOR IMPLEMENTATION UNTIL PHASE 8**

**CURRENT PHASE:** Phase 1 (Platform Foundations)

**WHEN TO IMPLEMENT:** Phase 8 (After platform foundation complete - Phases 1-7)

**CRITICAL CONSTRAINT (FROZEN ARCHITECTURE):**
- **DO NOT IMPLEMENT** this module until Phase 8 begins
- This documentation serves as **specification only** for future implementation
- Platform foundation (Phases 1-7) MUST be complete before business module rollout
- Requires: Module framework, subscription system, migration automation, AI infrastructure all operational
- Any attempt to implement before Phase 8 will be rejected (requires ACP + Board approval)

**WHY THIS CONSTRAINT EXISTS:**
- Business modules require stable module packaging framework (Phase 5)
- AI agent infrastructure must be safe and governed (Phase 4)
- Migration and upgrade automation must be proven (Phase 6-7)
- Platform must handle scale, sharding, multi-region (Phase 3)
- Premature business module implementation creates technical debt and architectural violations

---

**Module Code**: `crm`
**Category**: Core Business (Phase 8)
**Priority**: Critical - Customer Lifecycle
**Version**: 1.0.0 (Specification)
**Specification Status**: Complete (Ready for Phase 8 implementation)

---

## Executive Summary

The CRM module provides comprehensive **customer lifecycle management** from lead acquisition to customer advocacy. Powered by AI agents, this module automates lead scoring, sales process management, customer engagement, and predictive analytics—delivering a world-class CRM experience that rivals Salesforce, HubSpot, and Microsoft Dynamics.

### Vision

**"Every customer interaction, intelligently managed from first touch to lifetime advocacy."**

---

## World-Class Features

### 1. Lead Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Lead Capture**:
```python
lead_sources = {
    "web_forms": "Website contact forms",
    "landing_pages": "Dedicated campaign pages",
    "social_media": "LinkedIn, Facebook lead ads",
    "email": "Email inquiries",
    "phone": "Call tracking",
    "chat": "Live chat conversations",
    "events": "Trade shows, webinars",
    "api": "External system integration",
    "manual": "Sales rep manual entry",
    "referral": "Customer referrals"
}
```

**AI-Powered Lead Scoring**:
```python
scoring_model = {
    "demographic": {
        "title": {"C-Level": 20, "VP": 15, "Manager": 10, "Other": 5},
        "company_size": {">1000": 20, "500-1000": 15, "100-500": 10, "<100": 5},
        "industry": {"Technology": 20, "Finance": 18, "Other": 10}
    },
    "behavioral": {
        "website_visits": "1 point per visit (max 30)",
        "email_opens": "2 points per open (max 20)",
        "content_downloads": "10 points per download",
        "pricing_page_visit": "25 points",
        "demo_request": "50 points"
    },
    "engagement": {
        "email_replies": "15 points per reply",
        "meeting_attended": "30 points",
        "proposal_opened": "20 points"
    },
    "grade": "A (80-100), B (60-79), C (40-59), D (0-39)"
}
```

**Lead Qualification (BANT)**:
- **Budget**: Does prospect have budget?
- **Authority**: Are you talking to decision-maker?
- **Need**: Do they have a genuine need?
- **Timeline**: What's their purchasing timeline?

**Lead Routing**:
- Round-robin assignment
- Territory-based routing
- Skill-based matching
- Workload balancing
- Priority-based (hot leads first)

### 2. Contact & Account Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Contact Management**:
```python
contact_fields = {
    "basic": ["name", "email", "phone", "title", "department"],
    "professional": ["linkedin", "twitter", "company", "role"],
    "engagement": ["last_contacted", "contact_frequency", "preferred_channel"],
    "scoring": ["lead_score", "engagement_score", "influence_score"],
    "lifecycle": ["stage", "status", "owner"],
    "custom": "Unlimited custom fields via metadata"
}
```

**Account Hierarchy**:
```
Parent Account (Corporation)
├── Child Account (Division A)
│   ├── Location 1
│   └── Location 2
└── Child Account (Division B)
    ├── Location 3
    └── Location 4
```

**Relationship Mapping**:
- Org chart visualization
- Decision-maker identification
- Influence mapping
- Buying committee tracking

**360° Customer View**:
```python
customer_360_view = {
    "overview": "Name, company, title, photo",
    "contact_info": "Email, phone, social profiles",
    "interaction_history": "All emails, calls, meetings",
    "deals": "Open and closed opportunities",
    "tickets": "Support tickets and status",
    "invoices": "Billing history",
    "documents": "Proposals, contracts, quotes",
    "notes": "Sales notes and call logs",
    "timeline": "Chronological activity feed",
    "ai_insights": "Next best action, risk alerts"
}
```

### 3. Opportunity Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Sales Pipeline**:
```python
pipeline_stages = {
    "prospecting": {"probability": 10, "actions": ["qualify_lead"]},
    "qualification": {"probability": 20, "actions": ["discovery_call"]},
    "needs_analysis": {"probability": 40, "actions": ["demo", "proposal"]},
    "proposal": {"probability": 60, "actions": ["send_proposal", "follow_up"]},
    "negotiation": {"probability": 80, "actions": ["handle_objections"]},
    "closed_won": {"probability": 100, "actions": ["onboarding"]},
    "closed_lost": {"probability": 0, "actions": ["lost_analysis"]}
}
```

**Opportunity Fields**:
- Deal name & description
- Account & contact
- Amount & currency
- Close date (expected)
- Stage & probability
- Competitors
- Products/services
- Next steps

**Weighted Pipeline**:
```python
weighted_forecast = sum([
    opportunity.amount * opportunity.probability
    for opportunity in pipeline
])
```

**Win/Loss Analysis**:
- Capture loss reasons
- Competitor analysis
- Pricing feedback
- Product gaps
- Sales process insights

### 4. Sales Activities & Task Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Activity Types**:
- **Calls**: Log calls, duration, outcome
- **Emails**: Track opens, clicks, replies
- **Meetings**: Calendar integration, attendees
- **Tasks**: To-dos with due dates
- **Notes**: Call notes, meeting minutes

**Activity Tracking**:
```python
activity_metrics = {
    "total_activities": "Count per rep per day/week/month",
    "activity_by_type": "Calls, emails, meetings breakdown",
    "response_time": "Time to first response",
    "follow_up_adherence": "% tasks completed on time",
    "meeting_conversion": "% meetings that advance deal"
}
```

**AI Task Suggestions**:
```
"Based on this deal's inactivity for 7 days, I suggest:
1. Send follow-up email (template: Check-in)
2. Schedule call for Tuesday 2pm
3. Share case study relevant to their industry"
```

### 5. Sales Automation & Workflows
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Automated Workflows**:
```python
workflow_examples = {
    "lead_assignment": {
        "trigger": "New lead created",
        "conditions": "Lead score > 70",
        "actions": ["Assign to senior rep", "Send Slack notification"]
    },
    "follow_up_sequence": {
        "trigger": "Demo completed",
        "actions": [
            "Day 0: Send thank you email",
            "Day 1: Share case study",
            "Day 3: Check-in call",
            "Day 7: Send proposal",
            "Day 10: Follow-up if no response"
        ]
    },
    "stale_deal_alert": {
        "trigger": "Deal inactive for 14 days",
        "actions": ["Alert manager", "Suggest next action"]
    }
}
```

**Email Sequences**:
- Drip campaigns for lead nurturing
- Personalized templates
- A/B testing
- Automatic pause on reply
- Performance analytics

**Sales Cadences**:
```
Day 1: Email #1 (Introduction)
Day 2: LinkedIn connection request
Day 4: Email #2 (Value proposition)
Day 6: Phone call
Day 8: Email #3 (Case study)
Day 10: Phone call
Day 14: Email #4 (Break-up email)
```

### 6. Forecasting & Analytics
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Sales Forecasting**:
```python
forecast_methods = {
    "pipeline": "Sum of weighted opportunities",
    "historical": "Based on past win rates",
    "ai_predictive": "ML model prediction",
    "rep_input": "Rep-submitted forecast",
    "hybrid": "Combination of methods"
}
```

**AI Predictive Analytics**:
- Deal win probability (AI-calculated)
- Revenue prediction by quarter
- Churn risk identification
- Upsell opportunity detection
- Sales rep performance prediction

**Key Metrics**:
```python
crm_kpis = {
    # Pipeline
    "pipeline_value": "Total value of open opportunities",
    "pipeline_velocity": "Speed deals move through pipeline",
    "average_deal_size": "Mean deal value",
    "win_rate": "% opportunities won",

    # Activity
    "activities_per_rep": "Calls, emails, meetings per rep",
    "response_time": "Time to first response",
    "sales_cycle_length": "Days from lead to close",

    # Performance
    "quota_attainment": "% of quota achieved",
    "revenue_vs_target": "Actual vs. forecasted revenue",
    "conversion_rates": "Lead→Opp→Win rates",

    # Customer
    "customer_acquisition_cost": "CAC",
    "customer_lifetime_value": "CLV",
    "cltv_cac_ratio": "CLV:CAC ratio"
}
```

**Dashboards**:
- Sales rep dashboard (personal metrics)
- Manager dashboard (team performance)
- Executive dashboard (revenue, forecast)
- Pipeline dashboard (visual funnel)

### 7. Quote & Proposal Management
**Status**: Must-Have | **Competitive Parity**: Advanced

**Quote Builder**:
```python
quote_features = {
    "product_catalog": "Select from product library",
    "pricing_rules": "Volume discounts, bundles",
    "discount_approval": "Manager approval for >20%",
    "tax_calculation": "Automatic tax calculation",
    "templates": "Professional quote templates",
    "e_signature": "DocuSign, Adobe Sign integration",
    "versioning": "Track quote versions",
    "expiration": "Auto-expire after 30 days"
}
```

**Proposal Generation**:
- Template library
- Dynamic content (personalized)
- Tracking (view, time spent)
- Collaboration (internal comments)
- Approval workflow

**CPQ (Configure, Price, Quote)**:
- Product configuration
- Pricing optimization
- Quote generation
- Contract management

### 8. Territory & Quota Management
**Status**: Must-Have | **Competitive Parity**: Advanced

**Territory Management**:
```python
territory_assignment = {
    "geographic": "By country, state, zip code",
    "industry": "By vertical (tech, finance, healthcare)",
    "account_size": "By revenue or employee count",
    "named_accounts": "Strategic accounts assigned directly",
    "combination": "Multi-criteria territories"
}
```

**Quota Setting**:
- Annual, quarterly, monthly quotas
- Revenue and unit quotas
- Team and individual quotas
- Historical quota attainment
- Quota vs. actual tracking

### 9. Sales Collaboration
**Status**: Should-Have | **Competitive Advantage**: Advanced

**Team Selling**:
- Shared accounts
- Deal teams (Sales, SE, CS)
- Internal chat per deal
- @mentions and notifications
- File sharing

**Sales Enablement**:
- Content library (pitch decks, case studies)
- Playbooks (sales process guides)
- Training materials
- Competitive battle cards
- Product documentation

**Manager Coaching**:
- Deal reviews
- Pipeline reviews
- Call recording playback
- Performance feedback
- Goal setting

### 10. Mobile CRM
**Status**: Should-Have | **Competitive Parity**: Industry Standard

**Mobile App Features**:
```python
mobile_capabilities = {
    "offline_mode": "Work offline, sync when online",
    "voice_to_text": "Dictate notes and emails",
    "camera": "Scan business cards, capture photos",
    "geolocation": "Check-in at customer locations",
    "notifications": "Push notifications for tasks",
    "quick_actions": "Log call, send email quickly",
    "dashboard": "Key metrics at a glance"
}
```

---

## AI Agent Integration

### Sales AI Agents

**1. Lead Qualifier Agent**
```python
agent_capabilities = {
    "score_leads": "Auto-score using ML model",
    "enrich_data": "Append company info from LinkedIn, Clearbit",
    "route_leads": "Assign to best rep",
    "send_intro": "Auto-send personalized intro email"
}
```

**2. Follow-Up Agent**
```python
agent_capabilities = {
    "detect_inactivity": "Find deals with no activity in 7+ days",
    "suggest_actions": "Recommend email, call, or meeting",
    "draft_emails": "Generate personalized follow-up emails",
    "schedule_tasks": "Create tasks with due dates"
}
```

**3. Insights Agent**
```python
agent_capabilities = {
    "deal_risk": "Flag at-risk deals",
    "win_probability": "Predict likelihood to close",
    "next_best_action": "Suggest next step",
    "competitive_intel": "Alert on competitor mentions"
}
```

---

## Database Schema

```sql
-- Leads
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Contact Info
    first_name VARCHAR(100),
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    title VARCHAR(100),
    company VARCHAR(255),

    -- Scoring
    lead_score INTEGER DEFAULT 0,
    grade VARCHAR(2),  -- A, B, C, D

    -- Source
    source VARCHAR(100),  -- web, social, event, referral
    campaign_id UUID REFERENCES campaigns(id),

    -- Assignment
    owner_id UUID REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'new',  -- new, contacted, qualified, converted, lost

    -- Dates
    created_at TIMESTAMPTZ DEFAULT NOW(),
    converted_at TIMESTAMPTZ,

    INDEX idx_tenant_status (tenant_id, status),
    INDEX idx_owner (owner_id),
    INDEX idx_score (lead_score DESC)
);

-- Accounts
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Company Info
    name VARCHAR(255) NOT NULL,
    website VARCHAR(255),
    industry VARCHAR(100),
    employees INTEGER,
    annual_revenue DECIMAL(15, 2),

    -- Hierarchy
    parent_account_id UUID REFERENCES accounts(id),

    -- Address
    billing_street TEXT,
    billing_city VARCHAR(100),
    billing_state VARCHAR(100),
    billing_postal_code VARCHAR(20),
    billing_country VARCHAR(100),

    -- Assignment
    owner_id UUID REFERENCES users(id),
    account_type VARCHAR(50),  -- prospect, customer, partner

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_name (tenant_id, name),
    INDEX idx_owner (owner_id)
);

-- Contacts
CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    account_id UUID REFERENCES accounts(id),

    -- Contact Info
    first_name VARCHAR(100),
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    mobile VARCHAR(50),
    title VARCHAR(100),
    department VARCHAR(100),

    -- Social
    linkedin VARCHAR(255),
    twitter VARCHAR(100),

    -- Engagement
    last_contacted_at TIMESTAMPTZ,
    engagement_score INTEGER DEFAULT 0,

    -- Assignment
    owner_id UUID REFERENCES users(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_account (account_id),
    INDEX idx_email (email)
);

-- Opportunities
CREATE TABLE opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    account_id UUID REFERENCES accounts(id),

    -- Opportunity Info
    name VARCHAR(255) NOT NULL,
    description TEXT,
    amount DECIMAL(15, 2) NOT NULL,
    probability INTEGER DEFAULT 0,  -- 0-100

    -- Stage
    stage VARCHAR(100) NOT NULL,
    close_date DATE NOT NULL,

    -- Product
    product_ids UUID[],

    -- Competition
    competitors TEXT[],

    -- Assignment
    owner_id UUID REFERENCES users(id),

    -- Status
    status VARCHAR(50) DEFAULT 'open',  -- open, won, lost
    closed_at TIMESTAMPTZ,
    loss_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_status (tenant_id, status),
    INDEX idx_owner_stage (owner_id, stage),
    INDEX idx_close_date (close_date)
);

-- Activities
CREATE TABLE activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Type
    activity_type VARCHAR(50) NOT NULL,  -- call, email, meeting, task, note

    -- Related Records
    lead_id UUID REFERENCES leads(id),
    account_id UUID REFERENCES accounts(id),
    contact_id UUID REFERENCES contacts(id),
    opportunity_id UUID REFERENCES opportunities(id),

    -- Content
    subject VARCHAR(500),
    description TEXT,
    outcome VARCHAR(100),  -- For calls: connected, voicemail, no_answer

    -- Scheduling
    due_date TIMESTAMPTZ,
    completed BOOLEAN DEFAULT false,
    completed_at TIMESTAMPTZ,

    -- Assignment
    owner_id UUID REFERENCES users(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_owner_due (owner_id, due_date),
    INDEX idx_lead (lead_id),
    INDEX idx_opportunity (opportunity_id)
);
```

---

## Implementation Roadmap

### Phase 1: Core CRM (Month 1-2) ✅ **COMPLETE**
- [x] Lead, contact, customer management
- [x] Opportunity tracking
- [x] Activity logging
- [x] Basic reporting (API routes implemented)

### Phase 2: Sales Automation (Month 3) 🔄 **PARTIAL**
- [x] Lead scoring (AI-powered service implemented)
- [ ] Email sequences (requires email_marketing module integration)
- [x] Workflows (defined in manifest: lead_to_opportunity, opportunity_to_customer)
- [x] Task automation (activity service with automation hooks)

### Phase 3: AI & Analytics (Month 4) ✅ **CORE COMPLETE**
- [x] AI agents (lead_scoring_agent, customer_sentiment_agent defined in manifest)
- [x] Predictive analytics (sales forecasting service implemented)
- [x] Sales forecasting (AI-powered service with pipeline, scenarios, accuracy tracking)
- [x] Advanced dashboards (backend routes exist, frontend components: 18 components, 17 pages)

### Phase 4: Advanced Features (Month 5-6) 🔴 **NOT STARTED**
- [ ] Quote & proposal management (not implemented)
- [ ] Territory management (not implemented)
- [ ] Mobile app (not implemented)
- [ ] Sales enablement (content library, playbooks - not implemented)

---

## Competitive Analysis

| Feature | SARAISE | Salesforce | HubSpot | Microsoft Dynamics | Pipedrive |
|---------|---------|------------|---------|-------------------|-----------|
| **Lead Scoring** | ✓ AI-powered | ✓ AI | ✓ AI | ✓ AI | ✓ Basic |
| **Pipeline Management** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Email Sequences** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **AI Agents** | ✓ 3+ types | ✓ Einstein | ✓ Basic | ✓ Copilot | ✗ |
| **Mobile App** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **ERP Integration** | ✓ Native | Via connector | Via connector | ✓ Native | Limited |
| **CPQ** | ✓ | ✓ (add-on) | ✓ (add-on) | ✓ | ✗ |
| **Pricing** | $$ | $$$$ | $$ | $$$ | $ |

**Verdict**: Comparable to Salesforce/HubSpot with superior ERP integration and lower cost.

---

## Success Metrics

- **Lead Conversion**: > 20% lead-to-opportunity
- **Win Rate**: > 30% opportunity-to-customer
- **Sales Cycle**: Reduce by 25%
- **Pipeline Accuracy**: ±10% forecast accuracy
- **User Adoption**: > 90% daily active users
- **ROI**: 5x return in year 1

---

**Document Control**:
- **Author**: SARAISE Architecture Team
- **Last Updated**: 2025-01-XX
- **Status**: ✅ **Core Implementation Complete** | 🔄 **Advanced Features Pending**
- **Planning Status**: ✅ **100% Planning Complete** - See `PLANNING_INDEX.md` for complete planning guide ⭐
- **Implementation Status**: See `IMPLEMENTATION_STATUS.md` for detailed verification
- **Complete Implementation Plan**: See `COMPLETE_IMPLEMENTATION_PLAN.md` for 100% planning ⭐
- **Technical Specifications**: See `TECHNICAL_SPECIFICATIONS.md` for detailed technical specs ⭐
- **Sprint Breakdown**: See `SPRINT_BREAKDOWN.md` for 2-week sprint planning ⭐
- **Quick Reference**: See `QUICK_REFERENCE.md` for quick access to key information
