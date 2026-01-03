<!-- SPDX-License-Identifier: Apache-2.0 -->
# Human Resources Management (HRM) Module

**Module Code**: `hr`
**Category**: Core Business
**Priority**: Critical - Human Capital Management
**Version**: 1.0.0
**Status**: Implementation Complete

---

## Executive Summary

The Human Resources Management module provides end-to-end **employee lifecycle management** from recruitment to retirement. Powered by AI agents, this module automates talent acquisition, performance management, payroll processing, and workforce analytics—delivering a world-class HCM experience that rivals SAP SuccessFactors, Workday, Oracle HCM Cloud, and ADP.

### Vision

**"Empowering organizations to attract, develop, and retain world-class talent through intelligent automation and data-driven insights."**

---

### Next-Gen HR Vision

The HR module in SARAISE is designed to go beyond parity with leading HCM suites and deliver a **fully-orchestrated, AI-native people platform** that treats the employee lifecycle as a set of configurable journeys, tightly integrated with SARAISE’s workflow, metadata, and analytics engines.

- **Employee Lifecycle as Orchestrated Journeys**
  - Predefined, customizable workflows for **onboarding**, **role change**, **transfer**, **promotion**, **sabbatical/leave of absence**, and **offboarding**.
  - Journey templates per persona (IC, manager, executive, contractor) and per geography, built on SARAISE’s workflow engine.
  - Each journey decomposed into tasks for HR, IT, Facilities, Finance, and the manager; tracked with SLAs, escalations, and AI-driven nudges.

- **Work Hours, Days & Compliance Tracking**
  - Rich modeling of **work patterns**: full-time, part-time, gig, shifts, compressed weeks, flexible hours, remote/hybrid, geo-fenced on-site roles.
  - **Work calendar service** that understands company holidays, local holidays, weekends, and individual work-week patterns.
  - Consolidated **hours & days ledger** per employee (and per assignment) used by time tracking, overtime calculation, payroll, billing, and cost allocation.
  - Policy engine for overtime, minimum rest periods, maximum weekly hours, and labor-law specific rules (jurisdiction-aware).

- **Bands, Rate Cards & Compensation Architecture**
  - First-class model for **job families**, **levels/bands** (e.g., L1–L10), and **banded compensation ranges** by location and currency.
  - **Rate cards** that map band + role + location + contract type to:
    - Hourly/day/monthly internal cost rate.
    - Optional external billing rate (for professional services scenarios).
  - Automated **band promotions** and **comp review workflows** driven by performance data, tenure, internal equity, and market benchmarks.
  - Guardrails on band changes (e.g., max % increase, promotion frequency, exceptional approvals).

- **Performance, KPIs & KRAs as First-Class Citizens**
  - Hierarchical goals: **Company → Unit → Team → Individual** with support for OKRs, KPIs, and KRAs in the same framework.
  - Library of **role-specific KRAs** (e.g., Sales, Engineering, HR, Manufacturing) that can be reused and versioned.
  - Tight integration between **performance reviews**, **1:1s**, **feedback cycles**, and **goal progress**, with AI auto-summarization and suggested talking points.
  - AI agents that propose **goal sets** for new hires, promotions, or role changes based on templates and historical success patterns.

- **Leaves, Absence & Return-to-Work Programs**
  - Multi-country leave policies already defined in the Time & Attendance section, extended with:
    - **Journeys for long-term leave** (parental, medical, sabbatical) including pre-leave prep and return-to-work reintegration.
    - AI assistants that forecast **leave liability** and highlight potential risk hotspots (e.g., chronic absenteeism, burnout indicators).
  - Configurable approval workflows per leave type, with delegation, escalation, and SLAs.

- **Transfers, Role/Location Changes & Internal Mobility**
  - Structured flows for **department transfer**, **manager change**, **location move**, and **temporary assignments/secondments**.
  - Impact analysis across: cost centers, projects, seat planning, and access rights.
  - Alignment with job architecture (families, bands) and automatic updates to reporting lines and org charts.

- **Service Recognition, Rewards & Milestones**
  - Engine for **service recognition** (work anniversaries, key milestones, projects completed) with configuration for: badges, certificates, gifts, and monetary awards.
  - Integration with performance and engagement data to surface **recognition opportunities** (e.g., standout contributors, cross-functional heroes).
  - Optional reward catalogs and point-based systems, with audit-friendly integration to payroll or expense modules.

- **AI Automation & Workflow Templates**
  - Library of **predesigned, customizable HR workflows** modeled as SARAISE workflows:
    - New hire onboarding (by role and location).
    - Internal transfer and promotion.
    - Band change and compensation review.
    - Performance cycle kickoff, mid-cycle check-in, and final review.
    - Offboarding (voluntary/involuntary) with risk and compliance checks.
  - AI agents that:
    - Generate personalized onboarding plans and checklists.
    - Draft performance review summaries from multi-source feedback and KPIs/KRAs.
    - Recommend promotions, band changes, and retention actions based on signals from HR, Finance, and operational modules.
    - Continuously monitor policy adherence and raise flags/compliance tasks when patterns deviate.

This vision acts as the **north star** for implementation of the HR module, ensuring that every enhancement moves SARAISE closer to an AI-orchestrated, best-in-class HCM platform.

---

## World-Class Features

### 1. Employee Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Employee Master Data**:
```python
employee_fields = {
    "personal": {
        "employee_id": "Auto-generated unique ID",
        "first_name": "Legal first name",
        "middle_name": "Middle name/initial",
        "last_name": "Legal last name",
        "preferred_name": "Name used in workplace",
        "date_of_birth": "DOB for age calculations",
        "gender": "Gender identity (customizable)",
        "marital_status": "Single, Married, etc.",
        "nationality": "Primary nationality",
        "national_id": "SSN, Aadhaar, etc.",
        "passport_number": "For international assignments"
    },
    "contact": {
        "personal_email": "Personal contact",
        "work_email": "Company email",
        "mobile_phone": "Primary contact",
        "home_phone": "Secondary contact",
        "current_address": "Full address details",
        "permanent_address": "Home address",
        "emergency_contacts": "Multiple emergency contacts"
    },
    "employment": {
        "hire_date": "Original hire date",
        "start_date": "Current position start",
        "employment_type": "Full-time, Part-time, Contract",
        "job_title": "Current position title",
        "department_id": "Department assignment",
        "manager_id": "Direct manager",
        "work_location": "Office/remote location",
        "employment_status": "Active, On Leave, Terminated",
        "probation_end_date": "End of probation period",
        "confirmation_date": "Permanent status date"
    },
    "compensation": {
        "salary": "Base salary",
        "currency": "Salary currency",
        "pay_frequency": "Monthly, Bi-weekly, etc.",
        "pay_grade": "Compensation grade",
        "salary_history": "Historical compensation"
    },
    "organization": {
        "cost_center": "For accounting",
        "employee_type": "Exempt, Non-exempt",
        "worker_category": "Full-time, Contractor, Intern",
        "union_membership": "Union affiliation if any"
    }
}
```

**Employee Self-Service Portal**:
- Update personal information
- View payslips and tax documents
- Request time off
- Submit expense claims
- Access company policies
- Update benefits enrollment
- View organizational chart
- Download employment verification

**Organizational Hierarchy**:
```
CEO
├── CFO
│   ├── Controller
│   │   ├── Accountant 1
│   │   └── Accountant 2
│   └── Treasury Manager
├── CTO
│   ├── VP Engineering
│   │   ├── Engineering Manager
│   │   │   ├── Senior Developer
│   │   │   └── Developer
│   │   └── QA Manager
│   └── VP Product
└── COO
    ├── Operations Manager
    └── Facilities Manager
```

**Position Management**:
- Position definitions
- Job descriptions
- Position hierarchy
- Headcount planning
- Vacant positions tracking
- Position budgets

