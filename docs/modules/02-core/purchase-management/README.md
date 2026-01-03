<!-- SPDX-License-Identifier: Apache-2.0 -->
# Purchase & Procurement Management Module

**Module Code**: `purchase`
**Category**: Core Business
**Priority**: Critical - Supply Chain Management
**Version**: 1.0.0
**Status**: Implementation Complete

---

## Executive Summary

The Purchase & Procurement Management module provides comprehensive **procure-to-pay** workflow from purchase requisitions to supplier invoices, payments, and supplier performance analytics. Powered by AI agents, this module automates supplier selection, price negotiation, purchase order generation, and spend analytics—delivering a world-class procurement experience that rivals SAP Ariba, Oracle Procurement Cloud, Microsoft Dynamics 365 Supply Chain, and Odoo Purchase.

### Vision

**"Every purchase optimized for cost, quality, and delivery through AI-powered procurement intelligence."**

---

## World-Class Features

### 1. Purchase Requisition
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Requisition Creation**:
```python
requisition_sources = {
    "manual": "Employee creates requisition",
    "auto_reorder": "Auto-generated from reorder point",
    "mrp": "Generated from production planning",
    "project": "Project material requirements",
    "sales_order": "Dropship or special order",
    "maintenance": "Maintenance work orders"
}
```

**Requisition Workflow**:
```python
workflow = {
    "1_create": {
        "requester": "Employee submits request",
        "fields": ["Item", "Quantity", "Required by date", "Purpose"],
        "attachments": "Specs, drawings, quotes"
    },
    "2_approval": {
        "dept_manager": "Manager approves need",
        "procurement": "Procurement reviews sourcing options",
        "finance": "Budget approval if required",
        "parallel_sequential": "Configurable approval routing"
    },
    "3_sourcing": {
        "rfq_creation": "Create RFQ if needed",
        "supplier_selection": "Choose supplier(s)",
        "price_negotiation": "Negotiate pricing"
    },
    "4_conversion": {
        "create_po": "Convert approved requisition to PO",
        "consolidation": "Consolidate multiple requisitions to single PO"
    }
}
```

**Approval Rules**:
```python
approval_matrix = {
    "amount_based": {
        "0_1000": "Manager approval only",
        "1000_10000": "Manager + Procurement",
        "10000_plus": "Manager + Procurement + Finance Director"
    },
    "category_based": {
        "office_supplies": "Manager approval",
        "it_equipment": "Manager + IT Director",
        "capital_equipment": "CFO approval",
        "services": "VP approval"
    },
    "budget_check": {
        "within_budget": "Standard approval",
        "over_budget": "Additional CFO approval"
    }
}
```

### 2. Request for Quotation (RFQ)
**Status**: Must-Have | **Competitive Parity**: Advanced

**RFQ Process**:
```python
rfq_workflow = {
    "1_create_rfq": {
        "from_requisition": "Create from requisition",
        "ad_hoc": "Direct RFQ creation",
        "items": "List items with specs and quantities",
        "terms": "Payment terms, delivery requirements"
    },
    "2_invite_suppliers": {
        "supplier_list": "Select from approved supplier list",
        "new_suppliers": "Invite new suppliers",
        "broadcast": "Public tender posting",
        "portal_access": "Suppliers access via supplier portal"
    },
    "3_quote_submission": {
        "online_submission": "Suppliers submit quotes online",
        "email_submission": "Email quotes (auto-import)",
        "deadline": "Quote submission deadline",
        "amendments": "Allow quote amendments before deadline"
    },
    "4_quote_comparison": {
        "side_by_side": "Compare quotes side-by-side",
        "scoring": "Weighted scoring (price, quality, delivery)",
        "negotiation": "Negotiate with selected suppliers",
        "ai_recommendation": "AI suggests best supplier"
    },
    "5_award": {
        "award_po": "Award PO to winning supplier(s)",
        "notify_losers": "Notify unsuccessful suppliers",
        "split_award": "Split among multiple suppliers"
    }
}
```

**Supplier Scoring**:
```python
scoring_model = {
    "price": {
        "weight": 50,
        "calculation": "Lowest price = 100 points, others proportional"
    },
    "quality": {
        "weight": 30,
        "factors": ["Defect rate", "Certification", "Past performance"]
    },
    "delivery": {
        "weight": 15,
        "factors": ["Lead time", "On-time delivery history"]
    },
    "service": {
        "weight": 5,
        "factors": ["Responsiveness", "Support quality"]
    },
    "total_score": "Weighted sum (0-100)"
}
```

### 3. Purchase Order Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**PO Creation**:
```python
po_sources = {
    "from_rfq": "Convert RFQ award to PO",
    "from_requisition": "Convert approved requisition to PO",
    "direct_po": "Direct PO creation",
    "blanket_po": "Long-term purchase agreement",
    "auto_po": "Auto-generated from reorder rules",
    "dropship": "Dropship PO from sales order"
}
```

**PO Types**:
```python
po_types = {
    "standard_po": "One-time purchase",
    "blanket_po": {
        "definition": "Contract for recurring purchases over period",
        "release_orders": "Release orders against blanket PO",
        "use_case": "Office supplies, raw materials"
    },
    "contract_po": {
        "definition": "Long-term contract with pricing",
        "use_case": "Managed services, subscriptions"
    },
    "dropship_po": {
        "definition": "Ship directly to customer",
        "link": "Linked to sales order"
    }
}
```

**PO Workflow**:
```python
po_lifecycle = {
    "1_draft": {
        "status": "Draft",
        "actions": ["Edit items", "Change supplier", "Modify terms"]
    },
    "2_approval": {
        "status": "Pending Approval",
        "rules": "Same as requisition approval",
        "actions": ["Approve", "Reject", "Request changes"]
    },
    "3_sent": {
        "status": "Sent to Supplier",
        "delivery": ["Email PDF", "EDI", "Supplier portal"],
        "acknowledgment": "Supplier acknowledges receipt"
    },
    "4_confirmed": {
        "status": "Confirmed by Supplier",
        "changes": "Supplier can propose changes",
        "acceptance": "Buyer accepts or negotiates"
    },
    "5_receiving": {
        "status": "Partially Received / Fully Received",
        "goods_receipt": "Warehouse receives items",
        "3_way_match": "PO ↔ GRN ↔ Invoice"
    },
    "6_invoiced": {
        "status": "Partially Invoiced / Fully Invoiced",
        "invoice_matching": "Match invoice to PO + GRN"
    },
    "7_paid": {
        "status": "Paid",
        "payment": "Payment processed"
    },
    "8_closed": {
        "status": "Closed",
        "reason": "Completed or cancelled"
    }
}
```

**PO Terms & Conditions**:
```python
po_terms = {
    "payment_terms": ["COD", "Net 15", "Net 30", "Net 60", "2/10 Net 30"],
    "delivery_terms": ["FOB Origin", "FOB Destination", "CIF", "DDP"],
    "shipping_method": ["Ground", "Air", "Ocean freight", "Courier"],
    "quality_standards": "Specifications and acceptance criteria",
    "warranty": "Warranty terms",
    "penalties": "Late delivery penalties",
    "cancellation": "Cancellation policy"
}
```

