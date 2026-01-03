<!-- SPDX-License-Identifier: Apache-2.0 -->
# Crm - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Crm module.

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

**Module**: `crm`
**Category**: Core Business
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the CRM module. Use these customization capabilities to extend customer management, customize lead scoring, automate opportunity workflows, and integrate with external systems.

**Related Documentation**:
- [Customization Framework](../../01-foundation/customization-framework/README.md) - Complete customization framework documentation
- [Event System](../../../architecture/11-event-system.md) - Event-driven architecture patterns

---

## Customization Points

### 1. Customer Model

**Available Events**:
- `before_insert` - Before customer creation
- `after_insert` - After customer creation
- `before_update` - Before customer update
- `after_update` - After customer update
- `before_delete` - Before customer deletion
- `after_delete` - After customer deletion

**Use Cases**:
- Auto-generate customer codes
- Validate customer data
- Sync customer to external systems
- Calculate customer lifetime value
- Trigger welcome emails

**Example Server Script**:
```python
# Auto-generate customer code
def before_insert(doc, method):
    """Generate customer code if not provided"""
    if not doc.customer_code:
        # Generate code: CUST-YYYYMMDD-XXX
        date_prefix = frappe.utils.today().replace("-", "")
        last_customer = frappe.db.get_value(
            "Customer",
            {"customer_code": ["like", f"CUST-{date_prefix}%"]},
            "customer_code",
            order_by="customer_code desc"
        )
        if last_customer:
            seq = int(last_customer.split("-")[-1]) + 1
        else:
            seq = 1
        doc.customer_code = f"CUST-{date_prefix}-{seq:03d}"
```

### 2. Lead Model

**Available Events**:
- `before_insert`, `after_insert`
- `before_update`, `after_update`
- `before_delete`, `after_delete`

**Use Cases**:
- Auto-calculate lead scores
- Validate lead data
- Trigger lead nurturing workflows
- Sync leads to marketing automation

**Example Server Script**:
```python
# Auto-calculate lead score
def after_insert(doc, method):
    """Calculate lead score after creation"""
    from src.modules.crm.services.lead_scoring_service import LeadScoringService
    service = LeadScoringService(frappe.db)
    score = await service.calculate_lead_score(doc.name, doc.tenant_id)
    doc.lead_score = score
    doc.save()
```

### 3. Opportunity Model

**Available Events**:
- `before_insert`, `after_insert`
- `before_update`, `after_update`
- `before_delete`, `after_delete`

**Use Cases**:
- Auto-calculate expected revenue
- Validate opportunity data
- Trigger sales workflows
- Update sales forecasts

**Example Server Script**:
```python
# Auto-calculate expected revenue
def before_save(doc, method):
    """Calculate expected revenue"""
    if doc.amount and doc.probability:
        doc.expected_revenue = (doc.amount * doc.probability) / 100
        doc.weighted_amount = doc.expected_revenue
```

### 4. Contact Resource

**Available Events**:
- `before_insert`, `after_insert`
- `before_update`, `after_update`
- `before_delete`, `after_delete`

**Use Cases**:
- Auto-generate full name
- Validate contact data
- Sync contacts to external systems

### 5. Activity Resource

**Available Events**:
- `before_insert`, `after_insert`
- `before_update`, `after_update`
- `before_delete`, `after_delete`

**Use Cases**:
- Auto-assign activities
- Calculate activity duration
- Trigger follow-up activities
- Send activity reminders

---

## Custom API Endpoints

### Example: Custom Lead Scoring Endpoint

```python
# API Script: Custom lead scoring with advanced rules
# Endpoint: POST /api/v1/customization/custom-endpoints/crm_advanced_lead_scoring

@frappe.whitelist(allow_guest=False)
def advanced_lead_scoring(lead_id, custom_rules=None):
    """Advanced lead scoring with custom rules"""
    from src.modules.crm.services.lead_scoring_service import LeadScoringService
    service = LeadScoringService(frappe.db)

    # Apply custom scoring rules
    if custom_rules:
        score = service.calculate_lead_score_with_rules(lead_id, custom_rules)
    else:
        score = service.calculate_lead_score(lead_id)

    return {"lead_id": lead_id, "score": score}
```

### Example: Customer Lifetime Value Calculation

