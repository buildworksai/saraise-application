<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sales Management Module

**Module Code**: `sales`
**Category**: Core Business
**Priority**: Critical - Revenue Generation
**Version**: 1.0.0
**Status**: Planning Phase

---

## Executive Summary

The Sales Management module provides comprehensive **order-to-cash** workflow from quotations to delivery, invoicing, and revenue analytics. Powered by AI agents, this module automates pricing, quote generation, sales forecasting, and customer analytics—delivering a world-class sales management experience that rivals SAP S/4HANA Sales, Oracle NetSuite Order Management, Microsoft Dynamics 365 Sales, and Odoo Sales.

### Vision

**"Every sales opportunity converted efficiently from quote to cash with AI-powered insights and zero errors."**

---

## World-Class Features

### 1. Quotation Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Quote Creation**:
```python
quotation_workflow = {
    "lead_conversion": "Convert lead/opportunity to quote",
    "product_selection": {
        "catalog_browse": "Browse product catalog",
        "search": "Search by name, SKU, category",
        "favorites": "Quick add from favorites",
        "bundles": "Add product bundles",
        "configurable": "Configure complex products (CPQ)"
    },
    "pricing": {
        "list_price": "Standard catalog price",
        "customer_price": "Customer-specific pricing",
        "volume_discount": "Quantity-based discounts",
        "promotional": "Campaign pricing",
        "manual_override": "Sales rep override (with approval)"
    },
    "terms": {
        "payment_terms": "Net 30, Net 60, COD, etc.",
        "delivery_terms": "FOB, CIF, DDP (Incoterms)",
        "validity": "Quote valid for 30 days",
        "warranty": "Warranty terms"
    }
}
```

**Quote Versions**:
```python
versioning = {
    "auto_versioning": "Auto-save each major change",
    "compare": "Compare versions side-by-side",
    "restore": "Restore previous version",
    "track_changes": "Audit trail of all changes",
    "share": "Share specific version with customer"
}
```

**Quote Templates**:
```python
templates = {
    "industry_specific": ["Manufacturing", "Services", "Retail", "Construction"],
    "product_bundles": "Pre-configured product packages",
    "terms_library": "Standard terms and conditions",
    "design_themes": "Professional quote designs",
    "multi_language": "Generate quotes in customer's language"
}
```

**Approval Workflow**:
```python
approval_rules = {
    "discount_approval": {
        "0_10_percent": "Auto-approved",
        "10_20_percent": "Manager approval",
        "20_plus_percent": "Director approval"
    },
    "amount_approval": {
        "under_10k": "Auto-approved",
        "10k_50k": "Manager approval",
        "50k_plus": "VP approval"
    },
    "margin_approval": {
        "below_20_percent": "Requires explanation + approval",
        "20_30_percent": "Manager review",
        "30_plus_percent": "Auto-approved"
    }
}
```

### 2. CPQ (Configure, Price, Quote)
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Product Configuration**:
```python
configurator = {
    "use_cases": [
        "Computers (CPU, RAM, Storage, etc.)",
        "Furniture (Wood, Fabric, Dimensions)",
        "Machinery (Motor, Features, Accessories)",
        "Software (Modules, Users, Features)"
    ],
    "configuration_rules": {
        "dependencies": "If Option A selected, Option B required",
        "conflicts": "Option X and Option Y cannot coexist",
        "quantities": "Min/max quantity constraints",
        "pricing_impact": "Each option affects price"
    },
    "visual_configurator": {
        "3d_preview": "Show 3D model of configured product",
        "image_generation": "Generate product image from config",
        "ar_preview": "AR preview on mobile"
    }
}
```

**Dynamic Pricing Engine**:
```python
pricing_engine = {
    "base_price": "Product base price",
    "configuration_cost": "Sum of selected options",
    "quantity_discount": {
        "1_10": "List price",
        "11_50": "5% discount",
        "51_100": "10% discount",
        "100_plus": "15% discount"
    },
    "customer_tier": {
        "platinum": "20% discount",
        "gold": "15% discount",
        "silver": "10% discount",
        "standard": "0% discount"
    },
    "promotional": "Active promotions",
    "margin_check": "Ensure minimum margin",
    "competitor_pricing": "AI-suggested competitive pricing"
}
```

**Quote Generation**:
```python
quote_output = {
    "pdf_generation": "Professional PDF quote",
    "interactive_quote": "Customer portal interactive quote",
    "e_signature": "DocuSign, Adobe Sign integration",
    "online_acceptance": "Customer accepts quote online",
    "payment_link": "Include payment link for deposits",
    "auto_email": "Auto-email to customer",
    "tracking": "Track views, time spent, downloads"
}
```

### 3. Sales Order Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Order Creation**:
```python
order_sources = {
    "from_quote": "Convert accepted quote to sales order",
    "direct_order": "Direct customer order (phone, email)",
    "portal_order": "Customer self-service portal",
    "ecommerce": "Integrated from e-commerce site",
    "edi": "EDI integration (automotive, retail)",
    "marketplace": "Amazon, eBay, Shopify",
    "subscription": "Recurring orders"
}
```

**Order Types**:
```python
order_types = {
    "standard_order": "Regular sale with delivery",
    "cash_sale": "Immediate payment and delivery",
    "credit_order": "Payment on credit terms",
    "dropship": "Ship directly from supplier to customer",
    "backorder": "Partial ship, balance later",
    "blanket_order": "Umbrella order with multiple releases",
    "consignment": "Consignment inventory",
    "rental": "Equipment rental",
    "service": "Service orders"
}
```

**Order Fulfillment Workflow**:
```python
fulfillment_process = {
    "1_order_received": {
        "status": "Submitted",
        "actions": ["Validate stock", "Check credit limit", "Fraud check"]
    },
    "2_order_confirmed": {
        "status": "Confirmed",
        "actions": ["Reserve stock", "Send confirmation email"]
    },
    "3_picking": {
        "status": "Picking",
        "actions": ["Generate pick list", "Warehouse picking"]
    },
    "4_packing": {
        "status": "Packing",
        "actions": ["Pack items", "Print shipping label", "Weigh package"]
    },
    "5_ready_to_ship": {
        "status": "Ready to Ship",
        "actions": ["Carrier pickup scheduled"]
    },
    "6_shipped": {
        "status": "Shipped",
        "actions": ["Update tracking", "Send tracking email", "Create invoice"]
    },
    "7_delivered": {
        "status": "Delivered",
        "actions": ["Confirm delivery", "Request feedback"]
    }
}
```