### 4. Goods Receipt & Inspection
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Receiving Process**:
```python
receiving_workflow = {
    "1_arrival": {
        "notification": "Carrier notification of delivery",
        "schedule": "Schedule receiving appointment",
        "dock_assignment": "Assign dock door"
    },
    "2_unloading": {
        "inspect_packaging": "Check for damage",
        "count_packages": "Count boxes/pallets",
        "scan_barcode": "Scan delivery barcode"
    },
    "3_verification": {
        "match_po": "Match to PO",
        "verify_qty": "Verify quantity",
        "verify_items": "Verify correct items",
        "discrepancy": "Flag over/under shipments"
    },
    "4_qc_inspection": {
        "sample_inspection": "QC sample inspection",
        "full_inspection": "100% inspection if needed",
        "acceptance": "Accept, reject, or partial accept",
        "quarantine": "Hold rejected items"
    },
    "5_grn_creation": {
        "create_grn": "Create Goods Receipt Note",
        "accepted_qty": "Record accepted quantity",
        "rejected_qty": "Record rejected quantity",
        "batch_serial": "Record batch/serial numbers"
    },
    "6_putaway": {
        "location_assignment": "Assign storage location",
        "putaway_task": "Create putaway task",
        "stock_update": "Update inventory"
    }
}
```

**3-Way Match**:
```python
three_way_match = {
    "documents": {
        "po": "Purchase Order",
        "grn": "Goods Receipt Note",
        "invoice": "Supplier Invoice"
    },
    "matching_fields": [
        "Supplier",
        "Items and quantities",
        "Unit prices",
        "Total amount"
    ],
    "tolerance": {
        "qty_tolerance": "±2% quantity variance allowed",
        "price_tolerance": "±1% price variance allowed",
        "amount_tolerance": "$50 amount variance allowed"
    },
    "outcomes": {
        "full_match": "Auto-approve invoice for payment",
        "within_tolerance": "Manager review",
        "outside_tolerance": "Requires investigation and approval"
    }
}
```

**Rejected Goods**:
```python
rejection_handling = {
    "reasons": [
        "Wrong item delivered",
        "Damaged in transit",
        "Quality inspection failed",
        "Quantity mismatch",
        "Late delivery (time-sensitive goods)"
    ],
    "actions": {
        "return_to_supplier": "Create return shipment",
        "debit_note": "Issue debit note to supplier",
        "replacement": "Request replacement shipment",
        "credit": "Request credit on invoice"
    }
}
```

### 5. Supplier Management
**Status**: Must-Have | **Competitive Parity**: Advanced

**Supplier Master Data**:
```python
supplier_data = {
    "basic_info": {
        "supplier_name": "Legal name",
        "supplier_code": "Unique identifier",
        "tax_id": "Tax ID / VAT number",
        "website": "Company website",
        "industry": "Industry classification"
    },
    "contacts": {
        "primary_contact": "Main contact person",
        "accounts_payable": "AP contact",
        "sales_rep": "Sales representative",
        "support": "Support contact"
    },
    "addresses": {
        "billing_address": "Invoice address",
        "shipping_address": "Return address",
        "remittance_address": "Payment address"
    },
    "banking": {
        "bank_name": "Bank name",
        "account_number": "Account number (encrypted)",
        "routing_number": "Routing/SWIFT code",
        "payment_methods": ["ACH", "Wire", "Check", "Card"]
    },
    "terms": {
        "payment_terms": "Default payment terms",
        "credit_limit": "Credit limit",
        "currency": "Preferred currency",
        "tax_treatment": "Tax withholding rules"
    }
}
```

**Supplier Categories**:
```python
categories = {
    "preferred_supplier": "Best pricing and service",
    "approved_supplier": "Meets quality standards",
    "trial_supplier": "Under evaluation",
    "blocked_supplier": "Do not use"
}
```

**Supplier Onboarding**:
```python
onboarding_process = {
    "1_application": {
        "supplier_submits": "Supplier submits application via portal",
        "documents": ["Business license", "Tax certificate", "Insurance", "References"]
    },
    "2_evaluation": {
        "credit_check": "Financial stability check",
        "capability_assessment": "Can they meet our needs?",
        "quality_audit": "Quality management system review",
        "site_visit": "Optional site visit for critical suppliers"
    },
    "3_approval": {
        "procurement_approval": "Procurement team approves",
        "finance_approval": "Finance approves credit terms",
        "quality_approval": "Quality approves if required"
    },
    "4_setup": {
        "create_supplier_record": "Add to ERP",
        "portal_access": "Provide supplier portal access",
        "training": "Train on processes and systems"
    }
}
```

**Supplier Performance Metrics**:
```python
performance_kpis = {
    "quality": {
        "defect_rate": "% of items rejected",
        "first_pass_yield": "% accepted without rework",
        "rma_rate": "% items returned"
    },
    "delivery": {
        "on_time_delivery": "% deliveries on time",
        "lead_time_accuracy": "Actual vs. quoted lead time",
        "fill_rate": "% orders fulfilled completely"
    },
    "cost": {
        "price_competitiveness": "Price vs. market average",
        "cost_savings": "Year-over-year savings",
        "payment_terms": "Early payment discounts offered"
    },
    "service": {
        "responsiveness": "Time to respond to inquiries",
        "issue_resolution": "Time to resolve problems",
        "communication": "Quality of communication"
    },
    "overall_score": "Weighted composite score (0-100)"
}
```

**Supplier Scorecards**:
```python
scorecard = {
    "frequency": "Quarterly scorecards",
    "sharing": "Share scorecard with supplier",
    "review_meetings": "Quarterly business reviews",
    "improvement_plans": "Corrective action plans for low performers",
    "recognition": "Supplier of the quarter/year awards"
}
```

### 6. Supplier Invoice Processing
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Invoice Receipt**:
```python
invoice_channels = {
    "email": "Email with PDF attachment",
    "portal": "Supplier portal upload",
    "edi": "EDI 810 invoice",
    "api": "API integration",
    "mail": "Paper invoice (scan)"
}
```

**AI Invoice Processing**:
```python
ai_ocr_engine = {
    "extraction": {
        "header": [
            "Supplier name and address",
            "Invoice number and date",
            "PO number",
            "Payment terms",
            "Total amount"
        ],
        "line_items": [
            "Item description",
            "Quantity",
            "Unit price",
            "Amount",
            "Tax"
        ]
    },
    "validation": {
        "supplier_match": "Match supplier to master data",
        "po_match": "Find matching PO",
        "duplicate_check": "Check for duplicate invoice number",
        "amount_check": "Validate calculations",
        "tax_validation": "Verify tax calculations"
    },
    "gl_coding": {
        "auto_coding": "AI predicts GL account based on history",
        "cost_center": "Assign to cost center/project",
        "confidence": "95%+ accuracy on auto-coding"
    },
    "routing": {
        "3_way_match": "If matched, route to AP",
        "manual_review": "If unmatched, route to buyer",
        "approval": "Route for approval if needed"
    }
}
```

