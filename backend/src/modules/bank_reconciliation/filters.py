"""Strict allowlisted FilterSets for bank-reconciliation collections.

The repository foundation currently has no django-filter dependency.  This
compatible boundary keeps query parsing out of ViewSets while exposing the
usual ``is_valid()``, ``errors`` and ``qs`` interface.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_date


class FilterValidationError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__("Invalid collection filters")


class BaseFilterSet:
    allowed: ClassVar[frozenset[str]] = frozenset({"page", "page_size", "ordering", "search"})
    ordering_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})
    default_ordering: ClassVar[str] = "-created_at"
    uuid_fields: ClassVar[dict[str, str]] = {}
    exact_fields: ClassVar[dict[str, str]] = {}
    boolean_fields: ClassVar[dict[str, str]] = {}
    date_fields: ClassVar[dict[str, str]] = {}

    def __init__(self, data: object | None = None, queryset: QuerySet[Any] | None = None) -> None:
        self.data = data or {}
        self.queryset = queryset
        self.errors: dict[str, str] = {}
        self._qs: QuerySet[Any] | None = None

    def _get(self, key: str) -> object | None:
        getter = getattr(self.data, "get", None)
        return getter(key) if callable(getter) else None

    def is_valid(self) -> bool:
        keys = set(getattr(self.data, "keys", lambda: ())())
        unknown = keys - self.allowed
        if unknown:
            self.errors["query"] = f"Unsupported filters: {', '.join(sorted(unknown))}."
            return False
        try:
            self._qs = self.apply(self.queryset)
        except FilterValidationError as exc:
            self.errors.update(exc.errors)
        return not self.errors

    @property
    def qs(self) -> QuerySet[Any]:
        if self._qs is None and not self.is_valid():
            raise FilterValidationError(self.errors)
        if self._qs is None:
            raise ValueError("FilterSet requires a queryset")
        return self._qs

    def apply(self, queryset: QuerySet[Any] | None) -> QuerySet[Any]:
        if queryset is None:
            raise ValueError("FilterSet requires a queryset")
        result = queryset
        errors: dict[str, str] = {}
        for parameter, lookup in self.uuid_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            try:
                parsed = UUID(str(value))
            except (TypeError, ValueError, AttributeError):
                errors[parameter] = "Must be a valid UUID."
            else:
                result = result.filter(**{lookup: parsed})
        for parameter, lookup in self.exact_fields.items():
            value = self._get(parameter)
            if value not in (None, ""):
                result = result.filter(**{lookup: value})
        for parameter, lookup in self.boolean_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            normalized = str(value).lower()
            if normalized not in {"true", "false", "1", "0"}:
                errors[parameter] = "Must be a boolean."
            else:
                result = result.filter(**{lookup: normalized in {"true", "1"}})
        for parameter, lookup in self.date_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            parsed = parse_date(str(value))
            if parsed is None:
                errors[parameter] = "Must be an ISO date."
            else:
                result = result.filter(**{lookup: parsed})
        search = self._get("search")
        if search not in (None, ""):
            if len(str(search)) > 100:
                errors["search"] = "Search is limited to 100 characters."
            else:
                result = self.apply_search(result, str(search).strip())
        ordering = str(self._get("ordering") or self.default_ordering)
        order_fields = [part.strip() for part in ordering.split(",") if part.strip()]
        if not order_fields or any(part.lstrip("-") not in self.ordering_fields for part in order_fields):
            errors["ordering"] = "Ordering field is not allowed."
        else:
            result = result.order_by(*order_fields)
        if errors:
            raise FilterValidationError(errors)
        return self.apply_extra(result)

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        del search
        return queryset

    def apply_extra(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset


class BankAccountFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"is_active", "account_type", "currency"})
    boolean_fields = {"is_active": "is_active"}
    exact_fields = {"account_type": "account_type", "currency": "currency"}
    ordering_fields = frozenset({"bank_name", "account_name", "created_at"})
    default_ordering = "bank_name,account_name"

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        # Searching the last four digits is safe; raw account numbers are never
        # searched or exposed from ordinary list endpoints.
        digits = "".join(character for character in search if character.isdigit())
        query = Q(bank_name__icontains=search) | Q(account_name__icontains=search)
        if len(digits) == 4:
            query |= Q(account_number_last4=digits)
        return queryset.filter(query)


class BankStatementFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset(
        {"account", "bank_account", "status", "period_start", "period_end", "has_variance"}
    )
    uuid_fields = {"account": "bank_account_id", "bank_account": "bank_account_id"}
    exact_fields = {"status": "status"}
    date_fields = {"period_start": "period_end__gte", "period_end": "period_start__lte"}
    boolean_fields = {"has_variance": "balance_variance__gt"}
    ordering_fields = frozenset({"period_end", "created_at", "balance_variance"})
    default_ordering = "-period_end"

    def apply(self, queryset: QuerySet[Any] | None) -> QuerySet[Any]:
        # has_variance is not a normal boolean lookup.
        value = self._get("has_variance")
        original = self.boolean_fields
        self.boolean_fields = {}
        try:
            result = super().apply(queryset)
        finally:
            self.boolean_fields = original
        if value in (None, ""):
            return result
        normalized = str(value).lower()
        if normalized not in {"true", "false", "1", "0"}:
            raise FilterValidationError({"has_variance": "Must be a boolean."})
        return result.exclude(balance_variance=0) if normalized in {"true", "1"} else result.filter(balance_variance=0)

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(
            Q(statement_reference__icontains=search) | Q(bank_account__account_name__icontains=search)
        )


class BankTransactionFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset(
        {
            "statement",
            "bank_statement",
            "match_status",
            "transaction_type",
            "date_from",
            "date_to",
            "amount_min",
            "amount_max",
        }
    )
    uuid_fields = {"statement": "bank_statement_id", "bank_statement": "bank_statement_id"}
    exact_fields = {"match_status": "match_status", "transaction_type": "transaction_type"}
    date_fields = {"date_from": "transaction_date__gte", "date_to": "transaction_date__lte"}
    ordering_fields = frozenset({"transaction_date", "amount", "created_at", "sequence_number"})
    default_ordering = "-transaction_date,-sequence_number"

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(
            Q(description__icontains=search)
            | Q(reference_number__icontains=search)
            | Q(counterparty_name__icontains=search)
        )

    def apply_extra(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = queryset
        errors: dict[str, str] = {}
        for parameter, lookup in (("amount_min", "amount__gte"), ("amount_max", "amount__lte")):
            value = self._get(parameter)
            if value in (None, ""):
                continue
            try:
                amount = Decimal(str(value))
            except (InvalidOperation, ValueError):
                errors[parameter] = "Must be a finite decimal."
                continue
            if not amount.is_finite():
                errors[parameter] = "Must be a finite decimal."
            else:
                result = result.filter(**{lookup: amount})
        if errors:
            raise FilterValidationError(errors)
        return result


class StatementImportFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset(
        {"account", "bank_account", "file_format", "format", "status", "created_from", "created_to"}
    )
    uuid_fields = {"account": "bank_account_id", "bank_account": "bank_account_id"}
    exact_fields = {"file_format": "file_format", "format": "file_format", "status": "status"}
    date_fields = {"created_from": "created_at__date__gte", "created_to": "created_at__date__lte"}
    ordering_fields = frozenset({"created_at", "status", "rows_received"})

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(Q(source_filename__icontains=search) | Q(idempotency_key__icontains=search))


class MatchingRuleFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"rule_type", "is_active"})
    exact_fields = {"rule_type": "rule_type"}
    boolean_fields = {"is_active": "is_active"}
    ordering_fields = frozenset({"priority", "name", "created_at"})
    default_ordering = "priority,name"

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))


class ReconciliationFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset(
        {
            "account",
            "bank_account",
            "statement",
            "bank_statement",
            "status",
            "date_from",
            "date_to",
            "has_difference",
            "finalized",
        }
    )
    uuid_fields = {
        "account": "bank_account_id",
        "bank_account": "bank_account_id",
        "statement": "bank_statement_id",
        "bank_statement": "bank_statement_id",
    }
    exact_fields = {"status": "status"}
    date_fields = {"date_from": "reconciliation_date__gte", "date_to": "reconciliation_date__lte"}
    ordering_fields = frozenset({"reconciliation_date", "difference", "created_at", "finalized_at"})
    default_ordering = "-reconciliation_date"

    def apply_extra(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = queryset
        for parameter, field, nonzero in (
            ("has_difference", "difference", True),
            ("finalized", "finalized_at", False),
        ):
            value = self._get(parameter)
            if value in (None, ""):
                continue
            normalized = str(value).lower()
            if normalized not in {"true", "false", "1", "0"}:
                raise FilterValidationError({parameter: "Must be a boolean."})
            truth = normalized in {"true", "1"}
            if nonzero:
                result = result.exclude(**{field: 0}) if truth else result.filter(**{field: 0})
            else:
                result = result.filter(**{f"{field}__isnull": not truth})
        return result

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(
            Q(bank_account__account_name__icontains=search) | Q(bank_statement__statement_reference__icontains=search)
        )


__all__ = [
    "BankAccountFilterSet",
    "BankStatementFilterSet",
    "BankTransactionFilterSet",
    "BaseFilterSet",
    "FilterValidationError",
    "MatchingRuleFilterSet",
    "ReconciliationFilterSet",
    "StatementImportFilterSet",
]