### 2. Recruitment & Onboarding
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Applicant Tracking System (ATS)**:
```python
recruitment_workflow = {
    "job_requisition": {
        "fields": ["title", "department", "hiring_manager", "positions", "budget"],
        "approval_workflow": "Manager → HR → Finance → CEO",
        "requisition_types": ["New Position", "Replacement", "Backfill"]
    },
    "job_posting": {
        "channels": ["Company Website", "LinkedIn", "Indeed", "Glassdoor", "Naukri"],
        "job_boards_integration": "API integration with major job boards",
        "social_sharing": "One-click sharing to social media",
        "career_page": "Branded career site"
    },
    "candidate_pipeline": {
        "stages": [
            "Applied",
            "Screening",
            "Phone Interview",
            "Technical Assessment",
            "Onsite Interview",
            "Offer",
            "Hired",
            "Rejected"
        ],
        "stage_actions": "Auto-email, schedule interview, send assessment"
    }
}
```

**AI Resume Screening**:
```python
ai_screening = {
    "resume_parsing": {
        "extract": ["skills", "experience", "education", "certifications"],
        "format_support": [".pdf", ".doc", ".docx", ".txt"],
        "accuracy": ">95% extraction accuracy"
    },
    "candidate_matching": {
        "skills_match": "Compare candidate skills vs. job requirements",
        "experience_match": "Years of experience matching",
        "education_match": "Degree and institution matching",
        "cultural_fit": "Analyze communication style, values",
        "score": "0-100 match score with explanations"
    },
    "bias_reduction": {
        "blind_screening": "Hide name, gender, age initially",
        "diverse_shortlists": "Ensure diverse candidate pools",
        "standardized_scoring": "Consistent evaluation criteria"
    }
}
```

**Interview Management**:
- Interview scheduling (calendar integration)
- Interview kits (questions, scorecards)
- Interviewer assignment
- Interview feedback collection
- Scorecard aggregation
- Candidate comparison

**Onboarding Automation**:
```python
onboarding_checklist = {
    "pre_boarding": [
        "Send offer letter (DocuSign)",
        "Background check initiation",
        "I-9/work authorization verification",
        "New hire paperwork (W-4, state tax, direct deposit)",
        "Benefits enrollment package",
        "Welcome email with first day info"
    ],
    "first_day": [
        "Create employee record",
        "Generate employee ID badge",
        "Provision IT equipment (laptop, phone)",
        "Create email account and system access",
        "Assign desk/workspace",
        "Company orientation",
        "Meet the team"
    ],
    "first_week": [
        "Department orientation",
        "System training (HRIS, email, tools)",
        "Assign mentor/buddy",
        "Review job responsibilities",
        "Set 30-60-90 day goals",
        "Schedule regular check-ins"
    ],
    "first_30_days": [
        "Product/service training",
        "Compliance training (security, harassment, etc.)",
        "Benefits enrollment deadline",
        "30-day check-in with manager",
        "30-day check-in with HR"
    ],
    "first_90_days": [
        "Skills assessment",
        "Performance review (probation)",
        "Confirmation decision",
        "Offboarding from onboarding program"
    ]
}
```

### 3. Time & Attendance Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Time Tracking**:
```python
time_tracking_features = {
    "clock_in_out": {
        "methods": ["Web portal", "Mobile app", "Biometric", "RFID card"],
        "geofencing": "Location-based clock in/out",
        "photo_capture": "Selfie on clock in (optional)",
        "offline_mode": "Clock in offline, sync later"
    },
    "timesheet": {
        "entry_types": ["Daily", "Weekly", "Project-based"],
        "fields": ["Date", "Hours", "Project", "Task", "Notes"],
        "approval_workflow": "Employee → Manager → HR",
        "bulk_approval": "Approve multiple timesheets at once"
    },
    "work_schedules": {
        "shift_types": ["Fixed", "Rotating", "Flexible", "Split"],
        "shift_planning": "Automatic shift scheduling",
        "shift_swapping": "Employee-initiated swaps (approval required)",
        "overtime_rules": ">40 hrs/week = 1.5x, >60 hrs = 2x"
    },
    "attendance_policies": {
        "core_hours": "Required hours: 10 AM - 4 PM",
        "flexible_hours": "Flex time around core hours",
        "grace_period": "15-minute grace for late arrival",
        "half_day": "<4 hours = half day",
        "absent": "No show without leave = absent"
    }
}
```

**Leave Management**:
```python
leave_types = {
    "paid_time_off": {
        "annual_leave": {
            "accrual": "1.67 days per month (20 days/year)",
            "carryover": "Max 5 days to next year",
            "encashment": "Encash unused days on exit"
        },
        "sick_leave": {
            "accrual": "1 day per month (12 days/year)",
            "medical_certificate": "Required for >2 consecutive days",
            "carryover": "No carryover, resets yearly"
        },
        "casual_leave": {
            "allocation": "10 days per year",
            "notice_period": "No advance notice required",
            "usage": "Personal matters, emergencies"
        },
        "public_holidays": {
            "national_holidays": "Auto-populated by country",
            "regional_holidays": "By state/province",
            "floating_holidays": "2 days, employee choice"
        }
    },
    "special_leave": {
        "maternity_leave": "12-26 weeks (country-specific)",
        "paternity_leave": "2-4 weeks",
        "parental_leave": "Additional weeks for adoption",
        "bereavement_leave": "3-5 days for immediate family",
        "jury_duty": "Paid leave for jury service",
        "military_leave": "As per legal requirements",
        "sabbatical": "Extended leave after X years"
    },
    "unpaid_leave": {
        "leave_without_pay": "Manager approval required",
        "max_duration": "Up to 30 days per year",
        "impact": "Affects salary, benefits, accruals"
    }
}
```

**Leave Request Workflow**:
1. Employee submits leave request
2. System checks leave balance
3. Manager receives notification
4. Manager approves/rejects (with comments)
5. HR notified of approval
6. Leave applied to calendar
7. Team notified of absence
8. Leave balance updated

### 4. Payroll Management
**Status**: Must-Have | **Competitive Parity**: Advanced

**Payroll Processing**:
```python
payroll_components = {
    "earnings": {
        "basic_salary": "Base salary (monthly/annual)",
        "house_rent_allowance": "HRA (tax-exempt portion)",
        "conveyance_allowance": "Transport allowance",
        "medical_allowance": "Medical reimbursement",
        "special_allowance": "Balancing component",
        "performance_bonus": "Annual/quarterly bonus",
        "overtime_pay": "Hours × rate × multiplier",
        "shift_allowance": "Night shift differential",
        "on_call_allowance": "On-call duty pay",
        "commission": "Sales commission"
    },
    "deductions": {
        "income_tax": "TDS/federal tax withholding",
        "social_security": "FICA, EPF, CPF (country-specific)",
        "health_insurance": "Employee premium contribution",
        "retirement_contribution": "401k, pension (employee share)",
        "garnishments": "Court-ordered deductions",
        "loan_repayment": "Company loan EMI",
        "advance_recovery": "Salary advance recovery",
        "unpaid_leave": "Pro-rated salary deduction"
    },
    "employer_contributions": {
        "employer_social_security": "Company's social security share",
        "employer_retirement": "Company's retirement contribution",
        "workers_compensation": "Workers' comp insurance",
        "unemployment_insurance": "Unemployment tax",
        "health_insurance_employer": "Company's health insurance share"
    }
}
```

**Payroll Cycle**:
```python
payroll_workflow = {
    "inputs": [
        "Attendance data (days worked)",
        "Timesheet data (hours, overtime)",
        "Leave data (paid/unpaid days)",
        "New hires (pro-rated salary)",
        "Terminations (final settlement)",
        "Salary revisions",
        "One-time bonuses",
        "Loans and advances",
        "Reimbursements"
    ],
    "processing": [
        "Calculate gross salary",
        "Apply tax calculations",
        "Calculate deductions",
        "Calculate net salary",
        "Generate payslips",
        "Bank transfer file (NACHA, SEPA)",
        "Update general ledger",
        "Generate reports"
    ],
    "outputs": [
        "Payslips (PDF, email)",
        "Bank transfer file",
        "Payroll register",
        "Tax reports (Form 16, W-2)",
        "Social security reports",
        "GL posting entries",
        "Payroll summary dashboard"
    ],
    "schedule": {
        "monthly": "Last working day of month",
        "cutoff_date": "25th of the month",
        "approval_deadline": "28th of the month",
        "payment_date": "Last day of month"
    }
}
```