**Invoice Approval Workflow**:
```python
approval_workflow = {
    "auto_approved": {
        "conditions": [
            "3-way match successful",
            "Within tolerance",
            "No prior issues with supplier"
        ],
        "action": "Queue for payment"
    },
    "manual_approval": {
        "triggers": [
            "No PO (non-PO invoice)",
            "Variance exceeds tolerance",
            "New supplier",
            "Amount exceeds threshold"
        ],
        "approvers": "Buyer, Manager, Finance"
    },
    "exceptions": {
        "hold_for_investigation": "Significant discrepancies",
        "request_credit": "Overcharge identified",
        "dispute": "Formal dispute process"
    }
}
```

### 7. Payment Processing
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Payment Methods**:
```python
payment_methods = {
    "ach": {
        "type": "ACH/Bank Transfer",
        "processing_time": "1-3 business days",
        "cost": "Low cost",
        "use_case": "Standard payments"
    },
    "wire": {
        "type": "Wire Transfer",
        "processing_time": "Same day",
        "cost": "Higher cost",
        "use_case": "Urgent or international payments"
    },
    "check": {
        "type": "Paper Check",
        "processing_time": "5-7 days",
        "cost": "Medium cost (printing, mailing)",
        "use_case": "Small suppliers, special situations"
    },
    "virtual_card": {
        "type": "Virtual Credit Card",
        "processing_time": "Immediate",
        "cost": "Card fee, offset by rebates",
        "use_case": "Earn rebates, extend payment terms"
    }
}
```

**Payment Batching**:
```python
batch_payment = {
    "selection": {
        "due_date": "Select invoices due by date",
        "supplier": "Pay all invoices from specific supplier",
        "amount": "Pay invoices below threshold",
        "early_payment": "Select invoices with early payment discount"
    },
    "approval": {
        "batch_review": "Review entire batch",
        "dual_authorization": "Two approvers for large batches",
        "fraud_check": "Verify bank account changes"
    },
    "execution": {
        "ach_file": "Generate ACH file for bank",
        "wire_instructions": "Wire transfer instructions",
        "check_printing": "Print checks",
        "virtual_cards": "Generate virtual card numbers"
    },
    "confirmation": {
        "update_status": "Mark invoices as paid",
        "supplier_notification": "Email remittance advice",
        "reconciliation": "Bank reconciliation data"
    }
}
```

**Early Payment Discounts**:
```python
discount_optimization = {
    "terms": "2/10 Net 30 (2% discount if paid in 10 days)",
    "calculation": {
        "discount_amount": "Invoice amount × 2%",
        "effective_interest_rate": "Annualized return ≈ 36%",
        "decision": "Take discount if cash available or cost of capital < 36%"
    },
    "ai_optimization": {
        "cash_forecast": "Predict cash availability",
        "recommendation": "AI suggests which discounts to take",
        "savings_tracking": "Track savings from discounts taken"
    }
}
```

### 8. Purchase Analytics & Reporting
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Spend Analysis**:
```python
spend_analytics = {
    "dimensions": {
        "by_supplier": "Who are we spending most with?",
        "by_category": "What categories consume most spend?",
        "by_department": "Which departments spend most?",
        "by_project": "Project-wise spend",
        "by_time": "Spend trends over time"
    },
    "insights": {
        "spend_concentration": "% spend with top 10 suppliers",
        "maverick_buying": "Purchases outside approved suppliers",
        "tail_spend": "Many small suppliers = opportunity to consolidate",
        "savings_opportunities": "Volume discounts, supplier consolidation"
    }
}
```

**Key Procurement Metrics**:
```python
procurement_kpis = {
    "cost_metrics": {
        "total_spend": "Total procurement spend",
        "cost_savings": "Year-over-year savings",
        "cost_avoidance": "Avoided price increases",
        "purchase_price_variance": "Actual vs. standard cost"
    },
    "efficiency_metrics": {
        "po_cycle_time": "Requisition to PO time",
        "invoice_cycle_time": "Invoice receipt to payment time",
        "e_procurement_adoption": "% purchases via e-procurement",
        "po_accuracy": "% POs without changes"
    },
    "supplier_metrics": {
        "on_time_delivery": "% deliveries on time",
        "quality_acceptance": "% items accepted (not rejected)",
        "supplier_lead_time": "Average lead time",
        "supplier_responsiveness": "Time to quote"
    },
    "compliance_metrics": {
        "po_compliance": "% purchases with PO",
        "contract_compliance": "% spend under contract",
        "supplier_diversity": "% spend with diverse suppliers",
        "maverick_spend": "% spend outside approved suppliers"
    }
}
```

**AI Procurement Insights**:
```python
ai_insights = {
    "price_prediction": {
        "commodity_prices": "Predict raw material price trends",
        "optimal_buy_time": "Suggest best time to buy",
        "hedging_recommendations": "Hedge against price volatility"
    },
    "demand_forecasting": {
        "material_requirements": "Predict future material needs",
        "seasonal_patterns": "Identify seasonal buying patterns",
        "lead_time_planning": "Optimize order timing"
    },
    "supplier_risk": {
        "financial_health": "Monitor supplier financial stability",
        "delivery_risk": "Predict late delivery probability",
        "quality_risk": "Identify quality degradation trends",
        "geographic_risk": "Political, weather, logistics risks"
    },
    "savings_opportunities": {
        "consolidation": "Identify consolidation opportunities",
        "alternative_suppliers": "Suggest lower-cost alternatives",
        "negotiation_leverage": "Identify negotiation opportunities",
        "contract_optimization": "Optimize contract terms"
    }
}
```

**Standard Reports**:
```python
purchase_reports = {
    "purchase_register": "All purchase transactions",
    "po_summary": "Open POs, PO value, PO status",
    "goods_receipt_report": "Items received",
    "pending_invoices": "Invoices awaiting approval",
    "payment_register": "Payments made",
    "supplier_wise_spend": "Spend by supplier",
    "category_wise_spend": "Spend by category",
    "budget_vs_actual": "Procurement budget tracking",
    "supplier_performance": "Supplier scorecards",
    "aging_report": "Payables aging"
}
```

### 9. Contract Management
**Status**: Should-Have | **Competitive Parity**: Advanced

**Contract Types**:
```python
contract_types = {
    "purchase_agreement": "Long-term supply agreement",
    "blanket_po": "Recurring purchases at fixed price",
    "service_contract": "Ongoing services (maintenance, support)",
    "lease_agreement": "Equipment leasing",
    "nda": "Non-disclosure agreement",
    "msa": "Master service agreement"
}
```

**Contract Lifecycle**:
```python
contract_lifecycle = {
    "1_creation": {
        "template": "Use contract template",
        "negotiation": "Negotiate terms with supplier",
        "legal_review": "Legal department review",
        "approval": "Executive approval"
    },
    "2_execution": {
        "signature": "E-signature (DocuSign, Adobe Sign)",
        "effective_date": "Contract effective date",
        "repository": "Store in contract repository"
    },
    "3_management": {
        "obligations": "Track deliverables and obligations",
        "milestones": "Monitor milestones",
        "amendments": "Track amendments and changes",
        "compliance": "Ensure compliance with terms"
    },
    "4_renewal": {
        "expiry_alerts": "90, 60, 30 day alerts",
        "renewal_decision": "Renew, renegotiate, or terminate",
        "auto_renewal": "Auto-renew if enabled"
    }
}
```

