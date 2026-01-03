# Accounting ERP - resource + Modular Monolith Architecture

> **Architecture**: resource-based framework with modular monolith design
>
> **Inspiration**: ERPNext/Frappe + Custom enhancements for enterprise accounting
>
> **Tech Stack**: Python/Django or TypeScript/NestJS (decision below)

---

## TABLE OF CONTENTS

1. [Technology Stack Decision](#1-technology-stack-decision)
2. [resource Framework Design](#2-resource-framework-design)
3. [Module Organization](#3-module-organization)
4. [Internal Event Architecture](#4-internal-event-architecture)
5. [API Layer Design](#5-api-layer-design)
6. [Frontend Architecture](#6-frontend-architecture)
7. [Deployment Architecture](#7-deployment-architecture)
8. [Complete resource Examples](#8-complete-resource-examples)

---

## 1. TECHNOLOGY STACK DECISION

### 1.1 BACKEND: Python Django (SARAISE Standard)

**DECISION MADE**: SARAISE uses **Django + Django REST Framework** exclusively.

| Aspect | Implementation |
|--------|----------------|
| **Framework** | Django REST Framework (DRF) 3.15.1+ |
| **Type Safety** | Type hints + MyPy static checking |
| **Performance** | Django ORM with query optimization |
| **AI/ML Integration** | Native Python support for TensorFlow, PyTorch |
| **ERP Ecosystem** | Django for ERP (Frappe-inspired patterns) |
| **Authentication** | Session-based (server-managed, Redis-backed) |
| **Authorization** | Policy Engine with RBAC/ABAC |

**Rationale:**
- ✅ **Session-based authentication** enforces security
- ✅ **Django ORM** with row-level multitenancy
- ✅ **AI/ML integration** via Python ecosystem
- ✅ **Established ERP patterns** from Django community
- ✅ **Excellent for financial calculations** (Decimal precision, NumPy/Pandas)
- ✅ **Unified stack** (Backend + AI/ML in same language)

**Trade-off Accepted:**
- Slightly less type-safe than TypeScript (mitigated by Pydantic, mypy)
- Slightly slower than Node.js (but FastAPI is async, very fast)

---

### 1.2 FULL TECHNOLOGY STACK

```yaml
Backend:
  Framework: Django REST Framework (DRF) 3.15.1+ (Python 3.11+)
    ORM: Django ORM (built-in) is required for all backend data access
  Data Validation: Django Serializers + Pydantic v2
  Async: Django async views, aiofiles
  Task Queue: Celery + Redis
  Scheduler: APScheduler

Database:
  Primary: PostgreSQL 15+
  Time-series: TimescaleDB (extension)
  Cache: Redis 7+
  Search: PostgreSQL Full-Text Search (or OpenSearch)

Frontend:
  Framework: React 18 with TypeScript
  UI Library: Shadcn/ui (Radix UI + Tailwind CSS)
  State: Zustand
  Forms: React Hook Form + Zod validation
  Data Grid: TanStack Table (React Table)
  Charts: Recharts
  Build: Vite

API:
  Protocol: REST (primary)
  Documentation: OpenAPI (Django-generated)
  Versioning: URL-based (/api/v1/)

Security:
  Authentication: Session-based (HTTP-only cookies, Redis-backed)
  Authorization: Policy Engine with RBAC/ABAC
  Encryption: AES-256 (data at rest), TLS 1.3 (in transit)
  Secrets: Environment variables or HashiCorp Vault

DevOps:
  Containerization: Docker
  Orchestration: Docker Compose (dev), Kubernetes (prod)
  CI/CD: GitHub Actions
  Monitoring: Prometheus + Grafana
  Logging: Loki (lightweight alternative to ELK)
  Tracing: OpenTelemetry
  Error Tracking: Sentry

Cloud:
  Hosting: AWS (primary), multi-cloud capable
  Storage: S3 (documents)
  CDN: CloudFront
  Email: SES or SendGrid
  SMS: Twilio or SNS

AI/ML:
  Framework: TensorFlow, PyTorch
  OCR: Tesseract + AWS Textract
  NLP: Hugging Face Transformers
  Serving: Python microservice with Django endpoint
```

---

## 2. resource FRAMEWORK DESIGN

### 2.1 WHAT IS A resource?

A **resource** (Document Type) is a **unified definition** of:
1. **Data Model** (database schema)
2. **Business Logic** (validation, workflows)
3. **Permissions** (who can read/write/delete)
4. **UI Metadata** (form layout, field types)
5. **Hooks** (lifecycle events: before_insert, after_update, etc.)

**Example**: The `Purchase Invoice` resource defines:
- Table schema: `ap_invoices`, `ap_invoice_lines`
- Validation: Invoice number uniqueness, vendor active check
- Permissions: AP Clerk can create, Approver can approve
- UI: Form layout with vendor dropdown, line items grid
- Hooks: `on_submit` → create GL journal, update vendor balance

---

### 2.2 resource DEFINITION STRUCTURE

#### **resource Metadata (JSON/YAML)**

```yaml
# resources/ap_invoice.yaml

name: "Purchase Invoice"
module: "Accounts Payable"
resource_name: "APInvoice"
table_name: "ap_invoices"
is_submittable: true  # Has workflow (Draft → Submit → Cancel)
track_changes: true   # Audit log enabled
naming_series: "PINV-.YYYY.-.#####"

fields:
  - fieldname: "invoice_number"
    label: "Invoice Number"
    fieldtype: "Data"
    required: true
    unique: true
    read_only: true  # Auto-generated

  - fieldname: "vendor"
    label: "Vendor"
    fieldtype: "Link"
    options: "Vendor"  # Links to Vendor resource
    required: true
    in_list_view: true

  - fieldname: "invoice_date"
    label: "Invoice Date"
    fieldtype: "Date"
    required: true
    default: "Today"

  - fieldname: "due_date"
    label: "Due Date"
    fieldtype: "Date"
    required: true
    depends_on: "eval:doc.payment_terms"

  - fieldname: "currency"
    label: "Currency"
    fieldtype: "Link"
    options: "Currency"
    required: true
    default: "get_default_currency"

  - fieldname: "total_amount"
    label: "Total Amount"
    fieldtype: "Currency"
    read_only: true
    calculated: true
    formula: "sum(items.net_amount)"

  - fieldname: "status"
    label: "Status"
    fieldtype: "Select"
    options: ["Draft", "Submitted", "Approved", "Posted", "Paid", "Cancelled"]
    default: "Draft"
    read_only: true

  - fieldname: "items"
    label: "Invoice Items"
    fieldtype: "Table"
    options: "APInvoiceLine"  # Child resource

permissions:
  - role: "AP Clerk"
    permlevel: 0
    read: 1
    write: 1
    create: 1
    delete: 0
    submit: 0
    cancel: 0

  - role: "AP Manager"
    permlevel: 0
    read: 1
    write: 1
    create: 1
    delete: 1
    submit: 1  # Can submit for posting
    cancel: 1

  - role: "Accountant"
    permlevel: 0
    read: 1
    write: 0
    create: 0

workflows:
  - name: "Invoice Approval Workflow"
    states:
      - name: "Draft"
        transitions: ["Submit for Approval"]
      - name: "Pending Approval"
        transitions: ["Approve", "Reject"]
      - name: "Approved"
        transitions: ["Post to GL", "Cancel"]
      - name: "Posted"
        transitions: ["Mark as Paid"]

hooks:
  before_insert:
    - "ap.invoice.validate_vendor_active"
    - "ap.invoice.check_duplicate"

  validate:
    - "ap.invoice.validate_total"
    - "ap.invoice.check_budget"

  on_submit:
    - "ap.invoice.create_gl_journal"
    - "ap.invoice.update_vendor_balance"
    - "ap.invoice.emit_event_invoice_submitted"

  on_cancel:
    - "ap.invoice.reverse_gl_journal"
    - "ap.invoice.update_vendor_balance_reversal"

  on_update_after_submit:
    - "ap.invoice.check_amendments"
```

---

### 2.3 PYTHON resource CLASS IMPLEMENTATION

```python
# app/resources/ap_invoice/ap_invoice.py

from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from rest_framework import serializers
from django.db import models

from app.core.resource import resource, Field
from app.core.db import BaseModel
from app.core.exceptions import ValidationError
from app.services.gl import GLService
from app.services.budget import BudgetService


class APInvoiceLine(BaseModel):
    """Child table: Invoice line items"""
    line_number: int
    description: str
    gl_account: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    line_amount: Decimal
    tax_code: Optional[str] = None
    tax_amount: Decimal = Decimal('0.00')
    net_amount: Decimal

    @validator('net_amount', always=True)
    def calculate_net_amount(cls, v, values):
        return values['line_amount'] + values.get('tax_amount', Decimal('0.00'))


class APInvoice(resource):
    """Purchase Invoice resource"""

    # Metadata
    __resource_name__ = "APInvoice"
    __module__ = "Accounts Payable"
    __table_name__ = "ap_invoices"
    __is_submittable__ = True

    # Database Model (Django ORM)
    class Model(models.Model):
        class Meta:
            db_table = 'ap_invoices'
            indexes = [
                models.Index(fields=['vendor_id', 'tenant_id']),
                models.Index(fields=['company_id', 'tenant_id']),
            ]

        invoice_id = models.CharField(max_length=36, primary_key=True)
        invoice_number = models.CharField(max_length=100, unique=True)
        vendor_id = models.ForeignKey('vendors.Vendor', on_delete=models.PROTECT)
        company_id = models.ForeignKey('companies.Company', on_delete=models.PROTECT)
        invoice_date = models.DateField()
        due_date = models.DateField()
        currency_code = models.CharField(max_length=3)
        tenant_id = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE)
        total_amount = Column(Numeric(20, 2), nullable=False)
        status = Column(Enum('Draft', 'Submitted', 'Approved', 'Posted', 'Paid', 'Cancelled'), default='Draft')
        # ... more columns

        # Relationships
        vendor = relationship("Vendor", back_populates="invoices")
        lines = relationship("APInvoiceLine", back_populates="invoice", cascade="all, delete-orphan")

    # Pydantic Schema (API validation)
    class Schema(BaseModel):
        invoice_number: Optional[str] = None  # Auto-generated
        vendor: str
        invoice_date: datetime.date
        due_date: datetime.date
        currency: str = Field(default="USD")
        items: List[APInvoiceLine]
        total_amount: Optional[Decimal] = None  # Calculated

        @validator('total_amount', always=True)
        def calculate_total(cls, v, values):
            items = values.get('items', [])
            return sum(item.net_amount for item in items)

    # Business Logic (Hooks)

    def before_insert(self):
        """Called before creating new invoice"""
        self.validate_vendor_active()
        self.check_duplicate_invoice()
        self.generate_invoice_number()

    def validate(self):
        """Validation before save/submit"""
        self.validate_total_amount()
        self.validate_line_items()
        self.check_budget_availability()

    def on_submit(self):
        """Called when invoice is submitted for posting"""
        self.validate_approvals()
        self.create_gl_journal()
        self.update_vendor_outstanding()
        self.emit_event('invoice_submitted', self.as_dict())

    def on_cancel(self):
        """Called when invoice is cancelled"""
        self.reverse_gl_journal()
        self.update_vendor_outstanding(reverse=True)
        self.emit_event('invoice_cancelled', self.as_dict())

    # Custom Methods

    def validate_vendor_active(self):
        """Ensure vendor is active"""
        vendor = self.get_doc('Vendor', self.vendor_id)
        if vendor.status != 'Active':
            raise ValidationError(f"Vendor {vendor.vendor_name} is not active")

    def check_duplicate_invoice(self):
        """Check for duplicate invoice numbers from same vendor"""
        existing = self.db.query(APInvoice.Model).filter_by(
            vendor_id=self.vendor_id,
            invoice_number=self.invoice_number
        ).first()
        if existing:
            raise ValidationError(f"Duplicate invoice number {self.invoice_number} for vendor")

    def check_budget_availability(self):
        """Check if budget is available for expenses"""
        if self.status in ['Draft', 'Pending Approval']:
            for line in self.items:
                BudgetService.check_budget(
                    gl_account=line.gl_account,
                    amount=line.net_amount,
                    period=self.get_current_period()
                )

    def create_gl_journal(self):
        """Create GL journal entry for invoice"""
        journal_lines = []

        # Credit: AP Control Account (Liability)
        journal_lines.append({
            'account': self.get_vendor_ap_account(),
            'debit': Decimal('0.00'),
            'credit': self.total_amount,
            'description': f"Purchase Invoice {self.invoice_number}"
        })

        # Debit: Expense/Asset accounts
        for line in self.items:
            journal_lines.append({
                'account': line.gl_account,
                'debit': line.net_amount,
                'credit': Decimal('0.00'),
                'description': line.description,
                'department': line.department_id,
                'project': line.project_id
            })

        # Create journal via GL Service
        journal = GLService.create_journal(
            journal_type='AP Invoice',
            journal_date=self.invoice_date,
            lines=journal_lines,
            source_resource_type='APInvoice',
            source_id=self.invoice_id
        )

        # Link journal to invoice
        self.gl_journal_id = journal.journal_id
        self.save()

        return journal

    def reverse_gl_journal(self):
        """Reverse the GL journal when invoice is cancelled"""
        if self.gl_journal_id:
            GLService.reverse_journal(self.gl_journal_id)

    def update_vendor_outstanding(self, reverse=False):
        """Update vendor's outstanding balance"""
        vendor = self.get_doc('Vendor', self.vendor_id)
        if reverse:
            vendor.total_outstanding -= self.total_amount
        else:
            vendor.total_outstanding += self.total_amount
        vendor.save()

    def get_vendor_ap_account(self):
        """Get AP control account for vendor"""
        vendor = self.get_doc('Vendor', self.vendor_id)
        return vendor.ap_control_account_id or self.get_default_ap_account()

    def generate_invoice_number(self):
        """Auto-generate invoice number based on naming series"""
        if not self.invoice_number:
            self.invoice_number = self.get_naming_series('PINV-.YYYY.-.#####')

    # API Methods

    @classmethod
    async def get_list(cls, filters=None, limit=20, offset=0):
        """Get list of invoices with filters"""
        query = cls.db.query(cls.Model)

        if filters:
            if filters.get('vendor'):
                query = query.filter(cls.Model.vendor_id == filters['vendor'])
            if filters.get('status'):
                query = query.filter(cls.Model.status == filters['status'])
            if filters.get('from_date'):
                query = query.filter(cls.Model.invoice_date >= filters['from_date'])
            if filters.get('to_date'):
                query = query.filter(cls.Model.invoice_date <= filters['to_date'])

        return query.limit(limit).offset(offset).all()

    @classmethod
    async def create(cls, data: dict):
        """Create new invoice"""
        invoice = cls(data)
        invoice.insert()
        return invoice

    async def submit(self):
        """Submit invoice for posting"""
        if self.status != 'Draft':
            raise ValidationError("Only Draft invoices can be submitted")

        self.status = 'Submitted'
        self.on_submit()
        self.save()

    async def approve(self, approver_id: str):
        """Approve submitted invoice"""
        if self.status != 'Submitted':
            raise ValidationError("Only Submitted invoices can be approved")

        self.status = 'Approved'
        self.approved_by = approver_id
        self.approved_at = datetime.now()
        self.save()

    async def post_to_gl(self):
        """Post approved invoice to GL"""
        if self.status != 'Approved':
            raise ValidationError("Only Approved invoices can be posted")

        self.create_gl_journal()
        self.status = 'Posted'
        self.posted_at = datetime.now()
        self.save()
```

---

### 2.4 resource FRAMEWORK CORE

```python
# app/core/resource.py

from typing import Dict, List, Any, Optional, Type
from abc import ABC, abstractmethod
from django.db import models
from rest_framework import serializers

from app.core.db import get_db
from app.core.events import EventBus
from app.core.permissions import PermissionEngine
from app.core.naming import NamingSeries


class resourceBase(ABC):
    """Base class for all resources"""

    # Metadata (must be defined by subclass)
    __resource_name__: str
    __module__: str
    __table_name__: str
    __is_submittable__: bool = False
    __track_changes__: bool = True

    # Django Model (must be defined by subclass)
    Model: Type[models.Model]

    # DRF Serializer (must be defined by subclass)
    Serializer: Type[serializers.Serializer]

    def __init__(self, data: Optional[Dict] = None):
        self.db = get_db()
        self.event_bus = EventBus()
        self.permissions = PermissionEngine()
        self.naming = NamingSeries()

        if data:
            self.load_from_dict(data)

    # Lifecycle Hooks (override in subclass)

    def before_insert(self):
        """Hook: Before inserting new document"""
        pass

    def after_insert(self):
        """Hook: After inserting new document"""
        pass

    def before_save(self):
        """Hook: Before saving document"""
        pass

    def after_save(self):
        """Hook: After saving document"""
        pass

    def validate(self):
        """Hook: Validation before save"""
        pass

    def on_submit(self):
        """Hook: When document is submitted (if submittable)"""
        pass

    def on_cancel(self):
        """Hook: When document is cancelled (if submittable)"""
        pass

    def on_update_after_submit(self):
        """Hook: When submitted document is updated"""
        pass

    # Core Methods

    def insert(self):
        """Insert new document"""
        self.before_insert()
        self.validate()

        # Create DB record
        db_obj = self.Model(**self.as_dict())
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)

        self.after_insert()
        self.emit_event('after_insert')

        return self

    def save(self):
        """Save document"""
        self.before_save()
        self.validate()

        # Update DB record
        db_obj = self.db.query(self.Model).filter_by(id=self.id).first()
        for key, value in self.as_dict().items():
            setattr(db_obj, key, value)

        self.db.commit()
        self.db.refresh(db_obj)

        self.after_save()
        self.emit_event('after_save')

        return self

    def delete(self):
        """Delete document"""
        self.check_permission('delete')

        db_obj = self.db.query(self.Model).filter_by(id=self.id).first()
        self.db.delete(db_obj)
        self.db.commit()

        self.emit_event('after_delete')

    def submit(self):
        """Submit document (if submittable)"""
        if not self.__is_submittable__:
            raise Exception(f"{self.__resource_name__} is not submittable")

        self.check_permission('submit')
        self.on_submit()
        self.emit_event('on_submit')

    def cancel(self):
        """Cancel document (if submittable)"""
        if not self.__is_submittable__:
            raise Exception(f"{self.__resource_name__} is not cancellable")

        self.check_permission('cancel')
        self.on_cancel()
        self.emit_event('on_cancel')

    # Utility Methods

    def as_dict(self) -> Dict:
        """Convert to dictionary"""
        return self.Schema(**self.__dict__).dict()

    def load_from_dict(self, data: Dict):
        """Load from dictionary"""
        schema_obj = self.Schema(**data)
        for key, value in schema_obj.dict().items():
            setattr(self, key, value)

    def get_doc(self, resource: str, name: str):
        """Get another document"""
        # Dynamic import of resource
        module = __import__(f'app.resources.{resource.lower()}', fromlist=[resource_type])
        resourceClass = getattr(module, resource)
        return resourceClass.get(name)

    def emit_event(self, event_type: str, data: Optional[Dict] = None):
        """Emit event to event bus"""
        self.event_bus.emit(
            event_type=f'{self.__resource_name__}.{event_type}',
            data=data or self.as_dict()
        )

    def check_permission(self, action: str):
        """Check if user has permission for action"""
        if not self.permissions.has_permission(
            user_id=self.get_current_user(),
            resource_type=self.__resource_name__,
            action=action
        ):
            raise PermissionError(f"No permission to {action} {self.__resource_name__}")

    def get_naming_series(self, pattern: str) -> str:
        """Generate document name from naming series"""
        return self.naming.get_next_number(
            resource_type=self.__resource_name__,
            pattern=pattern
        )

    @staticmethod
    def get_current_user():
        """Get current user from context"""
        # Implementation depends on auth system
        pass

    @staticmethod
    def get_current_period():
        """Get current accounting period"""
        # Implementation
        pass

    @staticmethod
    def get_default_ap_account():
        """Get default AP control account"""
        # Implementation
        pass
```

---

## 3. MODULE ORGANIZATION

### 3.1 PROJECT STRUCTURE

```
accounting-erp/
├── app/
│   ├── __init__.py
│   ├── main.py                          # Django app entry point
│   │
│   ├── core/                            # Core framework
│   │   ├── __init__.py
│   │   ├── config.py                    # Configuration
│   │   ├── db.py                        # Database connection
│   │   ├── resource.py                   # resource base class
│   │   ├── events.py                    # Event bus
│   │   ├── permissions.py               # Permission engine
│   │   ├── naming.py                    # Naming series
│   │   ├── workflows.py                 # Workflow engine
│   │   ├── exceptions.py                # Custom exceptions
│   │   └── utils.py                     # Utilities
│   │
│   ├── modules/                         # Accounting modules
│   │   ├── __init__.py
│   │   │
│   │   ├── general_ledger/              # GL Module
│   │   │   ├── __init__.py
│   │   │   ├── models/                  # Django ORM models
│   │   │   │   ├── chart_of_accounts.py
│   │   │   │   ├── journal_entry.py
│   │   │   │   ├── account_balance.py
│   │   │   │   └── gl_transaction_log.py
│   │   │   ├── serializers/             # DRF serializers
│   │   │   │   ├── coa_schema.py
│   │   │   │   └── journal_schema.py
│   │   │   ├── services/                # Business logic
│   │   │   │   ├── gl_service.py
│   │   │   │   ├── journal_service.py
│   │   │   │   └── consolidation_service.py
│   │   │   ├── resources/                # resource definitions
│   │   │   │   ├── chart_of_accounts.py
│   │   │   │   ├── journal_entry.py
│   │   │   │   └── accounting_period.py
│   │   │   ├── api/                     # API routes
│   │   │   │   ├── coa_api.py
│   │   │   │   └── journal_api.py
│   │   │   └── reports/                 # Reports
│   │   │       ├── trial_balance.py
│   │   │       └── general_ledger.py
│   │   │
│   │   ├── accounts_payable/            # AP Module
│   │   │   ├── __init__.py
│   │   │   ├── models/
│   │   │   │   ├── vendor.py
│   │   │   │   ├── ap_invoice.py
│   │   │   │   └── ap_payment.py
│   │   │   ├── schemas/
│   │   │   ├── services/
│   │   │   │   ├── vendor_service.py
│   │   │   │   ├── invoice_service.py
│   │   │   │   └── payment_service.py
│   │   │   ├── resources/
│   │   │   │   ├── vendor.py
│   │   │   │   ├── ap_invoice.py
│   │   │   │   └── ap_payment.py
│   │   │   ├── api/
│   │   │   └── reports/
│   │   │       ├── ap_aging.py
│   │   │       └── vendor_statement.py
│   │   │
│   │   ├── accounts_receivable/         # AR Module
│   │   │   └── (similar structure to AP)
│   │   │
│   │   ├── cash_management/             # Cash Module
│   │   │   └── (similar structure)
│   │   │
│   │   ├── fixed_assets/                # FA Module
│   │   │   └── (similar structure)
│   │   │
│   │   ├── tax_management/              # Tax Module
│   │   │   ├── gst/                     # India GST
│   │   │   ├── vat/                     # GCC VAT
│   │   │   ├── e_invoicing/             # E-invoice
│   │   │   └── (similar structure)
│   │   │
│   │   ├── project_accounting/          # Project Module
│   │   │   └── (similar structure)
│   │   │
│   │   └── reporting/                   # Reporting Module
│   │       ├── financial_statements.py
│   │       ├── management_reports.py
│   │       └── analytics.py
│   │
│   ├── services/                        # Shared services
│   │   ├── __init__.py
│   │   ├── ai_service.py                # AI/ML service
│   │   ├── notification_service.py      # Notifications
│   │   ├── email_service.py             # Email
│   │   ├── document_service.py          # Document storage
│   │   └── integration_service.py       # External integrations
│   │
│   ├── api/                             # API layer
│   │   ├── __init__.py
│   │   ├── v1/                          # API version 1
│   │   │   ├── __init__.py
│   │   │   ├── endpoints/               # DRF viewsets
│   │   │   │   ├── gl.py
│   │   │   │   ├── ap.py
│   │   │   │   ├── ar.py
│   │   │   │   └── ...
│   │   │   ├── permissions.py           # DRF permissions
│   │   │   └── filters.py               # DRF filters
│   │   └── urls.py                      # URL routing
│   │
│   ├── migrations/                      # Django migrations
│   │   ├── 0001_initial.py
│   │   └── ...
│   │
│   └── tests/                           # Tests
│       ├── unit/
│       ├── integration/
│       └── e2e/
│
├── frontend/                            # React frontend
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── App.tsx
│   └── package.json
│
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
│
├── scripts/
│   ├── setup.sh
│   └── deploy.sh
│
├── .env.example
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

### 3.2 MODULE BOUNDARIES & COMMUNICATION

**Principle**: Modules communicate via:
1. **Internal Events** (preferred for async operations)
2. **Service calls** (for synchronous operations)
3. **NOT direct database access** (maintain encapsulation)

**Example: AP Invoice → GL Journal**

```python
# ❌ BAD: Direct database access from AP to GL
def create_ap_invoice():
    # AP Module directly inserting into GL tables
    journal = gl_models.JournalEntry(...)  # WRONG!
    db.add(journal)

# ✅ GOOD: Via GL Service
def create_ap_invoice():
    # AP Module calls GL Service
    journal = GLService.create_journal(lines=...)

# ✅ BEST: Via Events (async, decoupled)
def create_ap_invoice():
    # AP Module emits event
    event_bus.emit('ap.invoice.posted', invoice_data)

    # GL Module listens to event
    @event_bus.on('ap.invoice.posted')
    def handle_invoice_posted(invoice_data):
        GLService.create_journal_from_ap_invoice(invoice_data)
```

---

## 4. INTERNAL EVENT ARCHITECTURE

### 4.1 EVENT BUS IMPLEMENTATION

```python
# app/core/events.py

from typing import Dict, Callable, List, Any
from collections import defaultdict
import asyncio
import logging

logger = logging.getLogger(__name__)


class EventBus:
    """Internal event bus for module communication"""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._async_listeners: Dict[str, List[Callable]] = defaultdict(list)

    def on(self, event_type: str, handler: Callable):
        """Register synchronous event handler"""
        self._listeners[event_type].append(handler)
        logger.info(f"Registered handler for event: {event_type}")

    def on_async(self, event_type: str, handler: Callable):
        """Register asynchronous event handler"""
        self._async_listeners[event_type].append(handler)
        logger.info(f"Registered async handler for event: {event_type}")

    def emit(self, event_type: str, data: Any = None):
        """Emit event (synchronous handlers)"""
        logger.info(f"Event emitted: {event_type}")

        for handler in self._listeners.get(event_type, []):
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Error in event handler {handler.__name__}: {e}")

    async def emit_async(self, event_type: str, data: Any = None):
        """Emit event (asynchronous handlers)"""
        logger.info(f"Async event emitted: {event_type}")

        tasks = []
        for handler in self._async_listeners.get(event_type, []):
            tasks.append(handler(data))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def remove_listener(self, event_type: str, handler: Callable):
        """Remove event listener"""
        if handler in self._listeners[event_type]:
            self._listeners[event_type].remove(handler)

# Global event bus instance
event_bus = EventBus()
```

---

### 4.2 EVENT-DRIVEN WORKFLOWS

**Example: Invoice Posting Flow**

```python
# app/modules/accounts_payable/resources/ap_invoice.py

from app.core.events import event_bus

class APInvoice(resource):

    def on_submit(self):
        """When invoice is submitted"""
        # Emit event
        event_bus.emit('ap.invoice.submitted', {
            'invoice_id': self.invoice_id,
            'vendor_id': self.vendor_id,
            'total_amount': self.total_amount,
            'invoice_date': self.invoice_date,
            'lines': [line.as_dict() for line in self.items]
        })

# app/modules/general_ledger/services/gl_service.py

from app.core.events import event_bus

class GLService:

    @staticmethod
    @event_bus.on('ap.invoice.submitted')
    def handle_ap_invoice_submitted(invoice_data):
        """Automatically create GL journal when AP invoice is submitted"""
        journal_lines = GLService._create_journal_lines_from_ap_invoice(invoice_data)
        journal = GLService.create_journal(
            journal_type='AP Invoice',
            source_id=invoice_data['invoice_id'],
            lines=journal_lines
        )
        logger.info(f"GL Journal {journal.journal_number} created from AP Invoice")

# app/modules/cash_management/services/cash_forecast_service.py

from app.core.events import event_bus

class CashForecastService:

    @staticmethod
    @event_bus.on('ap.invoice.submitted')
    def update_cash_forecast(invoice_data):
        """Update cash forecast with new payable"""
        CashForecastService.add_cash_outflow(
            date=invoice_data['due_date'],
            amount=invoice_data['total_amount'],
            description=f"AP Invoice payment due"
        )

# app/modules/tax_management/services/tax_service.py

from app.core.events import event_bus

class TaxService:

    @staticmethod
    @event_bus.on('ap.invoice.submitted')
    def record_tax_transaction(invoice_data):
        """Record tax transactions for GST/VAT"""
        for line in invoice_data['lines']:
            if line.get('tax_amount'):
                TaxService.create_tax_transaction(
                    transaction_type='PURCHASE',
                    taxable_amount=line['line_amount'],
                    tax_code=line['tax_code'],
                    tax_amount=line['tax_amount'],
                    source='ap_invoice',
                    source_id=invoice_data['invoice_id']
                )
```

**Events Catalog:**

| Event | Emitted By | Listeners |
|-------|-----------|-----------|
| `ap.invoice.submitted` | AP Module | GL (create journal), Cash (forecast), Tax (record) |
| `ar.invoice.posted` | AR Module | GL (create journal), Cash (forecast), Tax (record) |
| `payment.processed` | Cash Module | AP/AR (update outstanding), GL (post) |
| `journal.posted` | GL Module | Account Balances (update), Audit (log) |
| `vendor.created` | AP Module | Credit Agency (check), MDM (sync) |
| `budget.exceeded` | Budget Module | Notification (alert), Workflow (escalate) |

---

This is an excellent foundation! Would you like me to continue with:

1. ✅ **Complete API Layer Design** (DRF viewsets, session authentication, rate limiting)?
2. ✅ **Frontend Architecture** (React components, state management, forms)?
3. ✅ **Deployment & DevOps** (Docker, Kubernetes, CI/CD)?
4. ✅ **Security & Auth Framework** (Session-based auth, RBAC, SOD, Policy Engine)?
5. ✅ **More Complete resource Examples** (AR Invoice, Customer, Vendor, etc.)?

Let me know which you'd like next! 🚀