**Tax Management**:
```python
tax_features = {
    "tax_calculation": {
        "progressive_tax": "Tax slabs based on annual income",
        "tax_deductions": "Standard deduction, exemptions",
        "tax_credits": "Child tax credit, education credits",
        "year_end_projection": "Annual tax projection in real-time"
    },
    "tax_filing": {
        "form_generation": "W-2, 1099, Form 16, IT return forms",
        "e_filing": "Direct e-filing integration",
        "quarterly_filings": "941, state quarterly returns",
        "annual_filings": "Year-end tax forms"
    },
    "multi_country": {
        "usa": "Federal + state + local taxes",
        "india": "TDS, EPF, ESI",
        "uk": "PAYE, NI contributions",
        "singapore": "CPF contributions",
        "australia": "PAYG withholding, superannuation"
    }
}
```

**Payroll Compliance**:
- Minimum wage compliance
- Overtime regulations (FLSA)
- Equal pay monitoring
- Garnishment processing
- Child support deductions
- Audit trail for all changes
- Payroll tax deposits

### 5. Performance Management
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Performance Review Cycles**:
```python
review_types = {
    "annual_review": {
        "frequency": "Yearly",
        "components": ["Goals achievement", "Competencies", "360 feedback"],
        "outcome": "Rating, salary increase, promotion"
    },
    "mid_year_review": {
        "frequency": "6 months",
        "components": ["Goal progress", "Development needs"],
        "outcome": "Course correction, support needed"
    },
    "quarterly_check_in": {
        "frequency": "Quarterly",
        "components": ["Goal status", "Feedback"],
        "outcome": "Real-time adjustments"
    },
    "probation_review": {
        "frequency": "After probation period (3-6 months)",
        "components": ["Job performance", "Cultural fit", "Skills"],
        "outcome": "Confirmation or termination"
    },
    "project_review": {
        "frequency": "End of project",
        "components": ["Project delivery", "Team collaboration"],
        "outcome": "Project-specific feedback"
    }
}
```

**Goal Management (OKRs/KPIs)**:
```python
goal_framework = {
    "okr": {
        "objective": "Qualitative goal (e.g., Improve customer satisfaction)",
        "key_results": [
            "Increase NPS from 45 to 60",
            "Reduce ticket resolution time by 30%",
            "Achieve 95% CSAT score"
        ],
        "alignment": "Individual → Team → Department → Company",
        "check_ins": "Weekly progress updates"
    },
    "smart_goals": {
        "specific": "Clearly defined goal",
        "measurable": "Quantifiable metrics",
        "achievable": "Realistic given resources",
        "relevant": "Aligned with business objectives",
        "time_bound": "Specific deadline"
    },
    "goal_types": {
        "performance_goals": "Job-specific deliverables",
        "development_goals": "Skill building, learning",
        "behavioral_goals": "Leadership, collaboration"
    }
}
```

**360-Degree Feedback**:
```python
feedback_sources = {
    "self_assessment": "Employee self-rates performance",
    "manager_review": "Direct manager evaluation",
    "peer_review": "Colleagues feedback (3-5 peers)",
    "direct_reports": "Subordinates feedback (for managers)",
    "customer_feedback": "Client/stakeholder input",
    "aggregation": "Weighted average with anonymized peer/subordinate feedback"
}
```

**Performance Rating Scale**:
```python
rating_scale = {
    "5_exceeds_expectations": {
        "rating": 5,
        "label": "Exceptional",
        "description": "Consistently exceeds all expectations",
        "percentage": "Top 5% of employees",
        "salary_increase": "15-20%",
        "bonus": "200% of target"
    },
    "4_exceeds_most": {
        "rating": 4,
        "label": "Exceeds Expectations",
        "description": "Frequently exceeds expectations",
        "percentage": "15-20% of employees",
        "salary_increase": "10-15%",
        "bonus": "150% of target"
    },
    "3_meets": {
        "rating": 3,
        "label": "Meets Expectations",
        "description": "Consistently meets all expectations",
        "percentage": "60-70% of employees",
        "salary_increase": "5-10%",
        "bonus": "100% of target"
    },
    "2_needs_improvement": {
        "rating": 2,
        "label": "Needs Improvement",
        "description": "Does not consistently meet expectations",
        "percentage": "10% of employees",
        "salary_increase": "0-3%",
        "bonus": "0-50% of target",
        "pip": "Performance Improvement Plan required"
    },
    "1_unsatisfactory": {
        "rating": 1,
        "label": "Unsatisfactory",
        "description": "Fails to meet basic expectations",
        "percentage": "<5% of employees",
        "salary_increase": "0%",
        "bonus": "0%",
        "action": "Termination or mandatory PIP"
    }
}
```

**Performance Improvement Plan (PIP)**:
- Clear performance gaps identified
- Specific improvement objectives
- Timeline (typically 30-90 days)
- Regular check-ins (weekly/bi-weekly)
- Support provided (training, mentoring)
- Success criteria defined
- Outcomes: Improvement, extension, or termination

**Continuous Feedback**:
- Real-time praise and recognition
- Constructive feedback anytime
- Peer-to-peer recognition
- Manager check-ins
- Feedback analytics

### 6. Compensation & Benefits Management
**Status**: Must-Have | **Competitive Parity**: Advanced

**Compensation Management**:
```python
compensation_features = {
    "salary_structure": {
        "pay_grades": "Grade 1-15 with salary bands",
        "salary_bands": {
            "minimum": "Entry level for grade",
            "midpoint": "Market competitive rate",
            "maximum": "Top of grade ceiling"
        },
        "compa_ratio": "Employee salary / midpoint (target: 0.9-1.1)",
        "range_penetration": "Position within salary band"
    },
    "salary_reviews": {
        "annual_increment": "Merit-based increases",
        "promotion_increases": "10-15% on promotion",
        "market_adjustments": "Alignment with market data",
        "cost_of_living": "COLA adjustments",
        "equity_adjustments": "Close pay gaps"
    },
    "variable_pay": {
        "annual_bonus": "Performance-based (0-20% of base)",
        "sales_commission": "% of sales (for sales roles)",
        "profit_sharing": "Company profit distribution",
        "spot_awards": "One-time recognition awards ($500-$5000)",
        "referral_bonus": "$1000-$5000 for successful hires"
    },
    "equity_compensation": {
        "stock_options": "Options with vesting schedule",
        "rsus": "Restricted stock units",
        "espp": "Employee stock purchase plan",
        "vesting_schedule": "4-year vest with 1-year cliff"
    }
}
```

**Benefits Administration**:
```python
benefits_catalog = {
    "health_insurance": {
        "medical": "Health insurance plans (multiple tiers)",
        "dental": "Dental coverage",
        "vision": "Vision/eye care",
        "plans": ["HMO", "PPO", "HDHP with HSA"],
        "coverage": ["Employee only", "Employee + Spouse", "Family"],
        "employer_contribution": "70-80% of premium"
    },
    "retirement": {
        "401k": "Retirement savings plan (US)",
        "employer_match": "50% match up to 6% of salary",
        "pension": "Defined benefit plan (legacy)",
        "roth_401k": "Post-tax retirement savings"
    },
    "insurance": {
        "life_insurance": "1-2x annual salary (employer-paid)",
        "disability_insurance": "Short-term (60% salary) and long-term (60% salary)",
        "accident_insurance": "Voluntary supplemental coverage",
        "critical_illness": "Lump sum for major illnesses"
    },
    "wellness": {
        "gym_membership": "$50/month reimbursement",
        "wellness_program": "Health challenges, incentives",
        "eap": "Employee Assistance Program (counseling)",
        "mental_health": "Therapy sessions covered"
    },
    "time_off": {
        "pto": "Paid time off (see Leave Management)",
        "parental_leave": "Maternity, paternity leave",
        "sabbatical": "Extended leave after 5-7 years",
        "volunteer_time": "2 days/year for volunteering"
    },
    "perks": {
        "remote_work": "Work from home options",
        "flexible_hours": "Flextime around core hours",
        "professional_development": "$2000/year learning budget",
        "tuition_reimbursement": "Up to $5000/year for degrees",
        "commuter_benefits": "Transit/parking pre-tax",
        "meal_allowance": "Free lunch or meal stipend",
        "mobile_reimbursement": "$50/month phone stipend",
        "home_office_setup": "$1000 one-time for remote setup"
    }
}
```