**Stock Allocation**:
```python
allocation_strategies = {
    "fifo": "First order gets first priority",
    "priority": "VIP customers get priority",
    "proximity": "Allocate from nearest warehouse",
    "multi_warehouse": "Split order across warehouses",
    "backorder_handling": {
        "partial_ship": "Ship available, backorder rest",
        "hold_order": "Hold entire order until complete",
        "cancel_balance": "Ship available, cancel rest"
    }
}
```

### 4. Delivery Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Delivery Note / Packing Slip**:
```python
delivery_note = {
    "creation": "Auto-created from sales order",
    "picking_integration": "Updates from warehouse picking",
    "contents": {
        "customer_details": "Ship-to address",
        "items": "List of items with quantities",
        "serial_batch": "Serial/batch numbers",
        "weight_dimensions": "Package weight and dimensions",
        "special_instructions": "Handling instructions"
    },
    "barcode": "Barcode for scanning at delivery",
    "signature_capture": "Customer signature on delivery (mobile app)"
}
```

**Shipping Integration**:
```python
shipping_carriers = {
    "major_carriers": [
        "FedEx",
        "UPS",
        "USPS",
        "DHL",
        "Regional carriers"
    ],
    "features": {
        "rate_shopping": "Compare rates across carriers",
        "label_printing": "Print shipping labels",
        "tracking": "Real-time tracking updates",
        "pickup_scheduling": "Schedule carrier pickup",
        "delivery_confirmation": "Proof of delivery",
        "international": "Customs documentation"
    },
    "customer_choice": "Let customer choose carrier/speed"
}
```

**Delivery Scheduling**:
```python
scheduling = {
    "delivery_windows": {
        "standard": "5-7 business days",
        "express": "2-3 business days",
        "overnight": "Next day",
        "scheduled": "Customer picks date/time"
    },
    "route_optimization": "Optimize delivery routes (for own fleet)",
    "capacity_planning": "Ensure delivery capacity available",
    "notifications": {
        "dispatch": "Order dispatched notification",
        "in_transit": "Package in transit updates",
        "out_for_delivery": "Out for delivery notification",
        "delivered": "Delivery confirmation"
    }
}
```

### 5. Invoice & Payment
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Invoice Generation**:
```python
invoicing = {
    "auto_invoice": "Auto-create on shipment",
    "manual_invoice": "Manual invoice creation",
    "consolidated": "Consolidate multiple deliveries",
    "milestone_billing": "Bill by project milestone",
    "recurring": "Subscription recurring invoices",
    "advance_payment": "Advance payment invoices",
    "final_invoice": "Final invoice after project completion"
}
```

**Payment Collection**:
```python
payment_methods = {
    "credit_card": {
        "processors": ["Stripe", "PayPal", "Square", "Authorize.net"],
        "features": ["Tokenization", "PCI compliance", "Auto-charge on invoice"]
    },
    "ach_bank_transfer": {
        "same_day_ach": "Faster clearing",
        "auto_debit": "Recurring auto-debit"
    },
    "wire_transfer": "International payments",
    "check": "Check payments (manual entry)",
    "cash": "Cash on delivery",
    "financing": "Third-party financing (Affirm, Klarna)"
}
```

**Payment Terms**:
```python
terms = {
    "immediate": "Cash on delivery, prepaid",
    "net_terms": ["Net 15", "Net 30", "Net 60", "Net 90"],
    "early_payment_discount": "2/10 Net 30 (2% discount if paid in 10 days)",
    "installments": "Pay in 3, 6, 12 monthly installments",
    "milestone_based": "Pay upon project milestones",
    "consignment": "Pay as inventory is sold"
}
```

### 6. Returns & Credits
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Sales Return Process**:
```python
return_workflow = {
    "1_return_request": {
        "channels": ["Customer portal", "Email", "Phone", "In-store"],
        "reason_codes": [
            "Defective product",
            "Wrong item shipped",
            "Customer changed mind",
            "Product damaged in transit",
            "Not as described"
        ]
    },
    "2_rma_approval": {
        "auto_approve": "If within return window and valid reason",
        "manual_review": "Manager review for exceptions",
        "restocking_fee": "Apply fee if applicable"
    },
    "3_return_shipment": {
        "return_label": "Email prepaid return label",
        "customer_ships": "Customer arranges return"
    },
    "4_receive_return": {
        "warehouse_receipt": "Scan and receive return",
        "qc_inspection": "Inspect returned item",
        "disposition": ["Restock", "Refurbish", "Scrap"]
    },
    "5_credit_processing": {
        "refund": "Refund to original payment method",
        "store_credit": "Issue store credit",
        "exchange": "Exchange for different product",
        "repair": "Repair and return"
    }
}
```

**Credit Notes**:
```python
credit_note_scenarios = {
    "full_return": "Full refund of invoice",
    "partial_return": "Partial refund for some items",
    "price_adjustment": "Reduce price after sale",
    "damaged_goods": "Credit for damaged items",
    "billing_error": "Correct overcharge",
    "promotional_credit": "Marketing promotion credit"
}
```

### 7. Sales Analytics & Reporting
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Sales Dashboards**:
```python
dashboards = {
    "executive_dashboard": {
        "revenue_today": "Today's revenue vs. target",
        "revenue_mtd": "Month-to-date revenue",
        "revenue_ytd": "Year-to-date revenue",
        "top_products": "Best-selling products",
        "top_customers": "Top customers by revenue",
        "sales_by_region": "Geographic breakdown",
        "conversion_rate": "Quote-to-order conversion"
    },
    "sales_rep_dashboard": {
        "my_quota": "Quota vs. actual",
        "pipeline": "Active quotes",
        "pending_orders": "Orders awaiting fulfillment",
        "this_week_activities": "Calls, emails, meetings",
        "commissions": "Commission earned"
    },
    "operations_dashboard": {
        "orders_to_fulfill": "Orders pending shipping",
        "backorders": "Items on backorder",
        "shipments_today": "Shipments scheduled",
        "avg_fulfillment_time": "Order to ship time",
        "on_time_delivery_rate": "% orders delivered on time"
    }
}
```