**Contract Repository**:
```python
repository_features = {
    "storage": "Centralized contract storage",
    "search": "Full-text search",
    "metadata": "Tag by supplier, category, value, dates",
    "version_control": "Track contract versions",
    "access_control": "Role-based access",
    "audit_trail": "Track all access and changes",
    "reporting": "Contract value, expirations, compliance"
}
```

### 10. Supplier Collaboration
**Status**: Should-Have | **Competitive Parity**: Advanced

**Supplier Portal**:
```python
portal_features = {
    "registration": "Supplier self-registration",
    "profile_management": "Update company information",
    "catalog_management": "Upload product catalogs",
    "rfq_response": "View and respond to RFQs",
    "po_acknowledgment": "Acknowledge POs, propose changes",
    "asn_submission": "Submit Advanced Ship Notices",
    "invoice_submission": "Submit invoices electronically",
    "payment_status": "View invoice and payment status",
    "performance_dashboard": "View performance metrics",
    "messaging": "Communicate with buyers"
}
```

**Collaborative Planning**:
```python
collaboration = {
    "demand_sharing": "Share demand forecast with key suppliers",
    "inventory_visibility": "Suppliers see inventory levels",
    "vmi": "Vendor Managed Inventory programs",
    "consignment": "Consignment stock agreements",
    "jit_delivery": "Just-in-time delivery schedules",
    "quality_collaboration": "Joint quality improvement programs"
}
```

### 11. Purchase Returns & Debit Notes
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Purchase Return Process**:
```python
return_workflow = {
    "1_return_authorization": {
        "reason": ["Defective", "Wrong item", "Excess quantity", "Damaged"],
        "approval": "Manager approval",
        "rma": "Obtain RMA from supplier"
    },
    "2_return_shipment": {
        "packing": "Pack items for return",
        "shipping": "Ship to supplier (carrier tracking)",
        "documentation": "Return delivery note"
    },
    "3_debit_note": {
        "creation": "Create debit note",
        "amount": "Return value",
        "adjustment": "Adjust payables"
    },
    "4_supplier_action": {
        "credit_note": "Supplier issues credit note",
        "replacement": "Supplier ships replacement",
        "refund": "Supplier refunds payment"
    }
}
```

### 12. Compliance & Sustainability
**Status**: Should-Have | **Competitive Advantage**: Advanced

**Compliance**:
```python
compliance_features = {
    "supplier_certifications": {
        "iso_9001": "Quality management",
        "iso_14001": "Environmental management",
        "iso_45001": "Occupational health and safety",
        "industry_specific": "FDA, UL, CE, etc."
    },
    "conflict_minerals": "Track conflict mineral usage",
    "trade_compliance": {
        "denied_party_screening": "Screen against restricted lists",
        "export_controls": "ITAR, EAR compliance",
        "sanctions": "OFAC sanctions compliance"
    },
    "audit_trail": "Complete procurement audit trail",
    "segregation_of_duties": "Prevent fraud through SOD controls"
}
```

**Sustainability**:
```python
sustainability = {
    "supplier_esg": {
        "environmental_score": "Carbon footprint, waste, energy",
        "social_score": "Labor practices, safety, diversity",
        "governance_score": "Ethics, transparency, compliance"
    },
    "carbon_tracking": "Track carbon footprint of purchases",
    "local_sourcing": "Prefer local suppliers (reduce transport emissions)",
    "sustainable_materials": "Prioritize sustainable materials",
    "supplier_diversity": "Diverse supplier program (MBE, WBE, etc.)",
    "reporting": "ESG procurement reporting"
}
```

---

## AI Agent Integration

### Procurement AI Agents

**1. Smart Sourcing Agent**
```python
agent_capabilities = {
    "supplier_recommendation": "Recommend best suppliers based on requirements",
    "price_benchmarking": "Compare prices across suppliers and market",
    "negotiation_support": "Suggest negotiation strategies and talking points",
    "should_cost_modeling": "Estimate fair market price",
    "alternative_sourcing": "Suggest alternative suppliers or materials",
    "risk_assessment": "Assess supplier and supply chain risks"
}
```

**2. Invoice Processing Agent**
```python
agent_capabilities = {
    "ocr_extraction": "Extract invoice data from PDF/image (95%+ accuracy)",
    "3_way_match": "Auto-match PO, GRN, Invoice",
    "duplicate_detection": "Flag duplicate invoices",
    "fraud_detection": "Detect invoice fraud patterns",
    "gl_auto_coding": "Predict GL account and cost center",
    "exception_handling": "Route exceptions to appropriate approver"
}
```

**3. Spend Analysis Agent**
```python
agent_capabilities = {
    "spend_categorization": "Auto-categorize spend",
    "savings_opportunities": "Identify consolidation and negotiation opportunities",
    "tail_spend_optimization": "Recommend actions for tail spend",
    "contract_compliance": "Flag purchases outside contracts",
    "maverick_spend_detection": "Identify off-contract purchases",
    "budget_variance_analysis": "Explain budget variances"
}
```

**4. Supplier Risk Agent**
```python
agent_capabilities = {
    "financial_health_monitoring": "Monitor supplier financial stability",
    "delivery_performance_prediction": "Predict late deliveries",
    "quality_degradation_detection": "Detect quality issues early",
    "geopolitical_risk": "Alert on supply chain disruptions",
    "alternative_supplier_suggestions": "Suggest backup suppliers",
    "risk_mitigation_plans": "Recommend risk mitigation strategies"
}
```

**5. Procurement Assistant Agent**
```python
agent_capabilities = {
    "auto_requisition": "Auto-create requisitions from reorder points",
    "smart_approval_routing": "Route approvals based on context",
    "po_optimization": "Consolidate requisitions to minimize POs",
    "delivery_date_optimization": "Suggest optimal delivery dates",
    "payment_term_optimization": "Balance cash flow vs. discounts",
    "query_answering": "Answer procurement policy questions"
}
```

---

## Database Schema