**Benefits Enrollment**:
- Annual open enrollment (30-day window)
- New hire enrollment (30 days from hire)
- Qualifying life events (marriage, birth, etc.)
- Plan comparison tools
- Cost calculators
- Dependent verification
- Beneficiary designation

### 7. Learning & Development
**Status**: Should-Have | **Competitive Advantage**: AI-Powered

**Training Management**:
```python
training_features = {
    "course_catalog": {
        "types": ["Compliance", "Technical", "Soft skills", "Leadership"],
        "formats": ["Instructor-led", "E-learning", "Video", "Workshop", "Conference"],
        "providers": ["Internal", "External", "Online platforms (LinkedIn Learning, Udemy)"]
    },
    "learning_paths": {
        "onboarding_path": "New hire training sequence",
        "role_based_paths": "Engineer, Manager, Sales tracks",
        "certification_paths": "Professional certifications (PMP, AWS, etc.)",
        "leadership_development": "Management training program"
    },
    "training_administration": {
        "course_scheduling": "Calendar integration, waitlists",
        "enrollment": "Self-enroll or manager-assigned",
        "attendance_tracking": "Mark attendance, completion",
        "assessments": "Quizzes, tests, certifications",
        "feedback": "Course evaluation surveys",
        "certificates": "Auto-generated completion certificates"
    },
    "compliance_training": {
        "mandatory_courses": [
            "Information Security (annual)",
            "Anti-Harassment (annual)",
            "Code of Conduct (annual)",
            "Data Privacy / GDPR (annual)",
            "Safety Training (for specific roles)"
        ],
        "auto_assignment": "Assign based on role, location, department",
        "deadline_tracking": "Reminders, escalations for overdue",
        "compliance_reports": "Completion rates, overdue employees"
    }
}
```

**Skills Management**:
```python
skills_framework = {
    "skills_inventory": {
        "technical_skills": "Programming languages, tools, technologies",
        "soft_skills": "Communication, leadership, problem-solving",
        "certifications": "Professional certifications",
        "proficiency_levels": "Beginner, Intermediate, Advanced, Expert"
    },
    "skills_assessment": {
        "self_assessment": "Employee rates own skills",
        "manager_assessment": "Manager validates skills",
        "skills_tests": "Online assessments, coding challenges",
        "project_evidence": "Skills demonstrated in work"
    },
    "skills_gap_analysis": {
        "current_skills": "Employee's current skill set",
        "required_skills": "Skills needed for role/promotion",
        "gap": "Skills to develop",
        "development_plan": "Training recommendations"
    },
    "career_development": {
        "career_paths": "Visualize career progression options",
        "next_role_skills": "Skills needed for promotion",
        "mentorship": "Connect with mentors in target roles",
        "stretch_assignments": "Projects to build skills"
    }
}
```

**Succession Planning**:
- Identify critical positions
- Assess readiness of successors
- Create development plans
- Track high-potential employees
- Succession pipeline reports

### 8. Employee Relations & Compliance
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Employee Lifecycle Events**:
```python
lifecycle_events = {
    "hire": "Onboarding, system provisioning",
    "promotion": "Title change, salary increase, announcement",
    "transfer": "Department/location change, manager reassignment",
    "leave_of_absence": "Extended leave (medical, personal)",
    "return_from_leave": "Reactivate benefits, back to active status",
    "resignation": "Exit interview, offboarding checklist",
    "retirement": "Final settlement, retirement benefits",
    "termination": "Exit process, access revocation, final pay"
}
```

**Offboarding Process**:
```python
offboarding_checklist = {
    "notice_period": [
        "Receive resignation letter",
        "Determine last working day",
        "Manager acceptance",
        "Create exit checklist"
    ],
    "knowledge_transfer": [
        "Document ongoing work",
        "Train replacement or team",
        "Handover responsibilities",
        "Share passwords, access details"
    ],
    "exit_interview": [
        "Schedule exit interview",
        "Feedback on role, manager, company",
        "Reasons for leaving",
        "Improvement suggestions"
    ],
    "clearance": [
        "Return company property (laptop, phone, badge)",
        "Clear outstanding expenses",
        "Clear outstanding dues/advances",
        "IT access revocation",
        "Building access deactivation"
    ],
    "final_settlement": [
        "Calculate final salary (pro-rated)",
        "Unused leave encashment",
        "Bonus payout (if applicable)",
        "Deduct notice period shortfall (if applicable)",
        "Tax documentation",
        "Relieving letter",
        "Experience certificate",
        "Final payslip"
    ],
    "post_exit": [
        "Alumni network invitation",
        "Exit survey",
        "Update organizational chart",
        "Close employee record"
    ]
}
```

**Compliance Management**:
```python
compliance_areas = {
    "labor_laws": {
        "usa": ["FLSA", "FMLA", "ADA", "Title VII", "COBRA", "HIPAA"],
        "india": ["Shops and Establishments Act", "EPF Act", "ESI Act", "Gratuity Act"],
        "uk": ["Employment Rights Act", "Equality Act", "Working Time Regulations"],
        "eu": ["GDPR", "Working Time Directive", "Employment Equality Directive"]
    },
    "workplace_safety": {
        "osha": "Occupational Safety and Health Administration (US)",
        "incident_reporting": "Workplace accidents, injuries",
        "safety_training": "Mandatory safety protocols",
        "ergonomics": "Workstation assessments"
    },
    "equal_opportunity": {
        "eeo_reporting": "EEO-1 report (US)",
        "diversity_metrics": "Track workforce diversity",
        "pay_equity": "Identify and close pay gaps",
        "anti_discrimination": "Policies and training"
    },
    "data_privacy": {
        "gdpr": "Employee data protection (EU)",
        "ccpa": "California Consumer Privacy Act",
        "data_retention": "Retention policies for employee records",
        "consent_management": "Employee data consent tracking"
    }
}
```

**Case Management**:
- Employee grievances
- Disciplinary actions
- Investigation tracking
- Resolution documentation
- Appeal process
- Compliance audit trail

### 9. Workforce Analytics & Reporting
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**HR Dashboards**:
```python
dashboard_metrics = {
    "headcount": {
        "total_employees": "Current employee count",
        "by_department": "Breakdown by department",
        "by_location": "Breakdown by office/region",
        "by_type": "Full-time, part-time, contractor",
        "trend": "Headcount growth over time"
    },
    "turnover": {
        "attrition_rate": "% employees leaving per year",
        "voluntary_turnover": "Resignations",
        "involuntary_turnover": "Terminations",
        "retention_rate": "% employees staying",
        "tenure_analysis": "Avg. employee tenure"
    },
    "recruitment": {
        "time_to_hire": "Days from req to offer acceptance",
        "time_to_fill": "Days from req to start date",
        "cost_per_hire": "Total recruitment cost / hires",
        "offer_acceptance_rate": "% offers accepted",
        "source_effectiveness": "Best recruitment channels"
    },
    "diversity": {
        "gender_ratio": "M/F/Other breakdown",
        "age_distribution": "Age group analysis",
        "ethnicity": "Ethnic diversity (where legal)",
        "leadership_diversity": "Diversity in management"
    },
    "compensation": {
        "average_salary": "Mean and median salary",
        "salary_by_department": "Compensation comparison",
        "compa_ratio": "Salary vs. market rate",
        "pay_equity": "Gender/ethnicity pay gaps"
    },
    "performance": {
        "rating_distribution": "% employees per rating",
        "goal_completion": "% goals achieved on time",
        "promotion_rate": "% employees promoted",
        "pip_success_rate": "% employees improving after PIP"
    },
    "training": {
        "training_hours": "Avg. training hours per employee",
        "compliance_completion": "% mandatory training complete",
        "training_roi": "Impact of training on performance"
    },
    "engagement": {
        "employee_satisfaction": "Survey scores",
        "eNPS": "Employee Net Promoter Score",
        "engagement_score": "Overall engagement metric"
    }
}
```