**Key Sales Metrics**:
```python
sales_kpis = {
    "revenue_metrics": {
        "total_revenue": "Total sales revenue",
        "revenue_growth": "YoY, MoM growth %",
        "average_order_value": "Revenue / # orders",
        "revenue_per_customer": "Total revenue / # customers"
    },
    "conversion_metrics": {
        "quote_to_order": "% quotes converted to orders",
        "win_rate": "% quotes won vs. lost",
        "cart_abandonment": "% customers abandoning cart (e-commerce)"
    },
    "operational_metrics": {
        "order_fulfillment_time": "Days from order to shipment",
        "on_time_delivery_rate": "% orders delivered on time",
        "backorder_rate": "% orders with backorders",
        "return_rate": "% orders returned",
        "order_accuracy": "% orders shipped without errors"
    },
    "customer_metrics": {
        "customer_acquisition_cost": "Marketing spend / new customers",
        "customer_lifetime_value": "Projected revenue per customer",
        "repeat_purchase_rate": "% customers who reorder",
        "customer_retention_rate": "% customers retained annually"
    }
}
```

**AI Sales Analytics**:
```python
ai_analytics = {
    "sales_forecasting": {
        "inputs": ["Historical sales", "Seasonality", "Trends", "Pipeline"],
        "output": "Monthly revenue forecast ±8% accuracy",
        "scenarios": "Best case, worst case, most likely"
    },
    "customer_segmentation": {
        "rfm_analysis": "Recency, Frequency, Monetary",
        "segments": ["VIP", "Loyal", "At-risk", "New", "Lost"],
        "actions": "Targeted marketing campaigns per segment"
    },
    "product_recommendations": {
        "cross_sell": "Customers who bought X also bought Y",
        "upsell": "Recommend higher-value alternatives",
        "next_best_product": "AI suggests next product to pitch"
    },
    "churn_prediction": {
        "at_risk_customers": "Predict customers likely to churn",
        "retention_actions": "Suggest retention strategies",
        "win_back_campaigns": "Target lost customers"
    },
    "pricing_optimization": {
        "price_elasticity": "How demand changes with price",
        "optimal_price": "Maximize revenue or margin",
        "competitor_monitoring": "Track competitor pricing"
    }
}
```

**Standard Reports**:
```python
sales_reports = {
    "sales_register": "All sales transactions",
    "sales_by_customer": "Revenue per customer",
    "sales_by_product": "Revenue per product",
    "sales_by_territory": "Revenue by region/territory",
    "sales_by_salesperson": "Revenue per sales rep",
    "pending_orders": "Orders not yet fulfilled",
    "backorder_report": "Items on backorder",
    "delivery_performance": "On-time delivery metrics",
    "invoice_aging": "Unpaid invoices by age",
    "sales_trend": "Sales over time (daily, weekly, monthly)",
    "customer_acquisition": "New customers per period",
    "product_performance": "Fast/slow movers"
}
```

### 8. Pricing Management
**Status**: Must-Have | **Competitive Parity**: Advanced

**Price Lists**:
```python
price_list_types = {
    "standard": "Default catalog pricing",
    "customer_specific": "Negotiated pricing per customer",
    "tier_based": ["Platinum", "Gold", "Silver", "Bronze"],
    "volume_based": "Pricing tiers by quantity",
    "regional": "Pricing by country/region",
    "seasonal": "Holiday, summer, winter pricing",
    "promotional": "Campaign-specific pricing"
}
```

**Discount Management**:
```python
discount_types = {
    "percentage": "% off list price",
    "fixed_amount": "$X off",
    "buy_x_get_y": "Buy 2 get 1 free",
    "bundle_discount": "Bundle pricing < sum of parts",
    "volume_discount": "Tiered discounts by quantity",
    "early_payment": "Discount for early payment",
    "seasonal": "Holiday sales, clearance"
}
```

**Margin Management**:
```python
margin_controls = {
    "calculation": {
        "gross_margin": "(Revenue - COGS) / Revenue × 100",
        "contribution_margin": "(Revenue - Variable Costs) / Revenue × 100"
    },
    "targets": {
        "minimum_margin": "20% minimum across all products",
        "target_margin": "35% target margin",
        "high_margin_threshold": "50%+ = premium products"
    },
    "alerts": {
        "below_minimum": "Alert sales rep + require approval",
        "below_target": "Warning to sales rep",
        "negative_margin": "Block order, escalate to director"
    },
    "analysis": {
        "margin_by_product": "Which products are most profitable?",
        "margin_by_customer": "Which customers are most profitable?",
        "margin_trend": "Is margin improving or declining?"
    }
}
```

### 9. Sales Territory Management
**Status**: Should-Have | **Competitive Parity**: Advanced

**Territory Definition**:
```python
territory_types = {
    "geographic": {
        "by_zip": "Zip code based",
        "by_state": "State/province",
        "by_country": "Country",
        "by_region": "North, South, East, West"
    },
    "account_based": {
        "by_industry": "Technology, Healthcare, Finance",
        "by_revenue": "Enterprise, Mid-market, SMB",
        "named_accounts": "Strategic accounts assigned directly"
    },
    "product_based": {
        "by_product_line": "Hardware, Software, Services",
        "by_category": "Specialists per product category"
    }
}
```

**Territory Assignment**:
```python
assignment_rules = {
    "auto_assignment": {
        "new_lead": "Auto-assign to territory owner",
        "new_order": "Route to correct sales rep",
        "reassignment": "Reassign if rep leaves"
    },
    "split_territories": {
        "shared_accounts": "Large accounts with multiple reps",
        "split_commission": "Commission split rules"
    },
    "territory_coverage": {
        "coverage_analysis": "Identify uncovered territories",
        "workload_balancing": "Ensure even distribution"
    }
}
```

**Quota Management**:
```python
quota_setting = {
    "types": {
        "revenue_quota": "Dollar amount target",
        "unit_quota": "Number of units sold",
        "activity_quota": "Calls, meetings, demos"
    },
    "periods": {
        "annual": "Fiscal year quota",
        "quarterly": "Q1, Q2, Q3, Q4 quotas",
        "monthly": "Monthly targets"
    },
    "allocation": {
        "top_down": "Executive sets total, cascades down",
        "bottom_up": "Reps propose, management approves",
        "hybrid": "Combination approach"
    },
    "tracking": {
        "quota_attainment": "% of quota achieved",
        "pace": "On track, behind, ahead",
        "forecast_vs_quota": "Projected vs. quota"
    }
}
```

### 10. Subscription & Recurring Sales
**Status**: Should-Have | **Competitive Advantage**: Advanced