```sql
-- Suppliers
CREATE TABLE suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Basic Info
    supplier_code VARCHAR(50) NOT NULL,
    supplier_name VARCHAR(255) NOT NULL,
    tax_id VARCHAR(100),
    website VARCHAR(255),

    -- Classification
    supplier_type VARCHAR(50), -- manufacturer, distributor, service_provider
    supplier_category VARCHAR(100),
    industry VARCHAR(100),

    -- Status
    status VARCHAR(50) DEFAULT 'active', -- active, inactive, blocked
    rating VARCHAR(10), -- preferred, approved, trial, blocked

    -- Payment Terms
    default_payment_terms VARCHAR(100),
    default_currency VARCHAR(3) DEFAULT 'USD',
    credit_limit DECIMAL(15, 2),

    -- Lead Time
    default_lead_time_days INTEGER,

    -- Contact
    primary_contact VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),

    -- Address
    billing_address JSONB,
    shipping_address JSONB,

    -- Banking
    bank_name VARCHAR(255),
    bank_account_number VARCHAR(100), -- Encrypted
    bank_routing_number VARCHAR(50),
    payment_methods TEXT[], -- ACH, Wire, Check, Card

    -- Tax
    tax_withholding_applicable BOOLEAN DEFAULT false,
    tax_withholding_percent DECIMAL(5, 2),

    -- Performance
    on_time_delivery_rate DECIMAL(5, 2),
    quality_acceptance_rate DECIMAL(5, 2),
    overall_score DECIMAL(5, 2),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, supplier_code),
    INDEX idx_tenant (tenant_id),
    INDEX idx_status (status)
);

-- Purchase Requisitions
CREATE TABLE purchase_requisitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Requisition Info
    requisition_no VARCHAR(100) NOT NULL,
    requisition_date DATE NOT NULL,
    required_by_date DATE NOT NULL,

    -- Requester
    requested_by UUID REFERENCES users(id) NOT NULL,
    department_id UUID,
    cost_center_id UUID REFERENCES cost_centers(id),
    project_id UUID REFERENCES projects(id),

    -- Purpose
    purpose TEXT,
    justification TEXT,

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, submitted, approved, rejected, ordered, closed

    -- Approval
    approval_status VARCHAR(50) DEFAULT 'pending',
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,

    -- Conversion
    converted_to_po BOOLEAN DEFAULT false,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, requisition_no),
    INDEX idx_requested_by (requested_by),
    INDEX idx_status (status)
);

-- Purchase Requisition Items
CREATE TABLE purchase_requisition_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requisition_id UUID REFERENCES purchase_requisitions(id) ON DELETE CASCADE,

    -- Item
    item_id UUID REFERENCES items(id),
    item_name VARCHAR(255),
    description TEXT,

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    uom VARCHAR(50),

    -- Pricing (estimated)
    estimated_unit_price DECIMAL(15, 2),
    estimated_amount DECIMAL(15, 2),

    -- Specification
    specifications TEXT,
    attachments TEXT[], -- URLs to spec documents

    -- Sourcing
    suggested_supplier_id UUID REFERENCES suppliers(id),

    -- Status
    qty_ordered DECIMAL(15, 4) DEFAULT 0,

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_requisition (requisition_id),
    INDEX idx_item (item_id)
);

-- Request for Quotations (RFQ)
CREATE TABLE rfqs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- RFQ Info
    rfq_no VARCHAR(100) NOT NULL,
    rfq_date DATE NOT NULL,
    quote_deadline DATE NOT NULL,

    -- Requirements
    title VARCHAR(255),
    description TEXT,

    -- Terms
    payment_terms VARCHAR(100),
    delivery_terms VARCHAR(100),
    required_by_date DATE,

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, sent, receiving_quotes, awarded, closed

    -- Buyer
    buyer_id UUID REFERENCES users(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, rfq_no),
    INDEX idx_tenant (tenant_id),
    INDEX idx_status (status)
);

-- RFQ Items
CREATE TABLE rfq_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfq_id UUID REFERENCES rfqs(id) ON DELETE CASCADE,

    -- Item
    item_id UUID REFERENCES items(id),
    item_name VARCHAR(255),
    description TEXT,
    specifications TEXT,

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    uom VARCHAR(50),

    -- Reference
    requisition_item_id UUID REFERENCES purchase_requisition_items(id),

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_rfq (rfq_id),
    INDEX idx_item (item_id)
);

-- RFQ Suppliers (Invited)
CREATE TABLE rfq_suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfq_id UUID REFERENCES rfqs(id) ON DELETE CASCADE,
    supplier_id UUID REFERENCES suppliers(id) NOT NULL,

    -- Invitation
    invited_at TIMESTAMPTZ DEFAULT NOW(),
    invitation_sent BOOLEAN DEFAULT false,

    -- Response
    quote_submitted BOOLEAN DEFAULT false,
    quote_submitted_at TIMESTAMPTZ,

    -- Award
    awarded BOOLEAN DEFAULT false,

    INDEX idx_rfq (rfq_id),
    INDEX idx_supplier (supplier_id)
);

-- Supplier Quotes
CREATE TABLE supplier_quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfq_id UUID REFERENCES rfqs(id),
    supplier_id UUID REFERENCES suppliers(id) NOT NULL,

    -- Quote Info
    quote_no VARCHAR(100),
    quote_date DATE NOT NULL,
    valid_until DATE,

    -- Terms
    payment_terms VARCHAR(100),
    delivery_lead_time_days INTEGER,
    shipping_terms VARCHAR(100),

    -- Total
    total_amount DECIMAL(15, 2),
    currency VARCHAR(3) DEFAULT 'USD',

    -- Scoring
    price_score DECIMAL(5, 2),
    quality_score DECIMAL(5, 2),
    delivery_score DECIMAL(5, 2),
    overall_score DECIMAL(5, 2),

    -- Status
    status VARCHAR(50) DEFAULT 'submitted', -- submitted, shortlisted, awarded, rejected

    -- Notes
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_rfq (rfq_id),
    INDEX idx_supplier (supplier_id)
);

-- Supplier Quote Items
CREATE TABLE supplier_quote_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_quote_id UUID REFERENCES supplier_quotes(id) ON DELETE CASCADE,
    rfq_item_id UUID REFERENCES rfq_items(id),

    -- Item
    item_id UUID REFERENCES items(id),
    item_name VARCHAR(255),
    supplier_part_no VARCHAR(100),

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    uom VARCHAR(50),

    -- Pricing
    unit_price DECIMAL(15, 2) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,

    -- Lead Time
    lead_time_days INTEGER,

    -- Notes
    notes TEXT,

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_quote (supplier_quote_id)
);

-- Purchase Orders
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- PO Info
    po_no VARCHAR(100) NOT NULL,
    po_date DATE NOT NULL,
    delivery_date DATE,

    -- Supplier
    supplier_id UUID REFERENCES suppliers(id) NOT NULL,
    supplier_quote_id UUID REFERENCES supplier_quotes(id),

    -- Addresses
    billing_address JSONB,
    shipping_address JSONB,

    -- Amounts
    subtotal DECIMAL(15, 2) NOT NULL,
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

    -- PO Type
    po_type VARCHAR(50) DEFAULT 'standard', -- standard, blanket, dropship, service

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, sent, confirmed, receiving, received, invoiced, paid, closed, cancelled
    receiving_status VARCHAR(50) DEFAULT 'not_received',
    invoicing_status VARCHAR(50) DEFAULT 'not_invoiced',
    payment_status VARCHAR(50) DEFAULT 'unpaid',

    -- Fulfillment
    warehouse_id UUID REFERENCES warehouses(id),

    -- Reference
    requisition_id UUID REFERENCES purchase_requisitions(id),
    rfq_id UUID REFERENCES rfqs(id),
    sales_order_id UUID REFERENCES sales_orders(id), -- For dropship

    -- Approval
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    -- Buyer
    buyer_id UUID REFERENCES users(id),

    -- Tracking
    sent_at TIMESTAMPTZ,
    confirmed_by_supplier BOOLEAN DEFAULT false,
    confirmed_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, po_no),
    INDEX idx_supplier (supplier_id),
    INDEX idx_status (status),
    INDEX idx_po_date (po_date)
);

-- Purchase Order Items
CREATE TABLE purchase_order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_order_id UUID REFERENCES purchase_orders(id) ON DELETE CASCADE,

    -- Item
    item_id UUID REFERENCES items(id) NOT NULL,
    item_name VARCHAR(255),
    description TEXT,

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    received_qty DECIMAL(15, 4) DEFAULT 0,
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

    -- GL Coding
    expense_account_id UUID REFERENCES accounts(id),
    cost_center_id UUID REFERENCES cost_centers(id),
    project_id UUID REFERENCES projects(id),

    -- Reference
    requisition_item_id UUID REFERENCES purchase_requisition_items(id),
    rfq_item_id UUID REFERENCES rfq_items(id),

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_po (purchase_order_id),
    INDEX idx_item (item_id)
);

-- Goods Receipt Notes (GRN)
CREATE TABLE goods_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Receipt Info
    grn_no VARCHAR(100) NOT NULL,
    receipt_date DATE NOT NULL,

    -- Purchase Order
    purchase_order_id UUID REFERENCES purchase_orders(id) NOT NULL,
    supplier_id UUID REFERENCES suppliers(id) NOT NULL,

    -- Warehouse
    warehouse_id UUID REFERENCES warehouses(id) NOT NULL,

    -- Delivery Info
    carrier VARCHAR(255),
    tracking_number VARCHAR(255),
    delivery_note_no VARCHAR(100),

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, submitted, completed

    -- Quality Inspection
    inspection_required BOOLEAN DEFAULT false,
    inspection_status VARCHAR(50), -- pending, passed, failed

    -- Receiver
    received_by UUID REFERENCES users(id),

    -- Notes
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, grn_no),
    INDEX idx_po (purchase_order_id),
    INDEX idx_supplier (supplier_id)
);

-- Goods Receipt Items
CREATE TABLE goods_receipt_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goods_receipt_id UUID REFERENCES goods_receipts(id) ON DELETE CASCADE,
    po_item_id UUID REFERENCES purchase_order_items(id),

    -- Item
    item_id UUID REFERENCES items(id) NOT NULL,
    item_name VARCHAR(255),

    -- Quantity
    ordered_qty DECIMAL(15, 4),
    received_qty DECIMAL(15, 4) NOT NULL,
    accepted_qty DECIMAL(15, 4) NOT NULL,
    rejected_qty DECIMAL(15, 4) DEFAULT 0,
    uom VARCHAR(50),

    -- Rejection
    rejection_reason TEXT,

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_nos TEXT[],

    -- Storage
    location_id UUID REFERENCES storage_locations(id),

    -- Valuation
    valuation_rate DECIMAL(15, 4),

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_grn (goods_receipt_id),
    INDEX idx_item (item_id)
);

-- Purchase Returns
CREATE TABLE purchase_returns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Return Info
    return_no VARCHAR(100) NOT NULL,
    return_date DATE NOT NULL,

    -- Supplier & PO
    supplier_id UUID REFERENCES suppliers(id) NOT NULL,
    purchase_order_id UUID REFERENCES purchase_orders(id),
    goods_receipt_id UUID REFERENCES goods_receipts(id),

    -- Return Reason
    reason_code VARCHAR(100),
    reason_description TEXT,

    -- Amounts
    total_amount DECIMAL(15, 2) NOT NULL,

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, approved, shipped, completed

    -- RMA
    supplier_rma_no VARCHAR(100),

    -- Warehouse
    warehouse_id UUID REFERENCES warehouses(id),

    -- Debit Note
    debit_note_id UUID,

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, return_no),
    INDEX idx_supplier (supplier_id),
    INDEX idx_po (purchase_order_id)
);

-- Purchase Return Items
CREATE TABLE purchase_return_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_return_id UUID REFERENCES purchase_returns(id) ON DELETE CASCADE,
    po_item_id UUID REFERENCES purchase_order_items(id),

    -- Item
    item_id UUID REFERENCES items(id) NOT NULL,
    item_name VARCHAR(255),

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    uom VARCHAR(50),

    -- Pricing
    unit_price DECIMAL(15, 2) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_nos TEXT[],

    line_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_return (purchase_return_id)
);

-- Supplier Performance Scorecards
CREATE TABLE supplier_scorecards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    supplier_id UUID REFERENCES suppliers(id) NOT NULL,

    -- Period
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- Quality Metrics
    total_received_qty DECIMAL(15, 4),
    accepted_qty DECIMAL(15, 4),
    rejected_qty DECIMAL(15, 4),
    defect_rate DECIMAL(5, 2),
    quality_score DECIMAL(5, 2),

    -- Delivery Metrics
    total_deliveries INTEGER,
    on_time_deliveries INTEGER,
    late_deliveries INTEGER,
    on_time_delivery_rate DECIMAL(5, 2),
    avg_lead_time_days DECIMAL(8, 2),
    delivery_score DECIMAL(5, 2),

    -- Cost Metrics
    total_spend DECIMAL(15, 2),
    cost_savings DECIMAL(15, 2),
    cost_score DECIMAL(5, 2),

    -- Service Metrics
    avg_response_time_hours DECIMAL(8, 2),
    issues_raised INTEGER,
    issues_resolved INTEGER,
    service_score DECIMAL(5, 2),

    -- Overall
    overall_score DECIMAL(5, 2),
    rating VARCHAR(20), -- excellent, good, fair, poor

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_supplier_period (supplier_id, period_start, period_end)
);

-- Contracts
CREATE TABLE contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Contract Info
    contract_no VARCHAR(100) NOT NULL,
    contract_name VARCHAR(255) NOT NULL,
    contract_type VARCHAR(50), -- purchase_agreement, blanket_po, service_contract, lease, nda

    -- Party
    supplier_id UUID REFERENCES suppliers(id),

    -- Dates
    start_date DATE NOT NULL,
    end_date DATE,
    notice_period_days INTEGER,

    -- Value
    contract_value DECIMAL(15, 2),
    currency VARCHAR(3) DEFAULT 'USD',

    -- Terms
    payment_terms VARCHAR(100),
    auto_renewal BOOLEAN DEFAULT false,

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, active, expired, terminated

    -- Documents
    document_url TEXT,

    -- Alerts
    renewal_alert_sent BOOLEAN DEFAULT false,

    -- Approval
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, contract_no),
    INDEX idx_supplier (supplier_id),
    INDEX idx_status (status),
    INDEX idx_end_date (end_date)
);

-- Purchase Analytics
CREATE TABLE purchase_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Period
    period_date DATE NOT NULL,
    period_type VARCHAR(20), -- daily, weekly, monthly

    -- Dimensions
    supplier_id UUID REFERENCES suppliers(id),
    item_id UUID REFERENCES items(id),
    category VARCHAR(100),
    department_id UUID,

    -- Metrics
    po_count INTEGER DEFAULT 0,
    total_spend DECIMAL(15, 2) DEFAULT 0,
    units_purchased DECIMAL(15, 4) DEFAULT 0,
    avg_unit_cost DECIMAL(15, 4) DEFAULT 0,

    -- Lead Time
    avg_lead_time_days DECIMAL(8, 2),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_date (tenant_id, period_date),
    INDEX idx_supplier (supplier_id),
    INDEX idx_item (item_id)
);
```

