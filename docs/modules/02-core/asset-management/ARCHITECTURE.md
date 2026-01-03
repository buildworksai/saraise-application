<!-- SPDX-License-Identifier: Apache-2.0 -->
# Asset Management Module - Architecture

**Version:** 1.0.0
**Last Updated:** 2025-12-02
**Status:** Architecture Design
**Merged from:** ASSET-MANAGEMENT-DESIGN.md and ASSET-MANAGEMENT-DESIGN-PART2.md

---

## Table of Contents

- [1. Module Overview](#1-module-overview)
  - [1.1 Purpose & Value Proposition](#11-purpose--value-proposition)
  - [1.2 Success Metrics](#12-success-metrics)
- [2. Market & Competitive Research](#2-market--competitive-research)
  - [2.1 Competitive Landscape](#21-competitive-landscape)
  - [2.2 Market Gaps & Opportunities](#22-market-gaps--opportunities)
  - [2.3 Feature Comparison Matrix](#23-feature-comparison-matrix)
- [3. Architecture & Technical Design](#3-architecture--technical-design)
  - [3.1 Module Structure](#31-module-structure)
  - [3.2 Core Data Models](#32-core-data-models)
  - [3.3 Service Layer Architecture](#33-service-layer-architecture)
  - [3.4 API Endpoints](#34-api-endpoints)
- [4. UX/UI Design](#4-uxui-design)
  - [4.1 User Personas & Jobs-to-Be-Done](#41-user-personas--jobs-to-be-done)
  - [4.2 Key User Flows](#42-key-user-flows)
  - [4.3 Design System](#43-design-system)
- [4. UX/UI Design (Continued)](#4-uxui-design-continued)
  - [4.4 Accessibility (WCAG 2.2 AA+)](#44-accessibility-wcag-22-aa)
  - [4.5 Component Inventory](#45-component-inventory)
    - [Core Components](#core-components)
    - [Third-Party Dependencies](#third-party-dependencies)
- [5. Performance & Quality](#5-performance--quality)
  - [5.1 Performance Budgets](#51-performance-budgets)
  - [5.2 Code Quality Standards](#52-code-quality-standards)
  - [5.3 Internationalization (i18n)](#53-internationalization-i18n)
  - [5.4 Mobile-First Responsiveness](#54-mobile-first-responsiveness)
- [6. Security & Compliance](#6-security--compliance)
  - [6.1 Data Privacy & Protection](#61-data-privacy--protection)
  - [6.2 RBAC Integration](#62-rbac-integration)
  - [6.3 Audit Logging](#63-audit-logging)
  - [6.4 Compliance Features](#64-compliance-features)
- [7. Testing Strategy](#7-testing-strategy)
  - [7.1 Unit Tests](#71-unit-tests)
  - [7.2 Integration Tests](#72-integration-tests)
  - [7.3 E2E Tests](#73-e2e-tests)
  - [7.4 Performance Tests](#74-performance-tests)
- [8. Telemetry & Observability](#8-telemetry--observability)
  - [8.1 Metrics Collection](#81-metrics-collection)
  - [8.2 Logging Strategy](#82-logging-strategy)
  - [8.3 Alerting](#83-alerting)
- [9. Implementation Roadmap](#9-implementation-roadmap)
  - [Phase 1: Foundation (Week 1-2)](#phase-1-foundation-week-1-2)
  - [Phase 2: Depreciation (Week 3-4)](#phase-2-depreciation-week-3-4)
  - [Phase 3: Asset Tracking (Week 5-6)](#phase-3-asset-tracking-week-5-6)
  - [Phase 4: Maintenance (Week 7-8)](#phase-4-maintenance-week-7-8)
  - [Phase 5: Advanced Features (Week 9-10)](#phase-5-advanced-features-week-9-10)
  - [Phase 6: AI & Predictive (Week 11-12)](#phase-6-ai--predictive-week-11-12)
- [10. Deliverables Checklist](#10-deliverables-checklist)
  - [Documentation](#documentation)
  - [Code Artifacts](#code-artifacts)
  - [Quality Gates](#quality-gates)
  - [UX/UI Deliverables](#uxui-deliverables)
  - [Integration Points](#integration-points)

---

**Module:** `assets`
**Location:** `backend/src/modules/assets/`
**Documentation Path:** `docs/modules/02-core-business/ASSET-MANAGEMENT-DESIGN.md`
**Dependencies:** `["base", "auth", "metadata", "accounting"]`
**Estimated Time:** 2 weeks
**Status:** 🟡 Planning

---

## 1. Module Overview

### 1.1 Purpose & Value Proposition

**Problem Statement:**
Organizations struggle with manual asset tracking, inaccurate depreciation calculations, lack of maintenance visibility, compliance complexity, and poor asset utilization. Current solutions are either enterprise-focused (SAP EAM, IBM Maximo) or too basic (spreadsheets), leaving mid-market companies without optimal fixed asset management capabilities.

**Value Proposition:**
- **AI-Powered Asset Intelligence:** Automated depreciation, predictive maintenance, failure forecasting, and utilization optimization
- **Complete Lifecycle Management:** From acquisition to disposal with full audit trail
- **Multi-Book Depreciation:** Corporate and tax depreciation with automatic journal entries
- **Maintenance Integration:** Preventive and corrective maintenance scheduling
- **Compliance Automation:** GAAP, IFRS, tax compliance, and regulatory reporting
- **Mobile Asset Tracking:** Barcode/QR scanning, location tracking, physical verification

**Target Users:**
- Asset Managers (primary)
- Finance/Accounting (depreciation, reporting)
- Maintenance Teams (work orders, scheduling)
- Procurement (asset acquisition)
- Compliance Officers (regulatory reporting)
- Field Technicians (mobile tracking)

### 1.2 Success Metrics

**Business Outcomes:**
- **Asset Visibility:** 100% asset register accuracy
- **Depreciation Accuracy:** 99.9% accuracy in calculations
- **Maintenance Efficiency:** Reduce unplanned downtime by 30%
- **Compliance:** Zero regulatory violations
- **Asset Utilization:** Increase utilization by 25%

**Technical Metrics:**
- **Module Performance:** < 200ms API response time (95th percentile)
- **Test Coverage:** ≥ 90%
- **Accessibility:** WCAG 2.2 AA+ compliance
- **Mobile Usage:** 60%+ of asset tracking via mobile

---

## 2. Market & Competitive Research

### 2.1 Competitive Landscape

**Direct Competitors:**
1. **SAP EAM (Enterprise Asset Management)**
   - **Strengths:** Comprehensive EAM, strong maintenance, integration with SAP ERP
   - **Weaknesses:** Complex implementation, expensive, SAP ecosystem dependency
   - **Market Position:** Large enterprise, manufacturing

2. **IBM Maximo**
   - **Strengths:** Industry-leading maintenance management, IoT integration, predictive analytics
   - **Weaknesses:** High cost, complex setup, requires IBM infrastructure
   - **Market Position:** Enterprise, asset-intensive industries

3. **Oracle EBS Assets**
   - **Strengths:** Strong depreciation, multi-book, Oracle ERP integration
   - **Weaknesses:** Oracle ecosystem dependency, dated UI, expensive
   - **Market Position:** Enterprise, Oracle customers

4. **Infor EAM**
   - **Strengths:** Good maintenance features, cloud-native, industry-specific solutions
   - **Weaknesses:** Limited depreciation features, weaker mobile app
   - **Market Position:** Mid-market to enterprise

5. **IFS Applications**
   - **Strengths:** Comprehensive EAM, good mobile app, industry focus
   - **Weaknesses:** Complex, expensive, limited mid-market presence
   - **Market Position:** Enterprise, asset-intensive industries

**Indirect Competitors:**
- **QuickBooks** (basic asset tracking)
- **Xero** (simple depreciation)
- **Asset Panda** (mobile-first tracking)
- **Fiix** (maintenance-focused)

### 2.2 Market Gaps & Opportunities

**Identified Gaps:**
1. **AI Integration:** Most solutions have limited AI beyond basic analytics
2. **Mid-Market Focus:** Gap between enterprise complexity and basic tools
3. **Unified Platform:** Fragmented tools for assets, maintenance, depreciation
4. **Mobile-First:** Many solutions have poor mobile experiences
5. **Predictive Maintenance:** Limited IoT and predictive capabilities
6. **Customization:** Limited ability to customize without coding

**SARAISE Opportunities:**
- **AI-First Approach:** Leverage AI for depreciation optimization, failure prediction, utilization insights
- **Metadata Framework:** Enable deep customization of asset fields and workflows
- **Unified Platform:** Single system for assets, depreciation, maintenance, compliance
- **Predictive Intelligence:** Advanced analytics for maintenance scheduling and asset lifecycle
- **Modern UX:** Consumer-grade interface with mobile-first design

### 2.3 Feature Comparison Matrix

| Feature Category | Feature Detail | SARAISE | SAP EAM | IBM Maximo | Oracle | Infor | IFS |
|------------------|----------------|---------|---------|------------|--------|-------|-----|
| **Asset Registration** | Asset master data | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Asset hierarchy | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Barcode/QR tracking | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Depreciation** | Multi-book depreciation | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ |
| | Multiple methods | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Tax depreciation | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ |
| **Maintenance** | Preventive maintenance | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Work order management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Spare parts tracking | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Mobile** | Mobile app | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ |
| | Barcode scanning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Location tracking | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ |
| **Compliance** | GAAP/IFRS reporting | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Tax compliance | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ |
| | Regulatory reporting | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ |
| **AI Features** | Predictive maintenance | ✅ | 🟡 | ✅ | 🟡 | 🟡 | 🟡 |
| | Failure prediction | ✅ | ❌ | 🟡 | ❌ | ❌ | 🟡 |
| | Utilization optimization | ✅ | ❌ | 🟡 | ❌ | ❌ | 🟡 |
| **Customization** | Metadata framework | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| | Custom workflows | ✅ | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 |
| **Integration** | Accounting integration | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Purchase integration | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Key Differentiators:**
- ✅ **AI-First:** Comprehensive AI for depreciation, maintenance, failure prediction
- ✅ **Metadata Framework:** Deep customization without code
- ✅ **Predictive Analytics:** Advanced maintenance and utilization forecasting
- ✅ **Unified Platform:** Single system for assets, depreciation, maintenance
- ✅ **Modern UX:** Consumer-grade interface with mobile-first design

---

## 3. Architecture & Technical Design

### 3.1 Module Structure

```
backend/src/modules/assets/
├── __init__.py              # Module manifest
├── models.py                # Django ORM models
├── serializers.py           # DRF serializers
├── routes.py                # DRF routes
├── services/                # Business logic
│   ├── __init__.py
│   ├── asset_service.py
│   ├── depreciation_service.py
│   ├── maintenance_service.py
│   ├── tracking_service.py
│   └── compliance_service.py
├── tests/                   # 90%+ coverage
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_services.py
│   └── test_routes.py
└── README.md                # Usage documentation
```

### 3.2 Core Data Models

**Asset Model:**
```python
class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    asset_tag: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100))
    asset_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Classification
    asset_category: Mapped[str] = mapped_column(String(100))  # Building, Vehicle, Equipment, IT, Furniture
    asset_class: Mapped[Optional[str]] = mapped_column(String(100))
    asset_type: Mapped[Optional[str]] = mapped_column(String(100))
    asset_status: Mapped[str] = mapped_column(String(50), default="active")  # active, idle, under_maintenance, disposed

    # Financial
    acquisition_cost: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    acquisition_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    placed_in_service_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    supplier_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("suppliers.id"))
    purchase_order_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("purchase_orders.id"))
    funding_source: Mapped[Optional[str]] = mapped_column(String(100))
    asset_value_type: Mapped[str] = mapped_column(String(50), default="owned")  # owned, leased, rented

    # Depreciation
    depreciation_method: Mapped[str] = mapped_column(String(50))  # straight_line, declining_balance, units_of_production
    useful_life_years: Mapped[Optional[int]] = mapped_column(Integer)
    salvage_value: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"))
    depreciation_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Location
    current_location: Mapped[Optional[str]] = mapped_column(String(255))
    responsible_department_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("departments.id"))
    custodian_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("employees.id"))
    site_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("sites.id"))
    gps_latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8))
    gps_longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8))

    # Specifications
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255))
    model_number: Mapped[Optional[str]] = mapped_column(String(255))
    year_manufactured: Mapped[Optional[int]] = mapped_column(Integer)
    technical_specs: Mapped[Optional[dict]] = mapped_column(JSON)

    # Warranty & Insurance
    warranty_expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    insured: Mapped[bool] = mapped_column(Boolean, default=False)
    insurance_policy_number: Mapped[Optional[str]] = mapped_column(String(100))
    insured_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    # Hierarchy
    parent_asset_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("assets.id"))

    # Metadata
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    parent_asset: Mapped[Optional["Asset"]] = relationship("Asset", remote_side=[id])
    child_assets: Mapped[List["Asset"]] = relationship("Asset", foreign_keys=[parent_asset_id])
    depreciation_entries: Mapped[List["DepreciationEntry"]] = relationship("DepreciationEntry")
    maintenance_work_orders: Mapped[List["MaintenanceWorkOrder"]] = relationship("MaintenanceWorkOrder")
```

**DepreciationEntry Model:**
```python
class DepreciationEntry(Base):
    __tablename__ = "depreciation_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("assets.id"), nullable=False, index=True)
    book_type: Mapped[str] = mapped_column(String(50))  # corporate, tax
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    depreciation_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    accumulated_depreciation: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    book_value: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    journal_entry_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("journal_entries.id"))

    # Metadata
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

**MaintenanceWorkOrder Model:**
```python
class MaintenanceWorkOrder(Base):
    __tablename__ = "maintenance_work_orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    work_order_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("assets.id"), nullable=False, index=True)
    work_order_type: Mapped[str] = mapped_column(String(50))  # preventive, corrective, inspection
    priority: Mapped[str] = mapped_column(String(50), default="medium")  # low, medium, high, critical
    status: Mapped[str] = mapped_column(String(50), default="open")  # open, assigned, in_progress, completed, cancelled

    # Scheduling
    scheduled_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Assignment
    assigned_to_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("employees.id"))
    department_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("departments.id"))

    # Details
    description: Mapped[str] = mapped_column(Text)
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    actual_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    # Metadata
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())
```

### 3.3 Service Layer Architecture

**AssetService:**
- `create_asset()` - Create new asset with validation
- `update_asset()` - Update asset information
- `get_asset()` - Get asset details with relationships
- `list_assets()` - Filterable list with pagination
- `transfer_asset()` - Transfer asset to new location/custodian
- `dispose_asset()` - Dispose asset with workflow
- `get_asset_hierarchy()` - Get asset parent-child relationships

**DepreciationService:**
- `calculate_depreciation()` - Calculate depreciation for period
- `run_depreciation()` - Process depreciation for all assets
- `get_depreciation_schedule()` - Get depreciation schedule
- `post_depreciation_journal()` - Create journal entries for depreciation
- `get_book_value()` - Calculate current book value

**MaintenanceService:**
- `create_work_order()` - Create maintenance work order
- `schedule_preventive_maintenance()` - Schedule PM based on plan
- `assign_work_order()` - Assign work order to technician
- `complete_work_order()` - Complete work order with cost tracking
- `get_maintenance_history()` - Get maintenance history for asset

**TrackingService:**
- `generate_barcode()` - Generate barcode/QR code for asset
- `scan_asset()` - Scan asset and update location
- `track_movement()` - Track asset movement/transfer
- `physical_verification()` - Record physical verification
- `get_asset_location()` - Get current asset location

### 3.4 API Endpoints

**Asset Management:**
```
POST   /api/v1/assets                         # Create asset
GET    /api/v1/assets                         # List assets
GET    /api/v1/assets/{id}                    # Get asset
PUT    /api/v1/assets/{id}                    # Update asset
DELETE /api/v1/assets/{id}                    # Dispose asset
POST   /api/v1/assets/{id}/transfer           # Transfer asset
GET    /api/v1/assets/{id}/hierarchy          # Get asset hierarchy
POST   /api/v1/assets/{id}/barcode            # Generate barcode
```

**Depreciation:**
```
POST   /api/v1/assets/depreciation/run        # Run depreciation
GET    /api/v1/assets/{id}/depreciation       # Get depreciation schedule
POST   /api/v1/assets/{id}/depreciation/calculate # Calculate depreciation
GET    /api/v1/assets/depreciation/report     # Depreciation report
```

**Maintenance:**
```
POST   /api/v1/assets/maintenance/work-orders # Create work order
GET    /api/v1/assets/maintenance/work-orders # List work orders
GET    /api/v1/assets/{id}/maintenance        # Get maintenance history
POST   /api/v1/assets/maintenance/schedule    # Schedule PM
```

**Tracking:**
```
POST   /api/v1/assets/{id}/scan               # Scan asset
POST   /api/v1/assets/{id}/move               # Record movement
POST   /api/v1/assets/verify                 # Physical verification
GET    /api/v1/assets/{id}/location           # Get location history
```

---

## 4. UX/UI Design

### 4.1 User Personas & Jobs-to-Be-Done

**Persona 1: Asset Manager (David)**
- **Role:** Manages asset register, depreciation, compliance
- **Goals:** Maintain accurate asset records, ensure compliance, optimize asset utilization
- **Pain Points:** Manual tracking, inaccurate depreciation, compliance complexity
- **Jobs-to-Be-Done:**
  - "I need to register a new asset quickly with all required information"
  - "I need to run depreciation accurately for all assets"
  - "I need to generate compliance reports for auditors"

**Persona 2: Maintenance Technician (Lisa)**
- **Role:** Performs maintenance, tracks work orders, updates asset status
- **Goals:** Complete work orders efficiently, track maintenance costs, prevent failures
- **Pain Points:** Manual work orders, lack of asset history, scheduling complexity
- **Jobs-to-Be-Done:**
  - "I need to see my assigned work orders on my mobile device"
  - "I need to update work order status and costs from the field"
  - "I need to access asset maintenance history quickly"

**Persona 3: Finance Manager (Robert)**
- **Role:** Reviews depreciation, generates financial reports, ensures compliance
- **Goals:** Accurate financial reporting, compliance with GAAP/IFRS, audit readiness
- **Pain Points:** Manual depreciation calculations, complex reporting, audit preparation
- **Jobs-to-Be-Done:**
  - "I need to review depreciation calculations before posting"
  - "I need to generate asset register and depreciation reports"
  - "I need to ensure compliance with accounting standards"

### 4.2 Key User Flows

**Flow 1: Asset Registration**
1. User creates asset from purchase order or manually
2. System generates unique asset number
3. User enters asset details (name, category, cost, location)
4. System validates required fields
5. User configures depreciation method and useful life
6. System calculates initial depreciation schedule
7. Asset is registered and available for tracking

**Flow 2: Depreciation Run**
1. Finance manager initiates depreciation run for period
2. System calculates depreciation for all active assets
3. System generates depreciation entries
4. Finance manager reviews depreciation report
5. System creates journal entries in accounting module
6. Depreciation is posted and book values updated

**Flow 3: Preventive Maintenance**
1. System generates PM work orders based on schedule
2. Work orders assigned to maintenance technicians
3. Technician receives notification on mobile app
4. Technician scans asset barcode to access work order
5. Technician completes maintenance and updates status
6. System records maintenance cost and updates asset status
7. Next PM scheduled automatically

### 4.3 Design System

**Color Palette:**
- Primary: Deep Blue (#1565C0) - Asset actions
- Secondary: Gold (#FF8F00) - Warnings, maintenance due
- Success: Green (#388E3C) - Active, compliant
- Error: Red (#D32F2F) - Disposed, maintenance overdue
- Info: Teal (#00ACC1) - Information, depreciation

**Typography:**
- Headings: Inter Bold
- Body: Inter Regular
- Data/Tables: JetBrains Mono

**Components:**
- Asset card with photo and key info
- Asset hierarchy tree view
- Depreciation schedule table
- Maintenance calendar with work orders
- Barcode scanner component
- Asset location map view
- Work order kanban board



---

*[Continuation of ASSET-MANAGEMENT-DESIGN.md]*

---

## 4. UX/UI Design (Continued)

### 4.4 Accessibility (WCAG 2.2 AA+)

**Requirements:**
- Keyboard navigation for all interactions
- Screen reader support with ARIA labels
- Color contrast ratios ≥ 4.5:1 for text
- Focus indicators visible on all interactive elements
- Form validation with clear error messages
- Alternative text for all images and icons
- Skip navigation links for screen readers

**Mobile Accessibility:**
- Touch target sizes ≥ 44x44px
- Voice input support for barcode scanning
- Haptic feedback for scan confirmation
- Screen reader optimization for mobile
- Camera accessibility for barcode scanning

### 4.5 Component Inventory

#### Core Components
- `AssetDashboard`: Dashboard with KPIs, charts, and alerts
- `AssetList`: Filterable table of assets
- `AssetForm`: Create/edit asset with validation
- `AssetDetail`: View asset with tabs (details, depreciation, maintenance, documents)
- `AssetHierarchy`: Tree view of asset parent-child relationships
- `DepreciationSchedule`: Table showing depreciation over time
- `DepreciationRun`: Interface for running depreciation batch
- `MaintenanceCalendar`: Calendar view of scheduled maintenance
- `WorkOrderList`: Filterable table of work orders
- `WorkOrderForm`: Create/edit work order
- `WorkOrderDetail`: View work order with status and history
- `BarcodeScanner`: Camera-based barcode/QR scanner
- `AssetLocationMap`: Map view showing asset locations
- `PhysicalVerification`: Interface for physical asset verification
- `AssetDisposalForm`: Dispose asset with workflow
- `ComplianceReport`: Generate compliance reports

#### Third-Party Dependencies
- `@tanstack/react-table`: Data table functionality
- `react-big-calendar`: Calendar component for maintenance
- `react-barcode-scanner`: Barcode scanning library
- `react-leaflet`: Map component for location tracking
- `recharts`: Chart visualization library
- `date-fns`: Date formatting and manipulation
- `zod`: Schema validation
- `react-hook-form`: Form state management

---

## 5. Performance & Quality

### 5.1 Performance Budgets

**Page Load Targets:**
- **First Contentful Paint (FCP):** < 1.8s
- **Largest Contentful Paint (LCP):** < 2.5s
- **Time to Interactive (TTI):** < 3.5s
- **Cumulative Layout Shift (CLS):** < 0.1

**API Response Times:**
- **Asset CRUD:** < 200ms (95th percentile)
- **Depreciation Run:** < 10s for 1000 assets
- **Maintenance Query:** < 150ms
- **Barcode Scan:** < 100ms
- **Location Update:** < 200ms

**Database Query Optimization:**
- Index on `asset_number`, `asset_tag`, `tenant_id`
- Index on `asset_id`, `period_start` for depreciation
- Index on `asset_id`, `status` for work orders
- Pagination for all list endpoints (default 50 items)
- Materialized views for depreciation reports

### 5.2 Code Quality Standards

**Test Coverage:**
- **Unit Tests:** ≥ 90% coverage
- **Integration Tests:** All API endpoints
- **E2E Tests:** Critical user flows (registration, depreciation, maintenance)

**Code Standards:**
- TypeScript strict mode
- ESLint with zero warnings
- Prettier code formatting
- Comprehensive JSDoc comments

### 5.3 Internationalization (i18n)

**Supported Languages (Phase 1):**
- English (en-US)
- Spanish (es-ES)
- French (fr-FR)
- German (de-DE)

**Localization Requirements:**
- Date/time formats by locale
- Currency formatting
- Number formatting
- Depreciation rules by country
- Tax compliance by jurisdiction
- Regulatory requirements by region

### 5.4 Mobile-First Responsiveness

**Breakpoint Strategy:**
- **Mobile (320px - 768px):**
  - Stack KPI cards vertically
  - Full-width tables with horizontal scroll
  - Bottom navigation for primary actions
  - Collapsible filters and sidebars
  - Touch-optimized buttons (min 44x44px)
  - Full-screen barcode scanner
  - Swipe gestures for asset cards

- **Tablet (768px - 1024px):**
  - 2-column layout for KPI cards
  - Side-by-side calendar views
  - Inline filters (not collapsible)
  - Split-view for asset detail/edit

- **Desktop (1024px+):**
  - 4-column KPI cards
  - Multi-column dashboard layout
  - Sidebar filters (always visible)
  - Full table views with all columns
  - Hover states for interactive elements

**Mobile-Specific Features:**
- Push notifications for maintenance due
- Offline mode for barcode scanning
- Location services for GPS tracking
- Camera integration for asset photos
- Voice input for work order notes

---

## 6. Security & Compliance

### 6.1 Data Privacy & Protection

**GDPR Compliance:**
- Asset data encryption at rest and in transit
- Right to access (export asset data)
- Data retention policies (7 years for disposed assets)
- Audit logging for all data access
- Secure file storage for documents

**PII Protection:**
- Mask sensitive data in logs
- Role-based field-level access control
- Audit logging for all data access
- Secure file storage for asset documents

### 6.2 RBAC Integration

**Asset Roles:**
- `asset_admin`: Full asset module access
- `asset_manager`: Asset management, depreciation, reporting
- `maintenance_technician`: Work order access, asset scanning
- `finance_manager`: Depreciation, financial reporting
- `compliance_officer`: Compliance reporting, audit access

**Permission Matrix:**
- **Asset Data:** `asset_admin` (CRUD), `asset_manager` (R/U), `maintenance_technician` (R)
- **Depreciation:** `asset_admin`, `asset_manager`, `finance_manager` (CRUD)
- **Maintenance:** `asset_admin`, `asset_manager`, `maintenance_technician` (CRUD)
- **Compliance Reports:** `asset_admin`, `asset_manager`, `compliance_officer` (R)

### 6.3 Audit Logging

**Required Audit Events:**
- Asset creation/modification/disposal
- Depreciation run execution
- Work order creation/completion
- Asset movement/transfer
- Location updates
- Compliance report generation
- Access to sensitive data (financial, compliance)

### 6.4 Compliance Features

**Accounting Standards:**
- **GAAP:** ASC 360 (Property, Plant, Equipment)
- **IFRS:** IAS 16, IAS 36
- **Lease Accounting:** ASC 842 (US GAAP), IFRS 16
- **SOX:** Internal controls over asset records

**Tax Compliance:**
- Tax depreciation per jurisdiction
- Property tax calculations
- Transfer tax on asset transfers
- Depreciation method by tax rules

**Regulatory Compliance:**
- OSHA equipment safety inspections
- EPA environmental compliance
- Industry-specific (FDA, DOT, FAA)
- Data retention per regulatory requirements

---

## 7. Testing Strategy

### 7.1 Unit Tests

**Service Layer Tests:**
- `test_asset_service.py`: Asset CRUD, hierarchy, transfers
- `test_depreciation_service.py`: Depreciation calculation, multi-book, journal entries
- `test_maintenance_service.py`: Work orders, PM scheduling, cost tracking
- `test_tracking_service.py`: Barcode generation, scanning, location tracking

**Model Tests:**
- Field validation
- Relationship integrity
- Constraint enforcement
- Tenant isolation

### 7.2 Integration Tests

**API Endpoint Tests:**
- All CRUD operations
- Depreciation run workflow
- Work order lifecycle
- Barcode scanning
- Permission enforcement
- Error handling
- Pagination and filtering

**Database Tests:**
- Transaction rollback on errors
- Concurrent access handling
- Data integrity constraints
- Depreciation calculation accuracy

### 7.3 E2E Tests

**Critical User Flows:**
- Asset registration end-to-end
- Depreciation run and journal posting
- Preventive maintenance scheduling
- Work order assignment and completion
- Asset disposal workflow
- Physical verification process

**Test Tools:**
- Playwright for browser automation
- API testing with pytest
- Database fixtures for test data
- Mock barcode scanner for testing

### 7.4 Performance Tests

**Load Testing:**
- 5000 concurrent assets
- Depreciation run for 2000 assets
- Maintenance scheduling for 500 assets
- Barcode scanning with 100 concurrent users

**Stress Testing:**
- API rate limiting
- Database connection pooling
- Memory usage under load
- Depreciation calculation performance

---

## 8. Telemetry & Observability

### 8.1 Metrics Collection

**Business Metrics:**
- Asset register accuracy
- Depreciation calculation accuracy
- Maintenance completion rate
- Preventive maintenance compliance
- Asset utilization rate
- Work order turnaround time

**Technical Metrics:**
- API response times by endpoint
- Error rates by endpoint
- Database query performance
- Depreciation run duration
- Barcode scan success rate
- Mobile app usage statistics

### 8.2 Logging Strategy

**Log Levels:**
- **ERROR:** Depreciation errors, data integrity issues
- **WARN:** Maintenance overdue, compliance warnings
- **INFO:** Asset actions, depreciation runs, work orders
- **DEBUG:** Detailed request/response logging (dev only)

**Structured Logging:**
- JSON format for all logs
- Include tenant_id, user_id, action, resource
- Correlation IDs for request tracing

### 8.3 Alerting

**Critical Alerts:**
- Depreciation run failures
- Data integrity violations
- High error rates (> 5%)
- Performance degradation (> 2s response time)

**Business Alerts:**
- Maintenance overdue (> 7 days)
- Depreciation calculation errors
- Asset disposal without approval
- Compliance report generation failures

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Asset master data model
- [ ] Asset CRUD operations
- [ ] Asset hierarchy support
- [ ] Asset categorization
- [ ] RBAC integration
- [ ] Unit tests (≥ 90% coverage)

### Phase 2: Depreciation (Week 3-4)
- [ ] Depreciation methods (SL, DB, UOP)
- [ ] Multi-book depreciation
- [ ] Depreciation run processing
- [ ] Depreciation schedule generation
- [ ] Journal entry posting
- [ ] Integration tests

### Phase 3: Asset Tracking (Week 5-6)
- [ ] Barcode/QR code generation
- [ ] Mobile app for scanning
- [ ] Asset movement tracking
- [ ] Location tracking (GPS)
- [ ] Physical verification
- [ ] Mobile app integration

### Phase 4: Maintenance (Week 7-8)
- [ ] Maintenance work order management
- [ ] Preventive maintenance plans
- [ ] PM scheduling and auto-generation
- [ ] Work order assignment
- [ ] Maintenance cost tracking
- [ ] E2E tests

### Phase 5: Advanced Features (Week 9-10)
- [ ] Asset disposal workflow
- [ ] Insurance management
- [ ] Compliance reporting
- [ ] Advanced analytics
- [ ] Performance optimization
- [ ] Documentation completion

### Phase 6: AI & Predictive (Week 11-12)
- [ ] Predictive maintenance (IoT integration)
- [ ] Failure prediction AI
- [ ] Utilization optimization
- [ ] Maintenance cost forecasting
- [ ] Advanced reporting dashboards

---

## 10. Deliverables Checklist

### Documentation
- [x] Module design document (this file)
- [ ] API documentation (OpenAPI/Swagger)
- [ ] User guide for asset managers
- [ ] Maintenance technician guide
- [ ] Finance manager guide (depreciation)
- [ ] Developer guide (integration)

### Code Artifacts
- [ ] Module manifest (`__init__.py`)
- [ ] Database models (`models.py`)
- [ ] DRF serializers (`serializers.py`)
- [ ] API routes (`routes.py`)
- [ ] Service layer (`services/`)
- [ ] Unit tests (≥ 90% coverage)
- [ ] Integration tests
- [ ] E2E tests

### Quality Gates
- [ ] Test coverage ≥ 90%
- [ ] All tests passing
- [ ] Zero linting errors
- [ ] Zero security vulnerabilities
- [ ] API documented (OpenAPI)
- [ ] Migration file created
- [ ] Clean install/uninstall

### UX/UI Deliverables
- [ ] Component library (Storybook)
- [ ] Design system documentation
- [ ] Mobile app wireframes
- [ ] Accessibility audit report (WCAG 2.2 AA+)
- [ ] Performance audit report

### Integration Points
- [ ] Accounting module integration (depreciation journal entries)
- [ ] Purchase module integration (asset acquisition)
- [ ] Metadata framework integration
- [ ] Customization framework integration
- [ ] AI agent integration (predictive maintenance)

---

**Status:** 🟡 Planning Complete - Ready for Development

**Next Steps:**
1. Review design document with stakeholders
2. Create detailed technical specifications
3. Set up development environment
4. Begin Phase 1 implementation