**Subscription Management**:
```python
subscription_model = {
    "billing_frequency": {
        "monthly": "Billed monthly",
        "quarterly": "Billed every 3 months",
        "annual": "Billed annually",
        "usage_based": "Based on consumption"
    },
    "pricing_models": {
        "flat_rate": "Fixed monthly fee",
        "per_user": "$X per user per month",
        "tiered": "Pricing tiers (Starter, Pro, Enterprise)",
        "usage_based": "Pay for what you use",
        "hybrid": "Base fee + usage overage"
    },
    "features": {
        "auto_renewal": "Auto-renew subscriptions",
        "proration": "Prorate for mid-cycle changes",
        "upgrades_downgrades": "Change plans anytime",
        "trial_period": "Free trial conversion",
        "cancellation": "Cancellation workflow",
        "dunning": "Retry failed payments"
    }
}
```

**Revenue Recognition**:
```python
revenue_recognition = {
    "deferred_revenue": "Recognize revenue over subscription period",
    "recognition_schedule": "Monthly/daily recognition",
    "mrr_arr": {
        "mrr": "Monthly Recurring Revenue",
        "arr": "Annual Recurring Revenue",
        "cmrr": "Committed Monthly Recurring Revenue"
    },
    "churn_metrics": {
        "customer_churn": "% customers canceling",
        "revenue_churn": "% revenue lost from cancellations",
        "net_revenue_retention": "Expansion - churn"
    }
}
```

### 11. E-Commerce Integration
**Status**: Should-Have | **Competitive Parity**: Industry Standard

**Channel Integration**:
```python
channels = {
    "own_website": "Integrated e-commerce storefront",
    "marketplaces": {
        "amazon": "Amazon Seller Central",
        "ebay": "eBay integration",
        "walmart": "Walmart Marketplace",
        "etsy": "Etsy shop"
    },
    "platforms": {
        "shopify": "Shopify store sync",
        "woocommerce": "WooCommerce integration",
        "magento": "Magento connector",
        "bigcommerce": "BigCommerce sync"
    }
}
```

**Omnichannel Features**:
```python
omnichannel = {
    "inventory_sync": "Real-time inventory across all channels",
    "order_aggregation": "All orders in single dashboard",
    "unified_customer": "Single customer record across channels",
    "pricing_sync": "Consistent pricing across channels",
    "fulfillment": "Fulfill from any warehouse to any channel",
    "returns": "Process returns from any channel"
}
```

### 12. Mobile Sales App
**Status**: Should-Have | **Competitive Parity**: Industry Standard

**Mobile Capabilities**:
```python
mobile_app = {
    "quote_creation": "Create quotes on the go",
    "product_catalog": "Browse products, check stock",
    "customer_lookup": "View customer history",
    "order_taking": "Take orders at customer site",
    "signature_capture": "Capture customer signature",
    "payment_collection": "Accept card payments (mobile reader)",
    "offline_mode": "Work offline, sync when online",
    "camera": "Scan barcodes, take product photos",
    "gps_check_in": "Check-in at customer location",
    "route_planning": "Optimize visit routes"
}
```

---

## AI Agent Integration

### Sales AI Agents

**1. Quote Assistant Agent**
```python
agent_capabilities = {
    "quote_generation": "Auto-generate quotes from customer requirements",
    "product_recommendation": "Suggest products based on customer profile",
    "pricing_optimization": "Recommend optimal pricing (win probability × margin)",
    "competitive_pricing": "Alert if competitor offers better price",
    "upsell_suggestions": "Suggest add-ons and upgrades",
    "quote_follow_up": "Auto-follow-up on pending quotes"
}
```

**2. Demand Forecasting Agent**
```python
agent_capabilities = {
    "sales_forecast": "Predict sales for next 90 days using ML",
    "seasonality_detection": "Identify seasonal patterns",
    "trend_analysis": "Detect product trends (growing/declining)",
    "promotion_impact": "Model impact of promotions on sales",
    "stockout_prevention": "Alert if forecast exceeds inventory",
    "pipeline_forecast": "Convert sales pipeline to revenue forecast"
}
```

**3. Customer Success Agent**
```python
agent_capabilities = {
    "churn_prediction": "Identify at-risk customers",
    "health_scoring": "Score customer health (usage, satisfaction, payments)",
    "expansion_opportunities": "Identify upsell/cross-sell opportunities",
    "renewal_reminders": "Proactive subscription renewal outreach",
    "sentiment_analysis": "Analyze customer communications for sentiment",
    "auto_escalation": "Escalate unhappy customers to CS team"
}
```

**4. Order Fulfillment Agent**
```python
agent_capabilities = {
    "auto_allocation": "Auto-allocate stock from optimal warehouse",
    "split_order_optimization": "Minimize split shipments",
    "carrier_selection": "Choose best carrier (cost vs. speed)",
    "delivery_date_prediction": "Predict accurate delivery date",
    "exception_handling": "Auto-handle fulfillment exceptions",
    "proactive_communication": "Auto-notify customers of delays"
}
```

**5. Revenue Optimization Agent**
```python
agent_capabilities = {
    "dynamic_pricing": "Adjust prices based on demand, competition, inventory",
    "promotion_optimization": "Optimize discount levels for max revenue",
    "product_mix_optimization": "Suggest optimal product mix",
    "customer_lifetime_value": "Calculate and predict CLV",
    "margin_maximization": "Balance volume vs. margin",
    "markdown_optimization": "Optimize clearance pricing"
}
```

---

## Database Schema

