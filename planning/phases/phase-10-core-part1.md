# Phase 10: Core Modules Part 1 — CRM & Finance

**Duration:** 5 weeks (Weeks 16-20)  
**Modules:** CRM (Customer Relationship Management), Accounting & Finance  
**Status:** ⏸️ BLOCKED (Awaiting Foundation completion)  
**Prerequisites:** Phase 9 complete (All Foundation modules operational)

---

## ⚠️ CRITICAL GATE

**This phase CANNOT begin until:**
- [ ] All 11 Foundation modules operational
- [ ] Platform-level billing operational
- [ ] Multi-tenancy proven at scale
- [ ] Architecture Board sign-off obtained

---

## Phase Objectives

Begin Core business module implementation with the two most critical customer-promised modules.

### Success Criteria
- [ ] 2 modules operational (backend + frontend + tests)
- [ ] ≥90% test coverage per module
- [ ] GL integration verified
- [ ] Multi-module workflows tested

---

## Week 16-18: CRM Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `crm` |
| Type | Core |
| Priority | P0 (Customer-Promised) |
| Dependencies | Tenant Management, Security, Workflow |
| Spec Location | `docs/modules/02-core/crm/` |
| Timeline | 10-12 days |

### Key Entities

```python
# CRM Core entities
- Contact (first_name, last_name, email, phone, company, tenant_id)
- Account (name, industry, size, status, owner_id, tenant_id)
- Lead (contact_id, source, status, score, tenant_id)
- Opportunity (account_id, name, stage, amount, close_date, tenant_id)
- Activity (entity_type, entity_id, activity_type, notes, tenant_id)
- Pipeline (name, stages, default, tenant_id)
- PipelineStage (pipeline_id, name, order, probability)
```

### API Endpoints

```
# Contacts
GET/POST /api/v1/crm/contacts/
GET/PUT/DELETE /api/v1/crm/contacts/{id}/
POST /api/v1/crm/contacts/{id}/convert-to-lead/

# Accounts
GET/POST /api/v1/crm/accounts/
GET/PUT/DELETE /api/v1/crm/accounts/{id}/
GET /api/v1/crm/accounts/{id}/contacts/
GET /api/v1/crm/accounts/{id}/opportunities/

# Leads
GET/POST /api/v1/crm/leads/
GET/PUT/DELETE /api/v1/crm/leads/{id}/
POST /api/v1/crm/leads/{id}/convert/
POST /api/v1/crm/leads/{id}/qualify/

# Opportunities
GET/POST /api/v1/crm/opportunities/
GET/PUT/DELETE /api/v1/crm/opportunities/{id}/
POST /api/v1/crm/opportunities/{id}/advance-stage/
POST /api/v1/crm/opportunities/{id}/won/
POST /api/v1/crm/opportunities/{id}/lost/

# Pipelines
GET/POST /api/v1/crm/pipelines/
GET/PUT/DELETE /api/v1/crm/pipelines/{id}/

# Activities
GET/POST /api/v1/crm/activities/
GET /api/v1/crm/activities/{entity_type}/{entity_id}/
```

### Key Implementation: Lead Conversion

```python
# backend/src/modules/crm/services.py

class LeadService:
    """Business logic for lead management."""

    def convert_lead(
        self,
        lead_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        create_account: bool = True,
        create_opportunity: bool = True,
        opportunity_data: dict = None
    ) -> LeadConversionResult:
        """
        Convert lead to account and/or opportunity.

        Architecture Compliance:
        - ✅ Tenant isolation enforced
        - ✅ Audit logging
        - ✅ Workflow trigger
        """

        lead = Lead.objects.get(
            id=lead_id,
            tenant_id=tenant_id  # TENANT ISOLATION
        )

        if lead.status == 'converted':
            raise ValueError("Lead already converted")

        result = LeadConversionResult()

        with transaction.atomic():
            # Create or link account
            if create_account:
                account = Account.objects.create(
                    tenant_id=tenant_id,
                    name=lead.company_name or f"{lead.contact.first_name} {lead.contact.last_name}",
                    owner_id=user_id,
                    source='lead_conversion'
                )
                result.account = account

                # Link contact to account
                lead.contact.account_id = account.id
                lead.contact.save()

            # Create opportunity
            if create_opportunity and opportunity_data:
                opportunity = Opportunity.objects.create(
                    tenant_id=tenant_id,
                    account_id=result.account.id if result.account else lead.contact.account_id,
                    name=opportunity_data.get('name', f"Opportunity from {lead.contact.full_name}"),
                    stage='qualification',
                    amount=opportunity_data.get('amount', 0),
                    close_date=opportunity_data.get('close_date'),
                    owner_id=user_id
                )
                result.opportunity = opportunity

            # Update lead status
            lead.status = 'converted'
            lead.converted_at = timezone.now()
            lead.converted_by = user_id
            lead.save()

            result.lead = lead

        # Trigger workflow
        WorkflowEngine().trigger_event(
            event_type='crm.lead.converted',
            tenant_id=tenant_id,
            payload={
                'lead_id': str(lead.id),
                'account_id': str(result.account.id) if result.account else None,
                'opportunity_id': str(result.opportunity.id) if result.opportunity else None
            }
        )

        # Audit log
        AuditService.log(
            action='crm.lead.converted',
            actor_id=user_id,
            resource_type='Lead',
            resource_id=lead.id,
            tenant_id=tenant_id,
            details={'conversion_result': result.to_dict()}
        )

        return result
```

