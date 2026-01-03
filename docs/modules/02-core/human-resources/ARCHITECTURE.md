<!-- SPDX-License-Identifier: Apache-2.0 -->
# Human Resources Module - Architecture

**Version:** 1.0.0
**Last Updated:** 2025-12-02
**Status:** Architecture Design
**Merged from:** HUMAN-RESOURCES-DESIGN.md and HUMAN-RESOURCES-DESIGN-PART2.md

---

## Table of Contents

- [1. Module Overview](#1-module-overview)
  - [1.1 Purpose & Value Proposition](#11-purpose--value-proposition)
  - [1.2 Success Metrics](#12-success-metrics)
  - [1.3 Next-Gen HR Architecture](#13-next-gen-hr-architecture)
    - [1.3.1 Domain Boundaries & Sub-Modules](#131-domain-boundaries--sub-modules)
    - [1.3.2 Key Data Models (Conceptual)](#132-key-data-models-conceptual)
    - [1.3.3 HR AI Agents](#133-hr-ai-agents)
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
  - [4.6 Next-Gen HR UX & Agents](#46-next-gen-hr-ux--agents)
    - [4.6.1 HR Operations Console](#461-hr-operations-console)
    - [4.6.2 Bands, Rate Cards & Compensation Admin](#462-bands-rate-cards--compensation-admin)
    - [4.6.3 Performance, KPIs & KRAs Experience](#463-performance-kpis--kras-experience)
    - [4.6.4 Time, Leave & Work Patterns](#464-time-leave--work-patterns)
    - [4.6.5 Recognition & Engagement Center](#465-recognition--engagement-center)
    - [4.6.6 HR Copilots & In-Context AI](#466-hr-copilots--in-context-ai)
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
  - [Phase 2: Recruitment (Week 3-4)](#phase-2-recruitment-week-3-4)
  - [Phase 3: Time & Attendance (Week 5-6)](#phase-3-time--attendance-week-5-6)
  - [Phase 4: Payroll (Week 7-8)](#phase-4-payroll-week-7-8)
  - [Phase 5: Performance & Learning (Week 9-10)](#phase-5-performance--learning-week-9-10)
  - [Phase 6: Advanced Features (Week 11-12)](#phase-6-advanced-features-week-11-12)
- [10. Deliverables Checklist](#10-deliverables-checklist)
  - [Documentation](#documentation)
  - [Code Artifacts](#code-artifacts)
  - [Quality Gates](#quality-gates)
  - [UX/UI Deliverables](#uxui-deliverables)
  - [Integration Points](#integration-points)

---

**Module:** `hr`
**Location:** `backend/src/modules/hr/`
**Documentation Path:** `docs/modules/02-core-business/HUMAN-RESOURCES-DESIGN.md`
**Dependencies:** `["base", "auth", "metadata"]`
**Estimated Time:** 2 weeks
**Status:** 🟡 Planning

---

## 1. Module Overview

### 1.1 Purpose & Value Proposition

**Problem Statement:**
HR teams struggle with manual employee lifecycle management, fragmented systems for recruitment/payroll/performance, lack of predictive insights for retention, and compliance complexity across jurisdictions. Current solutions are either enterprise-focused (Workday, SAP SuccessFactors) or too basic (BambooHR), leaving mid-market companies without optimal HCM capabilities.

**Value Proposition:**
- **AI-Powered Talent Intelligence:** Automated resume screening, candidate matching, attrition prediction, and performance insights
- **Unified Employee Experience:** Single platform for recruitment, onboarding, performance, payroll, and offboarding
- **Predictive Analytics:** AI-driven insights for retention risk, performance forecasting, and succession planning
- **Compliance Automation:** Multi-country payroll, statutory reporting, and regulatory compliance
- **Self-Service Excellence:** Intuitive employee and manager portals reducing HR administrative burden

**Target Users:**
- HR Administrators (primary)
- HR Managers
- Employees (self-service)
- Managers (team management)
- Finance (payroll integration)
- Recruiters (ATS users)

### 1.2 Success Metrics

**Business Outcomes:**
- **Time-to-Hire:** Reduce by 40% (from 45 days to 27 days average)
- **HR Administrative Efficiency:** Reduce manual tasks by 60%
- **Employee Satisfaction:** Achieve 85%+ satisfaction with HR services
- **Payroll Accuracy:** 99.9% accuracy rate
- **Compliance:** Zero regulatory violations

**Technical Metrics:**
- **Module Performance:** < 200ms API response time (95th percentile)
- **Test Coverage:** ≥ 90%
- **Accessibility:** WCAG 2.2 AA+ compliance
- **Mobile Usage:** 40%+ of employee interactions via mobile

---

### 1.3 Next-Gen HR Architecture

The HR module in SARAISE is designed as a **workflow- and AI-native people platform**. The design below is the blueprint for implementation.

#### 1.3.1 Domain Boundaries & Sub-Modules

Backend location: `backend/src/modules/hr/`

- `lifecycle`
  - Onboarding, internal transfers, promotions, long-term leaves, offboarding.
  - All modeled as **LifecycleJourneys** with **JourneyTasks** assigned across HR, IT, Facilities, Finance, Security, and managers.

- `time_and_attendance`
  - Work patterns, work calendars, hours/days ledger, overtime rules, shift management.
  - Feeds payroll, billing, utilization analytics, and compliance reports.

- `compensation`
  - Job architecture (families, bands), **Band** and **RateCard** models, comp cycles, band promotions.
  - Integrates with billing, Accounting, and Subscription/Plans for cost and margin analysis.

- `performance`
  - Goal/OKR/KPI/KRA framework, review cycles, 360 feedback, development plans.
  - Feeds promotion, band-change, and learning decisions.

- `recognition`
  - Service recognition events, milestone celebrations, reward catalogs.
  - Integrated with performance and engagement signals from other modules.

- `agents`
  - HR AI agents orchestrating workflows, drafting documents, and providing recommendations.
  - Built using SARAISE’s AI stack (OpenAI SDK, CrewAI/LangGraph, LiteLLM) and exposed via well-defined service interfaces.

#### 1.3.2 Key Data Models (Conceptual)

- **Employee** (extends the existing employee model)
  - Links to **Assignments**, **LifecycleJourneys**, **TimeLedgerEntries**, **Goals/KPIs/KRAs**, **RecognitionEvents**.

- **Assignment**
  - One Employee → many Assignments, each defining: job family, band, cost center, manager, work pattern, location, contract type.
  - Drives rate card lookup and eligibility for policies.

- **LifecycleJourney**
  - Types: `onboarding`, `transfer`, `promotion`, `leave_of_absence`, `return_to_work`, `offboarding`, etc.
  - Holds status, owner, SLA targets, and a list of **JourneyTasks**.

- **JourneyTask**
  - Task assigned to a role/user/team with due date, status, and blocking dependencies.
  - Can be user-driven or AI-driven (e.g., “Draft performance review summary”).

- **WorkPattern / WorkCalendar / TimeLedgerEntry**
  - WorkPattern: template for shifts and weekly patterns.
  - WorkCalendar: company + local holidays + individual exceptions.
  - TimeLedgerEntry: canonical record of work/absence hours and days per employee/assignment.

- **JobFamily / Band / RateCard**
  - JobFamily: e.g., Engineering, Sales, Plant Operations.
  - Band: L1–L10 levels per family, with expectations and KRAs.
  - RateCard: maps (JobFamily, Band, Location, ContractType) → internal cost rate, external billing rate.

- **PerformanceCycle / Goal / KPI / KRA**
  - PerformanceCycle: defines frequency, participants, and evaluation rules.
  - Goal/KPI/KRA: hierarchical objectives with metrics, owners, and alignment (Company → Team → Individual).

- **RecognitionEvent**
  - Captures milestones, achievements, and awards (service anniversaries, major project completions, hero incidents), with metadata for reporting and audit.

#### 1.3.3 HR AI Agents

- **Lifecycle Agent**
  - Orchestrates onboarding, transfers, promotions, offboarding.
  - Generates checklists, monitors SLAs, nudges owners, and escalates when at risk.

- **Talent & Mobility Agent**
  - Matches internal employees to roles using skills, performance, and aspirations.
  - Suggests internal moves and upskilling plans to mitigate attrition risk.

- **Performance Agent**
  - Drafts review summaries based on goals, KPIs/KRAs, feedback, and outcomes.
  - Highlights bias risk and suggests calibration actions.

- **Compensation Agent**
  - Recommends band changes and compensation adjustments considering performance, tenure, market benchmarks, equity, and budget constraints.

- **Recognition Agent**
  - Surfaces recognition opportunities from signals across SARAISE (tickets, incidents, project completions, peer feedback, learning completions).

Agents interact with HR services through well-defined, idempotent APIs and respect SARAISE’s RBAC, audit logging, and tenant isolation rules.

---

## 2. Market & Competitive Research

### 2.1 Competitive Landscape

**Direct Competitors:**
1. **Workday HCM**
   - **Strengths:** Comprehensive HCM suite, strong analytics, cloud-native
   - **Weaknesses:** Complex implementation, high cost, steep learning curve
   - **Market Position:** Enterprise-focused ($50M+ revenue companies)

2. **SAP SuccessFactors**
   - **Strengths:** Global compliance, deep ERP integration, strong performance management
   - **Weaknesses:** Complex UI, expensive, requires SAP ecosystem
   - **Market Position:** Large enterprise, global organizations

3. **Oracle HCM Cloud**
   - **Strengths:** Comprehensive features, AI capabilities, global reach
   - **Weaknesses:** Complex setup, Oracle ecosystem dependency
   - **Market Position:** Enterprise, Oracle customers

4. **ADP Workforce Now**
   - **Strengths:** Best-in-class payroll, strong compliance, extensive integrations
   - **Weaknesses:** Limited talent management, dated UI, expensive
   - **Market Position:** Mid-market to enterprise, payroll-focused

5. **BambooHR**
   - **Strengths:** User-friendly, affordable, good for SMBs
   - **Weaknesses:** Limited advanced features, basic payroll, no AI
   - **Market Position:** Small to mid-market (50-500 employees)

**Indirect Competitors:**
- **Greenhouse** (ATS-focused)
- **15Five** (Performance management)
- **Gusto** (Payroll for SMBs)
- **Zenefits** (All-in-one HRIS)

### 2.2 Market Gaps & Opportunities

**Identified Gaps:**
1. **AI Integration:** Most solutions have limited AI beyond basic chatbots
2. **Unified Experience:** Fragmented tools requiring multiple logins
3. **Mid-Market Focus:** Gap between enterprise complexity and SMB simplicity
4. **Predictive Analytics:** Limited predictive capabilities for retention/performance
5. **Mobile-First:** Many solutions have poor mobile experiences
6. **Customization:** Limited ability to customize workflows without coding

**SARAISE Opportunities:**
- **AI-First Approach:** Leverage AI agents for recruitment, engagement, payroll automation
- **Metadata Framework:** Enable deep customization without code changes
- **Unified Platform:** Single sign-on across all HR functions
- **Predictive Intelligence:** Advanced analytics for retention, performance, succession
- **Modern UX:** Consumer-grade interface with mobile-first design

### 2.3 Feature Comparison Matrix

| Feature Category | Feature Detail | SARAISE | Workday | SAP SF | Oracle | ADP | BambooHR |
|-----------------|----------------|---------|---------|--------|--------|-----|----------|
| **Employee Management** | Employee master data | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Org chart visualization | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Employee self-service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Recruitment** | ATS with pipeline | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | AI resume screening | ✅ | 🟡 | 🟡 | 🟡 | ❌ | ❌ |
| | Interview scheduling | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Time & Attendance** | Clock in/out | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Leave management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Timesheet tracking | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Payroll** | Multi-country payroll | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Tax calculations | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| | Statutory compliance | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Performance** | Performance reviews | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | OKR management | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| | 360-degree feedback | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Learning** | Training catalog | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| | Skills management | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **AI Features** | AI recruitment agent | ✅ | ❌ | ❌ | 🟡 | ❌ | ❌ |
| | Attrition prediction | ✅ | 🟡 | 🟡 | 🟡 | ❌ | ❌ |
| | Performance insights | ✅ | 🟡 | 🟡 | 🟡 | ❌ | ❌ |
| **Customization** | Metadata framework | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| | Custom workflows | ✅ | 🟡 | 🟡 | 🟡 | ❌ | 🟡 |
| **Mobile** | Native mobile app | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| | Mobile-first design | ✅ | 🟡 | 🟡 | 🟡 | 🟡 | ✅ |

**Key Differentiators:**
- ✅ **AI-First:** Comprehensive AI agents for recruitment, engagement, payroll
- ✅ **Metadata Framework:** Deep customization without code
- ✅ **Predictive Analytics:** Advanced retention and performance forecasting
- ✅ **Unified Platform:** Single sign-on across all HR functions
- ✅ **Modern UX:** Consumer-grade interface with mobile-first design

---

## 3. Architecture & Technical Design

### 3.1 Module Structure

```
backend/src/modules/hr/
├── __init__.py              # Module manifest
├── models.py                # Django ORM models
├── serializers.py           # DRF serializers
├── routes.py                # DRF routes
├── services/                # Business logic
│   ├── __init__.py
│   ├── employee_service.py
│   ├── recruitment_service.py
│   ├── attendance_service.py
│   ├── payroll_service.py
│   ├── performance_service.py
│   └── learning_service.py
├── tests/                   # 90%+ coverage
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_services.py
│   └── test_routes.py
└── README.md                # Usage documentation
```

### 3.2 Core Data Models

**Employee Model:**
```python
class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    employee_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))

    # Employment Details
    designation: Mapped[str] = mapped_column(String(100))
    department_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("departments.id"))
    manager_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("employees.id"))
    employment_type: Mapped[str] = mapped_column(String(50))  # Full-time, Part-time, Contract
    employment_status: Mapped[str] = mapped_column(String(50))  # Active, On Leave, Terminated
    hire_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    termination_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Compensation
    salary: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    pay_frequency: Mapped[str] = mapped_column(String(50))  # Monthly, Bi-weekly, Weekly

    # Personal Information
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    gender: Mapped[Optional[str]] = mapped_column(String(20))
    address: Mapped[Optional[dict]] = mapped_column(JSON)
    emergency_contact: Mapped[Optional[dict]] = mapped_column(JSON)

    # Metadata
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department")
    manager: Mapped[Optional["Employee"]] = relationship("Employee", remote_side=[id])
    direct_reports: Mapped[List["Employee"]] = relationship("Employee", foreign_keys=[manager_id])
```

**Job Requisition Model:**
```python
class JobRequisition(Base):
    __tablename__ = "job_requisitions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    requisition_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    job_title: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[str] = mapped_column(String, ForeignKey("departments.id"))
    hiring_manager_id: Mapped[str] = mapped_column(String, ForeignKey("employees.id"))
    positions: Mapped[int] = mapped_column(Integer, default=1)

    # Job Details
    job_description: Mapped[Optional[str]] = mapped_column(Text)
    required_skills: Mapped[List[str]] = mapped_column(JSON)
    preferred_qualifications: Mapped[Optional[List[str]]] = mapped_column(JSON)
    salary_range_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    salary_range_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    # Status & Workflow
    status: Mapped[str] = mapped_column(String(50), default="draft")  # draft, pending_approval, approved, open, filled, cancelled
    approval_status: Mapped[str] = mapped_column(String(50), default="pending")
    approved_by: Mapped[Optional[str]] = mapped_column(String, ForeignKey("employees.id"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Metadata
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())
```

**Candidate Model:**
```python
class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    requisition_id: Mapped[str] = mapped_column(String, ForeignKey("job_requisitions.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))

    # Application Details
    resume_url: Mapped[Optional[str]] = mapped_column(String(500))
    cover_letter: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))  # LinkedIn, Website, Referral, etc.
    applied_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Pipeline Stage
    stage: Mapped[str] = mapped_column(String(50), default="applied")  # applied, screening, interview, offer, hired, rejected
    ai_screening_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  # 0-100
    ai_screening_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Interview Details
    interview_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    interview_feedback: Mapped[Optional[dict]] = mapped_column(JSON)

    # Offer Details
    offer_extended: Mapped[bool] = mapped_column(Boolean, default=False)
    offer_accepted: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Metadata
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())
```

### 3.3 Service Layer Architecture

**EmployeeService:**
- `create_employee()` - Create new employee with validation
- `update_employee()` - Update employee information
- `get_employee()` - Get employee details with relationships
- `list_employees()` - Filterable list with pagination
- `get_org_chart()` - Generate organizational hierarchy
- `transfer_employee()` - Transfer employee to new department/manager
- `promote_employee()` - Promote employee with role change
- `terminate_employee()` - Terminate employment with workflow

**RecruitmentService:**
- `create_requisition()` - Create job requisition
- `approve_requisition()` - Approve requisition with workflow
- `post_job()` - Post job to multiple channels
- `add_candidate()` - Add candidate to pipeline
- `ai_screen_candidate()` - AI-powered resume screening
- `advance_candidate()` - Move candidate to next stage
- `schedule_interview()` - Schedule interview with calendar integration
- `extend_offer()` - Create and send offer letter
- `hire_candidate()` - Convert candidate to employee

**AttendanceService:**
- `clock_in()` - Record clock-in with location validation
- `clock_out()` - Record clock-out with validation
- `get_attendance()` - Get attendance records with filters
- `request_leave()` - Create leave request with workflow
- `approve_leave()` - Approve/reject leave request
- `get_leave_balance()` - Calculate leave balance by type
- `create_timesheet()` - Create timesheet entry
- `submit_timesheet()` - Submit timesheet for approval

**PayrollService:**
- `process_payroll()` - Run payroll for pay period
- `calculate_salary()` - Calculate salary with deductions
- `calculate_taxes()` - Calculate taxes by jurisdiction
- `generate_payslip()` - Generate PDF payslip
- `generate_bank_file()` - Generate bank transfer file
- `get_payroll_report()` - Generate payroll reports

### 3.4 API Endpoints

**Employee Management:**
```
POST   /api/v1/hr/employees                    # Create employee
GET    /api/v1/hr/employees                    # List employees
GET    /api/v1/hr/employees/{id}               # Get employee
PUT    /api/v1/hr/employees/{id}                # Update employee
DELETE /api/v1/hr/employees/{id}               # Deactivate employee
GET    /api/v1/hr/employees/{id}/org-chart      # Get org chart
POST   /api/v1/hr/employees/{id}/transfer       # Transfer employee
POST   /api/v1/hr/employees/{id}/promote        # Promote employee
```

**Recruitment:**
```
POST   /api/v1/hr/requisitions                  # Create requisition
GET    /api/v1/hr/requisitions                  # List requisitions
GET    /api/v1/hr/requisitions/{id}             # Get requisition
PUT    /api/v1/hr/requisitions/{id}             # Update requisition
POST   /api/v1/hr/requisitions/{id}/approve     # Approve requisition
POST   /api/v1/hr/requisitions/{id}/post        # Post job

POST   /api/v1/hr/candidates                    # Add candidate
GET    /api/v1/hr/candidates                    # List candidates
GET    /api/v1/hr/candidates/{id}               # Get candidate
PUT    /api/v1/hr/candidates/{id}               # Update candidate
POST   /api/v1/hr/candidates/{id}/screen        # AI screen candidate
POST   /api/v1/hr/candidates/{id}/advance       # Advance stage
POST   /api/v1/hr/candidates/{id}/hire          # Hire candidate
```

**Attendance & Time:**
```
POST   /api/v1/hr/attendance/clock-in           # Clock in
POST   /api/v1/hr/attendance/clock-out          # Clock out
GET    /api/v1/hr/attendance                    # Get attendance
POST   /api/v1/hr/leave/request                 # Request leave
POST   /api/v1/hr/leave/{id}/approve            # Approve leave
GET    /api/v1/hr/leave/balance                 # Get leave balance
POST   /api/v1/hr/timesheets                    # Create timesheet
GET    /api/v1/hr/timesheets                    # List timesheets
POST   /api/v1/hr/timesheets/{id}/submit        # Submit timesheet
```

---

## 4. UX/UI Design

### 4.1 User Personas & Jobs-to-Be-Done

**Persona 1: HR Administrator (Sarah)**
- **Role:** Manages employee lifecycle, processes payroll, handles compliance
- **Goals:** Reduce manual tasks, ensure accuracy, maintain compliance
- **Pain Points:** Fragmented systems, manual data entry, compliance complexity
- **Jobs-to-Be-Done:**
  - "I need to onboard a new employee quickly without manual paperwork"
  - "I need to process payroll accurately with zero errors"
  - "I need to ensure compliance with labor laws across jurisdictions"

**Persona 2: Hiring Manager (Michael)**
- **Role:** Manages recruitment, interviews candidates, makes hiring decisions
- **Goals:** Hire top talent quickly, reduce time-to-fill, improve candidate experience
- **Pain Points:** Manual scheduling, lack of candidate insights, slow approval process
- **Jobs-to-Be-Done:**
  - "I need to find qualified candidates quickly"
  - "I need to schedule interviews without back-and-forth emails"
  - "I need AI insights to help me make better hiring decisions"

**Persona 3: Employee (Emma)**
- **Role:** Uses self-service portal for personal HR needs
- **Goals:** Access information easily, request time off, view payslips
- **Pain Points:** Complex interfaces, multiple systems, lack of mobile access
- **Jobs-to-Be-Done:**
  - "I need to request time off quickly from my phone"
  - "I need to view my payslip and tax documents easily"
  - "I need to update my personal information without calling HR"

### 4.2 Key User Flows

**Flow 1: Employee Onboarding**
1. HR creates employee record
2. System sends welcome email with credentials
3. Employee logs in to self-service portal
4. Employee completes profile (personal info, emergency contact, bank details)
5. System generates employment documents
6. Employee signs documents electronically
7. System notifies HR and manager of completion

**Flow 2: Recruitment Pipeline**
1. Hiring manager creates job requisition
2. Requisition goes through approval workflow
3. HR posts job to multiple channels
4. Candidates apply via career page
5. AI screens resumes and scores candidates
6. HR reviews top candidates
7. Hiring manager schedules interviews
8. Interview feedback collected
9. Offer extended to selected candidate
10. Candidate accepts offer
11. Candidate converted to employee

**Flow 3: Leave Request**
1. Employee requests leave via mobile app
2. System checks leave balance
3. System applies leave policy rules
4. Request sent to manager for approval
5. Manager approves/rejects via mobile
6. System updates calendar and notifies team
7. System deducts from leave balance

### 4.3 Design System

**Color Palette:**
- Primary: Deep Blue (#1565C0) - HR actions
- Secondary: Gold (#FF8F00) - Warnings, pending
- Success: Green (#388E3C) - Approved, completed
- Error: Red (#D32F2F) - Rejected, errors
- Info: Teal (#00ACC1) - Information, notifications

**Typography:**
- Headings: Inter Bold
- Body: Inter Regular
- Data/Tables: JetBrains Mono

**Components:**
- Employee card with photo and key info
- Org chart visualization component
- Candidate pipeline kanban board
- Leave calendar with availability
- Payslip viewer with PDF download
- Performance review form
- Attendance timesheet grid



---

*[Continuation of HUMAN-RESOURCES-DESIGN.md]*

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
- Voice input support for forms
- Haptic feedback for actions
- Screen reader optimization for mobile

### 4.5 Component Inventory

#### Core Components
- `HRDashboard`: Dashboard with KPIs, charts, and alerts
- `EmployeeList`: Filterable table of employees
- `EmployeeForm`: Create/edit employee with validation
- `EmployeeDetail`: View employee with tabs (profile, attendance, performance, documents)
- `OrgChart`: Interactive organizational hierarchy visualization
- `RequisitionList`: Filterable table of job requisitions
- `RequisitionForm`: Create/edit requisition with approval workflow
- `CandidatePipeline`: Kanban board for candidate stages
- `CandidateCard`: Candidate card with resume preview
- `InterviewScheduler`: Calendar-based interview scheduling
- `AttendanceCalendar`: Monthly attendance calendar view
- `LeaveRequestForm`: Leave request with balance display
- `TimesheetGrid`: Weekly timesheet entry grid
- `PayrollDashboard`: Payroll processing dashboard
- `PayslipViewer`: PDF payslip viewer with download
- `PerformanceReviewForm`: Performance review with goals and feedback
- `TrainingCatalog`: Browse and enroll in training courses

#### Third-Party Dependencies
- `@tanstack/react-table`: Data table functionality
- `react-big-calendar`: Calendar component for scheduling
- `react-pdf`: PDF viewer for payslips
- `react-kanban-board`: Kanban board for candidate pipeline
- `recharts`: Chart visualization library
- `date-fns`: Date formatting and manipulation
- `zod`: Schema validation
- `react-hook-form`: Form state management

---

### 4.6 Next-Gen HR UX & Agents

The HR UX is designed as a **set of consoles and copilot experiences** that surface lifecycle journeys, performance, compensation, time, and recognition in a unified way.

#### 4.6.1 HR Operations Console

- **Lifecycle Pipelines**
  - Kanban-style views for **Onboarding**, **Transfers**, **Promotions**, **Leaves of Absence**, and **Offboarding**.
  - Each card represents a `LifecycleJourney` with status, SLA indicators, and owners.
  - Filters by department, location, job family, band, and journey type.

- **Journey Detail Drawer**
  - Shows the full task list (`JourneyTasks`): completed, in-progress, blocked.
  - Embedded approvals, comments, and audit trail.
  - Direct links to Employee, Assignment, and relevant documents.

- **Policy & Workflow Configuration**
  - Visual builder for onboarding/offboarding/transfer/promotion templates.
  - Per-tenant overrides for approvers, SLAs, and conditional logic (e.g., different flows for contractors vs. FTEs).

#### 4.6.2 Bands, Rate Cards & Compensation Admin

- **Job Architecture Explorer**
  - Tree/grid view of JobFamilies and Bands (L1–L10) with expectations and KRAs.
  - Per-band comp ranges (min/mid/max) by location and currency.

- **Rate Card Management UI**
  - Config tables for internal cost and external billing rates by (family, band, location, contract type).
  - History and effective-dates for audit and forecasting.

- **Comp Cycle & Band Change Workflows**
  - Dashboards showing who is up for band review, promotion, or exceptional adjustment.
  - Inline AI recommendations and impact analysis (cost, equity, headcount plans).

#### 4.6.3 Performance, KPIs & KRAs Experience

- **Goal Alignment Views**
  - Tree from company-level OKRs down to individual KPIs/KRAs.
  - Inline progress, risk flags, and dependencies.

- **Performance Cycle Hub**
  - For each cycle: status of self-reviews, manager reviews, peer feedback, calibration sessions.
  - Direct access to review forms with AI-generated summaries and suggested ratings.

- **Manager & Employee Portals**
  - Managers: team view with goals, performance, upcoming milestones, leave and workload indicators.
  - Employees: personal dashboard showing goals, feedback, upcoming 1:1s, learning and recognition.

#### 4.6.4 Time, Leave & Work Patterns

- **Work Pattern Designer**
  - UI to define shift templates, weekly schedules, and remote/hybrid rules.
  - Previews of how patterns affect overtime, compliance, and utilization.

- **Hours & Days Ledger Views**
  - Employee-centric and team-centric views of hours worked, leave taken, and upcoming absences.
  - Integrations to capacity planning, billing, and payroll checks.

#### 4.6.5 Recognition & Engagement Center

- **Recognition Feed**
  - Stream of RecognitionEvents: anniversaries, promotions, project completions, spot awards.
  - Supports badges, comments, and reactions.

- **Milestone Configuration**
  - UI for HR to configure which events create recognition, associated rewards, and approval rules.

- **Analytics**
  - Reports on recognition coverage, cross-team visibility, and its correlation with performance and attrition.

#### 4.6.6 HR Copilots & In-Context AI

- **HR Console Copilot**
  - Embedded assistant within HR Operations Console:
    - Explains why a journey is at risk.
    - Suggests next best actions (e.g., “remind manager”, “escalate to HRBP”).
    - Generates bulk communications (onboarding welcome emails, offboarding summaries).

- **Manager Copilot**
  - Contextual assistant on manager dashboards:
    - Summarizes team performance and risk.
    - Suggests promotions, band changes, and recognition events.
    - Drafts feedback and performance review comments.

- **Employee Copilot**
  - Within employee self-service:
    - Answers “How many leave days do I have?”, “What do I need to do for promotion to L3?”.
    - Explains policies in plain language, links to workflows (e.g., request transfer, ask for training).

All copilot interactions use SARAISE’s AI stack with strict guardrails: tenant isolation, RBAC enforcement, audit logging, and PII-aware redaction.

---

## 5. Performance & Quality

### 5.1 Performance Budgets

**Page Load Targets:**
- **First Contentful Paint (FCP):** < 1.8s
- **Largest Contentful Paint (LCP):** < 2.5s
- **Time to Interactive (TTI):** < 3.5s
- **Cumulative Layout Shift (CLS):** < 0.1

**API Response Times:**
- **Employee CRUD:** < 200ms (95th percentile)
- **Payroll Processing:** < 5s for 100 employees
- **AI Resume Screening:** < 3s per resume
- **Org Chart Generation:** < 500ms
- **Attendance Query:** < 150ms

**Database Query Optimization:**
- Index on `employee_number`, `email`, `tenant_id`
- Index on `requisition_id`, `stage` for candidates
- Index on `employee_id`, `date` for attendance
- Pagination for all list endpoints (default 50 items)

### 5.2 Code Quality Standards

**Test Coverage:**
- **Unit Tests:** ≥ 90% coverage
- **Integration Tests:** All API endpoints
- **E2E Tests:** Critical user flows (onboarding, recruitment, payroll)

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
- Address formats
- Tax calculation rules by country
- Statutory compliance by jurisdiction

### 5.4 Mobile-First Responsiveness

**Breakpoint Strategy:**
- **Mobile (320px - 768px):**
  - Stack KPI cards vertically
  - Full-width tables with horizontal scroll
  - Bottom navigation for primary actions
  - Collapsible filters and sidebars
  - Touch-optimized buttons (min 44x44px)
  - Swipe gestures for candidate cards

- **Tablet (768px - 1024px):**
  - 2-column layout for KPI cards
  - Side-by-side calendar views
  - Inline filters (not collapsible)
  - Split-view for employee detail/edit

- **Desktop (1024px+):**
  - 4-column KPI cards
  - Multi-column dashboard layout
  - Sidebar filters (always visible)
  - Full table views with all columns
  - Hover states for interactive elements

**Mobile-Specific Features:**
- Push notifications for leave approvals
- Biometric authentication (fingerprint/face)
- Location-based clock in/out
- Camera integration for document upload
- Offline mode for viewing payslips

---

## 6. Security & Compliance

### 6.1 Data Privacy & Protection

**GDPR Compliance:**
- Employee data encryption at rest and in transit
- Right to access (export employee data)
- Right to erasure (anonymize terminated employees)
- Data retention policies (7 years for payroll records)
- Consent management for data processing

**PII Protection:**
- Mask sensitive data in logs
- Role-based field-level access control
- Audit logging for all data access
- Secure file storage for documents

### 6.2 RBAC Integration

**HR Roles:**
- `hr_admin`: Full HR module access
- `hr_manager`: Team management, recruitment, performance
- `hr_analyst`: Read-only access to reports
- `employee`: Self-service portal access
- `manager`: Team management, leave approval, performance reviews
- `recruiter`: Recruitment pipeline access

**Permission Matrix:**
- **Employee Data:** `hr_admin` (CRUD), `hr_manager` (R/U), `employee` (R own), `manager` (R team)
- **Payroll:** `hr_admin` (CRUD), `hr_manager` (R), `employee` (R own)
- **Recruitment:** `hr_admin`, `hr_manager`, `recruiter` (CRUD)
- **Performance:** `hr_admin`, `hr_manager`, `manager` (CRUD), `employee` (R own)

### 6.3 Audit Logging

**Required Audit Events:**
- Employee creation/modification/termination
- Payroll processing
- Leave request approval/rejection
- Candidate stage changes
- Performance review submission
- Salary changes
- Access to sensitive data (payslips, performance reviews)

### 6.4 Compliance Features

**Multi-Country Payroll:**
- Country-specific tax calculations
- Statutory reporting (W-2, T4, etc.)
- Labor law compliance (overtime, minimum wage)
- Holiday calendar by country
- Currency conversion for global employees

**Labor Law Compliance:**
- Minimum wage enforcement
- Overtime calculation rules
- Break time requirements
- Maximum working hours
- Leave entitlement by jurisdiction

---

## 7. Testing Strategy

### 7.1 Unit Tests

**Service Layer Tests:**
- `test_employee_service.py`: Employee CRUD, org chart, transfers
- `test_recruitment_service.py`: Requisition workflow, AI screening, candidate pipeline
- `test_attendance_service.py`: Clock in/out, leave balance, timesheet
- `test_payroll_service.py`: Salary calculation, tax computation, payslip generation

**Model Tests:**
- Field validation
- Relationship integrity
- Constraint enforcement
- Tenant isolation

### 7.2 Integration Tests

**API Endpoint Tests:**
- All CRUD operations
- Workflow transitions
- Permission enforcement
- Error handling
- Pagination and filtering

**Database Tests:**
- Transaction rollback on errors
- Concurrent access handling
- Data integrity constraints

### 7.3 E2E Tests

**Critical User Flows:**
- Employee onboarding end-to-end
- Recruitment pipeline (requisition → hire)
- Leave request and approval
- Payroll processing
- Performance review cycle

**Test Tools:**
- Playwright for browser automation
- API testing with pytest
- Database fixtures for test data

### 7.4 Performance Tests

**Load Testing:**
- 1000 concurrent employees
- Payroll processing for 500 employees
- Org chart generation for 1000 employees
- Candidate pipeline with 100 active requisitions

**Stress Testing:**
- API rate limiting
- Database connection pooling
- Memory usage under load

---

## 8. Telemetry & Observability

### 8.1 Metrics Collection

**Business Metrics:**
- Time-to-hire by department
- Employee turnover rate
- Leave utilization rate
- Payroll processing time
- Performance review completion rate
- Training enrollment rate

**Technical Metrics:**
- API response times by endpoint
- Error rates by endpoint
- Database query performance
- AI screening accuracy
- Mobile app usage statistics

### 8.2 Logging Strategy

**Log Levels:**
- **ERROR:** Payroll errors, data integrity issues
- **WARN:** Leave balance warnings, approval delays
- **INFO:** Employee actions, workflow transitions
- **DEBUG:** Detailed request/response logging (dev only)

**Structured Logging:**
- JSON format for all logs
- Include tenant_id, user_id, action, resource
- Correlation IDs for request tracing

### 8.3 Alerting

**Critical Alerts:**
- Payroll processing failures
- Data integrity violations
- High error rates (> 5%)
- Performance degradation (> 2s response time)

**Business Alerts:**
- High turnover rate (> 15% monthly)
- Leave balance exhaustion
- Pending approvals (> 7 days)
- Recruitment pipeline bottlenecks

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Employee master data model
- [ ] Employee CRUD operations
- [ ] Org chart generation
- [ ] Employee self-service portal (basic)
- [ ] RBAC integration
- [ ] Unit tests (≥ 90% coverage)

### Phase 2: Recruitment (Week 3-4)
- [ ] Job requisition workflow
- [ ] Candidate pipeline (ATS)
- [ ] AI resume screening integration
- [ ] Interview scheduling
- [ ] Offer letter generation
- [ ] Integration tests

### Phase 3: Time & Attendance (Week 5-6)
- [ ] Clock in/out functionality
- [ ] Leave management
- [ ] Leave balance tracking
- [ ] Timesheet management
- [ ] Approval workflows
- [ ] Mobile app integration

### Phase 4: Payroll (Week 7-8)
- [ ] Payroll components configuration
- [ ] Salary calculation engine
- [ ] Tax calculation (multi-country)
- [ ] Payslip generation
- [ ] Bank file generation
- [ ] Compliance reporting

### Phase 5: Performance & Learning (Week 9-10)
- [ ] Performance review cycles
- [ ] Goal management (OKRs)
- [ ] 360-degree feedback
- [ ] Training catalog
- [ ] Skills management
- [ ] E2E tests

### Phase 6: Advanced Features (Week 11-12)
- [ ] AI agents (recruitment, engagement)
- [ ] Predictive analytics (attrition, performance)
- [ ] Advanced reporting and dashboards
- [ ] Mobile app enhancements
- [ ] Performance optimization
- [ ] Documentation completion

---

## 10. Deliverables Checklist

### Documentation
- [x] Module design document (this file)
- [ ] API documentation (OpenAPI/Swagger)
- [ ] User guide for HR administrators
- [ ] Employee self-service guide
- [ ] Manager guide (team management)
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
- [ ] Accounting module integration (payroll)
- [ ] CRM module integration (recruitment)
- [ ] Metadata framework integration
- [ ] Customization framework integration
- [ ] AI agent integration

---

**Status:** 🟡 Planning Complete - Ready for Development

**Next Steps:**
1. Review design document with stakeholders
2. Create detailed technical specifications
3. Set up development environment
4. Begin Phase 1 implementation