```sql
-- Quotations
CREATE TABLE quotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Quote Info
    quote_no VARCHAR(100) NOT NULL,
    quote_date DATE NOT NULL,
    valid_until DATE NOT NULL,

    -- Customer
    customer_id UUID REFERENCES customers(id),
    contact_id UUID REFERENCES contacts(id),

    -- Opportunity
    opportunity_id UUID REFERENCES opportunities(id),

    -- Addresses
    billing_address JSONB,
    shipping_address JSONB,

    -- Amounts
    subtotal DECIMAL(15, 2) NOT NULL,
    discount_amount DECIMAL(15, 2) DEFAULT 0,
    tax_amount DECIMAL(15, 2) DEFAULT 0,
    shipping_amount DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,

    -- Currency
    currency VARCHAR(3) DEFAULT 'USD',
    exchange_rate DECIMAL(12, 6) DEFAULT 1,

    -- Terms
    payment_terms VARCHAR(100),
    delivery_terms VARCHAR(100),
    notes TEXT,
    terms_conditions TEXT,

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, sent, accepted, rejected, expired, converted

    -- Tracking
    sent_at TIMESTAMPTZ,
    viewed_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    rejection_reason TEXT,

    -- Conversion
    converted_to_order BOOLEAN DEFAULT false,
    sales_order_id UUID REFERENCES sales_orders(id),

    -- Version Control
    version INTEGER DEFAULT 1,
    parent_quote_id UUID REFERENCES quotations(id),

    -- Assignment
    sales_rep_id UUID REFERENCES users(id),

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, quote_no),
    INDEX idx_customer (customer_id),
    INDEX idx_status (status),
    INDEX idx_sales_rep (sales_rep_id)
);

-- Quotation Items
CREATE TABLE quotation_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quotation_id UUID REFERENCES quotations(id) ON DELETE CASCADE,

    -- Item
    item_id UUID REFERENCES items(id) NOT NULL,
    item_name VARCHAR(255),
    description TEXT,

    -- Quantity & UOM
    qty DECIMAL(15, 4) NOT NULL,
    uom VARCHAR(50),

    -- Pricing
    list_price DECIMAL(15, 2),
    discount_percent DECIMAL(5, 2) DEFAULT 0,
    discount_amount DECIMAL(15, 2) DEFAULT 0,
    unit_price DECIMAL(15, 2) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,

    -- Tax
    tax_template_id UUID REFERENCES tax_templates(id),
    tax_amount DECIMAL(15, 2) DEFAULT 0,

    -- Delivery
    delivery_date DATE,
    warehouse_id UUID REFERENCES warehouses(id),

    -- Configuration (for CPQ)
    configuration JSONB,

    -- Margin
    cost_price DECIMAL(15, 2),
    margin_amount DECIMAL(15, 2),
    margin_percent DECIMAL(5, 2),

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_quotation (quotation_id),
    INDEX idx_item (item_id)
);

-- Sales Orders
CREATE TABLE sales_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Order Info
    order_no VARCHAR(100) NOT NULL,
    order_date DATE NOT NULL,
    delivery_date DATE,

    -- Customer
    customer_id UUID REFERENCES customers(id) NOT NULL,
    contact_id UUID REFERENCES contacts(id),

    -- Reference
    customer_po_no VARCHAR(100),
    quotation_id UUID REFERENCES quotations(id),

    -- Addresses
    billing_address JSONB NOT NULL,
    shipping_address JSONB NOT NULL,

    -- Amounts
    subtotal DECIMAL(15, 2) NOT NULL,
    discount_amount DECIMAL(15, 2) DEFAULT 0,
    tax_amount DECIMAL(15, 2) DEFAULT 0,
    shipping_amount DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,

    -- Currency
    currency VARCHAR(3) DEFAULT 'USD',
    exchange_rate DECIMAL(12, 6) DEFAULT 1,

    -- Terms
    payment_terms VARCHAR(100),
    delivery_terms VARCHAR(100),
    notes TEXT,

    -- Order Type
    order_type VARCHAR(50) DEFAULT 'standard', -- standard, dropship, backorder, rental, service

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, confirmed, picking, packing, ready_to_ship, shipped, delivered, cancelled
    billing_status VARCHAR(50) DEFAULT 'unbilled', -- unbilled, partially_billed, fully_billed
    delivery_status VARCHAR(50) DEFAULT 'not_delivered', -- not_delivered, partially_delivered, fully_delivered

    -- Fulfillment
    warehouse_id UUID REFERENCES warehouses(id),
    stock_reserved BOOLEAN DEFAULT false,

    -- Approval
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    -- Assignment
    sales_rep_id UUID REFERENCES users(id),

    -- Tracking
    confirmed_at TIMESTAMPTZ,
    shipped_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, order_no),
    INDEX idx_customer (customer_id),
    INDEX idx_status (status),
    INDEX idx_order_date (order_date),
    INDEX idx_sales_rep (sales_rep_id)
);

-- Sales Order Items
CREATE TABLE sales_order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sales_order_id UUID REFERENCES sales_orders(id) ON DELETE CASCADE,

    -- Item
    item_id UUID REFERENCES items(id) NOT NULL,
    item_name VARCHAR(255),
    description TEXT,

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    delivered_qty DECIMAL(15, 4) DEFAULT 0,
    billed_qty DECIMAL(15, 4) DEFAULT 0,
    uom VARCHAR(50),

    -- Pricing
    unit_price DECIMAL(15, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) DEFAULT 0,
    discount_amount DECIMAL(15, 2) DEFAULT 0,
    amount DECIMAL(15, 2) NOT NULL,

    -- Tax
    tax_template_id UUID REFERENCES tax_templates(id),
    tax_amount DECIMAL(15, 2) DEFAULT 0,

    -- Delivery
    delivery_date DATE,
    warehouse_id UUID REFERENCES warehouses(id),

    -- Stock
    stock_reserved BOOLEAN DEFAULT false,
    stock_reserved_qty DECIMAL(15, 4) DEFAULT 0,

    -- Configuration
    configuration JSONB,

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_nos TEXT[], -- Array of serial numbers

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_sales_order (sales_order_id),
    INDEX idx_item (item_id)
);

-- Delivery Notes / Packing Slips
CREATE TABLE delivery_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Delivery Info
    delivery_no VARCHAR(100) NOT NULL,
    delivery_date DATE NOT NULL,

    -- Sales Order
    sales_order_id UUID REFERENCES sales_orders(id) NOT NULL,
    customer_id UUID REFERENCES customers(id) NOT NULL,

    -- Address
    shipping_address JSONB NOT NULL,

    -- Warehouse
    warehouse_id UUID REFERENCES warehouses(id) NOT NULL,

    -- Shipping
    carrier VARCHAR(255),
    tracking_number VARCHAR(255),
    shipping_method VARCHAR(100),

    -- Package Info
    packages INTEGER DEFAULT 1,
    total_weight_kg DECIMAL(10, 2),
    total_volume_cbm DECIMAL(10, 2),

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, packed, shipped, in_transit, delivered, cancelled

    -- Tracking
    shipped_at TIMESTAMPTZ,
    estimated_delivery TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,

    -- Proof of Delivery
    delivered_to VARCHAR(255),
    signature_image TEXT, -- Base64 encoded signature
    delivery_notes TEXT,

    -- Invoice
    invoice_created BOOLEAN DEFAULT false,
    invoice_id UUID REFERENCES customer_invoices(id),

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, delivery_no),
    INDEX idx_sales_order (sales_order_id),
    INDEX idx_customer (customer_id),
    INDEX idx_status (status),
    INDEX idx_tracking (tracking_number)
);

-- Delivery Note Items
CREATE TABLE delivery_note_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delivery_note_id UUID REFERENCES delivery_notes(id) ON DELETE CASCADE,
    sales_order_item_id UUID REFERENCES sales_order_items(id),

    -- Item
    item_id UUID REFERENCES items(id) NOT NULL,
    item_name VARCHAR(255),

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    uom VARCHAR(50),

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_nos TEXT[],

    -- Location
    from_location_id UUID REFERENCES storage_locations(id),

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_delivery_note (delivery_note_id),
    INDEX idx_item (item_id)
);

-- Sales Returns (RMA)
CREATE TABLE sales_returns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Return Info
    return_no VARCHAR(100) NOT NULL,
    return_date DATE NOT NULL,

    -- Customer & Order
    customer_id UUID REFERENCES customers(id) NOT NULL,
    sales_order_id UUID REFERENCES sales_orders(id),
    delivery_note_id UUID REFERENCES delivery_notes(id),
    invoice_id UUID REFERENCES customer_invoices(id),

    -- Return Reason
    reason_code VARCHAR(100), -- defective, wrong_item, changed_mind, damaged, etc.
    reason_description TEXT,

    -- Amounts
    subtotal DECIMAL(15, 2) NOT NULL,
    tax_amount DECIMAL(15, 2) DEFAULT 0,
    restocking_fee DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,

    -- Status
    status VARCHAR(50) DEFAULT 'requested', -- requested, approved, rejected, received, completed, cancelled

    -- RMA
    rma_number VARCHAR(100),
    return_label_sent BOOLEAN DEFAULT false,

    -- Warehouse
    return_warehouse_id UUID REFERENCES warehouses(id),

    -- Resolution
    resolution_type VARCHAR(50), -- refund, exchange, store_credit, repair
    credit_note_id UUID REFERENCES credit_notes(id),

    -- Approval
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    -- Tracking
    received_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, return_no),
    INDEX idx_customer (customer_id),
    INDEX idx_sales_order (sales_order_id),
    INDEX idx_status (status)
);

-- Sales Return Items
CREATE TABLE sales_return_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sales_return_id UUID REFERENCES sales_returns(id) ON DELETE CASCADE,
    sales_order_item_id UUID REFERENCES sales_order_items(id),

    -- Item
    item_id UUID REFERENCES items(id) NOT NULL,
    item_name VARCHAR(255),

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    received_qty DECIMAL(15, 4) DEFAULT 0,
    uom VARCHAR(50),

    -- Pricing
    unit_price DECIMAL(15, 2) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_nos TEXT[],

    -- QC
    qc_status VARCHAR(50), -- pending, passed, failed
    qc_notes TEXT,

    -- Disposition
    disposition VARCHAR(50), -- restock, refurbish, scrap, return_to_vendor

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_sales_return (sales_return_id),
    INDEX idx_item (item_id)
);

-- Price Lists
CREATE TABLE price_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    price_list_name VARCHAR(255) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',

    -- Applicability
    valid_from DATE,
    valid_to DATE,

    -- Priority (higher number = higher priority)
    priority INTEGER DEFAULT 0,

    active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant (tenant_id)
);

-- Price List Items
CREATE TABLE price_list_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    price_list_id UUID REFERENCES price_lists(id) ON DELETE CASCADE,

    item_id UUID REFERENCES items(id) NOT NULL,

    price DECIMAL(15, 2) NOT NULL,

    -- Quantity Tiers
    min_qty DECIMAL(15, 4) DEFAULT 1,
    max_qty DECIMAL(15, 4),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_price_list (price_list_id),
    INDEX idx_item (item_id)
);

-- Customer Price Lists (customer-specific pricing)
CREATE TABLE customer_price_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id),
    price_list_id UUID REFERENCES price_lists(id),

    valid_from DATE,
    valid_to DATE,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_customer (customer_id)
);

-- Sales Territories
CREATE TABLE sales_territories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    territory_name VARCHAR(255) NOT NULL,
    territory_code VARCHAR(50),

    -- Territory Definition
    territory_type VARCHAR(50), -- geographic, industry, account_size

    -- Geographic
    countries TEXT[],
    states TEXT[],
    zip_codes TEXT[],

    -- Industry
    industries TEXT[],

    -- Parent Territory
    parent_territory_id UUID REFERENCES sales_territories(id),

    -- Assignment
    territory_manager_id UUID REFERENCES users(id),

    active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant (tenant_id),
    INDEX idx_manager (territory_manager_id)
);

-- Sales Quotas
CREATE TABLE sales_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Assignment
    sales_rep_id UUID REFERENCES users(id),
    territory_id UUID REFERENCES sales_territories(id),

    -- Period
    fiscal_year INTEGER NOT NULL,
    period_type VARCHAR(50), -- annual, quarterly, monthly
    period_number INTEGER, -- Q1-4 or 1-12

    -- Quota
    quota_type VARCHAR(50), -- revenue, units, activities
    quota_amount DECIMAL(15, 2) NOT NULL,

    -- Actual
    actual_amount DECIMAL(15, 2) DEFAULT 0,
    attainment_percent DECIMAL(5, 2) DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_sales_rep (sales_rep_id),
    INDEX idx_period (fiscal_year, period_number)
);

-- Subscriptions
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Subscription Info
    subscription_no VARCHAR(100) NOT NULL,
    customer_id UUID REFERENCES customers(id) NOT NULL,

    -- Plan
    plan_name VARCHAR(255) NOT NULL,
    plan_id UUID REFERENCES subscription_plans(id),

    -- Billing
    billing_frequency VARCHAR(50), -- monthly, quarterly, annual
    billing_amount DECIMAL(15, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',

    -- Dates
    start_date DATE NOT NULL,
    end_date DATE,
    next_billing_date DATE,

    -- Status
    status VARCHAR(50) DEFAULT 'active', -- trial, active, paused, cancelled, expired

    -- Trial
    trial_period_days INTEGER,
    trial_end_date DATE,

    -- Auto-Renewal
    auto_renew BOOLEAN DEFAULT true,

    -- Payment Method
    payment_method_id UUID REFERENCES payment_methods(id),

    -- Cancellation
    cancelled_at TIMESTAMPTZ,
    cancellation_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, subscription_no),
    INDEX idx_customer (customer_id),
    INDEX idx_status (status),
    INDEX idx_next_billing (next_billing_date)
);

-- Sales Analytics (Aggregated Metrics)
CREATE TABLE sales_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Period
    period_date DATE NOT NULL,
    period_type VARCHAR(20), -- daily, weekly, monthly

    -- Dimensions
    product_id UUID REFERENCES items(id),
    customer_id UUID REFERENCES customers(id),
    sales_rep_id UUID REFERENCES users(id),
    territory_id UUID REFERENCES sales_territories(id),

    -- Metrics
    orders_count INTEGER DEFAULT 0,
    revenue DECIMAL(15, 2) DEFAULT 0,
    units_sold DECIMAL(15, 4) DEFAULT 0,
    avg_order_value DECIMAL(15, 2) DEFAULT 0,

    -- Costs & Margin
    cogs DECIMAL(15, 2) DEFAULT 0,
    gross_margin DECIMAL(15, 2) DEFAULT 0,
    gross_margin_percent DECIMAL(5, 2) DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_date (tenant_id, period_date),
    INDEX idx_product (product_id),
    INDEX idx_customer (customer_id),
    INDEX idx_sales_rep (sales_rep_id)
);
```