### Tenant Isolation Tests (MANDATORY)

```python
# backend/src/modules/crm/tests/test_isolation.py

class CRMTenantIsolationTestCase(TestCase):
    """Critical tenant isolation tests for CRM."""

    def test_cannot_view_other_tenant_contacts(self):
        """User cannot see other tenant's contacts."""
        other_contact = Contact.objects.create(
            tenant_id=self.other_tenant_id,
            email='other@example.com',
            first_name='Other'
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f'/api/v1/crm/contacts/{other_contact.id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_convert_other_tenant_lead(self):
        """User cannot convert lead from another tenant."""
        other_lead = Lead.objects.create(
            tenant_id=self.other_tenant_id,
            contact=self.other_contact,
            status='qualified'
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            f'/api/v1/crm/leads/{other_lead.id}/convert/',
            {'create_account': True}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify lead unchanged
        other_lead.refresh_from_db()
        self.assertEqual(other_lead.status, 'qualified')

    def test_opportunity_pipeline_stage_isolation(self):
        """User can only use their tenant's pipeline stages."""
        other_pipeline = Pipeline.objects.create(
            tenant_id=self.other_tenant_id,
            name='Other Pipeline'
        )
        other_stage = PipelineStage.objects.create(
            pipeline=other_pipeline,
            name='Other Stage'
        )

        # Try to advance opportunity to other tenant's stage
        opportunity = Opportunity.objects.create(
            tenant_id=self.tenant_a_id,
            name='My Opportunity'
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            f'/api/v1/crm/opportunities/{opportunity.id}/advance-stage/',
            {'stage_id': str(other_stage.id)}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
```

---

## Week 18-20: Accounting & Finance Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `accounting_finance` |
| Type | Core |
| Priority | P0 (Customer-Promised) |
| Dependencies | Tenant Management, Security, Billing |
| Spec Location | `docs/modules/02-core/accounting-finance/` |
| Timeline | 10-12 days |
| Risk | HIGH (Financial accuracy critical) |

### Key Entities

```python
# Chart of Accounts
- Account (code, name, type, parent_id, tenant_id)
- AccountType (name, normal_balance, category)

# General Ledger
- JournalEntry (entry_number, date, description, status, tenant_id)
- JournalEntryLine (entry_id, account_id, debit, credit, description)
- Period (name, start_date, end_date, status, tenant_id)

# Accounts Receivable
- Customer (name, email, billing_address, credit_limit, tenant_id)
- Invoice (customer_id, invoice_number, date, due_date, status, tenant_id)
- InvoiceLine (invoice_id, description, quantity, unit_price, tax)
- Payment (invoice_id, amount, date, method, tenant_id)

# Accounts Payable
- Vendor (name, email, payment_terms, tenant_id)
- Bill (vendor_id, bill_number, date, due_date, status, tenant_id)
- BillLine (bill_id, description, quantity, unit_price, account_id)
- VendorPayment (bill_id, amount, date, method, tenant_id)
```

### API Endpoints

