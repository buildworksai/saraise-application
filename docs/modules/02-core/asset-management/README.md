<!-- SPDX-License-Identifier: Apache-2.0 -->
# Asset Management Module

**Module Code**: `asset_management`
**Category**: Core Business
**Priority**: High - Capital Asset Lifecycle
**Version**: 1.0.0
**Status**: Planning Phase

---

## Executive Summary

The Asset Management module provides comprehensive **fixed asset lifecycle management** from acquisition to disposal. Powered by AI agents, this module automates depreciation calculations, maintenance scheduling, asset tracking, and compliance reporting—delivering a world-class asset management experience that rivals SAP EAM, IBM Maximo, Infor EAM, Oracle EBS Assets, and IFS Applications.

### Vision

**"Maximize asset value and minimize total cost of ownership through intelligent asset lifecycle management and predictive insights."**

---

## World-Class Features

### 1. Asset Registration & Master Data
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Asset Master Data**:
```python
asset_fields = {
    "identification": {
        "asset_number": "Unique system-generated ID (FA-2025-00001)",
        "asset_tag": "Physical tag/barcode on asset",
        "serial_number": "Manufacturer serial number",
        "asset_name": "Descriptive name",
        "description": "Detailed description"
    },
    "classification": {
        "asset_category": "Building, Vehicle, Equipment, Furniture, IT",
        "asset_class": "Detailed classification (Office Equipment, Production Machinery)",
        "asset_type": "Specific type (Desktop Computer, Forklift)",
        "asset_status": "Active, Idle, Under Maintenance, Disposed"
    },
    "financial": {
        "acquisition_cost": "Original purchase price",
        "acquisition_date": "Date acquired/placed in service",
        "supplier_id": "Vendor/supplier",
        "purchase_order": "PO reference",
        "funding_source": "Capex budget, grant, lease",
        "asset_value_type": "Owned, Leased, Rented"
    },
    "depreciation": {
        "depreciation_method": "Straight Line, Declining Balance, Units of Production",
        "useful_life_years": "Expected useful life",
        "salvage_value": "Residual value at end of life",
        "depreciation_start_date": "When to start depreciating",
        "accumulated_depreciation": "Total depreciation to date",
        "book_value": "Cost - Accumulated Depreciation"
    },
    "location": {
        "current_location": "Building, floor, room",
        "responsible_department": "Department responsible",
        "custodian": "Employee responsible",
        "site_id": "For multi-site organizations",
        "gps_coordinates": "Lat/long for mobile assets"
    },
    "specifications": {
        "manufacturer": "Manufacturer name",
        "model_number": "Model/version",
        "year_manufactured": "Manufacturing year",
        "capacity": "Capacity (tons, seats, etc.)",
        "technical_specs": "Detailed specifications (JSON)",
        "warranty_expiry": "Warranty end date",
        "service_contract": "Maintenance contract details"
    },
    "insurance": {
        "insured": "Yes/No",
        "insurance_policy": "Policy number",
        "insured_value": "Insured amount",
        "insurance_expiry": "Policy expiry date"
    },
    "compliance": {
        "regulatory_compliance": "OSHA, EPA, FDA requirements",
        "certifications": "Required certifications",
        "inspection_due_date": "Next mandatory inspection",
        "permit_license": "Operating permits/licenses"
    }
}
```

**Asset Hierarchy**:
```
Corporate Campus
├── Building A
│   ├── HVAC System
│   │   ├── Chiller Unit 1
│   │   ├── Chiller Unit 2
│   │   └── Air Handling Units (10)
│   ├── Electrical System
│   │   ├── Transformer
│   │   ├── Generator
│   │   └── UPS System
│   └── Production Floor
│       ├── CNC Machine 1
│       └── CNC Machine 2
└── Building B
    └── Office Equipment
        ├── Computers (100)
        ├── Printers (20)
        └── Furniture
```

**Asset Components**:
```python
component_tracking = {
    "parent_asset": "CNC Machine #5",
    "components": [
        {
            "component": "Spindle Motor",
            "serial": "SPN-12345",
            "cost": 5000,
            "installation_date": "2023-01-15",
            "warranty_months": 24,
            "expected_life_hours": 10000,
            "current_hours": 3500
        },
        {
            "component": "Control Panel",
            "serial": "CTL-67890",
            "cost": 3000,
            "installation_date": "2023-01-15"
        }
    ],
    "benefit": "Track component-level maintenance and replacement"
}
```

**Asset Documents**:
- Purchase documents (invoice, receipt)
- Warranty certificates
- User manuals
- Technical drawings
- Maintenance history
- Inspection reports
- Insurance policies
- Disposal documentation

### 2. Depreciation Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Depreciation Methods**:
```python
depreciation_methods = {
    "straight_line": {
        "formula": "(Cost - Salvage Value) / Useful Life",
        "description": "Equal depreciation each year",
        "example": {
            "cost": 100000,
            "salvage": 10000,
            "life_years": 5,
            "annual_depreciation": 18000,  # (100000-10000)/5
            "schedule": [
                {"year": 1, "depreciation": 18000, "accumulated": 18000, "book_value": 82000},
                {"year": 2, "depreciation": 18000, "accumulated": 36000, "book_value": 64000},
                {"year": 3, "depreciation": 18000, "accumulated": 54000, "book_value": 46000},
                {"year": 4, "depreciation": 18000, "accumulated": 72000, "book_value": 28000},
                {"year": 5, "depreciation": 18000, "accumulated": 90000, "book_value": 10000}
            ]
        },
        "use_case": "Most common, simple, predictable"
    },
    "declining_balance": {
        "formula": "Book Value × Depreciation Rate",
        "types": {
            "double_declining": "Rate = 2 / Useful Life",
            "150_declining": "Rate = 1.5 / Useful Life"
        },
        "description": "Higher depreciation in early years",
        "example": {
            "cost": 100000,
            "life_years": 5,
            "rate": 0.40,  # 2/5 = 40% for double declining
            "schedule": [
                {"year": 1, "depreciation": 40000, "book_value": 60000},
                {"year": 2, "depreciation": 24000, "book_value": 36000},
                {"year": 3, "depreciation": 14400, "book_value": 21600},
                {"year": 4, "depreciation": 8640, "book_value": 12960},
                {"year": 5, "depreciation": 2960, "book_value": 10000}  # Switch to SL if needed
            ]
        },
        "use_case": "Technology assets (computers, software) that lose value quickly"
    },
    "units_of_production": {
        "formula": "(Cost - Salvage) × (Units Produced / Total Expected Units)",
        "description": "Depreciation based on usage",
        "example": {
            "cost": 100000,
            "salvage": 10000,
            "total_units": 1000000,  # Total expected production units
            "year_1_units": 250000,
            "year_1_depreciation": 22500  # (100000-10000) × (250000/1000000)
        },
        "use_case": "Manufacturing equipment, vehicles (based on mileage/hours)"
    },
    "sum_of_years_digits": {
        "formula": "(Cost - Salvage) × (Remaining Life / Sum of Years)",
        "description": "Accelerated depreciation (not as aggressive as DDB)",
        "example": {
            "cost": 100000,
            "salvage": 10000,
            "life_years": 5,
            "sum_of_years": 15,  # 5+4+3+2+1
            "schedule": [
                {"year": 1, "fraction": "5/15", "depreciation": 30000, "book_value": 70000},
                {"year": 2, "fraction": "4/15", "depreciation": 24000, "book_value": 46000},
                {"year": 3, "fraction": "3/15", "depreciation": 18000, "book_value": 28000},
                {"year": 4, "fraction": "2/15", "depreciation": 12000, "book_value": 16000},
                {"year": 5, "fraction": "1/15", "depreciation": 6000, "book_value": 10000}
            ]
        },
        "use_case": "Assets that lose value quickly but want smoother curve than DDB"
    }
}
```

