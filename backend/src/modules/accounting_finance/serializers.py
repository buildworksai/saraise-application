"""Explicit read, command, query, and projection serializers for accounting v2."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import APInvoice, APInvoiceLine, ARInvoice, ARInvoiceLine, Account, JournalEntry, JournalLine, Payment, PostingPeriod


class CurrencyField(serializers.CharField):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(min_length=3, max_length=3, **kwargs)

    def to_internal_value(self, data: object) -> str:
        value = super().to_internal_value(data).upper()
        if not value.isalpha():
            raise serializers.ValidationError("Use a three-letter ISO-4217 currency code.")
        return value


class VersionUpdateSerializer(serializers.Serializer[dict[str, object]]):
    version = serializers.IntegerField(min_value=1, write_only=True)


class JournalLineReadSerializer(serializers.ModelSerializer[JournalLine]):
    account_id = serializers.UUIDField(read_only=True)
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = JournalLine
        fields = ("id", "line_number", "account_id", "account_code", "account_name", "debit_amount", "credit_amount", "currency", "exchange_rate", "base_debit_amount", "base_credit_amount", "description", "cost_center", "dimension_values", "created_at", "updated_at")


class JournalLineWriteSerializer(serializers.Serializer[dict[str, object]]):
    account_id = serializers.UUIDField()
    debit_amount = serializers.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), min_value=Decimal("0.00"))
    credit_amount = serializers.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), min_value=Decimal("0.00"))
    currency = CurrencyField(required=False)
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"), min_value=Decimal("0.00000001"))
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    cost_center = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    dimension_values = serializers.DictField(child=serializers.CharField(max_length=255), required=False, default=dict)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        debit, credit = attrs.get("debit_amount", Decimal("0")), attrs.get("credit_amount", Decimal("0"))
        if (debit > 0) == (credit > 0):
            raise serializers.ValidationError("Exactly one of debit_amount or credit_amount must be positive.")
        return attrs


class _InvoiceLineReadSerializer(serializers.ModelSerializer):
    account_id = serializers.UUIDField(read_only=True)
    account_code = serializers.CharField(source="account.code", read_only=True)

    class Meta:
        fields = ("id", "line_number", "description", "account_id", "account_code", "quantity", "unit_price", "tax_amount", "line_total", "cost_center", "dimension_values", "created_at", "updated_at")


class APInvoiceLineReadSerializer(_InvoiceLineReadSerializer):
    class Meta(_InvoiceLineReadSerializer.Meta):
        model = APInvoiceLine


class ARInvoiceLineReadSerializer(_InvoiceLineReadSerializer):
    class Meta(_InvoiceLineReadSerializer.Meta):
        model = ARInvoiceLine


class InvoiceLineWriteSerializer(serializers.Serializer[dict[str, object]]):
    description = serializers.CharField(max_length=500)
    account_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4, default=Decimal("1"), min_value=Decimal("0.0001"))
    unit_price = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.00"))
    tax_amount = serializers.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), min_value=Decimal("0.00"))
    cost_center = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    dimension_values = serializers.DictField(child=serializers.CharField(max_length=255), required=False, default=dict)


class APInvoiceLineWriteSerializer(InvoiceLineWriteSerializer):
    pass


class ARInvoiceLineWriteSerializer(InvoiceLineWriteSerializer):
    pass


ACCOUNT_READ_FIELDS = ("id", "tenant_id", "code", "name", "account_type", "normal_balance", "parent_id", "is_group", "is_active", "currency", "allow_multi_currency", "cash_flow_category", "description", "version", "created_by", "updated_by", "is_deleted", "created_at", "updated_at")


class AccountListSerializer(serializers.ModelSerializer[Account]):
    class Meta:
        model = Account
        fields = ACCOUNT_READ_FIELDS
        read_only_fields = ("id", "tenant_id", "version", "created_by", "updated_by", "is_deleted", "created_at", "updated_at")


class AccountDetailSerializer(AccountListSerializer):
    children_count = serializers.IntegerField(read_only=True, required=False)

    class Meta(AccountListSerializer.Meta):
        fields = ACCOUNT_READ_FIELDS + ("children_count", "deleted_at", "deleted_by")
        read_only_fields = AccountListSerializer.Meta.read_only_fields + ("children_count", "deleted_at", "deleted_by")


class AccountCreateSerializer(serializers.Serializer[dict[str, object]]):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=255)
    account_type = serializers.ChoiceField(choices=("asset", "liability", "equity", "revenue", "expense"))
    normal_balance = serializers.ChoiceField(choices=("debit", "credit"), required=False)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    is_group = serializers.BooleanField(default=False)
    is_active = serializers.BooleanField(default=True)
    currency = CurrencyField(default="USD")
    allow_multi_currency = serializers.BooleanField(default=False)
    cash_flow_category = serializers.ChoiceField(choices=("operating", "investing", "financing"), required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class AccountUpdateSerializer(VersionUpdateSerializer):
    code = serializers.CharField(max_length=50, required=False)
    name = serializers.CharField(max_length=255, required=False)
    account_type = serializers.ChoiceField(choices=("asset", "liability", "equity", "revenue", "expense"), required=False)
    normal_balance = serializers.ChoiceField(choices=("debit", "credit"), required=False)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    is_group = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
    currency = CurrencyField(required=False)
    allow_multi_currency = serializers.BooleanField(required=False)
    cash_flow_category = serializers.ChoiceField(choices=("operating", "investing", "financing"), required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)


PERIOD_READ_FIELDS = ("id", "tenant_id", "period_name", "start_date", "end_date", "fiscal_year", "status", "closed_at", "closed_by", "locked_at", "locked_by", "transition_history", "version", "created_by", "updated_by", "created_at", "updated_at")


class PostingPeriodListSerializer(serializers.ModelSerializer[PostingPeriod]):
    class Meta:
        model = PostingPeriod
        fields = PERIOD_READ_FIELDS
        read_only_fields = ("id", "tenant_id", "status", "closed_at", "closed_by", "locked_at", "locked_by", "transition_history", "version", "created_by", "updated_by", "created_at", "updated_at")
        extra_kwargs = {"fiscal_year": {"required": False}}


class PostingPeriodDetailSerializer(PostingPeriodListSerializer):
    pass


class PostingPeriodCreateSerializer(serializers.Serializer[dict[str, object]]):
    period_name = serializers.CharField(max_length=50)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    fiscal_year = serializers.IntegerField(min_value=1)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError({"end_date": "Must not precede start_date."})
        return attrs


class PostingPeriodUpdateSerializer(VersionUpdateSerializer):
    period_name = serializers.CharField(max_length=50, required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    fiscal_year = serializers.IntegerField(min_value=1, required=False)


JOURNAL_READ_FIELDS = ("id", "tenant_id", "entry_number", "posting_date", "posting_period_id", "reference", "description", "status", "currency", "debit_total", "credit_total", "posted_at", "posted_by", "reversed_at", "reversed_by", "reversed_entry_id", "source_module", "source_reference", "source_idempotency_key", "transition_history", "version", "created_by", "updated_by", "is_deleted", "created_at", "updated_at")


class JournalEntryListSerializer(serializers.ModelSerializer[JournalEntry]):
    class Meta:
        model = JournalEntry
        fields = JOURNAL_READ_FIELDS
        read_only_fields = ("id", "tenant_id", "status", "debit_total", "credit_total", "posted_at", "posted_by", "reversed_at", "reversed_by", "reversed_entry_id", "transition_history", "version", "created_by", "updated_by", "is_deleted", "created_at", "updated_at")


class JournalEntryDetailSerializer(JournalEntryListSerializer):
    lines = JournalLineReadSerializer(many=True, read_only=True)

    class Meta(JournalEntryListSerializer.Meta):
        fields = JOURNAL_READ_FIELDS + ("lines",)


class JournalEntryCreateSerializer(serializers.Serializer[dict[str, object]]):
    entry_number = serializers.CharField(max_length=50)
    posting_date = serializers.DateField()
    posting_period_id = serializers.UUIDField()
    reference = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    currency = CurrencyField(default="USD")
    source_module = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    source_reference = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    lines = JournalLineWriteSerializer(many=True, allow_empty=False, min_length=2)


class JournalEntryUpdateSerializer(VersionUpdateSerializer):
    posting_date = serializers.DateField(required=False)
    posting_period_id = serializers.UUIDField(required=False)
    reference = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    currency = CurrencyField(required=False)
    lines = JournalLineWriteSerializer(many=True, required=False, allow_empty=False, min_length=2)


INVOICE_READ_FIELDS = ("id", "tenant_id", "invoice_number", "invoice_date", "due_date", "amount", "tax_amount", "total_amount", "paid_amount", "currency", "exchange_rate", "status", "description", "posted_at", "posted_by", "cancelled_at", "cancelled_by", "journal_entry_id", "legacy_without_lines", "transition_history", "version", "created_by", "updated_by", "is_deleted", "created_at", "updated_at")


class APInvoiceListSerializer(serializers.ModelSerializer[APInvoice]):
    class Meta:
        model = APInvoice
        fields = INVOICE_READ_FIELDS + ("supplier_id", "approved_at", "approved_by")
        read_only_fields = ("id", "tenant_id", "amount", "tax_amount", "total_amount", "paid_amount", "status", "posted_at", "posted_by", "cancelled_at", "cancelled_by", "journal_entry_id", "legacy_without_lines", "transition_history", "version", "created_by", "updated_by", "is_deleted", "created_at", "updated_at", "approved_at", "approved_by")


class APInvoiceDetailSerializer(APInvoiceListSerializer):
    lines = APInvoiceLineReadSerializer(many=True, read_only=True)
    payments = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta(APInvoiceListSerializer.Meta):
        fields = APInvoiceListSerializer.Meta.fields + ("lines", "payments")


class ARInvoiceListSerializer(serializers.ModelSerializer[ARInvoice]):
    class Meta:
        model = ARInvoice
        fields = INVOICE_READ_FIELDS + ("customer_id",)
        read_only_fields = ("id", "tenant_id", "amount", "tax_amount", "total_amount", "paid_amount", "status", "posted_at", "posted_by", "cancelled_at", "cancelled_by", "journal_entry_id", "legacy_without_lines", "transition_history", "version", "created_by", "updated_by", "is_deleted", "created_at", "updated_at")


class ARInvoiceDetailSerializer(ARInvoiceListSerializer):
    lines = ARInvoiceLineReadSerializer(many=True, read_only=True)
    payments = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta(ARInvoiceListSerializer.Meta):
        fields = ARInvoiceListSerializer.Meta.fields + ("lines", "payments")


class _InvoiceCreateSerializer(serializers.Serializer[dict[str, object]]):
    invoice_number = serializers.CharField(max_length=100)
    invoice_date = serializers.DateField()
    due_date = serializers.DateField()
    currency = CurrencyField(default="USD")
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"), min_value=Decimal("0.00000001"))
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["invoice_date"] > attrs["due_date"]:
            raise serializers.ValidationError({"due_date": "Must not precede invoice_date."})
        return attrs


class APInvoiceCreateSerializer(_InvoiceCreateSerializer):
    supplier_id = serializers.UUIDField()
    lines = APInvoiceLineWriteSerializer(many=True, allow_empty=False)


class ARInvoiceCreateSerializer(_InvoiceCreateSerializer):
    customer_id = serializers.UUIDField()
    lines = ARInvoiceLineWriteSerializer(many=True, allow_empty=False)


class _InvoiceUpdateSerializer(VersionUpdateSerializer):
    invoice_number = serializers.CharField(max_length=100, required=False)
    invoice_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False)
    currency = CurrencyField(required=False)
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=8, min_value=Decimal("0.00000001"), required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class APInvoiceUpdateSerializer(_InvoiceUpdateSerializer):
    supplier_id = serializers.UUIDField(required=False)
    lines = APInvoiceLineWriteSerializer(many=True, required=False, allow_empty=False)


class ARInvoiceUpdateSerializer(_InvoiceUpdateSerializer):
    customer_id = serializers.UUIDField(required=False)
    lines = ARInvoiceLineWriteSerializer(many=True, required=False, allow_empty=False)


PAYMENT_READ_FIELDS = ("id", "tenant_id", "payment_date", "amount", "payment_method", "currency", "reference_number", "ap_invoice_id", "ar_invoice_id", "description", "status", "voided_at", "voided_by", "void_reason", "transition_history", "idempotency_key", "created_by", "created_at", "updated_at")


class PaymentListSerializer(serializers.ModelSerializer[Payment]):
    class Meta:
        model = Payment
        fields = PAYMENT_READ_FIELDS
        read_only_fields = ("id", "tenant_id", "status", "voided_at", "voided_by", "void_reason", "transition_history", "idempotency_key", "created_by", "created_at", "updated_at")


class PaymentDetailSerializer(PaymentListSerializer):
    pass


class PaymentCreateSerializer(serializers.Serializer[dict[str, object]]):
    payment_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    payment_method = serializers.ChoiceField(choices=("cash", "check", "wire_transfer", "ach", "credit_card", "other"))
    currency = CurrencyField(default="USD")
    reference_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    ap_invoice_id = serializers.UUIDField(required=False, allow_null=True)
    ar_invoice_id = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if bool(attrs.get("ap_invoice_id")) == bool(attrs.get("ar_invoice_id")):
            raise serializers.ValidationError("Exactly one AP or AR invoice is required.")
        return attrs


class PaymentUpdateSerializer(serializers.Serializer[dict[str, object]]):
    reference_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")


class TransitionRequestSerializer(serializers.Serializer[dict[str, object]]):
    transition_key = serializers.CharField(max_length=255)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    version = serializers.IntegerField(min_value=1, required=False)
    comments = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class ReversalRequestSerializer(TransitionRequestSerializer):
    posting_date = serializers.DateField()
    reason = serializers.CharField(max_length=1000)


class BatchImportRequestSerializer(serializers.Serializer[dict[str, object]]):
    file_reference = serializers.CharField(max_length=512)


class AgingQuerySerializer(serializers.Serializer[dict[str, object]]):
    as_of_date = serializers.DateField()


class AsOfDateQuerySerializer(AgingQuerySerializer):
    pass


class DateRangeQuerySerializer(serializers.Serializer[dict[str, object]]):
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError({"end_date": "Must not precede start_date."})
        return attrs


class GeneralLedgerQuerySerializer(DateRangeQuerySerializer):
    account_id = serializers.UUIDField()


class ReportGenerateSerializer(serializers.Serializer[dict[str, object]]):
    report_type = serializers.ChoiceField(choices=("trial_balance", "general_ledger", "balance_sheet", "income_statement", "cash_flow"))
    parameters = serializers.DictField(default=dict)


class FinancialReportResponseSerializer(serializers.Serializer[dict[str, object]]):
    currency = serializers.CharField()
    generated_at = serializers.DateTimeField()
    correlation_id = serializers.CharField()


class AgingResponseSerializer(FinancialReportResponseSerializer):
    as_of_date = serializers.DateField()
    buckets = serializers.DictField()
    items = serializers.ListField()


class AccountingJobSerializer(serializers.ModelSerializer[AsyncJob]):
    class Meta:
        model = AsyncJob
        fields = ("id", "command", "status", "attempts", "correlation_id", "result", "error_message", "created_at", "updated_at", "started_at", "completed_at")


class AccountingHealthSerializer(serializers.Serializer[dict[str, object]]):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unhealthy"))
    module_version = serializers.CharField()
    checks = serializers.DictField()
    latency_ms = serializers.FloatField()


# Deprecated class aliases preserve imports while v1 delegates to v2 services.
AccountSerializer = AccountDetailSerializer
PostingPeriodSerializer = PostingPeriodDetailSerializer
JournalEntrySerializer = JournalEntryDetailSerializer
APInvoiceSerializer = APInvoiceDetailSerializer
ARInvoiceSerializer = ARInvoiceDetailSerializer
PaymentSerializer = PaymentDetailSerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