```python
# API Script: Calculate customer lifetime value
# Endpoint: POST /api/v1/customization/custom-endpoints/crm_customer_ltv

@frappe.whitelist(allow_guest=False)
def calculate_customer_ltv(customer_id):
    """Calculate customer lifetime value"""
    # Get all opportunities for customer
    opportunities = frappe.get_all(
        "Opportunity",
        filters={"customer_id": customer_id, "is_won": 1},
        fields=["amount", "actual_close_date"]
    )

    total_revenue = sum(opp.amount for opp in opportunities)

    # Calculate average deal size
    avg_deal_size = total_revenue / len(opportunities) if opportunities else 0

    # Calculate purchase frequency
    # (simplified - would use actual purchase history)
    purchase_frequency = len(opportunities) / 12  # per year

    # Calculate customer lifetime value
    customer_lifetime = 5  # years (assumed)
    ltv = avg_deal_size * purchase_frequency * customer_lifetime

    return {
        "customer_id": customer_id,
        "total_revenue": total_revenue,
        "avg_deal_size": avg_deal_size,
        "purchase_frequency": purchase_frequency,
        "customer_lifetime": customer_lifetime,
        "ltv": ltv
    }
```

---

## Webhooks

### Available Events

| Event Type | Description | Payload |
|------------|-------------|---------|
| `crm.lead.created` | Lead created | `{lead_id, lead_name, tenant_id, timestamp}` |
| `crm.lead.converted` | Lead converted to customer | `{lead_id, customer_id, tenant_id, timestamp}` |
| `crm.opportunity.created` | Opportunity created | `{opportunity_id, opportunity_name, customer_id, tenant_id, timestamp}` |
| `crm.opportunity.won` | Opportunity won | `{opportunity_id, amount, customer_id, tenant_id, timestamp}` |
| `crm.opportunity.lost` | Opportunity lost | `{opportunity_id, lost_reason, tenant_id, timestamp}` |
| `crm.customer.created` | Customer created | `{customer_id, customer_name, tenant_id, timestamp}` |

### Example Webhook Configuration

```python
# Create webhook for opportunity won events
POST /api/v1/webhooks
{
    "name": "Opportunity Won Notifier",
    "event_type": "crm.opportunity.won",
    "url": "https://example.com/webhooks/opportunity-won",
    "method": "POST",
    "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
    },
    "tenant_id": "tenant-123",
    "is_active": true
}
```

---

## AI-Powered Code Generation

Ask Amani can generate customizations for the CRM module using AI. Example queries:

- "Create a server script that auto-assigns leads based on territory"
- "Generate a webhook that syncs customers to Salesforce"
- "Create a custom API endpoint to calculate customer health score"
- "Generate a script that sends welcome emails to new customers"

---

## Best Practices

1. **Error Handling**: Always use proper error handling in server scripts
2. **Validation**: Validate data before processing
3. **Performance**: Use async operations for external API calls
4. **Security**: Validate tenant isolation and user permissions
5. **Logging**: Log important operations for debugging

---

## Examples Repository