**Multi-Book Depreciation**:
```python
depreciation_books = {
    "corporate_book": {
        "purpose": "Internal financial reporting",
        "method": "Straight Line",
        "life": 5,
        "convention": "Half-year (½ year depreciation in year 1 and last year)"
    },
    "tax_book": {
        "purpose": "Tax filing (IRS Form 4562 in US)",
        "method": "MACRS (Modified Accelerated Cost Recovery System)",
        "life": 7,  # Per IRS tables
        "convention": "Half-year",
        "section_179": "Optional immediate expensing up to limit",
        "bonus_depreciation": "Additional first-year depreciation"
    },
    "ifrs_book": {
        "purpose": "IFRS financial statements",
        "method": "Component-based depreciation",
        "life": "Varies by component"
    },
    "benefit": "Different depreciation for different reporting purposes"
}
```

**Depreciation Processing**:
```python
depreciation_run = {
    "frequency": "Monthly, Quarterly, or Annually",
    "process": [
        "Calculate depreciation for period",
        "Post depreciation journal entries",
        "Update asset book values",
        "Generate depreciation reports"
    ],
    "adjustments": {
        "mid_year_acquisition": "Pro-rate depreciation",
        "asset_improvement": "Add to cost, extend life, or both",
        "impairment": "Write down to recoverable amount",
        "revaluation": "Adjust to fair value (IFRS)"
    }
}
```

**Depreciation Reports**:
- Depreciation schedule (all assets)
- Asset valuation report (by category, location, department)
- Depreciation expense by period
- Tax depreciation summary
- Book vs. tax reconciliation
- Projected depreciation (future periods)

### 3. Asset Tracking & Physical Verification
**Status**: Must-Have | **Competitive Parity**: Advanced

**Tracking Technologies**:
```python
tracking_methods = {
    "barcode": {
        "technology": "1D or 2D barcodes",
        "application": "Affix barcode label to asset",
        "scanning": "Mobile app or handheld scanner",
        "use_case": "General asset tracking, cost-effective"
    },
    "rfid": {
        "technology": "Radio Frequency Identification",
        "types": {
            "passive": "No battery, powered by reader (range: few feet)",
            "active": "Battery-powered, long range (100+ feet)"
        },
        "benefits": ["Bulk scanning", "No line-of-sight needed", "Real-time location"],
        "use_case": "High-value assets, large quantities, automated tracking"
    },
    "gps": {
        "technology": "GPS/GNSS tracking devices",
        "data": "Real-time location, movement history, geofencing",
        "use_case": "Mobile assets (vehicles, trailers, heavy equipment)"
    },
    "iot_sensors": {
        "technology": "IoT devices with multiple sensors",
        "data": ["Location", "Temperature", "Vibration", "Usage hours", "Fuel level"],
        "use_case": "Critical assets, predictive maintenance"
    },
    "nfc": {
        "technology": "Near Field Communication",
        "application": "Tap phone to NFC tag",
        "use_case": "Quick check-in/check-out, field service"
    }
}
```

**Physical Verification (Asset Audit)**:
```python
physical_verification_process = {
    "planning": {
        "frequency": "Annual or as required",
        "scope": "All assets, or by location/category",
        "teams": "Assign auditors to locations/categories",
        "cutoff_date": "As of specific date"
    },
    "execution": {
        "methods": ["Barcode scan", "RFID scan", "Manual count"],
        "mobile_app": "Auditors use mobile app to scan and verify",
        "fields_to_verify": ["Location", "Condition", "Custodian"],
        "photos": "Capture asset photos"
    },
    "reconciliation": {
        "found_assets": "Assets located and verified",
        "missing_assets": "Assets not found (variance)",
        "untagged_assets": "Physical assets not in system (additions)",
        "variance_report": "Detailed variance analysis"
    },
    "resolution": {
        "update_records": "Correct location, custodian, status",
        "investigate_missing": "Search, declare lost, or write off",
        "add_new_assets": "Register untagged assets",
        "adjust_books": "Write off missing assets, add found assets"
    }
}
```

**Asset Movements**:
```python
movement_tracking = {
    "movement_types": {
        "transfer": "Move from location A to location B",
        "check_out": "Assign to employee (e.g., laptop)",
        "check_in": "Return from employee",
        "loan": "Temporary transfer to another department",
        "return": "Return from loan"
    },
    "approval": "Manager approval for high-value assets",
    "documentation": "Reason, transfer form, custody acknowledgment",
    "notification": "Notify old and new custodians",
    "audit_trail": "Complete movement history"
}
```

### 4. Maintenance Management
**Status**: Must-Have | **Competitive Advantage**: Predictive

**Maintenance Types**:
```python
maintenance_strategies = {
    "reactive": {
        "description": "Fix when broken",
        "use_case": "Low-value, non-critical assets",
        "cost": "Lowest maintenance cost, highest total cost (due to downtime)"
    },
    "preventive": {
        "description": "Scheduled maintenance based on time or usage",
        "triggers": ["Calendar (monthly, quarterly)", "Usage (hours, miles, cycles)"],
        "activities": ["Inspection", "Lubrication", "Parts replacement", "Calibration"],
        "use_case": "Critical assets, equipment with predictable wear",
        "benefit": "Reduce unexpected failures, extend asset life"
    },
    "predictive": {
        "description": "Condition-based maintenance",
        "monitoring": {
            "vibration_analysis": "Detect bearing wear, misalignment",
            "thermal_imaging": "Detect overheating, electrical issues",
            "oil_analysis": "Detect contamination, wear particles",
            "ultrasound": "Detect leaks, electrical discharge",
            "motor_current": "Detect motor issues"
        },
        "use_case": "High-value, critical assets with sensors",
        "benefit": "Optimize maintenance timing, avoid premature replacement"
    },
    "prescriptive": {
        "description": "AI predicts failure and prescribes action",
        "technology": "IoT + machine learning",
        "output": "Recommended action, optimal timing, expected failure mode",
        "use_case": "Mission-critical assets",
        "benefit": "Maximize uptime, minimize cost"
    }
}
```