---

## API Specification

### Purchase Requisition APIs

```python
# Create Requisition
POST /api/v1/purchase/requisitions
Request: {
    "requisition_date": "2025-11-10",
    "required_by_date": "2025-11-30",
    "purpose": "Office supplies for Q4",
    "cost_center_id": "uuid",
    "items": [
        {
            "item_id": "uuid",
            "qty": 100,
            "estimated_unit_price": 5.00
        }
    ]
}

# Submit for Approval
POST /api/v1/purchase/requisitions/{id}/submit

# Approve/Reject
POST /api/v1/purchase/requisitions/{id}/approve
POST /api/v1/purchase/requisitions/{id}/reject
Request: {
    "reason": "Not within budget"
}
```

### RFQ APIs

```python
# Create RFQ
POST /api/v1/purchase/rfqs
Request: {
    "title": "Office Furniture RFQ",
    "quote_deadline": "2025-11-20",
    "items": [
        {
            "item_name": "Office Desk",
            "qty": 50,
            "specifications": "Standing desk, electric height adjustment"
        }
    ],
    "suppliers": ["uuid1", "uuid2", "uuid3"]
}

# Send RFQ to Suppliers
POST /api/v1/purchase/rfqs/{id}/send

# Submit Supplier Quote
POST /api/v1/purchase/rfqs/{rfq_id}/quotes
Request: {
    "supplier_id": "uuid",
    "quote_date": "2025-11-15",
    "valid_until": "2025-12-15",
    "payment_terms": "Net 30",
    "items": [
        {
            "rfq_item_id": "uuid",
            "unit_price": 450.00,
            "lead_time_days": 14
        }
    ]
}

# Compare Quotes
GET /api/v1/purchase/rfqs/{id}/compare-quotes
Response: {
    "rfq_id": "uuid",
    "quotes": [
        {
            "supplier_name": "Supplier A",
            "total_amount": 22500.00,
            "lead_time_days": 14,
            "overall_score": 85.5
        },
        {
            "supplier_name": "Supplier B",
            "total_amount": 23000.00,
            "lead_time_days": 10,
            "overall_score": 88.2
        }
    ],
    "ai_recommendation": {
        "recommended_supplier": "Supplier B",
        "reasoning": "Best overall score balancing price, delivery, and quality"
    }
}

# Award PO
POST /api/v1/purchase/rfqs/{id}/award
Request: {
    "supplier_quote_id": "uuid"
}
Response: {
    "purchase_order_id": "uuid",
    "po_no": "PO-2025-001"
}
```