---

## API Specification

### Quotation APIs

```python
# Create Quotation
POST /api/v1/sales/quotations
Request: {
    "customer_id": "uuid",
    "quote_date": "2025-11-10",
    "valid_until": "2025-12-10",
    "items": [
        {
            "item_id": "uuid",
            "qty": 10,
            "unit_price": 100.00,
            "discount_percent": 5
        }
    ],
    "payment_terms": "Net 30",
    "notes": "Special pricing for valued customer"
}

# Send Quotation
POST /api/v1/sales/quotations/{id}/send
Request: {
    "recipients": ["customer@example.com"],
    "subject": "Quote Q-2025-001 from SARAISE",
    "message": "Please find attached quotation.",
    "attach_pdf": true
}

# Accept/Reject Quotation
POST /api/v1/sales/quotations/{id}/accept
POST /api/v1/sales/quotations/{id}/reject
Request: {
    "reason": "Pricing too high" # for reject
}

# Convert to Sales Order
POST /api/v1/sales/quotations/{id}/convert-to-order
Response: {
    "sales_order_id": "uuid",
    "order_no": "SO-2025-001"
}
```

### Sales Order APIs

```python
# Create Sales Order
POST /api/v1/sales/orders
Request: {
    "customer_id": "uuid",
    "order_date": "2025-11-10",
    "delivery_date": "2025-11-20",
    "items": [
        {
            "item_id": "uuid",
            "qty": 5,
            "unit_price": 150.00,
            "warehouse_id": "uuid"
        }
    ],
    "shipping_address": {...},
    "payment_terms": "Net 30"
}

# Confirm Order (Reserve Stock)
POST /api/v1/sales/orders/{id}/confirm

# Create Pick List
POST /api/v1/sales/orders/{id}/create-pick-list

# Create Shipment
POST /api/v1/sales/orders/{id}/create-shipment
Request: {
    "items": [
        {
            "item_id": "uuid",
            "qty": 5,
            "serial_nos": ["SN001", "SN002", "SN003", "SN004", "SN005"]
        }
    ],
    "carrier": "FedEx",
    "shipping_method": "Ground"
}

# Mark as Shipped
POST /api/v1/sales/orders/{id}/ship
Request: {
    "tracking_number": "1234567890",
    "shipped_at": "2025-11-10T14:30:00Z"
}

# Create Invoice
POST /api/v1/sales/orders/{id}/create-invoice
```