**Preventive Maintenance Scheduling**:
```python
pm_schedule = {
    "asset": "CNC Machine #5",
    "pm_plans": [
        {
            "task": "Daily Inspection",
            "frequency": "Daily",
            "duration": "15 minutes",
            "checklist": ["Check coolant level", "Inspect for leaks", "Verify safety guards"]
        },
        {
            "task": "Weekly Lubrication",
            "frequency": "Weekly",
            "duration": "30 minutes",
            "parts": ["Lubricant oil - 2 liters"]
        },
        {
            "task": "Monthly Calibration",
            "frequency": "Monthly",
            "duration": "2 hours",
            "technician": "Certified technician required",
            "tools": ["Calibration kit"]
        },
        {
            "task": "Annual Overhaul",
            "frequency": "Annually",
            "duration": "8 hours",
            "vendor": "External service provider",
            "parts": ["Replacement kit"],
            "cost_estimate": 5000
        }
    ],
    "auto_generation": "System auto-generates work orders based on schedule"
}
```

**Work Order Management**:
```python
maintenance_work_order = {
    "header": {
        "wo_number": "Auto-generated",
        "wo_type": "Corrective, Preventive, Predictive, Project",
        "asset_id": "Asset being maintained",
        "priority": "Emergency, High, Normal, Low",
        "status": "Open, Assigned, In Progress, On Hold, Completed, Closed"
    },
    "planning": {
        "description": "Work to be performed",
        "estimated_hours": "Labor hours",
        "required_skills": "Technician certifications",
        "required_parts": "Spare parts list",
        "required_tools": "Special tools/equipment",
        "safety_procedures": "Safety requirements"
    },
    "scheduling": {
        "scheduled_start": "When to start",
        "scheduled_end": "When to complete",
        "assigned_to": "Technician(s)",
        "coordination": "Production schedule (minimize disruption)"
    },
    "execution": {
        "actual_start": "Actual start time",
        "actual_end": "Actual completion time",
        "labor_hours": "Actual hours worked",
        "parts_used": "Parts consumed",
        "findings": "What was found/repaired",
        "follow_up": "Any follow-up required"
    },
    "completion": {
        "completion_notes": "Work performed",
        "root_cause": "Why failure occurred",
        "corrective_action": "What was done",
        "preventive_action": "How to prevent recurrence",
        "asset_condition": "After maintenance (Good, Fair, Poor)"
    },
    "costing": {
        "labor_cost": "Hours × labor rate",
        "parts_cost": "Parts consumed",
        "vendor_cost": "External services",
        "total_cost": "Sum of all costs"
    }
}
```

**Predictive Maintenance**:
```python
predictive_maintenance = {
    "data_collection": {
        "iot_sensors": "Continuous monitoring of asset health",
        "parameters": ["Vibration", "Temperature", "Pressure", "RPM", "Current", "Sound"],
        "frequency": "Real-time or periodic (e.g., every minute)"
    },
    "anomaly_detection": {
        "baseline": "Establish normal operating parameters",
        "detection": "ML models detect deviations from baseline",
        "alerts": "Notify maintenance team when anomaly detected"
    },
    "failure_prediction": {
        "model": "Machine learning (e.g., Random Forest, LSTM)",
        "features": ["Sensor data", "Historical failures", "Operating conditions"],
        "output": {
            "failure_probability": "% chance of failure in next X days",
            "expected_failure_date": "Predicted failure date",
            "failure_mode": "Most likely failure type (bearing, motor, etc.)",
            "confidence": "Prediction confidence score"
        }
    },
    "maintenance_recommendation": {
        "action": "Replace bearing, lubricate, adjust alignment, etc.",
        "urgency": "Critical (1-7 days), High (1-2 weeks), Medium (1 month)",
        "estimated_cost": "Cost if maintained now vs. cost if failure occurs",
        "roi": "Cost savings from proactive maintenance"
    }
}
```

**Spare Parts Management**:
```python
spare_parts_inventory = {
    "critical_spares": {
        "identification": "Parts required for critical assets",
        "min_stock": "Minimum quantity to maintain",
        "reorder_point": "Trigger for replenishment",
        "lead_time": "Supplier lead time",
        "vendor": "Preferred supplier"
    },
    "parts_forecast": {
        "historical_usage": "Past consumption patterns",
        "pm_schedule": "Planned maintenance requirements",
        "failure_prediction": "AI-predicted part failures",
        "recommended_stock": "Optimal inventory level"
    },
    "parts_usage_tracking": {
        "issue_to_wo": "Track which parts used for which work order",
        "cost_allocation": "Allocate parts cost to asset",
        "warranty_tracking": "Track parts under warranty"
    }
}
```

### 5. Asset Transfer & Disposal
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Asset Transfer**:
```python
transfer_process = {
    "internal_transfer": {
        "types": ["Interdepartmental", "Interlocation", "Intercompany"],
        "accounting": "Transfer between cost centers, no gain/loss",
        "documentation": "Transfer form, receiving acknowledgment",
        "approval": "Manager approval required"
    },
    "lease_transfer": {
        "scenario": "Transfer leased asset to new lessee",
        "accounting": "Update lease liability and ROU asset",
        "documentation": "Lease assignment agreement"
    }
}
```

**Asset Disposal**:
```python
disposal_methods = {
    "sale": {
        "process": [
            "Obtain approval for disposal",
            "Determine fair market value",
            "Find buyer (auction, direct sale, trade-in)",
            "Execute sale agreement",
            "Remove from asset register",
            "Calculate gain/loss on disposal"
        ],
        "accounting": {
            "proceeds": "Cash or value received",
            "book_value": "Cost - accumulated depreciation",
            "gain_loss": "Proceeds - book value",
            "journal_entry": {
                "debit": ["Cash", "Accumulated Depreciation", "Loss on Disposal (if loss)"],
                "credit": ["Asset Cost", "Gain on Disposal (if gain)"]
            }
        }
    },
    "scrap": {
        "process": "Asset has no residual value, dispose as scrap",
        "accounting": {
            "scrap_value": "Minimal or zero",
            "loss": "Book value recognized as loss"
        },
        "documentation": "Scrap certificate, destruction certificate"
    },
    "trade_in": {
        "process": "Trade old asset for new asset",
        "accounting": {
            "trade_in_value": "Credit toward new asset",
            "book_value": "Remaining book value of old asset",
            "gain_loss": "Trade-in value - book value"
        }
    },
    "donation": {
        "process": "Donate asset to charity, school, etc.",
        "accounting": {
            "fair_value": "Market value at donation date",
            "gain_loss": "Fair value - book value",
            "tax_benefit": "Donation receipt for tax deduction"
        }
    },
    "retirement": {
        "process": "Asset no longer usable, retire without sale",
        "accounting": "Write off remaining book value as loss"
    }
}
```

**Disposal Approval Workflow**:
```python
disposal_workflow = {
    "step_1_request": "Custodian requests disposal (reason, condition)",
    "step_2_evaluation": "Asset manager evaluates (repair vs. replace)",
    "step_3_approval": "Manager approves disposal",
    "step_4_valuation": "Determine fair market value",
    "step_5_disposal_method": "Select method (sale, scrap, donate)",
    "step_6_execute": "Complete disposal",
    "step_7_accounting": "Post disposal transaction, recognize gain/loss",
    "step_8_documentation": "Archive disposal records (compliance)"
}
```