### Purchase Order APIs

```python
# Create Purchase Order
POST /api/v1/purchase/orders
Request: {
    "supplier_id": "uuid",
    "po_date": "2025-11-10",
    "delivery_date": "2025-11-30",
    "items": [
        {
            "item_id": "uuid",
            "qty": 100,
            "unit_price": 10.00,
            "warehouse_id": "uuid"
        }
    ],
    "payment_terms": "Net 30",
    "shipping_address": {...}
}

# Send PO to Supplier
POST /api/v1/purchase/orders/{id}/send
Request: {
    "send_email": true,
    "email_to": "supplier@example.com"
}

# Supplier Confirms PO
POST /api/v1/purchase/orders/{id}/confirm
Request: {
    "confirmed_delivery_date": "2025-11-25",
    "supplier_notes": "Confirmed, will ship early"
}
```

### Goods Receipt APIs

```python
# Create Goods Receipt
POST /api/v1/purchase/goods-receipts
Request: {
    "purchase_order_id": "uuid",
    "receipt_date": "2025-11-10",
    "warehouse_id": "uuid",
    "items": [
        {
            "po_item_id": "uuid",
            "received_qty": 100,
            "accepted_qty": 98,
            "rejected_qty": 2,
            "rejection_reason": "Damaged packaging",
            "batch_no": "BATCH-20251110",
            "location_id": "uuid"
        }
    ]
}

# Quality Inspection
POST /api/v1/purchase/goods-receipts/{id}/inspect
Request: {
    "inspection_status": "passed",
    "inspector_notes": "All items meet specifications"
}
```

### Supplier Management APIs

```python
# Create Supplier
POST /api/v1/purchase/suppliers
Request: {
    "supplier_name": "Acme Supplies Inc.",
    "supplier_code": "SUP-001",
    "email": "ap@acmesupplies.com",
    "payment_terms": "Net 30",
    "billing_address": {...},
    "bank_account_number": "encrypted_value"
}

# Get Supplier Performance
GET /api/v1/purchase/suppliers/{id}/performance
Query Params: ?period_start=2025-01-01&period_end=2025-11-10
Response: {
    "supplier_id": "uuid",
    "supplier_name": "Acme Supplies",
    "period": "2025-01-01 to 2025-11-10",
    "metrics": {
        "on_time_delivery_rate": 95.5,
        "quality_acceptance_rate": 98.2,
        "avg_lead_time_days": 12.5,
        "total_spend": 250000.00,
        "overall_score": 92.3,
        "rating": "excellent"
    },
    "trend": "improving"
}

# AI Supplier Risk Assessment
GET /api/v1/purchase/suppliers/{id}/risk-assessment
Response: {
    "supplier_id": "uuid",
    "risk_score": 25, // 0-100, lower is better
    "risk_level": "low",
    "risk_factors": [
        {
            "factor": "Financial Health",
            "score": 10,
            "status": "stable"
        },
        {
            "factor": "Delivery Performance",
            "score": 5,
            "status": "excellent"
        },
        {
            "factor": "Geographic Risk",
            "score": 10,
            "status": "moderate",
            "details": "Supplier located in region with occasional weather disruptions"
        }
    ],
    "recommendations": [
        "Maintain current relationship",
        "Consider dual sourcing for critical items"
    ]
}
```

### Purchase Analytics APIs

```python
# Spend Analysis
GET /api/v1/purchase/analytics/spend-analysis
Query Params: ?from_date=2025-01-01&to_date=2025-11-10
Response: {
    "total_spend": 5000000.00,
    "by_supplier": [
        {
            "supplier_name": "Acme Supplies",
            "spend": 1500000.00,
            "percentage": 30
        }
    ],
    "by_category": [
        {
            "category": "Raw Materials",
            "spend": 3000000.00,
            "percentage": 60
        }
    ],
    "insights": {
        "top_10_suppliers_percentage": 75,
        "tail_spend_percentage": 15,
        "savings_opportunities": [
            {
                "opportunity": "Consolidate tail spend suppliers",
                "potential_savings": 75000.00
            }
        ]
    }
}

# AI Purchase Forecasting
GET /api/v1/purchase/analytics/forecast
Query Params: ?months=3
Response: {
    "forecast_period": "3 months",
    "forecast": [
        {
            "month": "2025-12",
            "predicted_spend": 480000.00,
            "confidence_interval": {
                "lower": 450000.00,
                "upper": 510000.00
            },
            "major_categories": [...]
        }
    ],
    "recommendations": [
        "Consider bulk purchasing for raw materials in December",
        "Negotiate annual contract for office supplies"
    ]
}

# Savings Opportunities
GET /api/v1/purchase/analytics/savings-opportunities
Response: {
    "opportunities": [
        {
            "type": "Supplier Consolidation",
            "description": "Consolidate 15 small suppliers into 3 preferred suppliers",
            "potential_savings": 125000.00,
            "effort": "medium",
            "timeline": "3 months"
        },
        {
            "type": "Contract Negotiation",
            "description": "Renegotiate pricing with Top 5 suppliers based on volume increase",
            "potential_savings": 200000.00,
            "effort": "low",
            "timeline": "1 month"
        }
    ],
    "total_potential_savings": 325000.00
}
```

