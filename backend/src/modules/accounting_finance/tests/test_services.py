"""
Service tests for Accounting & Finance module.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.modules.accounting_finance.integrations import JournalLegV1, JournalPostingRequestV1, PeriodCloseEvidenceV1
from src.modules.accounting_finance.models import Account, JournalEntry, JournalLine, Payment, PostingPeriod
from src.modules.accounting_finance.services import (
    AccountingServiceError,
    AccountService,
    APInvoiceService,
    ARInvoiceService,
    FinancialReportingService,
    JournalEntryService,
    PaymentService,
    PostingPeriodService,
    _currency,
    _dimensions,
    _identifier,
    _money,
    _rate,
    _tenant,
    _text,
)


def create_open_period(tenant_id, name="2024-01", start=date(2024, 1, 1), end=date(2024, 1, 31)):
    return PostingPeriodService.create_period(
        tenant_id,
        actor_id="controller",
        data={"period_name": name, "start_date": start, "end_date": end, "fiscal_year": start.year},
        idempotency_key=f"period-{tenant_id}-{name}",
    )


def create_account(tenant_id, code, name, account_type, **extra):
    return AccountService.create_account(
        tenant_id,
        actor_id="controller",
        data={"code": code, "name": name, "account_type": account_type, **extra},
        idempotency_key=f"account-{tenant_id}-{code}",
    )


def journal_payload(period, debit_account, credit_account, entry_number="JE-SVC-001", amount="125.00"):
    return {
        "entry_number": entry_number,
        "posting_date": period.start_date,
        "posting_period_id": period.id,
        "description": "service workflow",
        "currency": "USD",
        "lines": [
            {"account_id": debit_account.id, "debit_amount": amount, "credit_amount": "0.00"},
            {"account_id": credit_account.id, "debit_amount": "0.00", "credit_amount": amount},
        ],
    }


@pytest.mark.django_db
class TestAccountService:
    """Test AccountService."""

    def test_create_account(self):
        """Test creating an account via service."""
        tenant_id = uuid.uuid4()
        account = AccountService.create_account(
            tenant_id=str(tenant_id),
            code="1000",
            name="Cash",
            account_type="asset",
        )

        assert account.code == "1000"
        assert account.name == "Cash"
        assert str(account.tenant_id) == str(tenant_id)

    def test_create_account_idempotency_key_rejects_different_payload(self):
        tenant_id = uuid.uuid4()
        key = "account-create-cash"

        created = AccountService.create_account(
            tenant_id,
            actor_id="controller",
            data={"code": "1000", "name": "Cash", "account_type": "asset"},
            idempotency_key=key,
        )

        replay = AccountService.create_account(
            tenant_id,
            actor_id="controller",
            data={"code": "1000", "name": "Cash", "account_type": "asset"},
            idempotency_key=key,
        )
        assert replay.id == created.id

        with pytest.raises(AccountingServiceError) as exc:
            AccountService.create_account(
                tenant_id,
                actor_id="controller",
                data={"code": "1000", "name": "Operating Cash", "account_type": "asset"},
                idempotency_key=key,
            )
        assert exc.value.domain_code == "IDEMPOTENCY_CONFLICT"

    def test_update_account_stale_version_leaves_row_unchanged(self):
        tenant_id = uuid.uuid4()
        account = AccountService.create_account(
            tenant_id,
            actor_id="controller",
            data={"code": "2000", "name": "Payables", "account_type": "liability"},
            idempotency_key="account-create-payables",
        )

        with pytest.raises(AccountingServiceError) as exc:
            AccountService.update_account(
                tenant_id,
                account.id,
                actor_id="controller",
                version=account.version + 1,
                changes={"name": "Changed"},
            )

        assert exc.value.domain_code == "STALE_VERSION"
        account.refresh_from_db()
        assert account.name == "Payables"
        assert account.version == 1

    def test_validate_posting_accounts_rejects_group_inactive_and_foreign_accounts(self):
        tenant_id = uuid.uuid4()
        group = AccountService.create_account(
            tenant_id,
            actor_id="controller",
            data={"code": "3000", "name": "Grouped", "account_type": "asset", "is_group": True},
            idempotency_key="account-create-group",
        )
        inactive = AccountService.create_account(
            tenant_id,
            actor_id="controller",
            data={"code": "3100", "name": "Inactive", "account_type": "asset", "is_active": False},
            idempotency_key="account-create-inactive",
        )
        foreign = AccountService.create_account(
            uuid.uuid4(),
            actor_id="controller",
            data={"code": "3200", "name": "Foreign", "account_type": "asset"},
            idempotency_key="account-create-foreign",
        )

        with pytest.raises(AccountingServiceError) as exc:
            AccountService.validate_posting_accounts(tenant_id, [group.id, inactive.id, foreign.id])

        assert exc.value.domain_code == "INVALID_POSTING_ACCOUNT"

    def test_account_filters_hierarchy_and_soft_delete_guardrails(self):
        tenant_id = uuid.uuid4()
        parent = AccountService.create_account(
            tenant_id,
            actor_id="controller",
            data={"code": "1000", "name": "Assets", "account_type": "asset", "is_group": True},
            idempotency_key="account-create-assets-parent",
        )
        child = AccountService.create_account(
            tenant_id,
            actor_id="controller",
            data={"code": "1010", "name": "Cash", "account_type": "asset", "parent_id": parent.id},
            idempotency_key="account-create-assets-child",
        )
        inactive = AccountService.create_account(
            tenant_id,
            actor_id="controller",
            data={"code": "1020", "name": "Dormant", "account_type": "asset", "is_active": False},
            idempotency_key="account-create-dormant",
        )

        hierarchy = AccountService.get_hierarchy(tenant_id)
        filtered = list(AccountService.list_accounts(tenant_id, filters={"is_active": False}))

        assert hierarchy[0].id == parent.id
        assert hierarchy[0].children[0].id == child.id
        assert filtered == [inactive]

        AccountService.soft_delete_account(tenant_id, inactive.id, actor_id="controller", reason="closed account")
        with pytest.raises(AccountingServiceError) as missing:
            AccountService.get_account(tenant_id, inactive.id)
        assert missing.value.domain_code == "RESOURCE_NOT_FOUND"

    def test_soft_delete_account_with_journal_history_is_blocked(self):
        tenant_id = uuid.uuid4()
        period = create_open_period(tenant_id)
        cash = create_account(tenant_id, "1200", "Cash", "asset", cash_flow_category="operating")
        revenue = create_account(tenant_id, "4200", "Revenue", "revenue")
        draft = JournalEntryService.create_draft(
            tenant_id,
            actor_id="creator",
            payload=journal_payload(period, cash, revenue, entry_number="JE-HISTORY"),
            idempotency_key="journal-create-history",
        )

        with pytest.raises(AccountingServiceError) as exc:
            AccountService.soft_delete_account(tenant_id, cash.id, actor_id="controller", reason="cleanup")

        assert exc.value.domain_code == "ACCOUNT_HAS_HISTORY"
        assert JournalLine.objects.filter(journal_entry=draft, account=cash).exists()


@pytest.mark.django_db
class TestPostingPeriodService:
    def test_period_update_reopen_lock_and_resolve_guardrails(self):
        tenant_id = uuid.uuid4()
        period = create_open_period(tenant_id)

        updated = PostingPeriodService.update_period(
            tenant_id,
            period.id,
            actor_id="controller",
            version=period.version,
            changes={"period_name": "January 2024"},
        )
        assert updated.period_name == "January 2024"
        assert updated.version == 2

        with pytest.raises(AccountingServiceError) as overlap:
            PostingPeriodService.create_period(
                tenant_id,
                actor_id="controller",
                data={
                    "period_name": "Overlap",
                    "start_date": date(2024, 1, 15),
                    "end_date": date(2024, 2, 15),
                    "fiscal_year": 2024,
                },
                idempotency_key="period-overlap",
            )
        assert overlap.value.domain_code == "PERIOD_OVERLAP"

        closed = PostingPeriodService.close_period(
            tenant_id,
            period.id,
            actor_id="controller",
            transition_key="period-close-clean",
            reason="month-end",
        )
        assert closed.status == "closed"

        reopened = PostingPeriodService.reopen_period(
            tenant_id,
            period.id,
            actor_id="controller",
            transition_key="period-reopen-clean",
            reason="late entry",
        )
        assert reopened.status == "open"

        PostingPeriodService.close_period(
            tenant_id,
            period.id,
            actor_id="controller",
            transition_key="period-close-before-lock",
            reason="ready to lock",
        )
        locked = PostingPeriodService.lock_period(
            tenant_id,
            period.id,
            actor_id="controller",
            transition_key="period-lock-clean",
            reason="audit complete",
        )
        assert locked.status == "locked"

        with pytest.raises(AccountingServiceError) as unresolved:
            PostingPeriodService.resolve_open_period(tenant_id, date(2024, 1, 20))
        assert unresolved.value.domain_code == "POSTING_PERIOD_CLOSED"


@pytest.mark.django_db
class TestJournalEntryService:
    """Test JournalEntryService."""

    def test_post_journal_entry(self):
        """Test posting a journal entry."""
        tenant_id = uuid.uuid4()

        period = PostingPeriod.objects.create(
            tenant_id=tenant_id,
            period_name="2024-01",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        cash_account = Account.objects.create(
            tenant_id=tenant_id,
            code="1000",
            name="Cash",
            account_type="asset",
        )

        revenue_account = Account.objects.create(
            tenant_id=tenant_id,
            code="4000",
            name="Revenue",
            account_type="revenue",
        )

        from src.modules.accounting_finance.models import JournalEntry

        entry = JournalEntry.objects.create(
            tenant_id=tenant_id,
            entry_number="JE-001",
            posting_date=date(2024, 1, 15),
            posting_period=period,
            status="draft",
        )

        JournalLine.objects.create(
            tenant_id=tenant_id,
            journal_entry=entry,
            account=cash_account,
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0.00"),
        )

        JournalLine.objects.create(
            tenant_id=tenant_id,
            journal_entry=entry,
            account=revenue_account,
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("100.00"),
        )

        # Post the entry
        posted_entry = JournalEntryService.post_journal_entry(entry, "user-123")

        assert posted_entry.status == "posted"
        assert posted_entry.posted_at is not None
        assert posted_entry.posted_by == "user-123"

    def test_create_update_post_reverse_and_report_workflow_is_idempotent(self):
        tenant_id = uuid.uuid4()
        period = create_open_period(tenant_id)
        cash = create_account(tenant_id, "1000", "Cash", "asset", cash_flow_category="operating")
        revenue = create_account(tenant_id, "4000", "Revenue", "revenue")

        draft = JournalEntryService.create_draft(
            tenant_id,
            actor_id="creator",
            payload=journal_payload(period, cash, revenue),
            idempotency_key="journal-create-workflow",
        )
        replay = JournalEntryService.create_draft(
            tenant_id,
            actor_id="creator",
            payload=journal_payload(period, cash, revenue),
            idempotency_key="journal-create-workflow",
        )
        assert replay.id == draft.id

        with pytest.raises(AccountingServiceError) as conflict:
            JournalEntryService.create_draft(
                tenant_id,
                actor_id="creator",
                payload=journal_payload(period, cash, revenue, amount="126.00"),
                idempotency_key="journal-create-workflow",
            )
        assert conflict.value.domain_code == "IDEMPOTENCY_CONFLICT"

        updated = JournalEntryService.update_draft(
            tenant_id,
            draft.id,
            actor_id="editor",
            version=draft.version,
            payload={"reference": "REV-REF", "currency": "usd"},
        )
        assert updated.reference == "REV-REF"
        assert updated.currency == "USD"

        posted = JournalEntryService.post_entry(
            tenant_id,
            draft.id,
            actor_id="poster",
            transition_key="post-workflow",
        )
        repost = JournalEntryService.post_entry(
            tenant_id,
            draft.id,
            actor_id="poster",
            transition_key="post-workflow",
        )
        assert repost.id == posted.id
        assert posted.status == "posted"
        assert posted.debit_total == Decimal("125.00")
        assert posted.credit_total == Decimal("125.00")

        reversal = JournalEntryService.reverse_entry(
            tenant_id,
            posted.id,
            actor_id="reverser",
            transition_key="reverse-workflow",
            posting_date=period.start_date,
            reason="customer correction",
        )
        replayed_reversal = JournalEntryService.reverse_entry(
            tenant_id,
            posted.id,
            actor_id="reverser",
            transition_key="reverse-workflow",
            posting_date=period.start_date,
            reason="customer correction",
        )
        posted.refresh_from_db()
        assert reversal.id == replayed_reversal.id
        assert reversal.status == "posted"
        assert posted.status == "reversed"

        trial_balance = FinancialReportingService.trial_balance(tenant_id, as_of_date=period.end_date)
        general_ledger = FinancialReportingService.general_ledger(
            tenant_id,
            account_id=cash.id,
            start_date=period.start_date,
            end_date=period.end_date,
        )
        assert trial_balance["balanced"] is True
        assert trial_balance["total_debit"] == trial_balance["total_credit"]
        assert [row["entry_number"] for row in general_ledger] == [posted.entry_number, reversal.entry_number]

    def test_post_entry_rejects_sod_closed_period_and_unbalanced_lines(self):
        tenant_id = uuid.uuid4()
        period = create_open_period(tenant_id)
        cash = create_account(tenant_id, "1100", "Cash", "asset", cash_flow_category="operating")
        revenue = create_account(tenant_id, "4100", "Revenue", "revenue")
        draft = JournalEntryService.create_draft(
            tenant_id,
            actor_id="creator",
            payload=journal_payload(period, cash, revenue, entry_number="JE-SVC-002"),
            idempotency_key="journal-create-sod",
        )

        with pytest.raises(AccountingServiceError) as sod:
            JournalEntryService.post_entry(tenant_id, draft.id, actor_id="creator", transition_key="post-sod")
        assert sod.value.domain_code == "SOD_CREATOR_CANNOT_POST"

        with pytest.raises(AccountingServiceError) as draft_blocker:
            PostingPeriodService.close_period(
                tenant_id,
                period.id,
                actor_id="controller",
                transition_key="close-period-with-draft",
                reason="month-end",
            )
        assert draft_blocker.value.domain_code == "PERIOD_HAS_DRAFTS"

        closed_period = create_open_period(tenant_id, "2024-02", date(2024, 2, 1), date(2024, 2, 29))
        PostingPeriodService.close_period(
            tenant_id,
            closed_period.id,
            actor_id="controller",
            transition_key="close-period",
            reason="month-end",
        )
        closed_draft = JournalEntryService.create_draft(
            tenant_id,
            actor_id="creator",
            payload=journal_payload(closed_period, cash, revenue, entry_number="JE-SVC-003"),
            idempotency_key="journal-create-closed-period",
        )
        with pytest.raises(AccountingServiceError) as closed:
            JournalEntryService.post_entry(tenant_id, closed_draft.id, actor_id="poster", transition_key="post-closed")
        assert closed.value.domain_code == "POSTING_PERIOD_CLOSED"

        fresh_period = create_open_period(tenant_id, "2024-03", date(2024, 3, 1), date(2024, 3, 31))
        unbalanced = JournalEntryService.create_draft(
            tenant_id,
            actor_id="creator",
            payload=journal_payload(fresh_period, cash, revenue, entry_number="JE-SVC-004"),
            idempotency_key="journal-create-unbalanced",
        )
        JournalLine.objects.filter(journal_entry=unbalanced, credit_amount=Decimal("125.00")).update(
            credit_amount=Decimal("124.00"),
            base_credit_amount=Decimal("124.00"),
        )
        with pytest.raises(AccountingServiceError) as unbalanced_error:
            JournalEntryService.post_entry(
                tenant_id,
                unbalanced.id,
                actor_id="poster",
                transition_key="post-unbalanced",
            )
        assert unbalanced_error.value.domain_code == "JOURNAL_UNBALANCED"


@pytest.mark.django_db
class TestInvoiceAndPaymentServices:
    def test_ap_invoice_lifecycle_sod_delete_payment_and_void(self, monkeypatch):
        tenant_id = uuid.uuid4()
        supplier_id = uuid.uuid4()
        period = create_open_period(tenant_id)
        expense = create_account(tenant_id, "5100", "Repairs", "expense")
        payable = create_account(tenant_id, "2100", "Payables", "liability")
        cash = create_account(tenant_id, "1003", "Operating cash", "asset", cash_flow_category="operating")
        assert payable and cash
        monkeypatch.setattr(
            "src.modules.accounting_finance.services.extension_registry.resolve_party",
            lambda *args, **kwargs: None,
        )

        invoice = APInvoiceService.create_invoice(
            tenant_id,
            actor_id="buyer",
            payload={
                "invoice_number": "AP-001",
                "supplier_id": supplier_id,
                "invoice_date": period.start_date,
                "due_date": period.end_date,
                "currency": "USD",
                "lines": [{"description": "repair", "account_id": expense.id, "unit_price": "80.00"}],
            },
            idempotency_key="ap-create-001",
        )
        APInvoiceService.submit(tenant_id, invoice.id, actor_id="buyer", transition_key="ap-submit-001")
        with pytest.raises(AccountingServiceError) as sod:
            APInvoiceService.approve(tenant_id, invoice.id, actor_id="buyer", transition_key="ap-approve-buyer")
        assert sod.value.domain_code == "SOD_CREATOR_CONFLICT"

        approved = APInvoiceService.approve(tenant_id, invoice.id, actor_id="approver", transition_key="ap-approve-001")
        with pytest.raises(AccountingServiceError) as poster_sod:
            APInvoiceService.post_to_gl(tenant_id, approved.id, actor_id="approver", transition_key="ap-post-approver")
        assert poster_sod.value.domain_code == "SOD_APPROVER_POSTER_CONFLICT"

        posted = APInvoiceService.post_to_gl(tenant_id, approved.id, actor_id="poster", transition_key="ap-post-001")
        assert posted.status == "posted"

        payment = PaymentService.record_payment(
            tenant_id,
            actor_id="treasury",
            payload={
                "ap_invoice_id": posted.id,
                "amount": "30.00",
                "currency": "USD",
                "payment_date": period.start_date,
                "payment_method": "ach",
            },
            idempotency_key="payment-ap-001",
        )
        posted.refresh_from_db()
        assert posted.status == "partially_paid"
        assert posted.paid_amount == Decimal("30.00")

        voided = PaymentService.void_payment(
            tenant_id,
            payment.id,
            actor_id="treasury",
            transition_key="payment-ap-void-001",
            reason="bank rejected",
        )
        posted.refresh_from_db()
        assert voided.status == "voided"
        assert posted.status == "posted"
        assert posted.paid_amount == Decimal("0.00")

        with pytest.raises(AccountingServiceError) as immutable:
            APInvoiceService.soft_delete_draft(tenant_id, posted.id, actor_id="buyer", reason="not draft")
        assert immutable.value.domain_code == "INVOICE_IMMUTABLE"

    def test_ar_invoice_post_payment_and_payment_idempotency_conflict(self, monkeypatch):
        tenant_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        period = create_open_period(tenant_id)
        receivable = create_account(tenant_id, "0900", "Receivables", "asset")
        cash = create_account(tenant_id, "1001", "Operating cash", "asset", cash_flow_category="operating")
        revenue = create_account(tenant_id, "4010", "Consulting revenue", "revenue")
        assert receivable.code < cash.code

        monkeypatch.setattr(
            "src.modules.accounting_finance.services.extension_registry.resolve_party",
            lambda *args, **kwargs: None,
        )

        invoice = ARInvoiceService.create_invoice(
            tenant_id,
            actor_id="seller",
            payload={
                "invoice_number": "AR-001",
                "customer_id": customer_id,
                "invoice_date": period.start_date,
                "due_date": period.end_date,
                "currency": "usd",
                "description": "consulting",
                "lines": [
                    {
                        "description": "implementation",
                        "account_id": revenue.id,
                        "quantity": "2",
                        "unit_price": "50.00",
                        "tax_amount": "5.00",
                    }
                ],
            },
            idempotency_key="ar-create-001",
        )
        assert invoice.total_amount == Decimal("105.00")
        assert invoice.lines.count() == 1

        posted_invoice = ARInvoiceService.post_to_gl(
            tenant_id,
            invoice.id,
            actor_id="poster",
            transition_key="ar-post-001",
        )
        assert posted_invoice.status == "posted"
        assert JournalEntry.objects.filter(
            tenant_id=tenant_id,
            source_module="accounting_finance.ar",
            source_reference=str(invoice.id),
            status="posted",
        ).exists()

        payment_payload = {
            "ar_invoice_id": posted_invoice.id,
            "amount": "40.00",
            "currency": "USD",
            "payment_date": period.start_date,
            "payment_method": "wire_transfer",
            "reference_number": "BANK-40",
        }
        payment = PaymentService.record_payment(
            tenant_id,
            actor_id="cashier",
            payload=payment_payload,
            idempotency_key="payment-ar-001",
        )
        replay = PaymentService.record_payment(
            tenant_id,
            actor_id="cashier",
            payload=payment_payload,
            idempotency_key="payment-ar-001",
        )
        posted_invoice.refresh_from_db()
        assert replay.id == payment.id
        assert posted_invoice.status == "partially_paid"
        assert posted_invoice.paid_amount == Decimal("40.00")

        with pytest.raises(AccountingServiceError) as conflict:
            PaymentService.record_payment(
                tenant_id,
                actor_id="cashier",
                payload={**payment_payload, "amount": "41.00"},
                idempotency_key="payment-ar-001",
            )
        assert conflict.value.domain_code == "IDEMPOTENCY_CONFLICT"

        with pytest.raises(AccountingServiceError) as overpayment:
            PaymentService.record_payment(
                tenant_id,
                actor_id="cashier",
                payload={**payment_payload, "amount": "100.00"},
                idempotency_key="payment-ar-overpay",
            )
        assert overpayment.value.domain_code == "OVERPAYMENT"

        updated = PaymentService.update_reference(
            tenant_id,
            payment.id,
            actor_id="cashier",
            description="settled against bank batch",
            reference_number="BANK-40-UPDATED",
        )
        assert updated.reference_number == "BANK-40-UPDATED"
        assert Payment.objects.for_tenant(tenant_id).count() == 1

        aging = ARInvoiceService.aging(tenant_id, as_of_date=period.end_date)
        assert aging["buckets"]["current"] == Decimal("65.00")
        assert aging["items"][0]["outstanding"] == Decimal("65.00")

    def test_payment_validation_rejects_xor_unpayable_and_mismatched_invoice(self, monkeypatch):
        tenant_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        period = create_open_period(tenant_id)
        create_account(tenant_id, "0901", "Receivables", "asset")
        create_account(tenant_id, "1002", "Operating cash", "asset", cash_flow_category="operating")
        revenue = create_account(tenant_id, "4020", "Services", "revenue")
        monkeypatch.setattr(
            "src.modules.accounting_finance.services.extension_registry.resolve_party",
            lambda *args, **kwargs: None,
        )
        invoice = ARInvoiceService.create_invoice(
            tenant_id,
            actor_id="seller",
            payload={
                "invoice_number": "AR-VALIDATION",
                "customer_id": customer_id,
                "invoice_date": period.start_date,
                "due_date": period.end_date,
                "lines": [{"description": "service", "account_id": revenue.id, "unit_price": "10.00"}],
            },
            idempotency_key="ar-create-validation",
        )

        with pytest.raises(AccountingServiceError) as xor_error:
            PaymentService.record_payment(
                tenant_id,
                actor_id="cashier",
                payload={"amount": "1.00", "payment_date": period.start_date},
                idempotency_key="payment-xor",
            )
        assert xor_error.value.domain_code == "PAYMENT_INVOICE_XOR"

        with pytest.raises(AccountingServiceError) as unpayable:
            PaymentService.record_payment(
                tenant_id,
                actor_id="cashier",
                payload={"ar_invoice_id": invoice.id, "amount": "1.00", "payment_date": period.start_date},
                idempotency_key="payment-unpayable",
            )
        assert unpayable.value.domain_code == "INVOICE_NOT_PAYABLE"

        posted = ARInvoiceService.post_to_gl(
            tenant_id,
            invoice.id,
            actor_id="poster",
            transition_key="ar-post-validation",
        )
        with pytest.raises(AccountingServiceError) as mismatch:
            PaymentService.record_payment(
                tenant_id,
                actor_id="cashier",
                payload={
                    "ar_invoice_id": posted.id,
                    "amount": "1.00",
                    "currency": "EUR",
                    "payment_date": period.start_date,
                },
                idempotency_key="payment-mismatch",
            )
        assert mismatch.value.domain_code == "PAYMENT_INVOICE_MISMATCH"


@pytest.mark.django_db
class TestFinancialReportingService:
    def test_statement_reports_and_enqueue_validation_cover_empty_and_unclassified_paths(self):
        tenant_id = uuid.uuid4()
        period = create_open_period(tenant_id)
        cash = create_account(tenant_id, "1300", "Unclassified cash", "asset")
        revenue = create_account(tenant_id, "4300", "Service revenue", "revenue")
        draft = JournalEntryService.create_draft(
            tenant_id,
            actor_id="creator",
            payload=journal_payload(period, cash, revenue, entry_number="JE-REPORTS", amount="50.00"),
            idempotency_key="journal-create-reports",
        )
        JournalEntryService.post_entry(tenant_id, draft.id, actor_id="poster", transition_key="post-reports")

        balance_sheet = FinancialReportingService.balance_sheet(tenant_id, as_of_date=period.end_date)
        income = FinancialReportingService.income_statement(
            tenant_id, start_date=period.start_date, end_date=period.end_date
        )

        assert balance_sheet["assets"] == Decimal("50.00")
        assert balance_sheet["retained_earnings"] == Decimal("50.00")
        assert income["revenue"] == Decimal("50.00")
        assert income["net_income"] == Decimal("50.00")

        with pytest.raises(AccountingServiceError) as cash_flow:
            FinancialReportingService.cash_flow(tenant_id, start_date=period.start_date, end_date=period.end_date)
        assert cash_flow.value.domain_code == "UNCLASSIFIED_CASH_FLOW"

        cash.cash_flow_category = "operating"
        cash.save(update_fields=["cash_flow_category", "updated_at"])
        statement = FinancialReportingService.cash_flow(
            tenant_id, start_date=period.start_date, end_date=period.end_date
        )
        assert statement["sections"]["operating"] == Decimal("50.00")

        job = FinancialReportingService.enqueue_report(
            tenant_id,
            actor_id="analyst",
            report_type="trial_balance",
            parameters={"as_of_date": period.end_date},
            idempotency_key="report-trial-balance",
        )
        assert job.command == "accounting.reports.generate"

        with pytest.raises(AccountingServiceError) as invalid:
            FinancialReportingService.enqueue_report(
                tenant_id,
                actor_id="analyst",
                report_type="unsupported",
                parameters={},
                idempotency_key="report-invalid",
            )
        assert invalid.value.domain_code == "INVALID_REPORT_TYPE"


def test_accounting_value_normalizers_fail_closed_on_invalid_inputs():
    with pytest.raises(AccountingServiceError) as tenant:
        _tenant("not-a-uuid")
    assert tenant.value.domain_code == "INVALID_TENANT"

    with pytest.raises(AccountingServiceError):
        _identifier("not-a-uuid", "account_id")

    with pytest.raises(AccountingServiceError):
        _text("", "actor_id")

    assert _currency("usd") == "USD"
    with pytest.raises(AccountingServiceError):
        _currency("US1")

    assert _money("10.005") == Decimal("10.01")
    with pytest.raises(AccountingServiceError):
        _money("not-money")

    assert _rate("1.234567891") == Decimal("1.23456789")
    with pytest.raises(AccountingServiceError) as rate:
        _rate("0")
    assert rate.value.domain_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_invoice_update_delete_listing_and_payment_reference_guardrails(monkeypatch):
    tenant_id = uuid.uuid4()
    supplier_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    period = create_open_period(tenant_id)
    create_account(tenant_id, "2100", "Payables", "liability")
    create_account(tenant_id, "1100", "Receivables", "asset")
    create_account(tenant_id, "1000", "Cash", "asset", cash_flow_category="operating")
    expense = create_account(tenant_id, "6100", "Expense", "expense")
    revenue = create_account(tenant_id, "4100", "Revenue", "revenue")
    monkeypatch.setattr(
        "src.modules.accounting_finance.services.extension_registry.resolve_party",
        lambda *args, **kwargs: None,
    )

    ap_invoice = APInvoiceService.create_invoice(
        tenant_id,
        actor_id="buyer",
        payload={
            "invoice_number": "AP-GUARD",
            "supplier_id": supplier_id,
            "invoice_date": period.start_date,
            "due_date": period.end_date,
            "lines": [{"description": "service", "account_id": expense.id, "unit_price": "15.00"}],
        },
        idempotency_key="ap-guard",
    )
    updated_ap = APInvoiceService.update_draft(
        tenant_id,
        ap_invoice.id,
        actor_id="buyer",
        version=ap_invoice.version,
        payload={
            "description": "updated",
            "lines": [{"description": "service", "account_id": expense.id, "unit_price": "20.00"}],
        },
    )
    assert updated_ap.description == "updated"
    assert updated_ap.total_amount == Decimal("20.00")
    assert list(APInvoiceService.list_invoices(tenant_id, filters={"supplier_id": supplier_id, "currency": "USD"})) == [
        updated_ap
    ]
    with pytest.raises(AccountingServiceError) as empty_lines:
        APInvoiceService.update_draft(
            tenant_id,
            updated_ap.id,
            actor_id="buyer",
            version=updated_ap.version,
            payload={"lines": []},
        )
    assert empty_lines.value.domain_code == "INVOICE_LINES_REQUIRED"

    ar_invoice = ARInvoiceService.create_invoice(
        tenant_id,
        actor_id="seller",
        payload={
            "invoice_number": "AR-GUARD",
            "customer_id": customer_id,
            "invoice_date": period.start_date,
            "due_date": period.end_date,
            "lines": [{"description": "service", "account_id": revenue.id, "unit_price": "25.00"}],
        },
        idempotency_key="ar-guard",
    )
    posted_ar = ARInvoiceService.post_to_gl(
        tenant_id,
        ar_invoice.id,
        actor_id="poster",
        transition_key="ar-guard-post",
    )
    with pytest.raises(AccountingServiceError) as immutable_delete:
        ARInvoiceService.soft_delete_draft(tenant_id, posted_ar.id, actor_id="seller", reason="wrong")
    assert immutable_delete.value.domain_code == "INVOICE_IMMUTABLE"

    payment = PaymentService.record_payment(
        tenant_id,
        actor_id="cashier",
        payload={
            "ar_invoice_id": posted_ar.id,
            "amount": "5.00",
            "currency": "USD",
            "payment_date": period.start_date,
            "payment_method": "wire_transfer",
        },
        idempotency_key="payment-reference-guard",
    )
    assert list(
        PaymentService.list_payments(tenant_id, filters={"ar_invoice_id": posted_ar.id, "status": "recorded"})
    ) == [payment]
    voided = PaymentService.void_payment(
        tenant_id,
        payment.id,
        actor_id="cashier",
        transition_key="payment-reference-void",
        reason="bank rejected",
    )
    with pytest.raises(AccountingServiceError) as immutable_payment:
        PaymentService.update_reference(
            tenant_id,
            voided.id,
            actor_id="cashier",
            description="cannot update",
            reference_number="VOIDED",
        )
    assert immutable_payment.value.domain_code == "VOIDED_PAYMENT_IMMUTABLE"


@pytest.mark.django_db
def test_period_close_requires_registered_evidence_to_be_satisfied(monkeypatch):
    tenant_id = uuid.uuid4()
    period = create_open_period(tenant_id, name="2024-02", start=date(2024, 2, 1), end=date(2024, 2, 29))

    class BlockingEvidence:
        provider = "close_guard"

        def check(self, tenant_id, *, period_id, start_date, end_date):
            assert period_id == period.id
            assert start_date == period.start_date
            assert end_date == period.end_date
            return PeriodCloseEvidenceV1("1.0", self.provider, False, "", "unreconciled_bank_feed")

    monkeypatch.setattr(
        "src.modules.accounting_finance.services.extension_registry.period_close_evidence",
        lambda: (BlockingEvidence(),),
    )

    with pytest.raises(AccountingServiceError) as exc:
        PostingPeriodService.close_period(
            tenant_id,
            period.id,
            actor_id="controller",
            transition_key="period-close-blocked-evidence",
            reason="month-end",
        )

    assert exc.value.domain_code == "PERIOD_CLOSE_EVIDENCE_BLOCKED"
    period.refresh_from_db()
    assert period.status == "open"


@pytest.mark.django_db
def test_journal_posting_and_reversal_are_idempotent_by_transition_key():
    tenant_id = uuid.uuid4()
    period = create_open_period(tenant_id, name="2024-03", start=date(2024, 3, 1), end=date(2024, 3, 31))
    cash = create_account(tenant_id, "1300", "Cash", "asset", cash_flow_category="operating")
    revenue = create_account(tenant_id, "4300", "Revenue", "revenue")
    draft = JournalEntryService.create_draft(
        tenant_id,
        actor_id="creator",
        payload=journal_payload(period, cash, revenue, entry_number="JE-IDEMPOTENT", amount="77.00"),
        idempotency_key="journal-create-idempotent",
    )

    posted = JournalEntryService.post_entry(
        tenant_id,
        draft.id,
        actor_id="poster",
        transition_key="journal-post-idempotent",
    )
    replay = JournalEntryService.post_entry(
        tenant_id,
        draft.id,
        actor_id="poster",
        transition_key="journal-post-idempotent",
    )
    assert replay.id == posted.id
    assert replay.version == posted.version

    reversal = JournalEntryService.reverse_entry(
        tenant_id,
        posted.id,
        actor_id="reverser",
        transition_key="journal-reverse-idempotent",
        posting_date=period.start_date,
        reason="source correction",
    )
    replayed_reversal = JournalEntryService.reverse_entry(
        tenant_id,
        posted.id,
        actor_id="reverser",
        transition_key="journal-reverse-idempotent",
        posting_date=period.start_date,
        reason="source correction",
    )

    assert replayed_reversal.id == reversal.id
    assert JournalEntry.objects.for_tenant(tenant_id).filter(reversed_entry=posted).count() == 1


@pytest.mark.django_db
def test_post_from_source_rejects_tenant_mismatch_before_writing():
    authority_tenant = uuid.uuid4()
    request_tenant = uuid.uuid4()
    debit_account = uuid.uuid4()
    credit_account = uuid.uuid4()
    request = JournalPostingRequestV1(
        schema_version="1.0",
        tenant_id=request_tenant,
        posting_date=date(2024, 4, 1),
        currency="USD",
        source_module="fixed_assets",
        entry_number="FA-TENANT-MISMATCH",
        source_reference="asset:tenant-mismatch",
        idempotency_key="fixed-asset-tenant-mismatch",
        correlation_id="cmd-fixed-asset-tenant-mismatch",
        actor_id="fixed-assets",
        legs=(
            JournalLegV1(debit_account, "debit", Decimal("10.00"), "USD"),
            JournalLegV1(credit_account, "credit", Decimal("10.00"), "USD"),
        ),
    )

    with pytest.raises(AccountingServiceError) as exc:
        JournalEntryService.post_from_source(authority_tenant, actor_id="fixed-assets", request=request)

    assert exc.value.domain_code == "TENANT_MISMATCH"
    assert not JournalEntry.objects.filter(entry_number="FA-TENANT-MISMATCH").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("file_reference", ["https://example.test/import.csv", "../managed/import.csv"])
def test_batch_import_rejects_external_or_traversal_file_references(file_reference):
    with pytest.raises(AccountingServiceError) as exc:
        JournalEntryService.enqueue_batch_import(
            uuid.uuid4(),
            actor_id="controller",
            file_reference=file_reference,
            idempotency_key=f"batch-import-{file_reference}",
        )

    assert exc.value.domain_code == "INVALID_FILE_REFERENCE"


@pytest.mark.django_db
def test_dimensions_delegate_to_registered_validator_and_reject_non_objects(monkeypatch):
    tenant_id = uuid.uuid4()
    calls = []

    def validate_dimensions(tenant, values):
        calls.append((tenant, values))
        return {"cost_center": values["cost_center"].upper(), "project": values["project"]}

    monkeypatch.setattr(
        "src.modules.accounting_finance.services.extension_registry.validate_dimensions",
        validate_dimensions,
    )

    result = _dimensions(tenant_id, {"cost_center": "ops", "project": 42})

    assert result == {"cost_center": "OPS", "project": "42"}
    assert calls == [(tenant_id, {"cost_center": "ops", "project": "42"})]
    with pytest.raises(AccountingServiceError) as exc:
        _dimensions(tenant_id, ["not", "a", "mapping"])
    assert exc.value.domain_code == "VALIDATION_ERROR"