**Environmental & Compliance**:
```python
disposal_compliance = {
    "e_waste": {
        "regulation": "EPA, WEEE Directive (EU)",
        "requirement": "Proper disposal of electronics, batteries",
        "certified_recycler": "Use certified e-waste recycler",
        "documentation": "Certificate of recycling/destruction"
    },
    "hazardous_materials": {
        "regulation": "EPA, OSHA, DOT",
        "requirement": "Special handling and disposal",
        "documentation": "Hazmat disposal records"
    },
    "data_security": {
        "requirement": "Sanitize data from computers, drives, copiers",
        "methods": ["Data wiping software", "Physical destruction", "Degaussing"],
        "documentation": "Certificate of data destruction"
    },
    "audit_trail": {
        "requirement": "Maintain complete disposal records",
        "retention": "Per regulatory requirements (7+ years)",
        "fields": ["Disposal date", "Method", "Proceeds", "Gain/loss", "Approvals"]
    }
}
```

### 6. Asset Leasing (ASC 842 / IFRS 16 Compliance)
**Status**: Must-Have | **Competitive Parity**: Advanced

**Lease Accounting**:
```python
lease_accounting = {
    "asc_842": {
        "effective": "US GAAP (ASC 842) effective 2019+",
        "key_change": "All leases on balance sheet (with exceptions)",
        "lease_classification": {
            "finance_lease": {
                "criteria": "Transfer ownership, bargain purchase, >75% useful life, PV >90% FMV",
                "accounting": "Similar to asset purchase + loan",
                "balance_sheet": "ROU Asset + Lease Liability"
            },
            "operating_lease": {
                "criteria": "Does not meet finance lease criteria",
                "accounting": "Straight-line rent expense",
                "balance_sheet": "ROU Asset + Lease Liability"
            }
        },
        "short_term_exemption": "Leases ≤12 months can be expensed"
    },
    "ifrs_16": {
        "effective": "IFRS 16 effective 2019+",
        "key_change": "Single lessee accounting model (no operating lease concept)",
        "accounting": "All leases as ROU Asset + Lease Liability",
        "exemptions": ["Short-term leases (≤12 months)", "Low-value assets (<$5000)"]
    }
}
```

**Lease Management**:
```python
lease_lifecycle = {
    "lease_origination": {
        "fields": ["Lessor", "Lease term", "Payment schedule", "Purchase option", "Termination clauses"],
        "documents": ["Lease agreement", "Payment schedule", "Insurance certificate"]
    },
    "initial_recognition": {
        "rou_asset": "Right-of-Use Asset = PV of lease payments + initial direct costs",
        "lease_liability": "Present value of lease payments (discount rate = implicit rate or IBR)",
        "journal_entry": {
            "debit": "ROU Asset",
            "credit": "Lease Liability"
        }
    },
    "subsequent_measurement": {
        "monthly": {
            "interest_expense": "Lease Liability × discount rate",
            "lease_liability_reduction": "Payment - interest expense",
            "amortization": "ROU Asset / lease term (straight-line)",
            "journal_entries": [
                {
                    "debit": ["Interest Expense", "Lease Liability"],
                    "credit": "Cash"
                },
                {
                    "debit": "Amortization Expense",
                    "credit": "Accumulated Amortization - ROU Asset"
                }
            ]
        }
    },
    "modification": {
        "scenarios": ["Lease extension", "Termination", "Change in payments"],
        "accounting": "Remeasure ROU Asset and Lease Liability"
    },
    "termination": {
        "early_termination": "Write off ROU Asset and Lease Liability, recognize gain/loss",
        "normal_expiry": "ROU Asset fully amortized, liability fully paid"
    }
}
```

**Lease Reports**:
- Lease schedule (all leases with terms, payments)
- Lease liability maturity analysis (future payments by year)
- ROU asset rollforward
- Lease expense analysis (by category, location)
- ASC 842 / IFRS 16 disclosure reports

### 7. Asset Insurance & Risk Management
**Status**: Should-Have | **Competitive Parity**: Industry Standard

**Insurance Management**:
```python
insurance_features = {
    "insurance_policies": {
        "policy_tracking": ["Policy number", "Insurer", "Coverage type", "Policy limits"],
        "assets_covered": "Link assets to policies",
        "premium_tracking": "Premium amount, payment schedule",
        "renewal_alerts": "Alert before policy expiry",
        "documents": "Store policy documents"
    },
    "coverage_types": {
        "property_insurance": "Damage, theft, fire",
        "liability_insurance": "Third-party injury, damage",
        "equipment_breakdown": "Mechanical/electrical failure",
        "business_interruption": "Loss of income due to asset failure"
    },
    "claims_management": {
        "claim_creation": "Document incident, file claim",
        "claim_tracking": "Status, claim amount, settlement",
        "settlement": "Record insurance proceeds",
        "asset_update": "Update asset condition, book value after claim"
    }
}
```

**Risk Management**:
```python
risk_features = {
    "risk_assessment": {
        "identify_risks": "Asset failure, theft, damage, obsolescence",
        "risk_rating": "Likelihood × Impact",
        "criticality_analysis": "Which assets are mission-critical"
    },
    "risk_mitigation": {
        "preventive_maintenance": "Reduce failure risk",
        "security_measures": "Physical security, access control",
        "insurance": "Transfer financial risk",
        "redundancy": "Backup assets for critical functions",
        "diversification": "Don't over-rely on single asset/vendor"
    },
    "business_continuity": {
        "identify_critical_assets": "Assets required to operate",
        "recovery_time_objective": "How quickly asset must be restored",
        "recovery_plan": "Steps to recover from asset loss"
    }
}
```

### 8. Asset Analytics & Reporting
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Asset KPIs**:
```python
asset_metrics = {
    "financial": {
        "total_asset_value": "Sum of book values",
        "depreciation_expense": "Period depreciation",
        "roi_on_assets": "Income generated / asset value",
        "average_asset_age": "Average age of asset base",
        "capital_expenditure": "New asset acquisitions",
        "disposal_gain_loss": "Net gain/loss on disposals"
    },
    "operational": {
        "asset_utilization": "Actual usage / available capacity",
        "uptime": "% time asset is operational",
        "mtbf": "Mean Time Between Failures",
        "mttr": "Mean Time To Repair",
        "maintenance_cost_per_asset": "Annual maintenance cost / asset count",
        "cost_per_operating_hour": "Total cost / operating hours"
    },
    "maintenance": {
        "pm_compliance": "% of scheduled PM completed on time",
        "reactive_vs_proactive": "% work orders that are reactive",
        "work_order_backlog": "Open work orders / total work orders",
        "wrench_time": "% time technicians spend on actual work (vs. admin)"
    },
    "lifecycle": {
        "asset_lifecycle_cost": "Acquisition + operating + maintenance + disposal",
        "remaining_useful_life": "Years left before replacement",
        "replacement_forecast": "Assets due for replacement (next 1-5 years)",
        "obsolescence_risk": "Assets at risk of obsolescence"
    }
}
```