```
# Chart of Accounts
GET/POST /api/v1/accounting/accounts/
GET/PUT/DELETE /api/v1/accounting/accounts/{id}/
GET /api/v1/accounting/accounts/tree/

# Journal Entries
GET/POST /api/v1/accounting/journal-entries/
GET/PUT /api/v1/accounting/journal-entries/{id}/
POST /api/v1/accounting/journal-entries/{id}/post/
POST /api/v1/accounting/journal-entries/{id}/reverse/

# Invoices
GET/POST /api/v1/accounting/invoices/
GET/PUT/DELETE /api/v1/accounting/invoices/{id}/
POST /api/v1/accounting/invoices/{id}/send/
POST /api/v1/accounting/invoices/{id}/record-payment/

# Bills
GET/POST /api/v1/accounting/bills/
GET/PUT/DELETE /api/v1/accounting/bills/{id}/
POST /api/v1/accounting/bills/{id}/approve/
POST /api/v1/accounting/bills/{id}/pay/

# Reports
GET /api/v1/accounting/reports/trial-balance/
GET /api/v1/accounting/reports/income-statement/
GET /api/v1/accounting/reports/balance-sheet/
GET /api/v1/accounting/reports/cash-flow/
```

### Key Implementation: Double-Entry Bookkeeping

```python
# backend/src/modules/accounting_finance/services.py

class JournalEntryService:
    """
    Double-entry bookkeeping engine.

    CRITICAL: Debits must ALWAYS equal Credits.
    """

    def create_journal_entry(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        date: date,
        description: str,
        lines: list[dict]
    ) -> JournalEntry:
        """
        Create journal entry with balanced lines.

        Raises ValidationError if debits != credits.
        """

        # Validate balance
        total_debit = sum(line.get('debit', 0) for line in lines)
        total_credit = sum(line.get('credit', 0) for line in lines)

        if total_debit != total_credit:
            raise ValidationError(
                f"Journal entry must balance. Debit: {total_debit}, Credit: {total_credit}"
            )

        if total_debit == 0:
            raise ValidationError("Journal entry must have non-zero amounts")

        # Validate period is open
        period = self._get_period_for_date(tenant_id, date)
        if period.status != 'open':
            raise ValidationError(f"Period {period.name} is {period.status}")

        with transaction.atomic():
            # Generate entry number
            entry_number = self._generate_entry_number(tenant_id, date)

            entry = JournalEntry.objects.create(
                tenant_id=tenant_id,
                entry_number=entry_number,
                date=date,
                description=description,
                status='draft',
                created_by=user_id
            )

            for line_data in lines:
                # Verify account belongs to tenant
                account = Account.objects.get(
                    id=line_data['account_id'],
                    tenant_id=tenant_id  # TENANT ISOLATION
                )

                JournalEntryLine.objects.create(
                    entry=entry,
                    account=account,
                    debit=line_data.get('debit', 0),
                    credit=line_data.get('credit', 0),
                    description=line_data.get('description', '')
                )

        return entry

    def post_journal_entry(
        self,
        entry_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> JournalEntry:
        """Post journal entry to ledger (immutable after posting)."""

        entry = JournalEntry.objects.get(
            id=entry_id,
            tenant_id=tenant_id
        )

        if entry.status != 'draft':
            raise ValidationError(f"Cannot post entry with status: {entry.status}")

        # Re-validate balance
        lines = entry.lines.all()
        total_debit = sum(line.debit for line in lines)
        total_credit = sum(line.credit for line in lines)

        if total_debit != total_credit:
            raise ValidationError("Entry is unbalanced")

        entry.status = 'posted'
        entry.posted_at = timezone.now()
        entry.posted_by = user_id
        entry.save()

        # Update account balances
        for line in lines:
            self._update_account_balance(line.account, line.debit, line.credit)

        # Audit log (immutable)
        AuditService.log(
            action='accounting.journal_entry.posted',
            actor_id=user_id,
            resource_type='JournalEntry',
            resource_id=entry.id,
            tenant_id=tenant_id,
            details={
                'entry_number': entry.entry_number,
                'total_amount': float(total_debit)
            }
        )

        return entry


class InvoiceService:
    """Invoice management with GL integration."""

    def post_invoice(
        self,
        invoice_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Invoice:
        """
        Post invoice to AR and GL.

        Creates journal entry:
        - Debit: Accounts Receivable
        - Credit: Revenue + Tax Liability
        """

        invoice = Invoice.objects.get(
            id=invoice_id,
            tenant_id=tenant_id
        )

        if invoice.status != 'draft':
            raise ValidationError(f"Cannot post invoice with status: {invoice.status}")

        # Calculate totals
        subtotal = sum(line.quantity * line.unit_price for line in invoice.lines.all())
        tax_total = sum(line.tax_amount for line in invoice.lines.all())
        total = subtotal + tax_total

        # Get accounts
        ar_account = self._get_account(tenant_id, 'accounts_receivable')
        revenue_account = self._get_account(tenant_id, 'revenue')
        tax_account = self._get_account(tenant_id, 'tax_payable')

        # Create journal entry
        journal_lines = [
            {'account_id': ar_account.id, 'debit': total, 'credit': 0},
            {'account_id': revenue_account.id, 'debit': 0, 'credit': subtotal},
        ]

        if tax_total > 0:
            journal_lines.append(
                {'account_id': tax_account.id, 'debit': 0, 'credit': tax_total}
            )

        journal_entry = JournalEntryService().create_journal_entry(
            tenant_id=tenant_id,
            user_id=user_id,
            date=invoice.date,
            description=f"Invoice {invoice.invoice_number}",
            lines=journal_lines
        )

        # Post the journal entry
        JournalEntryService().post_journal_entry(
            journal_entry.id, tenant_id, user_id
        )

        # Update invoice
        invoice.status = 'posted'
        invoice.journal_entry = journal_entry
        invoice.posted_at = timezone.now()
        invoice.save()

        return invoice
```