**Predictive Analytics**:
```python
ai_predictions = {
    "attrition_risk": {
        "model": "Predict employees likely to leave",
        "factors": ["Tenure", "salary", "performance", "promotion history", "engagement"],
        "output": "Risk score (0-100) per employee",
        "action": "Retention interventions for high-risk employees"
    },
    "performance_prediction": {
        "model": "Predict future performance ratings",
        "factors": ["Past performance", "goals", "training", "peer feedback"],
        "output": "Predicted rating for next cycle",
        "action": "Proactive performance support"
    },
    "promotion_readiness": {
        "model": "Identify promotion candidates",
        "factors": ["Performance", "tenure", "skills", "potential"],
        "output": "Readiness score and timeline",
        "action": "Development plans for high-potential employees"
    },
    "hiring_forecasting": {
        "model": "Predict future hiring needs",
        "factors": ["Attrition trends", "business growth", "project pipeline"],
        "output": "Headcount forecast by quarter",
        "action": "Proactive recruitment planning"
    }
}
```

**Statutory Reports**:
- EEO-1 Report (US)
- Form 5500 (Retirement plans)
- ACA 1095 forms (Health insurance)
- State unemployment reports
- Workers' compensation reports
- Wage and hour compliance

### 10. Mobile HR App
**Status**: Should-Have | **Competitive Parity**: Industry Standard

**Mobile App Features**:
```python
mobile_capabilities = {
    "employee_features": [
        "View payslips and tax documents",
        "Request time off",
        "View time off balance",
        "Clock in/out with geofencing",
        "Submit expense reports",
        "View company directory",
        "Update personal info",
        "Access training modules",
        "View performance goals",
        "Receive push notifications"
    ],
    "manager_features": [
        "Approve time off requests",
        "Approve timesheets",
        "Approve expenses",
        "View team dashboard",
        "Access team directory",
        "Submit performance reviews",
        "View requisitions"
    ],
    "hr_features": [
        "Dashboard metrics",
        "Approve workflows",
        "View employee records",
        "Access reports"
    ]
}
```

---

## AI Agent Integration

### HR AI Agents

**1. Recruitment Assistant Agent**
```python
agent_capabilities = {
    "resume_screening": "Parse and score resumes automatically",
    "candidate_matching": "Match candidates to open positions",
    "interview_scheduling": "Find optimal interview slots",
    "candidate_communication": "Send automated updates, reminders",
    "offer_generation": "Create offer letters from templates",
    "onboarding_initiation": "Trigger onboarding workflows"
}
```

**2. Employee Engagement Agent**
```python
agent_capabilities = {
    "pulse_surveys": "Schedule and send engagement surveys",
    "sentiment_analysis": "Analyze feedback sentiment",
    "attrition_prediction": "Identify at-risk employees",
    "intervention_suggestions": "Recommend retention actions",
    "exit_interview_analysis": "Identify trends in exit reasons"
}
```

**3. Performance Coach Agent**
```python
agent_capabilities = {
    "goal_reminders": "Remind employees of goal deadlines",
    "feedback_prompts": "Suggest when to give/request feedback",
    "development_suggestions": "Recommend training based on gaps",
    "career_guidance": "Suggest career paths and development plans",
    "check_in_scheduling": "Prompt manager-employee check-ins"
}
```

**4. Payroll Assistant Agent**
```python
agent_capabilities = {
    "payroll_anomaly_detection": "Flag unusual payroll entries",
    "tax_compliance_check": "Ensure tax calculations are correct",
    "payroll_reconciliation": "Match payroll to bank transfers",
    "year_end_preparation": "Generate W-2s, tax forms",
    "payroll_query_response": "Answer employee payroll questions"
}
```

**5. Compliance Monitor Agent**
```python
agent_capabilities = {
    "training_compliance": "Track mandatory training completion",
    "certification_expiry": "Alert on expiring certifications",
    "labor_law_updates": "Monitor and alert on law changes",
    "audit_preparation": "Compile audit documentation",
    "policy_acknowledgment": "Track policy sign-offs"
}
```

---

## Database Schema