**Predictive Analytics**:
```python
ai_predictions = {
    "failure_prediction": {
        "model": "Predict asset failure within X days",
        "features": ["Age", "Usage", "Maintenance history", "Sensor data"],
        "output": "Failure probability, expected date, failure mode",
        "use": "Proactive maintenance, avoid unplanned downtime"
    },
    "lifecycle_cost_prediction": {
        "model": "Predict total cost of ownership",
        "features": ["Asset type", "Usage pattern", "Maintenance history"],
        "output": "Projected maintenance cost over next 5 years",
        "use": "Better capital planning, lease vs. buy decisions"
    },
    "optimal_replacement_timing": {
        "model": "Determine when to replace vs. maintain",
        "analysis": "Compare: (maintenance cost + downtime cost) vs. (new asset cost - residual value)",
        "output": "Recommended replacement date",
        "use": "Optimize asset lifecycle, avoid over-maintaining aging assets"
    },
    "utilization_optimization": {
        "model": "Identify underutilized assets",
        "output": "Assets with <50% utilization",
        "use": "Redeploy, sell, or rent out underutilized assets"
    },
    "spare_parts_forecasting": {
        "model": "Predict spare parts demand",
        "features": ["Asset base", "Failure rates", "PM schedules"],
        "output": "Recommended inventory levels",
        "use": "Optimize spare parts inventory (reduce stockouts and excess)"
    }
}
```

**Reports & Dashboards**:
```python
reports = {
    "asset_register": "Complete list of all assets with details",
    "depreciation_schedule": "Depreciation by asset, period",
    "asset_valuation": "Total asset value by category, location, department",
    "disposal_report": "Assets disposed in period with gain/loss",
    "maintenance_summary": "Maintenance cost, work orders by asset",
    "utilization_report": "Asset utilization rates",
    "pm_compliance": "% of PM completed on time",
    "capex_report": "Capital expenditure summary",
    "lease_schedule": "All leases with payment obligations",
    "asset_forecast": "Projected replacements and capex",
    "regulatory_compliance": "Inspections, certifications due"
}

dashboards = {
    "asset_overview": "Total assets, value, depreciation",
    "maintenance_dashboard": "Work orders, PM compliance, downtime",
    "financial_dashboard": "Depreciation, capex, disposal gains",
    "risk_dashboard": "Critical assets, failure predictions, insurance"
}
```

### 9. Regulatory Compliance & Audit
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Compliance Requirements**:
```python
compliance_areas = {
    "financial_reporting": {
        "gaap": "Asset capitalization, depreciation (ASC 360)",
        "ifrs": "IAS 16 (Property, Plant, Equipment), IAS 36 (Impairment)",
        "asc_842_ifrs_16": "Lease accounting",
        "sox": "Sarbanes-Oxley controls over asset records"
    },
    "tax_compliance": {
        "depreciation": "Tax depreciation (MACRS, CCA, etc.)",
        "form_4562": "Depreciation and Amortization (US)",
        "property_tax": "Annual property tax filings",
        "transfer_pricing": "Asset transfers between related entities"
    },
    "regulatory_inspections": {
        "osha": "Equipment safety inspections",
        "epa": "Environmental compliance (emissions, waste)",
        "fda": "Medical device, lab equipment validation",
        "dot": "Vehicle inspections, driver logs",
        "faa": "Aircraft maintenance and inspections"
    },
    "industry_specific": {
        "healthcare": "Biomedical equipment calibration, sterilization records",
        "manufacturing": "Equipment certifications, calibration",
        "utilities": "NERC CIP (critical infrastructure protection)",
        "transportation": "Vehicle maintenance logs, driver qualifications"
    }
}
```

**Audit Trail**:
```python
audit_features = {
    "change_log": "All changes to asset master data logged",
    "transaction_history": "Complete history of transactions (acquisition, transfer, disposal)",
    "user_actions": "Who did what and when",
    "document_retention": "Store all supporting documents",
    "reports": "Audit trail reports for specific assets or periods",
    "compliance_reports": "Pre-built reports for auditors"
}
```

### 10. Mobile Asset Management
**Status**: Should-Have | **Competitive Parity**: Industry Standard

**Mobile App Capabilities**:
```python
mobile_features = {
    "asset_lookup": "Search and view asset details",
    "barcode_qr_scanning": "Scan asset tags for quick access",
    "physical_verification": "Conduct asset audits from mobile",
    "location_update": "Update asset location with GPS",
    "condition_assessment": "Rate asset condition, add photos",
    "maintenance_wo": {
        "view_assigned_wo": "See work orders assigned to me",
        "update_wo_status": "Start, complete work orders",
        "record_time": "Log labor hours",
        "record_parts": "Record parts used",
        "add_notes": "Completion notes, findings",
        "capture_photos": "Before/after photos"
    },
    "check_out_check_in": "Check out assets (laptops, tools) to employees",
    "issue_reporting": "Report asset problems from field",
    "offline_mode": "Work offline, sync when online"
}
```

---

## AI Agent Integration

### Asset Management AI Agents

**1. Asset Lifecycle Optimizer Agent**
```python
agent_capabilities = {
    "lifecycle_cost_analysis": "Calculate and predict total cost of ownership",
    "replacement_recommendations": "Suggest optimal replacement timing",
    "lease_vs_buy_analysis": "Compare financial options",
    "utilization_optimization": "Identify underutilized assets",
    "portfolio_optimization": "Recommend optimal asset portfolio mix"
}
```

**2. Predictive Maintenance Agent**
```python
agent_capabilities = {
    "failure_prediction": "Predict equipment failures before they occur",
    "maintenance_scheduling": "Optimize PM schedules based on condition",
    "anomaly_detection": "Detect unusual patterns in sensor data",
    "root_cause_analysis": "Analyze failure patterns and suggest root causes",
    "spare_parts_forecasting": "Predict parts demand, optimize inventory"
}
```

**3. Compliance Monitor Agent**
```python
agent_capabilities = {
    "inspection_due_alerts": "Alert on upcoming inspections, certifications",
    "compliance_gap_analysis": "Identify non-compliant assets",
    "regulatory_updates": "Monitor for regulatory changes",
    "documentation_check": "Ensure required documents are on file",
    "audit_preparation": "Compile audit packages automatically"
}
```

**4. Financial Optimizer Agent**
```python
agent_capabilities = {
    "depreciation_optimization": "Optimize depreciation methods for tax",
    "disposal_timing": "Suggest optimal disposal timing for tax",
    "capex_planning": "Forecast capital expenditure needs",
    "budget_variance_alerts": "Alert when capex exceeds budget",
    "lease_vs_buy": "Financial analysis for lease vs. buy decisions"
}
```

**5. Asset Discovery Agent**
```python
agent_capabilities = {
    "network_scanning": "Discover IT assets on network",
    "software_license_audit": "Identify installed software, license compliance",
    "shadow_it_detection": "Detect unauthorized assets",
    "auto_tagging": "Suggest asset categorization and tagging",
    "duplicate_detection": "Identify duplicate asset records"
}
```

---

## Database Schema