### Financial Integrity Tests (MANDATORY)

```python
# backend/src/modules/accounting_finance/tests/test_financial_integrity.py

class FinancialIntegrityTestCase(TestCase):
    """Tests to ensure financial data integrity."""

    def test_journal_entry_must_balance(self):
        """Journal entry with unbalanced lines must be rejected."""

        lines = [
            {'account_id': self.cash_account.id, 'debit': 100, 'credit': 0},
            {'account_id': self.revenue_account.id, 'debit': 0, 'credit': 90},  # Unbalanced!
        ]

        with self.assertRaises(ValidationError) as context:
            JournalEntryService().create_journal_entry(
                tenant_id=self.tenant_id,
                user_id=self.user.id,
                date=date.today(),
                description='Test Entry',
                lines=lines
            )

        self.assertIn('must balance', str(context.exception))

    def test_posted_entry_cannot_be_modified(self):
        """Posted journal entry must be immutable."""

        entry = self._create_and_post_entry()

        with self.assertRaises(ValidationError):
            entry.description = "Modified"
            entry.save()

    def test_cannot_use_other_tenant_accounts(self):
        """Cannot create entry with accounts from another tenant."""

        other_account = Account.objects.create(
            tenant_id=self.other_tenant_id,
            code='1000',
            name='Other Cash'
        )

        lines = [
            {'account_id': other_account.id, 'debit': 100, 'credit': 0},
            {'account_id': self.revenue_account.id, 'debit': 0, 'credit': 100},
        ]

        with self.assertRaises(Account.DoesNotExist):
            JournalEntryService().create_journal_entry(
                tenant_id=self.tenant_id,
                user_id=self.user.id,
                date=date.today(),
                description='Test Entry',
                lines=lines
            )

    def test_trial_balance_sums_to_zero(self):
        """Trial balance must always sum to zero."""

        # Create multiple entries
        self._create_and_post_entry()
        self._create_and_post_entry()

        report = TrialBalanceReport(self.tenant_id).generate()

        total_debit = sum(item['debit'] for item in report['accounts'])
        total_credit = sum(item['credit'] for item in report['accounts'])

        self.assertEqual(total_debit, total_credit)
```

---

## Phase Completion Criteria

### Mandatory Checkpoints

- [ ] CRM module operational (contacts, leads, opportunities)
- [ ] Accounting module operational (GL, AR, AP)
- [ ] ≥90% test coverage per module
- [ ] Financial integrity tests passing
- [ ] Tenant isolation verified
- [ ] CRM-to-Invoice integration working
- [ ] All pre-commit hooks passing

### Integration Tests

```bash
# CRM to Accounting integration
pytest tests/integration/test_crm_accounting.py -v

# Example: Won opportunity creates invoice
def test_won_opportunity_creates_invoice():
    """When opportunity is won, invoice is auto-created."""
    opportunity = create_opportunity(amount=10000)
    response = client.post(f'/api/v1/crm/opportunities/{opportunity.id}/won/')

    assert response.status_code == 200

    # Invoice should be created
    invoice = Invoice.objects.get(opportunity_id=opportunity.id)
    assert invoice.total == 10000
    assert invoice.customer_id == opportunity.account.customer_id
```

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Financial calculation errors | 30% | CRITICAL | Extensive unit tests, decimal precision |
| GL integration complexity | 40% | HIGH | Double-entry validation, balance checks |
| Multi-currency issues | 20% | MEDIUM | Currency service abstraction |

---

## Document Status

**Status:** BLOCKED (Awaiting Foundation completion)  
**Last Updated:** January 5, 2026  
**Next Phase:** Phase 11 (Sales, Purchase, Inventory)

---