```sql
-- Employees
CREATE TABLE employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Employee Identification
    employee_id VARCHAR(50) UNIQUE NOT NULL,
    badge_number VARCHAR(50),

    -- Personal Info
    first_name VARCHAR(100) NOT NULL,
    middle_name VARCHAR(100),
    last_name VARCHAR(100) NOT NULL,
    preferred_name VARCHAR(100),
    date_of_birth DATE,
    gender VARCHAR(50),
    marital_status VARCHAR(50),
    nationality VARCHAR(100),
    national_id VARCHAR(100),  -- SSN, Aadhaar, etc.
    passport_number VARCHAR(100),

    -- Contact Info
    personal_email VARCHAR(255),
    work_email VARCHAR(255) UNIQUE NOT NULL,
    mobile_phone VARCHAR(50),
    home_phone VARCHAR(50),

    -- Address
    current_address_line1 TEXT,
    current_address_line2 TEXT,
    current_city VARCHAR(100),
    current_state VARCHAR(100),
    current_postal_code VARCHAR(20),
    current_country VARCHAR(100),

    permanent_address_line1 TEXT,
    permanent_address_line2 TEXT,
    permanent_city VARCHAR(100),
    permanent_state VARCHAR(100),
    permanent_postal_code VARCHAR(20),
    permanent_country VARCHAR(100),

    -- Employment
    hire_date DATE NOT NULL,
    start_date DATE NOT NULL,
    employment_type VARCHAR(50) NOT NULL,  -- Full-time, Part-time, Contract
    job_title VARCHAR(255) NOT NULL,
    department_id UUID REFERENCES departments(id),
    manager_id UUID REFERENCES employees(id),
    work_location VARCHAR(255),
    employment_status VARCHAR(50) DEFAULT 'active',  -- active, on_leave, terminated
    probation_end_date DATE,
    confirmation_date DATE,
    termination_date DATE,
    termination_reason TEXT,

    -- Compensation
    salary DECIMAL(15, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    pay_frequency VARCHAR(50),  -- monthly, bi-weekly, weekly
    pay_grade VARCHAR(50),

    -- Organization
    cost_center VARCHAR(50),
    employee_type VARCHAR(50),  -- Exempt, Non-exempt
    worker_category VARCHAR(50),  -- Full-time, Contractor, Intern

    -- System
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),

    INDEX idx_tenant_status (tenant_id, employment_status),
    INDEX idx_employee_id (employee_id),
    INDEX idx_manager (manager_id),
    INDEX idx_department (department_id),
    INDEX idx_work_email (work_email)
);

-- Departments
CREATE TABLE departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    department_code VARCHAR(50) UNIQUE NOT NULL,
    department_name VARCHAR(255) NOT NULL,
    parent_department_id UUID REFERENCES departments(id),
    head_of_department_id UUID REFERENCES employees(id),
    cost_center VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant (tenant_id)
);

-- Emergency Contacts
CREATE TABLE emergency_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES employees(id),

    name VARCHAR(255) NOT NULL,
    relationship VARCHAR(100),
    phone VARCHAR(50) NOT NULL,
    alternate_phone VARCHAR(50),
    email VARCHAR(255),
    address TEXT,
    is_primary BOOLEAN DEFAULT false,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_employee (employee_id)
);

-- Job Requisitions
CREATE TABLE job_requisitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    requisition_number VARCHAR(50) UNIQUE NOT NULL,
    job_title VARCHAR(255) NOT NULL,
    department_id UUID REFERENCES departments(id),
    hiring_manager_id UUID REFERENCES employees(id),

    requisition_type VARCHAR(50),  -- New Position, Replacement, Backfill
    positions_requested INTEGER DEFAULT 1,
    employment_type VARCHAR(50),
    work_location VARCHAR(255),

    job_description TEXT,
    requirements TEXT,
    salary_range_min DECIMAL(15, 2),
    salary_range_max DECIMAL(15, 2),

    status VARCHAR(50) DEFAULT 'draft',  -- draft, pending_approval, approved, rejected, filled, cancelled
    approval_status VARCHAR(50),
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_tenant_status (tenant_id, status),
    INDEX idx_hiring_manager (hiring_manager_id)
);

-- Job Postings
CREATE TABLE job_postings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    requisition_id UUID REFERENCES job_requisitions(id),

    job_title VARCHAR(255) NOT NULL,
    job_description TEXT,
    requirements TEXT,

    posting_channels TEXT[],  -- ["Company Website", "LinkedIn", "Indeed"]
    external_job_ids JSONB,  -- {"linkedin": "12345", "indeed": "67890"}

    posted_date DATE,
    closing_date DATE,
    status VARCHAR(50) DEFAULT 'draft',  -- draft, active, paused, closed

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_status (tenant_id, status),
    INDEX idx_requisition (requisition_id)
);

-- Candidates
CREATE TABLE candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    requisition_id UUID REFERENCES job_requisitions(id),

    -- Personal Info
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),

    -- Application
    source VARCHAR(100),  -- Company Website, LinkedIn, Referral
    referrer_employee_id UUID REFERENCES employees(id),
    applied_date DATE DEFAULT CURRENT_DATE,

    -- Resume
    resume_url VARCHAR(500),
    resume_parsed_data JSONB,  -- Extracted skills, experience, education

    -- Screening
    match_score INTEGER,  -- 0-100 AI match score
    screening_status VARCHAR(50) DEFAULT 'new',

    -- Current Stage
    current_stage VARCHAR(100) DEFAULT 'applied',
    stage_history JSONB,

    -- Final Status
    status VARCHAR(50) DEFAULT 'active',  -- active, hired, rejected, withdrawn
    rejection_reason TEXT,
    hired_as_employee_id UUID REFERENCES employees(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_requisition (tenant_id, requisition_id),
    INDEX idx_email (email),
    INDEX idx_status (status)
);

-- Interviews
CREATE TABLE interviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    candidate_id UUID REFERENCES candidates(id),
    requisition_id UUID REFERENCES job_requisitions(id),

    interview_type VARCHAR(100),  -- Phone Screen, Technical, Behavioral, Onsite
    interview_date TIMESTAMPTZ,
    duration_minutes INTEGER,

    interviewer_ids UUID[],  -- Array of employee IDs
    location VARCHAR(255),  -- Office, Video Call, Phone
    meeting_link VARCHAR(500),

    status VARCHAR(50) DEFAULT 'scheduled',  -- scheduled, completed, cancelled, no_show

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_candidate (candidate_id),
    INDEX idx_interview_date (interview_date)
);

-- Interview Feedback
CREATE TABLE interview_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID REFERENCES interviews(id),
    interviewer_id UUID REFERENCES employees(id),

    overall_rating INTEGER,  -- 1-5
    technical_skills_rating INTEGER,
    communication_rating INTEGER,
    cultural_fit_rating INTEGER,

    strengths TEXT,
    weaknesses TEXT,
    comments TEXT,
    recommendation VARCHAR(50),  -- strong_yes, yes, maybe, no, strong_no

    submitted_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_interview (interview_id),
    INDEX idx_interviewer (interviewer_id)
);

-- Attendance
CREATE TABLE attendance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    employee_id UUID REFERENCES employees(id),

    attendance_date DATE NOT NULL,

    -- Clock In/Out
    clock_in_time TIMESTAMPTZ,
    clock_out_time TIMESTAMPTZ,

    -- Location (for geofencing)
    clock_in_location POINT,
    clock_out_location POINT,

    -- Calculated
    hours_worked DECIMAL(5, 2),
    overtime_hours DECIMAL(5, 2),

    -- Status
    status VARCHAR(50),  -- present, absent, half_day, on_leave, holiday

    -- Approval
    approved_by UUID REFERENCES employees(id),
    approved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, employee_id, attendance_date),
    INDEX idx_employee_date (employee_id, attendance_date DESC)
);

-- Timesheets
CREATE TABLE timesheets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    employee_id UUID REFERENCES employees(id),

    period_start_date DATE NOT NULL,
    period_end_date DATE NOT NULL,

    total_hours DECIMAL(6, 2),
    regular_hours DECIMAL(6, 2),
    overtime_hours DECIMAL(6, 2),

    status VARCHAR(50) DEFAULT 'draft',  -- draft, submitted, approved, rejected
    submitted_at TIMESTAMPTZ,
    approved_by UUID REFERENCES employees(id),
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_employee_period (employee_id, period_start_date),
    INDEX idx_status (status)
);

-- Timesheet Entries
CREATE TABLE timesheet_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timesheet_id UUID REFERENCES timesheets(id),

    entry_date DATE NOT NULL,
    hours DECIMAL(5, 2) NOT NULL,

    project_id UUID,  -- Optional project tracking
    task_description TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_timesheet (timesheet_id)
);

-- Leave Types
CREATE TABLE leave_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    leave_code VARCHAR(50) UNIQUE NOT NULL,
    leave_name VARCHAR(255) NOT NULL,
    leave_category VARCHAR(50),  -- paid, unpaid, special

    accrual_rate DECIMAL(5, 2),  -- Days per month
    max_balance DECIMAL(5, 2),
    max_carryover DECIMAL(5, 2),
    encashment_allowed BOOLEAN DEFAULT false,

    requires_approval BOOLEAN DEFAULT true,
    requires_medical_certificate BOOLEAN DEFAULT false,

    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant (tenant_id)
);

-- Leave Balances
CREATE TABLE leave_balances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    employee_id UUID REFERENCES employees(id),
    leave_type_id UUID REFERENCES leave_types(id),

    year INTEGER NOT NULL,
    opening_balance DECIMAL(5, 2) DEFAULT 0,
    accrued DECIMAL(5, 2) DEFAULT 0,
    taken DECIMAL(5, 2) DEFAULT 0,
    encashed DECIMAL(5, 2) DEFAULT 0,
    lapsed DECIMAL(5, 2) DEFAULT 0,
    closing_balance DECIMAL(5, 2) DEFAULT 0,

    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, employee_id, leave_type_id, year),
    INDEX idx_employee_year (employee_id, year)
);

-- Leave Requests
CREATE TABLE leave_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    employee_id UUID REFERENCES employees(id),
    leave_type_id UUID REFERENCES leave_types(id),

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    number_of_days DECIMAL(4, 1) NOT NULL,

    reason TEXT,
    attachment_url VARCHAR(500),  -- For medical certificates

    status VARCHAR(50) DEFAULT 'pending',  -- pending, approved, rejected, cancelled
    approved_by UUID REFERENCES employees(id),
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_employee_status (employee_id, status),
    INDEX idx_date_range (start_date, end_date)
);

-- Payroll Cycles
CREATE TABLE payroll_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    cycle_name VARCHAR(100) NOT NULL,
    period_start_date DATE NOT NULL,
    period_end_date DATE NOT NULL,
    payment_date DATE NOT NULL,

    status VARCHAR(50) DEFAULT 'draft',  -- draft, processing, completed, paid

    total_gross DECIMAL(15, 2),
    total_deductions DECIMAL(15, 2),
    total_net DECIMAL(15, 2),

    processed_at TIMESTAMPTZ,
    processed_by UUID REFERENCES users(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_period (tenant_id, period_start_date)
);

-- Payroll Runs
CREATE TABLE payroll_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payroll_cycle_id UUID REFERENCES payroll_cycles(id),
    employee_id UUID REFERENCES employees(id),

    -- Attendance
    days_worked DECIMAL(5, 2),
    days_absent DECIMAL(5, 2),
    days_on_leave DECIMAL(5, 2),

    -- Earnings
    basic_salary DECIMAL(15, 2),
    hra DECIMAL(15, 2),
    conveyance DECIMAL(15, 2),
    medical_allowance DECIMAL(15, 2),
    special_allowance DECIMAL(15, 2),
    bonus DECIMAL(15, 2),
    overtime_pay DECIMAL(15, 2),
    other_earnings DECIMAL(15, 2),
    gross_salary DECIMAL(15, 2),

    -- Deductions
    income_tax DECIMAL(15, 2),
    social_security DECIMAL(15, 2),
    health_insurance DECIMAL(15, 2),
    retirement_contribution DECIMAL(15, 2),
    loan_repayment DECIMAL(15, 2),
    advance_recovery DECIMAL(15, 2),
    other_deductions DECIMAL(15, 2),
    total_deductions DECIMAL(15, 2),

    -- Net
    net_salary DECIMAL(15, 2),

    -- Payment
    payment_method VARCHAR(50),  -- bank_transfer, check, cash
    bank_account_number VARCHAR(100),
    payment_status VARCHAR(50) DEFAULT 'pending',  -- pending, paid, failed
    payment_date DATE,
    payment_reference VARCHAR(255),

    -- Payslip
    payslip_url VARCHAR(500),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_cycle_employee (payroll_cycle_id, employee_id)
);

-- Performance Review Cycles
CREATE TABLE performance_review_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    cycle_name VARCHAR(255) NOT NULL,
    review_type VARCHAR(50),  -- Annual, Mid-Year, Quarterly, Probation

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    review_period_start DATE,  -- Performance period being reviewed
    review_period_end DATE,

    status VARCHAR(50) DEFAULT 'draft',  -- draft, active, completed

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_dates (tenant_id, start_date, end_date)
);

-- Performance Reviews
CREATE TABLE performance_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    review_cycle_id UUID REFERENCES performance_review_cycles(id),
    employee_id UUID REFERENCES employees(id),
    reviewer_id UUID REFERENCES employees(id),

    review_type VARCHAR(50),  -- self, manager, peer, subordinate

    -- Ratings
    overall_rating DECIMAL(3, 2),  -- 1.00 to 5.00
    goals_rating DECIMAL(3, 2),
    competencies_rating DECIMAL(3, 2),
    values_rating DECIMAL(3, 2),

    -- Feedback
    strengths TEXT,
    areas_for_improvement TEXT,
    comments TEXT,

    -- Status
    status VARCHAR(50) DEFAULT 'draft',  -- draft, submitted, acknowledged
    submitted_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_cycle_employee (review_cycle_id, employee_id),
    INDEX idx_reviewer (reviewer_id)
);

-- Goals
CREATE TABLE goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    employee_id UUID REFERENCES employees(id),

    goal_title VARCHAR(500) NOT NULL,
    goal_description TEXT,

    goal_type VARCHAR(50),  -- performance, development, behavioral

    target_date DATE,
    status VARCHAR(50) DEFAULT 'active',  -- active, achieved, missed, cancelled
    progress_percentage INTEGER DEFAULT 0,  -- 0-100

    aligned_to_goal_id UUID REFERENCES goals(id),  -- For cascading OKRs

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_employee (employee_id),
    INDEX idx_status (status)
);

-- Training Courses
CREATE TABLE training_courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    course_code VARCHAR(50) UNIQUE NOT NULL,
    course_name VARCHAR(255) NOT NULL,
    course_description TEXT,

    course_type VARCHAR(50),  -- Compliance, Technical, Soft Skills, Leadership
    course_format VARCHAR(50),  -- Instructor-led, E-learning, Video, Workshop

    duration_hours DECIMAL(5, 2),
    provider VARCHAR(255),

    is_mandatory BOOLEAN DEFAULT false,
    validity_days INTEGER,  -- Recertification period

    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant (tenant_id)
);

-- Training Enrollments
CREATE TABLE training_enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    course_id UUID REFERENCES training_courses(id),
    employee_id UUID REFERENCES employees(id),

    enrolled_date DATE DEFAULT CURRENT_DATE,
    due_date DATE,
    completion_date DATE,

    status VARCHAR(50) DEFAULT 'enrolled',  -- enrolled, in_progress, completed, expired
    score DECIMAL(5, 2),  -- For assessments
    certificate_url VARCHAR(500),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_employee_course (employee_id, course_id),
    INDEX idx_status (status)
);

-- Employee Documents
CREATE TABLE employee_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    employee_id UUID REFERENCES employees(id),

    document_type VARCHAR(100),  -- Resume, Offer Letter, Contract, ID Proof, etc.
    document_name VARCHAR(255) NOT NULL,
    document_url VARCHAR(500) NOT NULL,
    file_size INTEGER,
    mime_type VARCHAR(100),

    uploaded_by UUID REFERENCES users(id),
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),

    expiry_date DATE,  -- For documents like passports, visas

    INDEX idx_employee (employee_id),
    INDEX idx_document_type (document_type)
);

-- Audit Trail for HR
CREATE TABLE hr_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    entity_type VARCHAR(100),  -- employee, payroll, leave, etc.
    entity_id UUID,
    action VARCHAR(50),  -- create, update, delete, approve, reject

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

### Employee Management

```
POST   /api/v1/hr/employees                    # Create employee
GET    /api/v1/hr/employees                    # List employees (with filters)
GET    /api/v1/hr/employees/{id}               # Get employee details
PUT    /api/v1/hr/employees/{id}               # Update employee
DELETE /api/v1/hr/employees/{id}               # Deactivate employee
GET    /api/v1/hr/employees/{id}/reporting-tree # Get org chart
POST   /api/v1/hr/employees/{id}/promote       # Promote employee
POST   /api/v1/hr/employees/{id}/transfer      # Transfer employee
```

### Recruitment

```
POST   /api/v1/hr/requisitions                 # Create job requisition
GET    /api/v1/hr/requisitions                 # List requisitions
GET    /api/v1/hr/requisitions/{id}            # Get requisition details
PUT    /api/v1/hr/requisitions/{id}            # Update requisition
POST   /api/v1/hr/requisitions/{id}/approve    # Approve requisition

