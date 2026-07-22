"""Strict, dependency-free query filters for compliance-risk collections.

The project does not require ``django-filter``.  These FilterSet-compatible
objects keep parsing out of ViewSets and reject every unknown parameter rather
than silently changing API semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_date


class FilterValidationError(ValueError):
    """Raised with stable, field-addressable query validation errors."""

    def __init__(self, errors: Mapping[str, str]) -> None:
        self.errors = dict(errors)
        super().__init__("Invalid collection filters")


class StrictFilterSet:
    """Small FilterSet contract with allow-listed parameters and ordering."""

    common_parameters: ClassVar[frozenset[str]] = frozenset({"page", "page_size", "ordering"})
    allowed_parameters: ClassVar[frozenset[str]] = common_parameters
    ordering_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})
    default_ordering: ClassVar[tuple[str, ...]] = ("-created_at",)
    exact_fields: ClassVar[Mapping[str, str]] = {}
    enum_fields: ClassVar[Mapping[str, tuple[str, frozenset[str]]]] = {}
    uuid_fields: ClassVar[Mapping[str, str]] = {}
    date_fields: ClassVar[Mapping[str, str]] = {}
    required_parameters: ClassVar[frozenset[str]] = frozenset()
    max_page_size: ClassVar[int] = 100

    def __init__(self, data: object | None = None, queryset: QuerySet[Any] | None = None) -> None:
        self.data = data or {}
        self.queryset = queryset
        self.errors: dict[str, str] = {}
        self._qs: QuerySet[Any] | None = None

    def _get(self, key: str) -> object | None:
        getter = getattr(self.data, "get", None)
        return getter(key) if callable(getter) else None

    def is_valid(self) -> bool:
        self.errors = {}
        keys = set(getattr(self.data, "keys", lambda: ())())
        unknown = keys - self.allowed_parameters
        if unknown:
            self.errors["query"] = f"Unsupported filters: {', '.join(sorted(unknown))}."
        for parameter in self.required_parameters:
            if self._get(parameter) in (None, ""):
                self.errors[parameter] = "This query parameter is required."
        self._validate_pagination()
        if self.errors:
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

    def _validate_pagination(self) -> None:
        for parameter, maximum in (("page", None), ("page_size", self.max_page_size)):
            raw = self._get(parameter)
            if raw in (None, ""):
                continue
            try:
                value = int(str(raw))
            except (TypeError, ValueError):
                self.errors[parameter] = "Must be a positive integer."
                continue
            if value < 1 or (maximum is not None and value > maximum):
                suffix = f" between 1 and {maximum}." if maximum else "."
                self.errors[parameter] = f"Must be a positive integer{suffix}"

    def apply(self, queryset: QuerySet[Any] | None) -> QuerySet[Any]:
        if queryset is None:
            raise ValueError("FilterSet requires a queryset")
        result = queryset
        errors: dict[str, str] = {}

        for parameter, lookup in self.exact_fields.items():
            value = self._get(parameter)
            if value not in (None, ""):
                result = result.filter(**{lookup: value})

        for parameter, (lookup, choices) in self.enum_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            normalized = str(value)
            if normalized not in choices:
                errors[parameter] = f"Must be one of: {', '.join(sorted(choices))}."
            else:
                result = result.filter(**{lookup: normalized})

        for parameter, lookup in self.uuid_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            try:
                parsed_uuid = UUID(str(value))
            except (TypeError, ValueError, AttributeError):
                errors[parameter] = "Must be a valid UUID."
            else:
                result = result.filter(**{lookup: parsed_uuid})

        parsed_dates: dict[str, object] = {}
        for parameter, lookup in self.date_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            parsed_date = parse_date(str(value))
            if parsed_date is None:
                errors[parameter] = "Must be an ISO 8601 date."
            else:
                parsed_dates[parameter] = parsed_date
                result = result.filter(**{lookup: parsed_date})
        self._validate_date_ranges(parsed_dates, errors)

        search = self._get("search")
        if search not in (None, ""):
            normalized_search = str(search).strip()
            if not normalized_search:
                errors["search"] = "Search must not be blank."
            elif len(normalized_search) > 200:
                errors["search"] = "Search is limited to 200 characters."
            else:
                result = self.apply_search(result, normalized_search)

        raw_ordering = str(self._get("ordering") or ",".join(self.default_ordering))
        ordering = tuple(part.strip() for part in raw_ordering.split(",") if part.strip())
        if not ordering or any(item.lstrip("-") not in self.ordering_fields for item in ordering):
            errors["ordering"] = "Ordering contains a field that is not allowed."
        else:
            result = result.order_by(*ordering)

        if errors:
            raise FilterValidationError(errors)
        return self.apply_extra(result)

    @staticmethod
    def _validate_date_ranges(parsed: Mapping[str, object], errors: dict[str, str]) -> None:
        for start_name, end_name in (
            ("date_from", "date_to"),
            ("review_from", "review_to"),
            ("due_from", "due_to"),
            ("scheduled_from", "scheduled_to"),
        ):
            invalid_order = (
                start_name in parsed
                and end_name in parsed
                and parsed[start_name] > parsed[end_name]  # type: ignore[operator]
            )
            if invalid_order:
                errors[end_name] = f"Must be on or after {start_name}."

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        del search
        return queryset

    def apply_extra(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset


RISK_CATEGORIES = frozenset({"operational", "financial", "compliance", "strategic", "technology", "reputational"})
RISK_LEVELS = frozenset({"negligible", "low", "medium", "high", "critical"})
RISK_STATUSES = frozenset({"identified", "assessed", "mitigating", "accepted", "closed"})


class RiskAssessmentFilterSet(StrictFilterSet):
    allowed_parameters = StrictFilterSet.common_parameters | frozenset(
        {"search", "category", "risk_level", "status", "owner_id", "review_from", "review_to", "likelihood", "impact"}
    )
    enum_fields = {
        "category": ("category", RISK_CATEGORIES),
        "risk_level": ("risk_level", RISK_LEVELS),
        "status": ("status", RISK_STATUSES),
    }
    uuid_fields = {"owner_id": "owner_id"}
    date_fields = {"review_from": "review_date__gte", "review_to": "review_date__lte"}
    ordering_fields = frozenset({"risk_code", "inherent_score", "review_date", "created_at"})
    default_ordering = ("risk_code",)

    def apply_extra(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = queryset
        errors: dict[str, str] = {}
        for field in ("likelihood", "impact"):
            raw = self._get(field)
            if raw in (None, ""):
                continue
            try:
                value = int(str(raw))
            except (TypeError, ValueError):
                errors[field] = "Must be an integer from 1 through 10."
                continue
            if not 1 <= value <= 10:
                errors[field] = "Must be an integer from 1 through 10."
            else:
                result = result.filter(**{field: value})
        if errors:
            raise FilterValidationError(errors)
        return result

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(Q(risk_code__icontains=search) | Q(name__icontains=search))


class ControlFilterSet(StrictFilterSet):
    allowed_parameters = StrictFilterSet.common_parameters | frozenset(
        {"risk_id", "status", "frequency", "owner_id", "due_from", "due_to"}
    )
    uuid_fields = {"risk_id": "risk_id", "owner_id": "owner_id"}
    enum_fields = {
        "status": ("status", frozenset({"draft", "active", "retired"})),
        "frequency": (
            "frequency",
            frozenset({"daily", "weekly", "monthly", "quarterly", "annually", "custom"}),
        ),
    }
    date_fields = {"due_from": "next_test_due__gte", "due_to": "next_test_due__lte"}
    ordering_fields = frozenset({"control_code", "next_test_due", "status", "created_at"})
    default_ordering = ("control_code",)


class ControlTestFilterSet(StrictFilterSet):
    allowed_parameters = StrictFilterSet.common_parameters | frozenset(
        {
            "control_id",
            "risk_id",
            "status",
            "result",
            "tester_id",
            "date_from",
            "date_to",
            "scheduled_from",
            "scheduled_to",
        }
    )
    uuid_fields = {"control_id": "control_id", "risk_id": "control__risk_id", "tester_id": "tester_id"}
    enum_fields = {
        "status": ("status", frozenset({"scheduled", "in_progress", "completed", "cancelled"})),
        "result": ("result", frozenset({"not_tested", "passed", "failed", "partially_passed"})),
    }
    date_fields = {
        "date_from": "scheduled_for__gte",
        "date_to": "scheduled_for__lte",
        "scheduled_from": "scheduled_for__gte",
        "scheduled_to": "scheduled_for__lte",
    }
    ordering_fields = frozenset({"scheduled_for", "completed_at", "created_at"})
    default_ordering = ("-scheduled_for",)


class ComplianceRequirementFilterSet(StrictFilterSet):
    allowed_parameters = StrictFilterSet.common_parameters | frozenset(
        {"search", "regulation_code", "applicability", "status", "owner_id", "due_from", "due_to"}
    )
    exact_fields = {"regulation_code": "regulation_code"}
    enum_fields = {
        "applicability": ("applicability", frozenset({"mandatory", "conditional", "recommended"})),
        "status": (
            "status",
            frozenset({"not_assessed", "compliant", "partially_compliant", "non_compliant"}),
        ),
    }
    uuid_fields = {"owner_id": "owner_id"}
    date_fields = {"due_from": "due_date__gte", "due_to": "due_date__lte"}
    ordering_fields = frozenset({"regulation_code", "requirement_code", "due_date", "created_at"})
    default_ordering = ("regulation_code", "requirement_code")

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(
            Q(regulation_code__icontains=search)
            | Q(requirement_code__icontains=search)
            | Q(regulation_name__icontains=search)
            | Q(title__icontains=search)
        )


class ComplianceCalendarFilterSet(StrictFilterSet):
    allowed_parameters = StrictFilterSet.common_parameters | frozenset(
        {"date_from", "date_to", "event_type", "status", "requirement_id", "assigned_to_id"}
    )
    required_parameters = frozenset({"date_from", "date_to"})
    enum_fields = {
        "event_type": ("event_type", frozenset({"deadline", "review", "submission", "audit", "renewal"})),
        "status": ("status", frozenset({"upcoming", "overdue", "completed", "cancelled"})),
    }
    uuid_fields = {"requirement_id": "requirement_id", "assigned_to_id": "assigned_to_id"}
    date_fields = {"date_from": "scheduled_date__gte", "date_to": "scheduled_date__lte"}
    ordering_fields = frozenset({"scheduled_date", "title", "created_at"})
    default_ordering = ("scheduled_date", "title")


class RemediationActionFilterSet(StrictFilterSet):
    allowed_parameters = StrictFilterSet.common_parameters | frozenset(
        {"risk_id", "control_test_id", "status", "priority", "assigned_to_id", "due_from", "due_to"}
    )
    uuid_fields = {
        "risk_id": "risk_id",
        "control_test_id": "control_test_id",
        "assigned_to_id": "assigned_to_id",
    }
    enum_fields = {
        "status": (
            "status",
            frozenset({"planned", "in_progress", "overdue", "completed", "cancelled"}),
        ),
        "priority": ("priority", frozenset({"low", "medium", "high", "critical"})),
    }
    date_fields = {"due_from": "due_date__gte", "due_to": "due_date__lte"}
    ordering_fields = frozenset({"action_code", "priority", "due_date", "created_at"})
    default_ordering = ("due_date", "action_code")


class DashboardFilterSet(RiskAssessmentFilterSet):
    """Risk filter vocabulary used by the dashboard projection."""


class HeatmapFilterSet(StrictFilterSet):
    allowed_parameters = StrictFilterSet.common_parameters | frozenset({"category", "owner_id", "status"})
    enum_fields = {
        "category": ("category", RISK_CATEGORIES),
        "status": ("status", RISK_STATUSES),
    }
    uuid_fields = {"owner_id": "owner_id"}
    ordering_fields = frozenset({"created_at"})


# Natural aliases used by API code and extension modules.
RiskFilterSet = RiskAssessmentFilterSet
RequirementFilterSet = ComplianceRequirementFilterSet
CalendarEntryFilterSet = ComplianceCalendarFilterSet
RemediationFilterSet = RemediationActionFilterSet


__all__ = [
    "CalendarEntryFilterSet",
    "ComplianceCalendarFilterSet",
    "ComplianceRequirementFilterSet",
    "ControlFilterSet",
    "ControlTestFilterSet",
    "DashboardFilterSet",
    "FilterValidationError",
    "HeatmapFilterSet",
    "RemediationActionFilterSet",
    "RemediationFilterSet",
    "RequirementFilterSet",
    "RiskAssessmentFilterSet",
    "RiskFilterSet",
    "StrictFilterSet",
]