```sql
-- Assets
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Identification
    asset_number VARCHAR(50) UNIQUE NOT NULL,
    asset_tag VARCHAR(50),
    serial_number VARCHAR(100),
    asset_name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Classification
    asset_category VARCHAR(100),  -- Building, Vehicle, Equipment, IT, Furniture
    asset_class VARCHAR(100),
    asset_type VARCHAR(100),
    asset_status VARCHAR(50) DEFAULT 'active',  -- active, idle, under_maintenance, disposed

    -- Financial
    acquisition_cost DECIMAL(15, 2) NOT NULL,
    acquisition_date DATE NOT NULL,
    placed_in_service_date DATE,
    supplier_id UUID REFERENCES suppliers(id),
    purchase_order_id UUID REFERENCES purchase_orders(id),
    funding_source VARCHAR(100),
    asset_value_type VARCHAR(50),  -- owned, leased, rented

    -- Depreciation
    depreciation_method VARCHAR(50),  -- straight_line, declining_balance, units_of_production
    useful_life_years INTEGER,
    salvage_value DECIMAL(15, 2) DEFAULT 0,
    depreciation_start_date DATE,

    -- Location
    current_location VARCHAR(255),
    responsible_department_id UUID REFERENCES departments(id),
    custodian_id UUID REFERENCES employees(id),
    site_id UUID REFERENCES sites(id),
    gps_latitude DECIMAL(10, 8),
    gps_longitude DECIMAL(11, 8),

    -- Specifications
    manufacturer VARCHAR(255),
    model_number VARCHAR(255),
    year_manufactured INTEGER,
    capacity VARCHAR(100),
    technical_specs JSONB,

    -- Warranty & Service
    warranty_expiry_date DATE,
    service_contract_id UUID,

    -- Insurance
    insured BOOLEAN DEFAULT false,
    insurance_policy_number VARCHAR(100),
    insured_value DECIMAL(15, 2),
    insurance_expiry_date DATE,

    -- Compliance
    regulatory_compliance VARCHAR(255),
    certifications TEXT[],
    next_inspection_date DATE,

    -- Hierarchy
    parent_asset_id UUID REFERENCES assets(id),

    -- Disposal
    disposal_date DATE,
    disposal_method VARCHAR(50),  -- sale, scrap, donation, trade_in, retirement
    disposal_proceeds DECIMAL(15, 2),
    disposal_book_value DECIMAL(15, 2),
    disposal_gain_loss DECIMAL(15, 2),

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID REFERENCES users(id),

    INDEX idx_tenant_status (tenant_id, asset_status),
    INDEX idx_asset_number (asset_number),
    INDEX idx_asset_tag (asset_tag),
    INDEX idx_category (asset_category),
    INDEX idx_location (site_id, current_location),
    INDEX idx_custodian (custodian_id),
    INDEX idx_parent (parent_asset_id)
);

-- Asset Depreciation Books
CREATE TABLE asset_depreciation_books (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id),

    book_type VARCHAR(50),  -- corporate, tax, ifrs
    depreciation_method VARCHAR(50),
    useful_life_years INTEGER,
    salvage_value DECIMAL(15, 2),

    accumulated_depreciation DECIMAL(15, 2) DEFAULT 0,
    book_value DECIMAL(15, 2),

    last_depreciation_date DATE,

    INDEX idx_asset (asset_id),
    INDEX idx_book_type (book_type)
);

-- Depreciation Runs
CREATE TABLE depreciation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    run_number VARCHAR(50) UNIQUE NOT NULL,
    period_start_date DATE NOT NULL,
    period_end_date DATE NOT NULL,
    book_type VARCHAR(50),

    total_depreciation DECIMAL(15, 2),
    asset_count INTEGER,

    status VARCHAR(50) DEFAULT 'draft',  -- draft, posted, reversed
    posted_at TIMESTAMPTZ,
    posted_by UUID REFERENCES users(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_period (tenant_id, period_start_date)
);

-- Depreciation Entries
CREATE TABLE depreciation_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    depreciation_run_id UUID REFERENCES depreciation_runs(id),
    asset_id UUID REFERENCES assets(id),

    depreciation_amount DECIMAL(15, 2),
    accumulated_depreciation DECIMAL(15, 2),
    book_value DECIMAL(15, 2),

    journal_entry_id UUID REFERENCES journal_entries(id),

    INDEX idx_run (depreciation_run_id),
    INDEX idx_asset (asset_id)
);

-- Asset Movements
CREATE TABLE asset_movements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    asset_id UUID REFERENCES assets(id),

    movement_type VARCHAR(50),  -- transfer, check_out, check_in, loan, return
    movement_date TIMESTAMPTZ DEFAULT NOW(),

    from_location VARCHAR(255),
    to_location VARCHAR(255),
    from_custodian_id UUID REFERENCES employees(id),
    to_custodian_id UUID REFERENCES employees(id),

    reason TEXT,
    notes TEXT,

    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id),

    INDEX idx_asset (asset_id),
    INDEX idx_movement_date (movement_date DESC)
);

-- Maintenance Work Orders
CREATE TABLE asset_maintenance_wo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    wo_number VARCHAR(50) UNIQUE NOT NULL,
    asset_id UUID REFERENCES assets(id),

    wo_type VARCHAR(50),  -- corrective, preventive, predictive, emergency, project
    priority VARCHAR(50) DEFAULT 'normal',  -- critical, high, normal, low

    problem_description TEXT,

    assigned_to UUID REFERENCES users(id),
    assigned_at TIMESTAMPTZ,

    scheduled_start TIMESTAMPTZ,
    scheduled_end TIMESTAMPTZ,
    actual_start TIMESTAMPTZ,
    actual_end TIMESTAMPTZ,

    labor_hours DECIMAL(8, 2),
    labor_cost DECIMAL(15, 2),
    parts_cost DECIMAL(15, 2),
    vendor_cost DECIMAL(15, 2),
    total_cost DECIMAL(15, 2),

    root_cause TEXT,
    corrective_action TEXT,
    preventive_action TEXT,

    asset_condition_after VARCHAR(50),  -- good, fair, poor

    status VARCHAR(50) DEFAULT 'open',  -- open, assigned, in_progress, on_hold, completed, closed, cancelled

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_tenant_status (tenant_id, status),
    INDEX idx_asset (asset_id),
    INDEX idx_assigned_to (assigned_to),
    INDEX idx_scheduled_start (scheduled_start)
);

-- Preventive Maintenance Plans
CREATE TABLE pm_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    asset_id UUID REFERENCES assets(id),

    plan_name VARCHAR(255) NOT NULL,
    description TEXT,

    frequency_type VARCHAR(50),  -- daily, weekly, monthly, quarterly, annually, usage_based
    frequency_value INTEGER,  -- e.g., every 500 hours

    duration_hours DECIMAL(5, 2),

    checklist TEXT,
    required_parts JSONB,
    required_tools TEXT,

    auto_generate_wo BOOLEAN DEFAULT true,
    advance_days INTEGER DEFAULT 7,  -- Generate WO X days in advance

    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_asset (asset_id)
);

-- PM Schedule (Generated Work Orders)
CREATE TABLE pm_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pm_plan_id UUID REFERENCES pm_plans(id),
    asset_id UUID REFERENCES assets(id),

    scheduled_date DATE NOT NULL,
    wo_id UUID REFERENCES asset_maintenance_wo(id),

    status VARCHAR(50) DEFAULT 'scheduled',  -- scheduled, wo_created, completed, skipped

    INDEX idx_pm_plan (pm_plan_id),
    INDEX idx_scheduled_date (scheduled_date)
);

-- Asset Physical Verification
CREATE TABLE asset_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    verification_number VARCHAR(50) UNIQUE NOT NULL,
    verification_date DATE NOT NULL,
    cutoff_date DATE,

    scope VARCHAR(50),  -- all, by_location, by_category
    location VARCHAR(255),
    category VARCHAR(100),

    total_assets_expected INTEGER,
    total_assets_found INTEGER,
    total_assets_missing INTEGER,
    total_assets_untagged INTEGER,

    status VARCHAR(50) DEFAULT 'in_progress',  -- in_progress, completed, reconciled

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_tenant (tenant_id),
    INDEX idx_status (status)
);

-- Verification Details
CREATE TABLE asset_verification_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    verification_id UUID REFERENCES asset_verifications(id),
    asset_id UUID REFERENCES assets(id),

    expected_location VARCHAR(255),
    actual_location VARCHAR(255),
    expected_custodian_id UUID REFERENCES employees(id),
    actual_custodian_id UUID REFERENCES employees(id),

    found BOOLEAN DEFAULT false,
    condition VARCHAR(50),  -- good, fair, poor
    notes TEXT,
    photo_url VARCHAR(500),

    verified_by UUID REFERENCES users(id),
    verified_at TIMESTAMPTZ,

    INDEX idx_verification (verification_id),
    INDEX idx_asset (asset_id)
);

-- Asset Leases
CREATE TABLE asset_leases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    lease_number VARCHAR(50) UNIQUE NOT NULL,
    lessor VARCHAR(255) NOT NULL,

    lease_start_date DATE NOT NULL,
    lease_end_date DATE NOT NULL,
    lease_term_months INTEGER,

    lease_classification VARCHAR(50),  -- finance, operating (ASC 842)
    discount_rate DECIMAL(8, 4),  -- %

    -- Payments
    payment_frequency VARCHAR(50),  -- monthly, quarterly, annually
    payment_amount DECIMAL(15, 2),

    -- Amounts
    rou_asset_initial DECIMAL(15, 2),
    lease_liability_initial DECIMAL(15, 2),

    rou_asset_current DECIMAL(15, 2),
    lease_liability_current DECIMAL(15, 2),
    accumulated_amortization DECIMAL(15, 2),

    -- Options
    purchase_option BOOLEAN DEFAULT false,
    purchase_option_amount DECIMAL(15, 2),
    renewal_option BOOLEAN DEFAULT false,

    status VARCHAR(50) DEFAULT 'active',  -- active, terminated, expired

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant (tenant_id),
    INDEX idx_status (status)
);

-- Leased Assets
CREATE TABLE leased_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lease_id UUID REFERENCES asset_leases(id),
    asset_id UUID REFERENCES assets(id),

    INDEX idx_lease (lease_id),
    INDEX idx_asset (asset_id)
);

-- Lease Payments
CREATE TABLE lease_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lease_id UUID REFERENCES asset_leases(id),

    payment_date DATE NOT NULL,
    payment_amount DECIMAL(15, 2),

    interest_expense DECIMAL(15, 2),
    principal_payment DECIMAL(15, 2),

    remaining_liability DECIMAL(15, 2),

    journal_entry_id UUID REFERENCES journal_entries(id),

    INDEX idx_lease (lease_id),
    INDEX idx_payment_date (payment_date)
);

-- Asset Documents
CREATE TABLE asset_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id),

    document_type VARCHAR(100),  -- invoice, warranty, manual, insurance, inspection_report
    document_name VARCHAR(255) NOT NULL,
    document_url VARCHAR(500) NOT NULL,
    file_size INTEGER,
    mime_type VARCHAR(100),

    uploaded_by UUID REFERENCES users(id),
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_asset (asset_id),
    INDEX idx_document_type (document_type)
);

-- Asset Audit Log
CREATE TABLE asset_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    entity_type VARCHAR(100),  -- asset, depreciation, movement, maintenance
    entity_id UUID,
    action VARCHAR(50),  -- create, update, delete, dispose

    field_name VARCHAR(100),
    old_value TEXT,
    new_value TEXT,

    performed_by UUID REFERENCES users(id),
    performed_at TIMESTAMPTZ DEFAULT NOW(),
    ip_address INET,

    INDEX idx_entity (entity_type, entity_id),
    INDEX idx_performed_at (performed_at DESC)
);
```

