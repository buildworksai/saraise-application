"""Operation-specific serializers for the governed bank-reconciliation API."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import (
    BankAccount,
    BankStatement,
    BankStatementImport,
    BankTransaction,
    MatchingRule,
    ReconciliationMatch,
    ReconciliationMatchLine,
    ReconciliationSession,
)


class ServerOwnedFieldGuard:
    """Reject ownership and lifecycle fields instead of silently ignoring them."""

    server_owned_fields = frozenset(
        {
            "id",
            "tenant_id",
            "created_at",
            "updated_at",
            "created_by_id",
            "requested_by_id",
            "started_by_id",
            "reviewed_by_id",
            "finalized_by_id",
            "account_number_hash",
            "account_number_last4",
            "status",
            "is_reconciled",
            "transaction_type",
            "match_status",
            "matched_payment_id",
            "transaction_total",
            "calculated_closing_balance",
            "balance_variance",
            "transition_history",
            "async_job_id",
            "rows_received",
            "rows_imported",
            "rows_rejected",
            "error_code",
            "error_detail",
            "started_at",
            "completed_at",
            "reconciled_at",
            "matched_at",
            "matched_by_id",
            "reversed_at",
            "reversed_by_id",
            "archived_at",
            "finalized_at",
            "reviewed_at",
        }
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        supplied = set(getattr(self, "initial_data", {})) & self.server_owned_fields
        if supplied:
            raise serializers.ValidationError({name: "This field is server-owned." for name in sorted(supplied)})
        return super().validate(attrs)  # type: ignore[misc]


class BankAccountListSerializer(serializers.ModelSerializer):
    masked_account_number = serializers.CharField(read_only=True)
    statement_count = serializers.IntegerField(read_only=True, required=False)
    reconciliation_count = serializers.IntegerField(read_only=True, required=False)
    unreconciled_count = serializers.IntegerField(read_only=True, required=False)
    active_session_count = serializers.IntegerField(read_only=True, required=False)
    last_statement_date = serializers.DateField(read_only=True, required=False, allow_null=True)

    class Meta:
        model = BankAccount
        fields = (
            "id",
            "masked_account_number",
            "account_number_last4",
            "bank_name",
            "account_name",
            "account_type",
            "currency",
            "bank_identifier",
            "ledger_account_id",
            "opening_balance",
            "opening_balance_date",
            "is_active",
            "archived_at",
            "statement_count",
            "reconciliation_count",
            "unreconciled_count",
            "active_session_count",
            "last_statement_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class BankAccountDetailSerializer(BankAccountListSerializer):
    pass


class BankAccountCreateSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    account_number = serializers.CharField(max_length=100, trim_whitespace=True, write_only=True)
    bank_name = serializers.CharField(max_length=255, trim_whitespace=True)
    account_name = serializers.CharField(max_length=255, trim_whitespace=True)
    account_type = serializers.ChoiceField(
        choices=BankAccount.AccountType.choices, default=BankAccount.AccountType.CHECKING
    )
    currency = serializers.RegexField(r"^[A-Za-z]{3}$", default="USD")
    bank_identifier = serializers.CharField(max_length=34, required=False, allow_blank=True)
    ledger_account_id = serializers.UUIDField(required=False, allow_null=True)
    opening_balance = serializers.DecimalField(max_digits=19, decimal_places=4, default="0.0000")
    opening_balance_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        attrs["currency"] = attrs["currency"].upper()
        if attrs["opening_balance"] and not attrs.get("opening_balance_date"):
            raise serializers.ValidationError({"opening_balance_date": "Required for a non-zero opening balance."})
        return attrs


class BankAccountUpdateSerializer(BankAccountCreateSerializer):
    account_number = serializers.CharField(max_length=100, trim_whitespace=True, required=False, write_only=True)
    bank_name = serializers.CharField(max_length=255, required=False)
    account_name = serializers.CharField(max_length=255, required=False)
    account_type = serializers.ChoiceField(choices=BankAccount.AccountType.choices, required=False)
    currency = serializers.RegexField(r"^[A-Za-z]{3}$", required=False)
    opening_balance = serializers.DecimalField(max_digits=19, decimal_places=4, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = ServerOwnedFieldGuard.validate(self, attrs)
        if "currency" in attrs:
            attrs["currency"] = attrs["currency"].upper()
        return attrs


class StatementListSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source="bank_account.account_name", read_only=True)
    account_number_masked = serializers.CharField(source="bank_account.masked_account_number", read_only=True)

    class Meta:
        model = BankStatement
        fields = (
            "id",
            "bank_account",
            "bank_account_name",
            "account_number_masked",
            "statement_reference",
            "period_start",
            "period_end",
            "statement_date",
            "opening_balance",
            "closing_balance",
            "transaction_total",
            "calculated_closing_balance",
            "balance_variance",
            "status",
            "is_reconciled",
            "reconciled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class StatementImportSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatementImport
        fields = (
            "id",
            "file_format",
            "source_filename",
            "status",
            "rows_received",
            "rows_imported",
            "rows_rejected",
            "error_code",
            "created_at",
            "completed_at",
        )
        read_only_fields = fields


class StatementDetailSerializer(StatementListSerializer):
    statement_import = StatementImportSummarySerializer(read_only=True)
    transaction_count = serializers.IntegerField(read_only=True, required=False)

    class Meta(StatementListSerializer.Meta):
        fields = StatementListSerializer.Meta.fields + ("statement_import", "transaction_count")


class ManualTransactionRowSerializer(serializers.Serializer):
    transaction_date = serializers.DateField()
    value_date = serializers.DateField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500)
    amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    reference_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    counterparty_name = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_amount(self, value: Any) -> Any:
        if value == 0:
            raise serializers.ValidationError("Amount must be non-zero.")
        return value


class ManualStatementCreateSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    bank_account = serializers.UUIDField(required=False)
    bank_account_id = serializers.UUIDField(required=False, write_only=True)
    statement_reference = serializers.CharField(max_length=100, required=False, allow_blank=False)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    opening_balance = serializers.DecimalField(max_digits=19, decimal_places=4)
    closing_balance = serializers.DecimalField(max_digits=19, decimal_places=4)
    transactions = ManualTransactionRowSerializer(many=True, required=False, default=list)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        bank_account = attrs.pop("bank_account_id", None) or attrs.get("bank_account")
        if bank_account is None:
            raise serializers.ValidationError({"bank_account": "This field is required."})
        attrs["bank_account"] = bank_account
        if attrs["period_start"] > attrs["period_end"]:
            raise serializers.ValidationError({"period_end": "Must be on or after period start."})
        return attrs


class StatementVoidSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=False)
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, write_only=True)


class TransactionListSerializer(serializers.ModelSerializer):
    statement_reference = serializers.CharField(source="bank_statement.statement_reference", read_only=True)
    source = serializers.SerializerMethodField()

    def get_source(self, obj: BankTransaction) -> str:
        statement_import = obj.bank_statement.statement_import
        if statement_import is None:
            return BankStatementImport.Source.MANUAL
        return statement_import.source

    class Meta:
        model = BankTransaction
        fields = (
            "id",
            "bank_statement",
            "statement_reference",
            "sequence_number",
            "transaction_date",
            "value_date",
            "description",
            "amount",
            "transaction_type",
            "running_balance",
            "reference_number",
            "counterparty_name",
            "counterparty_account_masked",
            "match_status",
            "is_reconciled",
            "source",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MatchLineReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationMatchLine
        fields = (
            "id",
            "side",
            "bank_transaction",
            "ledger_entry_id",
            "ledger_entry_type",
            "allocated_amount",
            "currency",
            "created_at",
        )
        read_only_fields = fields


class ReconciliationMatchCompactSerializer(serializers.ModelSerializer):
    lines = MatchLineReadSerializer(many=True, read_only=True)

    class Meta:
        model = ReconciliationMatch
        fields = (
            "id",
            "reconciliation",
            "match_type",
            "status",
            "score",
            "rule",
            "explanation",
            "matched_at",
            "matched_by_id",
            "reversed_at",
            "reversed_by_id",
            "reversal_reason",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TransactionDetailSerializer(TransactionListSerializer):
    source_data = serializers.JSONField(read_only=True)
    match_history = serializers.SerializerMethodField()

    def get_match_history(self, obj: BankTransaction) -> list[dict[str, Any]]:
        return ReconciliationMatchCompactSerializer(
            [line.match for line in obj.match_lines.select_related("match").all()], many=True
        ).data

    class Meta(TransactionListSerializer.Meta):
        fields = TransactionListSerializer.Meta.fields + (
            "external_id",
            "source_data",
            "matched_payment_id",
            "match_history",
        )


class ManualTransactionCreateSerializer(ServerOwnedFieldGuard, ManualTransactionRowSerializer):
    pass


class ManualTransactionUpdateSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    transaction_date = serializers.DateField(required=False)
    value_date = serializers.DateField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500, required=False)
    amount = serializers.DecimalField(max_digits=19, decimal_places=4, required=False)
    reference_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    counterparty_name = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_amount(self, value: Any) -> Any:
        if value == 0:
            raise serializers.ValidationError("Amount must be non-zero.")
        return value


class TransactionExclusionSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=False)


class StatementImportListSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source="bank_account.account_name", read_only=True)

    class Meta:
        model = BankStatementImport
        fields = (
            "id",
            "bank_account",
            "bank_account_name",
            "source",
            "file_format",
            "source_filename",
            "status",
            "async_job_id",
            "rows_received",
            "rows_imported",
            "rows_rejected",
            "error_code",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AsyncJobSummarySerializer(serializers.ModelSerializer):
    task_name = serializers.CharField(source="command", read_only=True)

    class Meta:
        model = AsyncJob
        fields = (
            "id",
            "task_name",
            "status",
            "attempts",
            "correlation_id",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        )
        read_only_fields = fields


class StatementImportDetailSerializer(StatementImportListSerializer):
    error_detail = serializers.JSONField(read_only=True)
    async_job = serializers.SerializerMethodField()
    statement_id = serializers.SerializerMethodField()
    correlation_id = serializers.SerializerMethodField()

    def _job(self, obj: BankStatementImport) -> AsyncJob | None:
        if not obj.async_job_id:
            return None
        return AsyncJob.objects.for_tenant(obj.tenant_id).filter(pk=obj.async_job_id).first()

    def get_async_job(self, obj: BankStatementImport) -> dict[str, Any] | None:
        job = self._job(obj)
        return AsyncJobSummarySerializer(job).data if job else None

    def get_statement_id(self, obj: BankStatementImport) -> str | None:
        try:
            return str(obj.statement.id)
        except BankStatement.DoesNotExist:
            return None

    def get_correlation_id(self, obj: BankStatementImport) -> str | None:
        job = self._job(obj)
        return job.correlation_id if job else None

    class Meta(StatementImportListSerializer.Meta):
        fields = StatementImportListSerializer.Meta.fields + (
            "source_document_id",
            "content_sha256",
            "mapping",
            "idempotency_key",
            "error_detail",
            "async_job",
            "statement_id",
            "correlation_id",
        )


class StatementImportCreateSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    bank_account = serializers.UUIDField()
    file_format = serializers.ChoiceField(
        choices=[choice for choice in BankStatementImport.FileFormat.values if choice != "manual"]
    )
    file = serializers.FileField(write_only=True)
    mapping = serializers.JSONField(required=False, default=dict)
    source_document_id = serializers.UUIDField(required=False)
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, write_only=True)

    def validate_file(self, value: Any) -> Any:
        if value.size <= 0:
            raise serializers.ValidationError("The file is empty.")
        if value.size > 20 * 1024 * 1024:
            raise serializers.ValidationError("The file exceeds the 20 MiB limit.")
        return value


class ImportRetrySerializer(ServerOwnedFieldGuard, serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, write_only=True)


class ImportCancelSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, default="Cancelled by operator")


class MatchingRuleListSerializer(serializers.ModelSerializer):
    usage_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = MatchingRule
        fields = (
            "id",
            "name",
            "description",
            "rule_type",
            "priority",
            "auto_confirm",
            "minimum_score",
            "extension_key",
            "is_active",
            "usage_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MatchingRuleDetailSerializer(MatchingRuleListSerializer):
    configuration = serializers.JSONField(read_only=True)

    class Meta(MatchingRuleListSerializer.Meta):
        fields = MatchingRuleListSerializer.Meta.fields + ("configuration",)


class MatchingRuleCreateSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True)
    rule_type = serializers.ChoiceField(choices=MatchingRule.RuleType.choices)
    priority = serializers.IntegerField(min_value=1, max_value=32767)
    configuration = serializers.JSONField(default=dict)
    auto_confirm = serializers.BooleanField(default=False)
    minimum_score = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1)
    extension_key = serializers.CharField(max_length=100, required=False, allow_blank=True)


class MatchingRuleUpdateSerializer(MatchingRuleCreateSerializer):
    name = serializers.CharField(max_length=120, required=False)
    rule_type = serializers.ChoiceField(choices=MatchingRule.RuleType.choices, required=False)
    priority = serializers.IntegerField(min_value=1, max_value=32767, required=False)
    configuration = serializers.JSONField(required=False)
    auto_confirm = serializers.BooleanField(required=False)
    minimum_score = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1, required=False)


class ReconciliationListSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="bank_account.account_name", read_only=True)
    statement_reference = serializers.CharField(source="bank_statement.statement_reference", read_only=True)
    match_count = serializers.IntegerField(read_only=True, required=False, default=0)

    class Meta:
        model = ReconciliationSession
        fields = (
            "id",
            "bank_account",
            "account_name",
            "bank_statement",
            "statement_reference",
            "reconciliation_date",
            "status",
            "statement_balance",
            "ledger_balance",
            "matched_amount",
            "unmatched_amount",
            "difference",
            "tolerance",
            "reviewed_by_id",
            "finalized_by_id",
            "reviewed_at",
            "finalized_at",
            "match_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ReconciliationDetailSerializer(ReconciliationListSerializer):
    transition_history = serializers.SerializerMethodField()
    matches = ReconciliationMatchCompactSerializer(many=True, read_only=True)
    statement = StatementDetailSerializer(source="bank_statement", read_only=True)

    def get_transition_history(self, obj: ReconciliationSession) -> list[dict[str, Any]]:
        """Expose stable public evidence without leaking the internal history shape."""

        return [
            {
                "command": item.get("command", ""),
                "from": item.get("from_state", ""),
                "to": item.get("to_state", ""),
                "actor_id": item.get("actor_id") or item.get("metadata", {}).get("actor_id"),
                "occurred_at": item.get("occurred_at"),
                "reason": item.get("reason") or item.get("metadata", {}).get("reason"),
            }
            for item in obj.transition_history
        ]

    class Meta(ReconciliationListSerializer.Meta):
        fields = ReconciliationListSerializer.Meta.fields + ("notes", "transition_history", "matches", "statement")


class ReconciliationCreateSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    bank_account = serializers.UUIDField(required=False)
    bank_statement = serializers.UUIDField()
    reconciliation_date = serializers.DateField()
    ledger_balance = serializers.DecimalField(max_digits=19, decimal_places=4)
    tolerance = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=0, default="0.0000")
    notes = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, write_only=True)


class IdempotentTransitionSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, write_only=True)


class ReasonedTransitionSerializer(IdempotentTransitionSerializer):
    reason = serializers.CharField(max_length=500, allow_blank=False)


class ReconciliationStartSerializer(IdempotentTransitionSerializer):
    pass


class ReconciliationSubmitReviewSerializer(IdempotentTransitionSerializer):
    pass


class ReconciliationFinalizeSerializer(IdempotentTransitionSerializer):
    pass


class ReconciliationReturnToWorkSerializer(ReasonedTransitionSerializer):
    pass


class ReconciliationVoidSerializer(ReasonedTransitionSerializer):
    pass


class CandidateGenerationSerializer(IdempotentTransitionSerializer):
    pass


class ReconciliationSummarySerializer(serializers.Serializer):
    reconciliation_id = serializers.UUIDField()
    statement_balance = serializers.DecimalField(max_digits=19, decimal_places=4)
    ledger_balance = serializers.DecimalField(max_digits=19, decimal_places=4)
    matched_amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    unmatched_amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    difference = serializers.DecimalField(max_digits=19, decimal_places=4)
    tolerance = serializers.DecimalField(max_digits=19, decimal_places=4)
    can_submit_review = serializers.BooleanField()
    can_finalize = serializers.BooleanField()
    blockers = serializers.ListField(child=serializers.CharField())


class MatchLineCreateSerializer(serializers.Serializer):
    side = serializers.ChoiceField(choices=ReconciliationMatchLine.Side.choices)
    bank_transaction_id = serializers.UUIDField(required=False)
    ledger_entry_id = serializers.UUIDField(required=False)
    ledger_entry_type = serializers.ChoiceField(choices=ReconciliationMatchLine.LedgerEntryType.choices, required=False)
    allocated_amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    currency = serializers.RegexField(r"^[A-Za-z]{3}$", required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs["allocated_amount"] == 0:
            raise serializers.ValidationError({"allocated_amount": "Must be non-zero."})
        if attrs["side"] == "bank" and not attrs.get("bank_transaction_id"):
            raise serializers.ValidationError({"bank_transaction_id": "Required for bank lines."})
        if attrs["side"] == "ledger" and (not attrs.get("ledger_entry_id") or not attrs.get("ledger_entry_type")):
            raise serializers.ValidationError({"ledger_entry_id": "Ledger identity and type are required."})
        return attrs


class ManualMatchCreateSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    match_type = serializers.ChoiceField(choices=["manual", "one_to_many", "many_to_one", "adjustment"], required=False)
    lines = MatchLineCreateSerializer(many=True, min_length=2)


class ReconciliationMatchDetailSerializer(ReconciliationMatchCompactSerializer):
    pass


class MatchConfirmSerializer(IdempotentTransitionSerializer):
    pass


class MatchRejectSerializer(ServerOwnedFieldGuard, serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=False)


class MatchReverseSerializer(ReasonedTransitionSerializer):
    pass


# Backward import aliases intentionally retain masking; v1 raw identifiers are gone.
BankAccountSerializer = BankAccountDetailSerializer
BankStatementSerializer = StatementDetailSerializer
BankTransactionSerializer = TransactionDetailSerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