### Delivery Note APIs

```python
# Get Delivery Note
GET /api/v1/sales/delivery-notes/{id}

# Update Tracking
PUT /api/v1/sales/delivery-notes/{id}/tracking
Request: {
    "tracking_number": "1234567890",
    "carrier": "FedEx",
    "estimated_delivery": "2025-11-15"
}

# Mark Delivered
POST /api/v1/sales/delivery-notes/{id}/deliver
Request: {
    "delivered_to": "John Doe",
    "signature_image": "base64_encoded_signature",
    "delivery_notes": "Left at front door"
}
```

### Sales Return APIs

```python
# Create Sales Return
POST /api/v1/sales/returns
Request: {
    "customer_id": "uuid",
    "sales_order_id": "uuid",
    "reason_code": "defective",
    "reason_description": "Product not working",
    "items": [
        {
            "item_id": "uuid",
            "qty": 2,
            "unit_price": 100.00
        }
    ]
}

# Approve Return (Generate RMA)
POST /api/v1/sales/returns/{id}/approve
Response: {
    "rma_number": "RMA-2025-001",
    "return_label_url": "https://..."
}

# Receive Return
POST /api/v1/sales/returns/{id}/receive
Request: {
    "items": [
        {
            "item_id": "uuid",
            "received_qty": 2,
            "qc_status": "passed",
            "disposition": "restock"
        }
    ]
}

# Process Refund
POST /api/v1/sales/returns/{id}/refund
Request: {
    "refund_amount": 200.00,
    "refund_method": "original_payment"
}
```

### Pricing APIs

```python
# Get Price for Customer
GET /api/v1/sales/pricing
Query Params: ?customer_id=uuid&item_id=uuid&qty=10&date=2025-11-10
Response: {
    "item_id": "uuid",
    "list_price": 100.00,
    "customer_price": 85.00,
    "discount_percent": 15,
    "final_price": 85.00,
    "price_list": "Gold Customer Pricing"
}

# AI Price Optimization
POST /api/v1/sales/pricing/optimize
Request: {
    "item_id": "uuid",
    "customer_id": "uuid",
    "competitor_price": 90.00,
    "target_margin_percent": 30
}
Response: {
    "recommended_price": 88.00,
    "expected_win_probability": 0.75,
    "expected_margin_percent": 28,
    "reasoning": "Price 2% below competitor with acceptable margin"
}
```

### Sales Analytics APIs

```python
# Sales Dashboard
GET /api/v1/sales/analytics/dashboard
Query Params: ?period=month&sales_rep_id=uuid
Response: {
    "revenue": {
        "today": 15000.00,
        "mtd": 450000.00,
        "ytd": 5400000.00,
        "target_mtd": 500000.00,
        "attainment_percent": 90
    },
    "orders": {
        "pending": 25,
        "to_ship": 15,
        "shipped_today": 10
    },
    "top_products": [...],
    "top_customers": [...]
}

# Sales Forecast
GET /api/v1/sales/analytics/forecast
Query Params: ?months=3
Response: {
    "forecast_period": "3 months",
    "forecast": [
        {
            "month": "2025-12",
            "predicted_revenue": 520000.00,
            "confidence_interval": {
                "lower": 480000.00,
                "upper": 560000.00
            },
            "model_accuracy": 92.5
        }
    ]
}

# Customer Segmentation
GET /api/v1/sales/analytics/customer-segmentation
Response: {
    "segments": [
        {
            "segment": "VIP",
            "customer_count": 50,
            "total_revenue": 2000000.00,
            "avg_order_value": 5000.00,
            "characteristics": "High value, frequent buyers"
        }
    ]
}

# Product Performance
GET /api/v1/sales/analytics/product-performance
Query Params: ?from_date=2025-01-01&to_date=2025-11-10
Response: {
    "products": [
        {
            "item_name": "Laptop Pro",
            "units_sold": 500,
            "revenue": 500000.00,
            "margin_percent": 35,
            "classification": "fast_moving"
        }
    ]
}
```