---

## API Specification

### Asset Management

```
POST   /api/v1/assets                           # Create asset
GET    /api/v1/assets                           # List assets (with filters)
GET    /api/v1/assets/{id}                      # Get asset details
PUT    /api/v1/assets/{id}                      # Update asset
DELETE /api/v1/assets/{id}                      # Dispose asset
GET    /api/v1/assets/{id}/hierarchy            # Get asset hierarchy
GET    /api/v1/assets/{id}/documents            # Get asset documents
POST   /api/v1/assets/{id}/documents            # Upload document
```

### Depreciation

```
POST   /api/v1/assets/depreciation/run          # Run depreciation
GET    /api/v1/assets/depreciation/runs         # List depreciation runs
GET    /api/v1/assets/depreciation/runs/{id}    # Get run details
POST   /api/v1/assets/depreciation/runs/{id}/post # Post depreciation
POST   /api/v1/assets/depreciation/runs/{id}/reverse # Reverse depreciation

GET    /api/v1/assets/{id}/depreciation-schedule # Get depreciation schedule
GET    /api/v1/assets/depreciation/forecast     # Forecast future depreciation
```

### Asset Movements

```
POST   /api/v1/assets/movements                 # Create movement (transfer)
GET    /api/v1/assets/movements                 # List movements
GET    /api/v1/assets/{id}/movement-history     # Get movement history

POST   /api/v1/assets/{id}/check-out            # Check out asset
POST   /api/v1/assets/{id}/check-in             # Check in asset
```

### Maintenance

```
POST   /api/v1/assets/maintenance/work-orders   # Create maintenance WO
GET    /api/v1/assets/maintenance/work-orders   # List work orders
GET    /api/v1/assets/maintenance/work-orders/{id} # Get WO details
PUT    /api/v1/assets/maintenance/work-orders/{id} # Update WO
POST   /api/v1/assets/maintenance/work-orders/{id}/complete # Complete WO

POST   /api/v1/assets/maintenance/pm-plans      # Create PM plan
GET    /api/v1/assets/maintenance/pm-plans      # List PM plans
GET    /api/v1/assets/{id}/maintenance-history  # Get maintenance history
```

### Physical Verification

```
POST   /api/v1/assets/verifications             # Create verification
GET    /api/v1/assets/verifications             # List verifications
GET    /api/v1/assets/verifications/{id}        # Get verification details
POST   /api/v1/assets/verifications/{id}/verify # Record asset verification
POST   /api/v1/assets/verifications/{id}/reconcile # Reconcile variances
```