POST   /api/v1/hr/candidates                   # Add candidate
GET    /api/v1/hr/candidates                   # List candidates
GET    /api/v1/hr/candidates/{id}              # Get candidate details
PUT    /api/v1/hr/candidates/{id}              # Update candidate
POST   /api/v1/hr/candidates/{id}/advance      # Move to next stage
POST   /api/v1/hr/candidates/{id}/reject       # Reject candidate
POST   /api/v1/hr/candidates/{id}/hire         # Convert to employee

POST   /api/v1/hr/interviews                   # Schedule interview
GET    /api/v1/hr/interviews                   # List interviews
POST   /api/v1/hr/interviews/{id}/feedback     # Submit interview feedback
```

### Attendance & Time Tracking

```
POST   /api/v1/hr/attendance/clock-in          # Clock in
POST   /api/v1/hr/attendance/clock-out         # Clock out
GET    /api/v1/hr/attendance                   # Get attendance records
PUT    /api/v1/hr/attendance/{id}              # Update attendance

POST   /api/v1/hr/timesheets                   # Create timesheet
GET    /api/v1/hr/timesheets                   # List timesheets
GET    /api/v1/hr/timesheets/{id}              # Get timesheet
POST   /api/v1/hr/timesheets/{id}/submit       # Submit for approval
POST   /api/v1/hr/timesheets/{id}/approve      # Approve timesheet
```

### Leave Management

```
GET    /api/v1/hr/leave-types                  # List leave types
POST   /api/v1/hr/leave-types                  # Create leave type

GET    /api/v1/hr/leave-balances               # Get employee leave balances
GET    /api/v1/hr/leave-balances/{employee_id} # Get specific employee balance

POST   /api/v1/hr/leave-requests               # Request leave
GET    /api/v1/hr/leave-requests               # List leave requests
GET    /api/v1/hr/leave-requests/{id}          # Get leave request
POST   /api/v1/hr/leave-requests/{id}/approve  # Approve leave
POST   /api/v1/hr/leave-requests/{id}/reject   # Reject leave
DELETE /api/v1/hr/leave-requests/{id}          # Cancel leave request
```

### Payroll

```
POST   /api/v1/hr/payroll/cycles               # Create payroll cycle
GET    /api/v1/hr/payroll/cycles               # List payroll cycles
POST   /api/v1/hr/payroll/cycles/{id}/process  # Process payroll
POST   /api/v1/hr/payroll/cycles/{id}/finalize # Finalize payroll

GET    /api/v1/hr/payroll/runs                 # List payroll runs
GET    /api/v1/hr/payroll/runs/{id}            # Get payroll details
GET    /api/v1/hr/payroll/runs/{id}/payslip    # Download payslip