---

## Security Considerations

### Access Controls

```python
purchase_permissions = {
    "purchase.requisitions.view": "View purchase requisitions",
    "purchase.requisitions.create": "Create requisitions",
    "purchase.requisitions.approve": "Approve requisitions",

    "purchase.rfqs.view": "View RFQs",
    "purchase.rfqs.create": "Create RFQs",
    "purchase.rfqs.award": "Award RFQs",

    "purchase.pos.view": "View purchase orders",
    "purchase.pos.create": "Create purchase orders",
    "purchase.pos.approve": "Approve purchase orders",
    "purchase.pos.send": "Send POs to suppliers",

    "purchase.grn.view": "View goods receipts",
    "purchase.grn.create": "Create goods receipts",

    "purchase.suppliers.view": "View suppliers",
    "purchase.suppliers.create": "Create/edit suppliers",
    "purchase.suppliers.banking": "View/edit bank details",

    "purchase.returns.view": "View purchase returns",
    "purchase.returns.create": "Create returns",
    "purchase.returns.approve": "Approve returns",

    "purchase.analytics.view": "View purchase analytics",
    "purchase.analytics.export": "Export reports",

    "purchase.contracts.view": "View contracts",
    "purchase.contracts.manage": "Create/edit contracts"
}
```

### Separation of Duties

```python
sod_controls = {
    "rule_1": {
        "conflict": ["purchase.requisitions.create", "purchase.requisitions.approve"],
        "reason": "Requester cannot approve own requisitions"
    },
    "rule_2": {
        "conflict": ["purchase.pos.create", "purchase.pos.approve"],
        "reason": "PO creator cannot approve own POs"
    },
    "rule_3": {
        "conflict": ["purchase.grn.create", "accounts.ap.approve"],
        "reason": "Person receiving goods cannot approve invoices"
    },
    "rule_4": {
        "conflict": ["purchase.suppliers.create", "purchase.suppliers.banking"],
        "reason": "Prevent fraudulent supplier setup with fake bank accounts"
    }
}
```

### Fraud Prevention

```python
fraud_controls = {
    "duplicate_po_detection": "Flag duplicate POs to same supplier",
    "supplier_master_changes": {
        "bank_account_change": "Require dual approval",
        "address_change": "Verify with supplier via phone",
        "audit_trail": "Log all supplier master changes"
    },
    "split_order_detection": "Flag orders split to avoid approval limits",
    "vendor_verification": "Periodic verification of vendor legitimacy",
    "payment_verification": "Verify bank account before first payment",
    "anomaly_detection": "AI flags unusual purchasing patterns"
}
```

### Audit Trail

```python
audit_events = {
    "requisition_created": "Who, when, items, amount",
    "requisition_approved": "Approver, timestamp",
    "po_created": "Buyer, supplier, amount",
    "po_sent": "Sent to, timestamp",
    "po_modified": "What changed, who changed, when",
    "goods_received": "Receiver, qty received, accepted, rejected",
    "invoice_approved": "Approver, timestamp, amount",
    "payment_made": "Payment amount, method, timestamp",
    "supplier_master_changed": "Field, old value, new value, who, when"
}
```

---

## Implementation Roadmap

### Phase 1: Core Procurement (Month 1-2)
- [ ] Supplier master data management
- [ ] Purchase requisitions
- [ ] Purchase orders
- [ ] Goods receipt notes
- [ ] Basic approval workflows

### Phase 2: RFQ & Sourcing (Month 3)
- [ ] Request for Quotation (RFQ)
- [ ] Supplier quotes
- [ ] Quote comparison and scoring
- [ ] AI supplier recommendations
- [ ] Supplier portal (basic)

### Phase 3: Supplier Management (Month 4)
- [ ] Supplier performance scorecards
- [ ] Supplier onboarding
- [ ] Contract management
- [ ] Purchase returns
- [ ] Debit notes

### Phase 4: Analytics & AI (Month 5)
- [ ] Spend analysis
- [ ] Purchase forecasting
- [ ] AI invoice processing
- [ ] Savings opportunity identification
- [ ] Supplier risk assessment

### Phase 5: Advanced Features (Month 6)
- [ ] 3-way match automation
- [ ] Blanket POs and contracts
- [ ] Early payment discount optimization
- [ ] EDI integration
- [ ] Compliance tracking

### Phase 6: Collaboration & Optimization (Month 7)
- [ ] Advanced supplier portal
- [ ] Collaborative planning
- [ ] AI procurement assistant
- [ ] Sustainability tracking
- [ ] Advanced fraud detection

---

## Competitive Analysis

| Feature | SARAISE | SAP Ariba | Oracle Procurement | Microsoft D365 | Odoo Purchase |
|---------|---------|-----------|-------------------|----------------|---------------|
| **Purchase Requisitions** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **RFQ/RFP** | ✓ | ✓ | ✓ | ✓ | ✓ Basic |
| **Purchase Orders** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **3-Way Match** | ✓ Auto | ✓ | ✓ | ✓ | ✓ |
| **AI Invoice OCR** | ✓ 95%+ | ✓ | ✓ Add-on | ✓ Copilot | ✗ |
| **Supplier Portal** | ✓ | ✓ | ✓ | ✓ | ✓ Limited |
| **Supplier Scorecards** | ✓ | ✓ | ✓ | ✓ | ✗ |
| **Contract Management** | ✓ | ✓ | ✓ | ✓ | ✗ |
| **Spend Analysis** | ✓ AI-powered | ✓ | ✓ | ✓ | ✓ Basic |
| **AI Forecasting** | ✓ ML-based | ✓ | ✓ | ✓ | ✗ |
| **Supplier Risk** | ✓ AI-driven | ✓ | ✓ Add-on | ✗ | ✗ |
| **Sustainability Tracking** | ✓ | ✓ | ✓ | ✗ | ✗ |
| **EDI Integration** | ✓ | ✓ | ✓ | ✓ | ✓ Limited |
| **Pricing** | $$ | $$$$ | $$$ | $$$ | $ |

**Verdict**: Matches SAP Ariba and Oracle on core procurement features with superior AI capabilities at significantly lower cost.

---

## Success Metrics

- **Purchase Cycle Time**: < 5 days (requisition to PO)
- **PO Compliance**: > 95% (purchases with PO)
- **Contract Compliance**: > 90% (spend under contract)
- **Cost Savings**: 10% annual cost reduction
- **Supplier On-Time Delivery**: > 95%
- **Invoice Processing Time**: < 24 hours (receipt to approval)
- **3-Way Match Rate**: > 90% (auto-matched invoices)
- **E-Procurement Adoption**: > 90% (electronic vs. manual)
- **Supplier Score**: > 85/100 (average supplier score)
- **Maverick Spend**: < 5% (off-contract purchases)
- **Days Payable Outstanding (DPO)**: 45-60 days (optimize cash flow)
- **ROI**: 4x return in year 1 (cost savings + efficiency gains)

---

**Document Control**:
- **Author**: SARAISE Architecture Team
- **Last Updated**: 2025-11-10
- **Status**: Planning - Ready for Implementation