---

## Security Considerations

### Access Controls

```python
sales_permissions = {
    "sales.quotations.view": "View quotations",
    "sales.quotations.create": "Create quotations",
    "sales.quotations.send": "Send quotations to customers",
    "sales.quotations.approve": "Approve discounts beyond limit",

    "sales.orders.view": "View sales orders",
    "sales.orders.create": "Create sales orders",
    "sales.orders.confirm": "Confirm orders (reserve stock)",
    "sales.orders.cancel": "Cancel orders",

    "sales.deliveries.view": "View deliveries",
    "sales.deliveries.create": "Create delivery notes",
    "sales.deliveries.ship": "Mark as shipped",

    "sales.returns.view": "View returns",
    "sales.returns.create": "Create returns",
    "sales.returns.approve": "Approve returns",
    "sales.returns.process": "Process refunds",

    "sales.pricing.view": "View pricing",
    "sales.pricing.override": "Override prices manually",

    "sales.analytics.view": "View sales reports",
    "sales.analytics.export": "Export reports",

    "sales.customers.view_all": "View all customers (not just assigned)",
    "sales.revenue.view_all": "View company-wide revenue (vs. personal)"
}
```

### Data Security

```python
security_features = {
    "customer_data_privacy": {
        "pci_compliance": "PCI-DSS for credit card data",
        "gdpr_compliance": "GDPR for EU customers",
        "data_encryption": "Encrypt sensitive customer data",
        "access_logs": "Log all customer data access"
    },
    "pricing_confidentiality": {
        "customer_specific_pricing": "Hide from other customers",
        "cost_data": "Restrict access to cost/margin data",
        "discount_approvals": "Audit trail of discount approvals"
    },
    "fraud_prevention": {
        "credit_limit_checks": "Enforce customer credit limits",
        "velocity_checks": "Flag unusual order volumes",
        "address_verification": "AVS for card payments",
        "geolocation_checks": "Flag mismatched locations"
    }
}
```

### Audit Trail

```python
audit_events = {
    "quote_created": "Who, when, for which customer",
    "quote_sent": "Sent to whom, when",
    "quote_accepted": "Accepted by, IP address",
    "order_created": "Who created, customer, amount",
    "price_override": "Original price, override price, approved by",
    "order_cancelled": "Cancelled by, reason",
    "shipment_created": "Shipped by, carrier, tracking",
    "return_processed": "Return reason, refund amount, processed by"
}
```

---

## Implementation Roadmap

### Phase 1: Core Sales (Month 1-2)
- [ ] Quotation management
- [ ] Sales order processing
- [ ] Customer master data
- [ ] Product catalog
- [ ] Basic pricing and discounts

### Phase 2: Fulfillment (Month 3)
- [ ] Delivery note/packing slip
- [ ] Shipping carrier integration
- [ ] Stock reservation and allocation
- [ ] Invoice generation
- [ ] Payment integration (Stripe)

### Phase 3: Returns & CPQ (Month 4)
- [ ] Sales returns (RMA)
- [ ] Credit notes and refunds
- [ ] CPQ (Configure, Price, Quote)
- [ ] Advanced pricing rules
- [ ] Approval workflows

### Phase 4: Analytics & Reporting (Month 5)
- [ ] Sales dashboards
- [ ] Revenue analytics
- [ ] Product performance reports
- [ ] Customer analytics
- [ ] Territory and quota management

### Phase 5: Advanced Features (Month 6)
- [ ] AI sales forecasting
- [ ] Customer segmentation
- [ ] Price optimization
- [ ] Subscription management
- [ ] E-commerce integration

### Phase 6: AI & Automation (Month 7)
- [ ] Quote automation agent
- [ ] Demand forecasting agent
- [ ] Customer success agent
- [ ] Order fulfillment optimization
- [ ] Dynamic pricing AI

---

## Competitive Analysis

| Feature | SARAISE | SAP S/4HANA | Oracle NetSuite | Microsoft D365 | Odoo Sales |
|---------|---------|-------------|-----------------|----------------|------------|
| **Quote Management** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **CPQ** | ✓ Advanced | ✓ | ✓ Add-on | ✓ | ✓ Basic |
| **Order Management** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Multi-Warehouse** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Shipping Integration** | ✓ | ✓ | ✓ | ✓ | ✓ Limited |
| **Returns (RMA)** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **AI Forecasting** | ✓ ML-powered | ✓ | ✓ Add-on | ✓ Copilot | ✗ |
| **Price Optimization** | ✓ AI-driven | ✓ | ✗ | ✓ | ✗ |
| **Customer Segmentation** | ✓ AI RFM | ✓ | ✓ | ✓ | ✓ Basic |
| **Subscription Billing** | ✓ | ✓ Add-on | ✓ | ✓ | ✗ |
| **E-commerce Integration** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Mobile App** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **API-First** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Pricing** | $$ | $$$$ | $$$ | $$$ | $ |

**Verdict**: Matches SAP/Oracle/Microsoft on core features with superior AI forecasting and pricing optimization at significantly lower cost.

---

## Success Metrics

- **Quote-to-Order Conversion**: > 30% (quotes converted to orders)
- **Order Fulfillment Time**: < 24 hours (order to shipment)
- **On-Time Delivery**: > 95% (orders delivered on time)
- **Order Accuracy**: > 99% (correct items shipped)
- **Return Rate**: < 3% (orders returned)
- **Sales Forecast Accuracy**: MAPE < 8% (forecast vs. actual revenue)
- **Average Order Value**: Increase by 20% (through upselling)
- **Customer Satisfaction**: > 4.5/5 (delivery experience)
- **Revenue per Sales Rep**: Increase by 25% (automation efficiency)
- **Margin Improvement**: Increase by 5% (pricing optimization)
- **ROI**: 5x return in year 1 (faster sales cycle + higher margins)

---

**Document Control**:
- **Author**: SARAISE Architecture Team
- **Last Updated**: 2025-11-10
- **Status**: Planning - Ready for Implementation