For more examples, see:
- `backend/scripts/demo_customizations/crm/` - Demo customization examples
- [Customization Framework Examples](../../01-foundation/customization-framework/README.md#examples)


## Demo Data

## Overview

This document describes the demo data structure for the CRM module. Demo data provides realistic examples of customers, contacts, leads, opportunities, and activities for testing and demonstration purposes.

## Demo Data Structure

### Customers

**Count:** 5-10 demo customers

**Sample Data:**
- Acme Corporation (Technology, Enterprise)
- Global Manufacturing Inc. (Manufacturing, Mid-market)
- Retail Solutions Ltd. (Retail, SMB)
- Healthcare Partners (Healthcare, Enterprise)
- Financial Services Group (Finance, Enterprise)

**Fields:**
- Customer name, type (company/individual)
- Industry, website
- Contact information (email, phone, mobile)
- Address (full address)
- Tax ID, credit limit, payment terms
- Status (active/inactive)

### Contacts

**Count:** 10-15 demo contacts (2-3 per customer)

**Sample Data:**
- Primary contacts for each customer
- Decision makers and influencers
- Various job titles (CEO, CTO, VP Sales, Manager, etc.)

**Fields:**
- First name, last name, full name
- Job title, department
- Contact information (email, phone, mobile, fax)
- Address
- Primary contact flag
- Status (active/inactive)

### Leads

**Count:** 15-20 demo leads

**Sample Data:**
- Leads from various sources (website, referral, cold call, etc.)
- Different statuses (new, contacted, qualified, converted, lost)
- Various lead scores (0-100)
- BANT qualification data

**Fields:**
- Lead name, company name
- Contact information
- Status, source, score
- Lead score, qualification status
- BANT score (Budget, Authority, Need, Timeline)
- Conversion tracking

### Opportunities

**Count:** 10-15 demo opportunities

**Sample Data:**
- Opportunities at various stages
- Different amounts and probabilities
- Mix of won, lost, and open opportunities
- Linked to customers and leads

**Fields:**
- Opportunity name, stage
- Amount, probability, expected revenue
- Currency
- Expected/actual close dates
- Customer, contact, lead relationships
- Won/lost status

### Activities

**Count:** 30-40 demo activities

**Sample Data:**
- Calls, emails, meetings, tasks, notes
- Various statuses (planned, in_progress, completed, cancelled)
- Different priorities (low, medium, high)
- Linked to customers, contacts, opportunities, leads

**Fields:**
- Activity type, subject, description
- Status, priority
- Due date, start date, end date
- Duration, location
- Outcome, notes
- Assigned to

### Sales Forecasts

**Count:** 5-10 demo forecasts

**Sample Data:**
- Monthly, quarterly, yearly forecasts
- Commit, best case, worst case scenarios
- Various confidence levels

**Fields:**
- Forecast period, type
- Forecasted amount, confidence level
- Period start/end dates
- Breakdown data

## Relationships

### Customer Relationships
- Each customer has 2-3 contacts
- Each customer has 1-3 opportunities
- Each customer has 5-10 activities

### Lead Relationships
- Some leads are converted to customers
- Some leads are converted to opportunities
- Each lead has 2-5 activities

### Opportunity Relationships
- Each opportunity is linked to a customer
- Some opportunities are linked to contacts
- Some opportunities originated from leads
- Each opportunity has 3-8 activities

### Activity Relationships
- Activities can be linked to customers, contacts, opportunities, or leads
- Activities are assigned to users
- Activities track interactions and tasks

## Data Seeding Script

The demo data seeding script should:

1. **Create Customers First**
   - Create 5-10 customers with realistic data
   - Include mix of company types and industries

2. **Create Contacts**
   - Create 2-3 contacts per customer
   - Mark one contact per customer as primary

3. **Create Leads**
   - Create 15-20 leads with various statuses
   - Include some qualified leads ready for conversion
   - Set lead scores and BANT data

4. **Convert Some Leads**
   - Convert 3-5 qualified leads to customers
   - Convert 2-3 leads to opportunities

5. **Create Opportunities**
   - Create opportunities linked to customers
   - Include mix of stages (prospecting to closed_won/lost)
   - Set realistic amounts and probabilities

6. **Create Activities**
   - Create activities for customers, contacts, opportunities, and leads
   - Include mix of activity types and statuses
   - Assign activities to users

7. **Create Sales Forecasts**
   - Create forecasts for different periods
   - Include various forecast types and confidence levels

## Integration with seed_demo_tenant.py

The demo data should be created in the `seed_demo_tenant()` function or a separate `seed_crm_demo_data()` function that is called from `seed_demo_tenant.py`.

**Example Integration:**
```python
# In seed_demo_tenant.py
from backend.scripts.seed_crm_demo_data import seed_crm_demo_data

async def seed_demo_tenant():
    # ... existing code ...

    # Seed CRM demo data
    await seed_crm_demo_data(session, tenant.id, demo_user.id)
```

## Usage

Demo data is used for:
- **Testing:** Verify module functionality with realistic data
- **Demonstrations:** Show module capabilities to potential users
- **Development:** Provide data for frontend development
- **Training:** Help users learn the system with sample data

## Maintenance

- Demo data should be idempotent (safe to run multiple times)
- Demo data should be clearly marked (e.g., prefix with "Demo" or use specific naming)
- Demo data can be reset/refreshed by re-running the seeding script

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