### Leases

```
POST   /api/v1/assets/leases                    # Create lease
GET    /api/v1/assets/leases                    # List leases
GET    /api/v1/assets/leases/{id}               # Get lease details
PUT    /api/v1/assets/leases/{id}               # Update lease
POST   /api/v1/assets/leases/{id}/payment       # Record lease payment
POST   /api/v1/assets/leases/{id}/terminate     # Terminate lease
```

### Analytics & Reports

```
GET    /api/v1/assets/analytics/summary         # Asset summary metrics
GET    /api/v1/assets/analytics/utilization     # Utilization metrics
GET    /api/v1/assets/analytics/maintenance-cost # Maintenance cost analysis

GET    /api/v1/assets/reports/register          # Asset register
GET    /api/v1/assets/reports/depreciation      # Depreciation schedule
GET    /api/v1/assets/reports/valuation         # Asset valuation report
GET    /api/v1/assets/reports/disposal          # Disposal report
GET    /api/v1/assets/reports/lease-schedule    # Lease payment schedule
```

---

## Security & Compliance

### Data Security
```python
security_measures = {
    "access_control": {
        "role_based": "Asset Manager, Maintenance Tech, Custodian roles",
        "field_level": "Restrict financial data to authorized users",
        "location_based": "Users see only assets at their locations",
        "audit_trail": "All transactions logged"
    },
    "approval_workflows": {
        "disposal": "Manager approval for asset disposal",
        "transfer": "Approval for high-value asset transfers",
        "purchase": "Capex approval workflow"
    }
}
```

### Compliance
```python
compliance_frameworks = {
    "financial_reporting": {
        "gaap": "ASC 360 (Property, Plant, Equipment)",
        "ifrs": "IAS 16, IAS 36",
        "asc_842": "Lease accounting (US GAAP)",
        "ifrs_16": "Lease accounting (IFRS)",
        "sox": "Internal controls over asset records"
    },
    "tax_compliance": {
        "depreciation": "Tax depreciation per jurisdiction",
        "property_tax": "Annual property tax filings",
        "transfer_tax": "Tax on asset transfers"
    },
    "regulatory": {
        "osha": "Equipment safety inspections",
        "epa": "Environmental compliance",
        "industry_specific": "FDA, DOT, FAA, etc."
    },
    "data_retention": {
        "asset_records": "Permanent (or until disposal + 7 years)",
        "supporting_docs": "Per regulatory requirements",
        "audit_trail": "Indefinite retention"
    }
}
```

---

## Implementation Roadmap

### Phase 1: Foundation (Month 1-2)
- [ ] Asset master data management
- [ ] Asset categorization and hierarchy
- [ ] Asset registration workflow
- [ ] Document management
- [ ] Basic reporting (asset register, valuation)

### Phase 2: Depreciation (Month 3)
- [ ] Depreciation methods (SL, DB, UOP)
- [ ] Multi-book depreciation (corporate, tax)
- [ ] Depreciation run processing
- [ ] Depreciation reports
- [ ] Journal entry posting

### Phase 3: Asset Tracking (Month 4)
- [ ] Barcode/QR code generation
- [ ] Mobile app for scanning
- [ ] Asset movements (transfer, check-out/in)
- [ ] Physical verification
- [ ] Location tracking

### Phase 4: Maintenance (Month 5-6)
- [ ] Maintenance work orders
- [ ] Preventive maintenance plans
- [ ] PM scheduling and auto-generation
- [ ] Spare parts management
- [ ] Maintenance cost tracking

### Phase 5: Advanced Features (Month 7-8)
- [ ] Lease accounting (ASC 842 / IFRS 16)
- [ ] Asset disposal workflow
- [ ] Insurance management
- [ ] Predictive maintenance (IoT sensors)
- [ ] AI failure prediction

### Phase 6: AI & Analytics (Month 9-10)
- [ ] AI agents (lifecycle optimizer, predictive maintenance)
- [ ] Predictive analytics (failure, replacement timing)
- [ ] Advanced dashboards
- [ ] Optimization recommendations

---

## Competitive Analysis

| Feature | SARAISE | SAP EAM | IBM Maximo | Infor EAM | Oracle EBS Assets | IFS Applications |
|---------|---------|---------|------------|-----------|------------------|------------------|
| **Asset Master Data** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Depreciation** | ✓ Multi-book | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Asset Tracking** | ✓ Barcode/RFID | ✓ | ✓ | ✓ | Limited | ✓ |
| **Maintenance Mgmt** | ✓ | ✓ | ✓ Best-in-class | ✓ | Limited | ✓ |
| **Preventive Maint** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Predictive Maint** | ✓ AI-powered | ✓ Limited | ✓ | ✓ Limited | ✗ | ✓ Limited |
| **Lease Accounting** | ✓ ASC842/IFRS16 | ✓ (add-on) | ✗ | ✗ | ✓ | ✓ |
| **Physical Verification** | ✓ Mobile app | ✓ | ✓ | ✓ | Limited | ✓ |
| **IoT Integration** | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **AI Agents** | ✓ 5+ types | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Predictive Analytics** | ✓ | ✓ Limited | ✓ Limited | ✗ | ✗ | ✗ |
| **Mobile App** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **ERP Integration** | ✓ Native | ✓ Native | Via connector | ✓ Native | ✓ Native | ✓ Native |
| **Pricing** | $$ | $$$$ | $$$$ | $$$ | $$$ | $$$ |

**Verdict**: Feature-comparable to SAP EAM and IBM Maximo for asset and maintenance management. Superior AI capabilities (predictive maintenance, lifecycle optimization). Best-in-class lease accounting. Significantly lower cost than enterprise solutions.

---

## Success Metrics

### Financial
- **Asset Utilization**: > 80% (optimize asset usage)
- **Depreciation Accuracy**: 100% accurate and on-time
- **Capital Planning Accuracy**: ±10% vs. actual capex
- **Cost Savings**: 20% reduction in maintenance costs (reactive → preventive/predictive)

### Operational
- **Asset Uptime**: > 95%
- **MTBF (Mean Time Between Failures)**: Increase by 30%
- **MTTR (Mean Time To Repair)**: Reduce by 25%
- **PM Compliance**: > 95% of scheduled PM completed on time

### Maintenance
- **Reactive vs. Proactive**: < 30% reactive maintenance (target: mostly preventive/predictive)
- **Work Order Backlog**: < 15% open work orders
- **Maintenance Cost per Asset**: Reduce by 20%
- **Failure Prediction Accuracy**: > 80%

### Compliance
- **Inspection Compliance**: 100% compliance with mandatory inspections
- **Audit Findings**: Zero material audit findings
- **Physical Verification Accuracy**: > 98% asset accuracy

### Business Impact
- **Total Cost of Ownership**: Reduce by 15%
- **Asset Lifecycle Extension**: Extend asset life by 10%
- **ROI**: 4x return on investment in year 1
- **Unplanned Downtime**: Reduce by 40%

---

**Document Control**:
- **Author**: SARAISE Architecture Team
- **Last Updated**: 2025-11-10
- **Status**: Planning - Ready for Implementation