GET    /api/v1/hr/payroll/reports/register     # Payroll register report
GET    /api/v1/hr/payroll/reports/tax-summary  # Tax summary report
```

### Performance Management

```
POST   /api/v1/hr/performance/cycles           # Create review cycle
GET    /api/v1/hr/performance/cycles           # List review cycles

POST   /api/v1/hr/performance/reviews          # Create review
GET    /api/v1/hr/performance/reviews          # List reviews
GET    /api/v1/hr/performance/reviews/{id}     # Get review
PUT    /api/v1/hr/performance/reviews/{id}     # Update review
POST   /api/v1/hr/performance/reviews/{id}/submit # Submit review

POST   /api/v1/hr/goals                        # Create goal
GET    /api/v1/hr/goals                        # List goals
PUT    /api/v1/hr/goals/{id}                   # Update goal
PUT    /api/v1/hr/goals/{id}/progress          # Update goal progress
```

### Learning & Development

```
POST   /api/v1/hr/training/courses             # Create course
GET    /api/v1/hr/training/courses             # List courses
GET    /api/v1/hr/training/courses/{id}        # Get course details

POST   /api/v1/hr/training/enrollments         # Enroll in course
GET    /api/v1/hr/training/enrollments         # List enrollments
PUT    /api/v1/hr/training/enrollments/{id}    # Update enrollment status
```

### Analytics & Reports

```
GET    /api/v1/hr/analytics/headcount          # Headcount metrics
GET    /api/v1/hr/analytics/turnover           # Turnover analysis
GET    /api/v1/hr/analytics/diversity          # Diversity metrics
GET    /api/v1/hr/analytics/compensation       # Compensation analysis
GET    /api/v1/hr/analytics/attrition-risk     # AI attrition predictions

GET    /api/v1/hr/reports/eeo1                 # EEO-1 report
GET    /api/v1/hr/reports/headcount            # Headcount report
GET    /api/v1/hr/reports/turnover             # Turnover report
```

---

## Security & Compliance

### Data Security
```python
security_measures = {
    "encryption": {
        "at_rest": "AES-256 encryption for PII data",
        "in_transit": "TLS 1.3 for all API communications",
        "database": "Column-level encryption for SSN, salary, bank details"
    },
    "access_control": {
        "rbac": "Role-based access control",
        "data_segregation": "Tenant-level data isolation",
        "field_level_security": "Restrict salary, SSN access to HR only",
        "audit_logging": "All data access logged"
    },
    "authentication": {
        "mfa": "Multi-factor authentication for HR admins",
        "sso": "SAML 2.0 / OIDC integration",
        "session_management": "30-minute idle timeout"
    }
}
```

### Compliance
```python
compliance_frameworks = {
    "data_privacy": {
        "gdpr": "Employee data protection (EU)",
        "ccpa": "Employee privacy rights (California)",
        "data_retention": "7 years for payroll, indefinite for employment records",
        "right_to_erasure": "Employee data deletion on request (post-retention)"
    },
    "labor_laws": {
        "usa": ["FLSA", "FMLA", "ADA", "Title VII", "COBRA", "ERISA"],
        "uk": ["Employment Rights Act", "Equality Act", "Pensions Act"],
        "india": ["Payment of Wages Act", "EPF Act", "ESI Act"]
    },
    "payroll_compliance": {
        "tax_withholding": "Accurate tax calculations per jurisdiction",
        "overtime_rules": "FLSA overtime compliance",
        "minimum_wage": "Federal and state minimum wage compliance",
        "recordkeeping": "3-7 years depending on regulation"
    },
    "equal_opportunity": {
        "eeo_reporting": "Annual EEO-1 filing (US)",
        "affirmative_action": "AAP reporting for federal contractors",
        "pay_equity": "Periodic pay equity audits"
    }
}
```

---

## Implementation Roadmap

### Phase 1: Core HR (Month 1-2)
- [ ] Employee master data management
- [ ] Department and organizational hierarchy
- [ ] Employee self-service portal
- [ ] Basic reporting (headcount, turnover)
- [ ] Document management

### Phase 2: Time & Leave (Month 3)
- [ ] Attendance tracking (clock in/out)
- [ ] Leave types configuration
- [ ] Leave request workflow
- [ ] Leave balance tracking
- [ ] Timesheet management

### Phase 3: Payroll (Month 4-5)
- [ ] Payroll components (earnings, deductions)
- [ ] Payroll processing engine
- [ ] Tax calculations
- [ ] Payslip generation
- [ ] Bank transfer file generation
- [ ] Statutory compliance (country-specific)

### Phase 4: Recruitment (Month 6)
- [ ] Job requisition workflow
- [ ] Applicant tracking system
- [ ] Resume parsing (AI)
- [ ] Interview scheduling
- [ ] Candidate pipeline management
- [ ] Offer letter generation

### Phase 5: Performance & Learning (Month 7-8)
- [ ] Performance review cycles
- [ ] Goal management (OKRs)
- [ ] 360-degree feedback
- [ ] Training course catalog
- [ ] Training enrollment and tracking
- [ ] Skills management

### Phase 6: Advanced Features (Month 9-10)
- [ ] AI agents (recruitment, engagement, payroll)
- [ ] Predictive analytics (attrition, performance)
- [ ] Succession planning
- [ ] Compensation planning
- [ ] Benefits administration
- [ ] Mobile app

---

## Competitive Analysis

| Feature | SARAISE | Workday | SAP SuccessFactors | Oracle HCM | ADP | BambooHR |
|---------|---------|---------|-------------------|------------|-----|----------|
| **Employee Management** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Attendance & Time** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Leave Management** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Payroll** | ✓ Multi-country | ✓ | ✓ | ✓ | ✓ Best-in-class | Limited |
| **Recruitment (ATS)** | ✓ AI-powered | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Performance Mgmt** | ✓ OKRs | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Learning & Development** | ✓ | ✓ | ✓ | ✓ | Limited | ✓ |
| **AI Agents** | ✓ 5+ types | ✓ Limited | ✓ Limited | ✓ Limited | ✗ | ✗ |
| **Predictive Analytics** | ✓ Attrition risk | ✓ | ✓ | ✓ | ✗ | ✗ |
| **Mobile App** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **ERP Integration** | ✓ Native | Via connector | ✓ Native | ✓ Native | Limited | Limited |
| **Multi-country Payroll** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| **Compliance** | ✓ Multi-region | ✓ | ✓ | ✓ | ✓ Excellent | Limited |
| **Pricing** | $$ | $$$$ | $$$$ | $$$$ | $$$ | $$ |

**Verdict**: Comparable to Workday/SAP SuccessFactors in features, superior ERP integration, significantly lower cost. Competitive with ADP for payroll, while offering broader HCM capabilities.

---

## Success Metrics

### Recruitment Efficiency
- **Time to Hire**: < 30 days from requisition to offer acceptance
- **Quality of Hire**: > 80% of new hires rated "Meets/Exceeds Expectations" in first year
- **Offer Acceptance Rate**: > 85%
- **Cost per Hire**: Reduce by 30% vs. external recruiters

### Operational Efficiency
- **Payroll Accuracy**: 99.9% error-free payroll runs
- **Time Savings**: 70% reduction in HR admin time
- **Employee Self-Service Adoption**: > 90% of employees using portal
- **Process Automation**: 80% of workflows automated

### Employee Experience
- **Employee Satisfaction**: > 4.0/5.0 in HR systems surveys
- **Time to Onboard**: Complete onboarding in < 2 weeks
- **Training Completion**: > 95% completion of mandatory training on time
- **Performance Review Completion**: 100% reviews completed on schedule

### Business Impact
- **Attrition Prediction Accuracy**: > 80% accuracy in identifying at-risk employees
- **Retention Improvement**: Reduce voluntary attrition by 20% year-over-year
- **Compliance**: Zero compliance violations or fines
- **ROI**: 4x return on investment in year 1

---

**Document Control**:
- **Author**: SARAISE Architecture Team
- **Last Updated**: 2025-11-10
- **Status**: Planning - Ready for Implementation
