"""Transactional domain authority for budget management.

Every public method accepts a canonical tenant UUID first, locks mutable
aggregates, derives monetary fields with :class:`~decimal.Decimal`, and emits a
sanitized transactional outbox event.  HTTP adapters are deliberately thin.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence
from uuid import UUID

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.state_machine import IdempotencyConflictError, IllegalTransitionError

from .integrations import get_integrations, require_accounting, require_workflow
from .models import (
    Budget,
    BudgetApproval,
    BudgetApprovalDecision,
    BudgetCommitment,
    BudgetLine,
    BudgetTransition,
    VarianceAlert,
)
from .state_machines import BUDGET_STATE_MACHINE

MONEY = Decimal("0.01")
PERCENT = Decimal("0.01")
EDITABLE_STATUSES = frozenset({"draft", "revision"})
PLANNING_FIELDS = frozenset(
    {
        "budget_code",
        "budget_name",
        "fiscal_year",
        "start_date",
        "end_date",
        "budget_type",
        "department_id",
        "project_id",
        "currency",
        "budget_ceiling",
    }
)
ISO_4217 = frozenset(
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWL".split()
)


class BudgetDomainError(RuntimeError):
    """Stable service error suitable for translation by the governed API."""

    def __init__(self, code: str, message: str, *, http_status: int = 400, detail: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail


@dataclass(frozen=True, slots=True)
class BudgetAvailabilityResult:
    allocated: Decimal
    committed: Decimal
    actual: Decimal
    available: Decimal
    deficit: Decimal
    sufficient: bool
    unbudgeted: bool


@dataclass(frozen=True, slots=True)
class VarianceLineResult:
    budget_line_id: UUID
    account_code: str
    account_name: str
    period_type: str
    period_number: int
    budgeted: Decimal
    committed: Decimal
    actual: Decimal
    variance: Decimal
    variance_percentage: Decimal | None
    favorable: bool
    over_budget: bool
    threshold_exceeded: bool


@dataclass(frozen=True, slots=True)
class VarianceReport:
    budget_id: UUID
    currency: str
    budgeted: Decimal
    committed: Decimal
    actual: Decimal
    variance: Decimal
    variance_percentage: Decimal | None
    favorable: bool
    threshold_percentage: Decimal
    lines: tuple[VarianceLineResult, ...]


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BudgetDomainError("INVALID_UUID", f"{field} must be a valid UUID") from exc


def _date(value: date | str, field: str) -> date:
    if isinstance(value, datetime):
        raise BudgetDomainError("INVALID_DATE", f"{field} must be a date")
    parsed = value if isinstance(value, date) else parse_date(str(value))
    if parsed is None:
        raise BudgetDomainError("INVALID_DATE", f"{field} must be an ISO date")
    return parsed


def _datetime(value: datetime | str, field: str) -> datetime:
    parsed = value if isinstance(value, datetime) else parse_datetime(str(value))
    if parsed is None or timezone.is_naive(parsed):
        raise BudgetDomainError("INVALID_TIMESTAMP", f"{field} must be a timezone-aware ISO timestamp")
    return parsed


def _decimal(value: Decimal | str | int, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, (float, bool)):
        raise BudgetDomainError("INVALID_DECIMAL", f"{field} must be a decimal string")
    try:
        unquantized = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BudgetDomainError("INVALID_DECIMAL", f"{field} must be a valid decimal") from exc
    if not unquantized.is_finite() or unquantized.as_tuple().exponent < -2:
        raise BudgetDomainError("INVALID_DECIMAL", f"{field} must have at most two fractional digits")
    result = unquantized.quantize(MONEY)
    if result < 0 or (positive and result <= 0):
        qualifier = "positive" if positive else "nonnegative"
        raise BudgetDomainError("INVALID_AMOUNT", f"{field} must be {qualifier}")
    return result


def _percent(value: Decimal | str | int, field: str = "threshold_percentage") -> Decimal:
    result = _decimal(value, field)
    if result > Decimal("10000.00"):
        raise BudgetDomainError("INVALID_PERCENTAGE", f"{field} is outside the supported range")
    return result


def _clean_text(value: Any, field: str, *, upper: bool = False, max_length: int | None = None) -> str:
    if not isinstance(value, str):
        raise BudgetDomainError("INVALID_TEXT", f"{field} must be text")
    cleaned = value.strip()
    if not cleaned:
        raise BudgetDomainError("REQUIRED", f"{field} is required")
    if max_length is not None and len(cleaned) > max_length:
        raise BudgetDomainError("MAX_LENGTH", f"{field} exceeds {max_length} characters")
    return cleaned.upper() if upper else cleaned


def _active(queryset: models.QuerySet[Any]) -> models.QuerySet[Any]:
    return queryset.filter(is_deleted=False)


def _budget_for_update(tenant_id: UUID, budget_id: UUID | str) -> Budget:
    try:
        return Budget.objects.select_for_update().get(id=_uuid(budget_id, "budget_id"), tenant_id=tenant_id, is_deleted=False)
    except Budget.DoesNotExist as exc:
        raise BudgetDomainError("NOT_FOUND", "Budget not found", http_status=404) from exc


def _line_for_update(tenant_id: UUID, line_id: UUID | str) -> BudgetLine:
    try:
        return BudgetLine.objects.select_for_update().select_related("budget").get(
            id=_uuid(line_id, "line_id"), tenant_id=tenant_id, is_deleted=False
        )
    except BudgetLine.DoesNotExist as exc:
        raise BudgetDomainError("NOT_FOUND", "Budget line not found", http_status=404) from exc


def _assert_editable(budget: Budget) -> None:
    if budget.status not in EDITABLE_STATUSES:
        raise BudgetDomainError("ILLEGAL_STATE", "Budget allocations and planning fields are immutable in this state", http_status=409)


def _assert_current(record: Any, expected_updated_at: datetime | str) -> None:
    expected = _datetime(expected_updated_at, "expected_updated_at")
    if record.updated_at != expected:
        raise BudgetDomainError(
            "CONCURRENT_UPDATE",
            "The record changed after it was loaded",
            http_status=409,
            detail={"updated_at": record.updated_at.isoformat()},
        )


def _emit(tenant_id: UUID, aggregate_type: str, aggregate_id: UUID, event_type: str, payload: Mapping[str, Any]) -> OutboxEvent:
    safe = {key: value for key, value in payload.items() if key in {"budget_id", "actor_id", "line_count", "fiscal_year", "status", "schema_version"}}
    safe["schema_version"] = 1
    return OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload={key: str(value) if isinstance(value, UUID) else value for key, value in safe.items()},
    )


class BudgetService:
    """Budget planning, allocation, and lifecycle commands."""

    @staticmethod
    @transaction.atomic
    def create_budget(
        tenant_id: UUID,
        actor_id: UUID,
        *,
        budget_code: str,
        budget_name: str,
        fiscal_year: int,
        start_date: date | str,
        end_date: date | str,
        budget_type: str,
        currency: str,
        budget_ceiling: Decimal | str | None = None,
        department_id: UUID | str | None = None,
        project_id: UUID | str | None = None,
    ) -> Budget:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        code = _clean_text(budget_code, "budget_code", upper=True, max_length=50)
        name = _clean_text(budget_name, "budget_name", max_length=255)
        start, end = _date(start_date, "start_date"), _date(end_date, "end_date")
        if start > end:
            raise BudgetDomainError("INVALID_DATE_RANGE", "start_date must not be later than end_date")
        if isinstance(fiscal_year, bool) or not isinstance(fiscal_year, int) or not 1 <= fiscal_year <= 9999:
            raise BudgetDomainError("INVALID_FISCAL_YEAR", "fiscal_year must be between 1 and 9999")
        if not start.year <= fiscal_year <= end.year:
            raise BudgetDomainError("FISCAL_YEAR_MISMATCH", "fiscal_year must fall within the budget period")
        budget_type = str(budget_type).strip().lower()
        if budget_type not in {"operating", "capital", "project", "departmental"}:
            raise BudgetDomainError("INVALID_BUDGET_TYPE", "Unsupported budget_type")
        department = _uuid(department_id, "department_id") if department_id else None
        project = _uuid(project_id, "project_id") if project_id else None
        if budget_type == "departmental" and department is None:
            raise BudgetDomainError("DEPARTMENT_REQUIRED", "department_id is required for departmental budgets")
        if budget_type == "project" and project is None:
            raise BudgetDomainError("PROJECT_REQUIRED", "project_id is required for project budgets")
        currency = _clean_text(currency, "currency", upper=True, max_length=3)
        if currency not in ISO_4217:
            raise BudgetDomainError("INVALID_CURRENCY", "currency must be an uppercase ISO 4217 code")
        ceiling = _decimal(budget_ceiling, "budget_ceiling") if budget_ceiling is not None else None
        if Budget.objects.filter(tenant_id=tenant_id, is_deleted=False, budget_code__iexact=code).exists():
            raise BudgetDomainError("DUPLICATE_BUDGET_CODE", "A budget with this code already exists", http_status=409)
        if Budget.objects.filter(tenant_id=tenant_id, is_deleted=False, fiscal_year=fiscal_year, budget_name__iexact=name).exists():
            raise BudgetDomainError("DUPLICATE_BUDGET_NAME", "A budget with this name already exists for the fiscal year", http_status=409)
        try:
            budget = Budget.objects.create(
                tenant_id=tenant_id,
                budget_code=code,
                budget_name=name,
                fiscal_year=fiscal_year,
                start_date=start,
                end_date=end,
                budget_type=budget_type,
                department_id=department,
                project_id=project,
                currency=currency,
                budget_ceiling=ceiling,
                status="draft",
                total_budget=Decimal("0.00"),
                created_by=actor_id,
                updated_by=actor_id,
            )
        except IntegrityError as exc:
            raise BudgetDomainError("DUPLICATE_BUDGET", "Budget uniqueness conflict", http_status=409) from exc
        _emit(tenant_id, "budget", budget.id, "budget.created", {"budget_id": budget.id, "actor_id": actor_id, "fiscal_year": fiscal_year})
        return budget

    @staticmethod
    @transaction.atomic
    def update_budget(
        tenant_id: UUID,
        budget_id: UUID,
        actor_id: UUID,
        *,
        expected_updated_at: datetime | str,
        changes: Mapping[str, Any],
    ) -> Budget:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        budget = _budget_for_update(tenant_id, budget_id)
        _assert_current(budget, expected_updated_at)
        _assert_editable(budget)
        unknown = set(changes) - PLANNING_FIELDS
        if unknown:
            raise BudgetDomainError("READ_ONLY_FIELD", f"Fields cannot be changed: {', '.join(sorted(unknown))}")
        values = {field: getattr(budget, field) for field in PLANNING_FIELDS}
        values.update(changes)
        # Reuse create-level validation without writing an intermediate object.
        code = _clean_text(values["budget_code"], "budget_code", upper=True, max_length=50)
        name = _clean_text(values["budget_name"], "budget_name", max_length=255)
        start, end = _date(values["start_date"], "start_date"), _date(values["end_date"], "end_date")
        raw_year = values["fiscal_year"]
        if isinstance(raw_year, bool) or not isinstance(raw_year, int) or not 1 <= raw_year <= 9999:
            raise BudgetDomainError("INVALID_FISCAL_YEAR", "fiscal_year must be between 1 and 9999")
        year = raw_year
        if start > end or not start.year <= year <= end.year:
            raise BudgetDomainError("INVALID_DATE_RANGE", "Budget dates and fiscal year are inconsistent")
        kind = str(values["budget_type"]).strip().lower()
        if kind not in {"operating", "capital", "project", "departmental"}:
            raise BudgetDomainError("INVALID_BUDGET_TYPE", "Unsupported budget_type")
        department = _uuid(values["department_id"], "department_id") if values.get("department_id") else None
        project = _uuid(values["project_id"], "project_id") if values.get("project_id") else None
        if kind == "departmental" and department is None:
            raise BudgetDomainError("DEPARTMENT_REQUIRED", "department_id is required for departmental budgets")
        if kind == "project" and project is None:
            raise BudgetDomainError("PROJECT_REQUIRED", "project_id is required for project budgets")
        currency = _clean_text(values["currency"], "currency", upper=True, max_length=3)
        if currency not in ISO_4217:
            raise BudgetDomainError("INVALID_CURRENCY", "currency must be an uppercase ISO 4217 code")
        ceiling = _decimal(values["budget_ceiling"], "budget_ceiling") if values.get("budget_ceiling") is not None else None
        duplicates = Budget.objects.filter(tenant_id=tenant_id, is_deleted=False).exclude(pk=budget.pk)
        if duplicates.filter(budget_code__iexact=code).exists():
            raise BudgetDomainError("DUPLICATE_BUDGET_CODE", "A budget with this code already exists", http_status=409)
        if duplicates.filter(fiscal_year=year, budget_name__iexact=name).exists():
            raise BudgetDomainError("DUPLICATE_BUDGET_NAME", "A budget with this name already exists for the fiscal year", http_status=409)
        normalized = {
            "budget_code": code, "budget_name": name, "fiscal_year": year, "start_date": start, "end_date": end,
            "budget_type": kind, "department_id": department, "project_id": project, "currency": currency, "budget_ceiling": ceiling,
        }
        for field in changes:
            setattr(budget, field, normalized[field])
        budget.updated_by = actor_id
        budget.save(update_fields=[*changes.keys(), "updated_by", "updated_at"])
        _emit(tenant_id, "budget", budget.id, "budget.updated", {"budget_id": budget.id, "actor_id": actor_id})
        return budget

    @staticmethod
    @transaction.atomic
    def delete_budget(tenant_id: UUID, budget_id: UUID, actor_id: UUID, *, expected_updated_at: datetime | str) -> None:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        budget = _budget_for_update(tenant_id, budget_id)
        _assert_current(budget, expected_updated_at)
        if budget.status != "draft":
            raise BudgetDomainError("ILLEGAL_STATE", "Only draft budgets may be deleted", http_status=409)
        now = timezone.now()
        budget.is_deleted, budget.deleted_at, budget.deleted_by, budget.updated_by = True, now, actor_id, actor_id
        budget.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_by", "updated_at"])
        _emit(tenant_id, "budget", budget.id, "budget.deleted", {"budget_id": budget.id, "actor_id": actor_id})

    @staticmethod
    def _allocation_values(data: Mapping[str, Any]) -> dict[str, Any]:
        account_code = _clean_text(data.get("account_code"), "account_code", upper=True, max_length=50)
        period_type = str(data.get("period_type", "")).strip().lower()
        limits = {"annual": 1, "monthly": 12, "quarterly": 4}
        if period_type not in limits:
            raise BudgetDomainError("INVALID_PERIOD_TYPE", "period_type must be annual, monthly, or quarterly")
        period_number = data.get("period_number")
        if isinstance(period_number, bool) or not isinstance(period_number, int) or not 1 <= period_number <= limits[period_type]:
            raise BudgetDomainError("INVALID_PERIOD_NUMBER", "period_number does not match period_type")
        allowed = {"account_id", "account_code", "period_type", "period_number", "budget_amount"}
        unknown = set(data) - allowed
        if unknown:
            raise BudgetDomainError("READ_ONLY_FIELD", f"Fields cannot be supplied: {', '.join(sorted(unknown))}")
        return {
            "account_id": _uuid(data["account_id"], "account_id") if data.get("account_id") else None,
            "account_code": account_code,
            "account_name": "",
            "period_type": period_type,
            "period_number": period_number,
            "budget_amount": _decimal(data.get("budget_amount"), "budget_amount"),
            "committed_amount": Decimal("0.00"),
            "actual_amount": Decimal("0.00"),
            "source": "manual",
        }

    @staticmethod
    @transaction.atomic
    def replace_allocations(
        tenant_id: UUID,
        budget_id: UUID,
        actor_id: UUID,
        allocations: Sequence[Mapping[str, Any]],
        *,
        expected_updated_at: datetime | str,
    ) -> Budget:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        budget = _budget_for_update(tenant_id, budget_id)
        _assert_current(budget, expected_updated_at)
        _assert_editable(budget)
        if isinstance(allocations, (str, bytes, Mapping)):
            raise BudgetDomainError("INVALID_ALLOCATIONS", "allocations must be a list")
        normalized = [BudgetService._allocation_values(item) for item in allocations]
        seen: set[tuple[str, str, int]] = set()
        account_schemes: dict[str, str] = {}
        for item in normalized:
            identity = (item["account_code"], item["period_type"], item["period_number"])
            if identity in seen:
                raise BudgetDomainError("DUPLICATE_ALLOCATION", "Duplicate account period allocation")
            seen.add(identity)
            prior_scheme = account_schemes.setdefault(item["account_code"], item["period_type"])
            if prior_scheme != item["period_type"]:
                raise BudgetDomainError("MIXED_PERIOD_SCHEME", "An account must use one period scheme")
        total = sum((item["budget_amount"] for item in normalized), Decimal("0.00"))
        if budget.budget_ceiling is not None and total != budget.budget_ceiling:
            raise BudgetDomainError(
                "CEILING_MISMATCH", "Allocation total must equal the budget ceiling", http_status=409,
                detail={"ceiling": str(budget.budget_ceiling), "allocated": str(total), "difference": str(budget.budget_ceiling - total)},
            )
        accounting = get_integrations().accounting
        if accounting is not None and normalized:
            accounting.validate_accounts(tenant_id, sorted({item["account_code"] for item in normalized}))
        now = timezone.now()
        BudgetLine.objects.filter(tenant_id=tenant_id, budget=budget, is_deleted=False).update(
            is_deleted=True, deleted_at=now, deleted_by=actor_id, updated_by=actor_id
        )
        BudgetLine.objects.bulk_create(
            [
                BudgetLine(
                    tenant_id=tenant_id, budget=budget, created_by=actor_id, updated_by=actor_id,
                    variance=item["budget_amount"] - item["actual_amount"], **item,
                )
                for item in normalized
            ]
        )
        budget.total_budget, budget.updated_by = total, actor_id
        budget.save(update_fields=["total_budget", "updated_by", "updated_at"])
        _emit(tenant_id, "budget", budget.id, "budget.allocations_replaced", {"budget_id": budget.id, "actor_id": actor_id, "line_count": len(normalized)})
        return budget

    @staticmethod
    @transaction.atomic
    def create_line(tenant_id: UUID, budget_id: UUID, actor_id: UUID, data: Mapping[str, Any]) -> BudgetLine:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        budget = _budget_for_update(tenant_id, budget_id)
        _assert_editable(budget)
        values = BudgetService._allocation_values(data)
        accounting = get_integrations().accounting
        if accounting is not None:
            accounting.validate_accounts(tenant_id, [values["account_code"]])
        if BudgetLine.objects.filter(
            tenant_id=tenant_id, budget=budget, is_deleted=False, account_code=values["account_code"],
            period_type=values["period_type"], period_number=values["period_number"],
        ).exists():
            raise BudgetDomainError("DUPLICATE_ALLOCATION", "This account period already exists", http_status=409)
        line = BudgetLine.objects.create(
            tenant_id=tenant_id, budget=budget, created_by=actor_id, updated_by=actor_id,
            variance=values["budget_amount"] - values["actual_amount"], **values,
        )
        BudgetService.recalculate_total_budget(tenant_id, budget.id, actor_id=actor_id)
        return line

    @staticmethod
    @transaction.atomic
    def update_line(
        tenant_id: UUID,
        line_id: UUID,
        actor_id: UUID,
        *,
        expected_updated_at: datetime | str,
        changes: Mapping[str, Any],
    ) -> BudgetLine:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        line = _line_for_update(tenant_id, line_id)
        _assert_current(line, expected_updated_at)
        budget = _budget_for_update(tenant_id, line.budget_id)
        _assert_editable(budget)
        current = {field: getattr(line, field) for field in ("account_id", "account_code", "period_type", "period_number", "budget_amount")}
        current.update(changes)
        values = BudgetService._allocation_values(current)
        for field, value in values.items():
            setattr(line, field, value)
        line.variance, line.updated_by = values["budget_amount"] - values["actual_amount"], actor_id
        line.save(update_fields=[*values.keys(), "variance", "updated_by", "updated_at"])
        BudgetService.recalculate_total_budget(tenant_id, budget.id, actor_id=actor_id)
        return line

    @staticmethod
    @transaction.atomic
    def delete_line(tenant_id: UUID, line_id: UUID, actor_id: UUID, *, expected_updated_at: datetime | str) -> None:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        line = _line_for_update(tenant_id, line_id)
        _assert_current(line, expected_updated_at)
        budget = _budget_for_update(tenant_id, line.budget_id)
        _assert_editable(budget)
        line.is_deleted, line.deleted_at, line.deleted_by, line.updated_by = True, timezone.now(), actor_id, actor_id
        line.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_by", "updated_at"])
        BudgetService.recalculate_total_budget(tenant_id, budget.id, actor_id=actor_id)

    @staticmethod
    @transaction.atomic
    def recalculate_total_budget(tenant_id: UUID, budget_id: UUID, *, actor_id: UUID | None = None) -> Budget:
        tenant_id = _uuid(tenant_id, "tenant_id")
        budget = _budget_for_update(tenant_id, budget_id)
        total = BudgetLine.objects.filter(tenant_id=tenant_id, budget=budget, is_deleted=False).aggregate(total=models.Sum("budget_amount"))["total"] or Decimal("0.00")
        budget.total_budget = total
        fields = ["total_budget", "updated_at"]
        if actor_id is not None:
            budget.updated_by = _uuid(actor_id, "actor_id")
            fields.append("updated_by")
        budget.save(update_fields=fields)
        return budget

    # Compatibility for the original public method, while retaining tenant-first scoping.
    calculate_total_budget = recalculate_total_budget

    @staticmethod
    @transaction.atomic
    def submit_for_approval(tenant_id: UUID, budget_id: UUID, actor_id: UUID, *, idempotency_key: str, notes: str = "") -> Budget:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        budget = _budget_for_update(tenant_id, budget_id)
        if budget.status not in {"draft", "revision"}:
            return BudgetService._apply_transition(tenant_id, budget, actor_id, "submit", idempotency_key, notes=notes)
        lines = list(BudgetLine.objects.filter(tenant_id=tenant_id, budget=budget, is_deleted=False))
        if not lines:
            raise BudgetDomainError("ALLOCATIONS_REQUIRED", "At least one active allocation is required", http_status=409)
        total = sum((line.budget_amount for line in lines), Decimal("0.00"))
        if budget.budget_ceiling is not None and total != budget.budget_ceiling:
            raise BudgetDomainError("CEILING_MISMATCH", "Allocations must balance to the budget ceiling", http_status=409)
        workflow = require_workflow()
        request = workflow.create_approval_request(
            tenant_id, budget=budget, submitter_id=actor_id, idempotency_key=idempotency_key
        )
        if not request.steps or any(step.approval_level < 1 or step.approver_id == actor_id for step in request.steps):
            raise BudgetDomainError("INVALID_APPROVAL_POLICY", "Workflow returned no valid independent approvers", http_status=503)
        for step in request.steps:
            BudgetApproval.objects.get_or_create(
                tenant_id=tenant_id,
                budget=budget,
                approval_level=step.approval_level,
                approver_id=step.approver_id,
                defaults={
                    "workflow_request_id": request.workflow_request_id,
                    "status": "pending",
                    "created_by": actor_id,
                },
            )
        result = BudgetService._apply_transition(
            tenant_id, budget, actor_id, "submit", idempotency_key, notes=notes,
            workflow_request_id=request.workflow_request_id, _submitted_at=timezone.now(),
        )
        enqueue(
            tenant_id, actor_id, "budget_management.dispatch_submission_notification",
            {"budget_id": str(budget.id), "recipient_ids": [str(step.approver_id) for step in request.steps]},
            f"budget-notify-submit:{idempotency_key}",
        )
        return result

    @staticmethod
    @transaction.atomic
    def approve_budget(tenant_id: UUID, budget_id: UUID, actor_id: UUID, *, idempotency_key: str, notes: str = "") -> Budget:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        budget = _budget_for_update(tenant_id, budget_id)
        prior_key = BudgetApprovalDecision.objects.filter(
            tenant_id=tenant_id, budget=budget, idempotency_key=idempotency_key
        ).first()
        if prior_key is not None:
            if prior_key.status != "approved":
                raise BudgetDomainError("IDEMPOTENCY_CONFLICT", "Approval key belongs to another decision", http_status=409)
            if budget.status == "approved":
                return budget
            if BudgetApproval.objects.filter(
                tenant_id=tenant_id, budget=budget, decisions__isnull=True
            ).exists():
                return budget
            return BudgetService._apply_transition(
                tenant_id, budget, actor_id, "approve", idempotency_key, notes=notes,
                approval_level=prior_key.approval.approval_level, _approved_at=budget.approved_at or timezone.now(),
            )
        if budget.submitted_by == actor_id:
            raise BudgetDomainError("SELF_APPROVAL_FORBIDDEN", "Submitters cannot approve their own budget", http_status=403)
        approval = BudgetApproval.objects.select_for_update().filter(
            tenant_id=tenant_id, budget=budget, approver_id=actor_id, decisions__isnull=True
        ).order_by("approval_level").first()
        if approval is None:
            raise BudgetDomainError("APPROVAL_NOT_ASSIGNED", "No pending approval is assigned to this actor", http_status=403)
        lower_pending = BudgetApproval.objects.filter(
            tenant_id=tenant_id, budget=budget, decisions__isnull=True, approval_level__lt=approval.approval_level
        ).exists()
        if lower_pending:
            raise BudgetDomainError("APPROVAL_LEVEL_PENDING", "Earlier approval levels must complete first", http_status=409)
        BudgetApprovalDecision.objects.create(
            tenant_id=tenant_id,
            approval=approval,
            budget=budget,
            actor_id=actor_id,
            status="approved",
            idempotency_key=idempotency_key,
            notes=str(notes).strip(),
        )
        remaining = BudgetApproval.objects.filter(tenant_id=tenant_id, budget=budget, decisions__isnull=True).exists()
        if remaining:
            return budget
        return BudgetService._apply_transition(
            tenant_id, budget, actor_id, "approve", idempotency_key, notes=notes,
            approval_level=approval.approval_level, _approved_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def reject_budget(tenant_id: UUID, budget_id: UUID, actor_id: UUID, *, idempotency_key: str, reason: str) -> Budget:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        reason = _clean_text(reason, "reason")
        budget = _budget_for_update(tenant_id, budget_id)
        prior_key = BudgetApprovalDecision.objects.filter(
            tenant_id=tenant_id, budget=budget, idempotency_key=idempotency_key
        ).first()
        if prior_key is not None:
            if prior_key.status != "rejected":
                raise BudgetDomainError("IDEMPOTENCY_CONFLICT", "Approval key belongs to another decision", http_status=409)
            return BudgetService._apply_transition(
                tenant_id, budget, actor_id, "reject", idempotency_key,
                approval_level=prior_key.approval.approval_level,
                _rejected_at=budget.rejected_at or timezone.now(), _rejection_reason=budget.rejection_reason or reason,
            )
        if budget.submitted_by == actor_id:
            raise BudgetDomainError("SELF_APPROVAL_FORBIDDEN", "Submitters cannot reject their own budget", http_status=403)
        approval = BudgetApproval.objects.select_for_update().filter(
            tenant_id=tenant_id, budget=budget, approver_id=actor_id, decisions__isnull=True
        ).order_by("approval_level").first()
        if approval is None:
            raise BudgetDomainError("APPROVAL_NOT_ASSIGNED", "No pending approval is assigned to this actor", http_status=403)
        BudgetApprovalDecision.objects.create(
            tenant_id=tenant_id,
            approval=approval,
            budget=budget,
            actor_id=actor_id,
            status="rejected",
            idempotency_key=idempotency_key,
            rejection_reason=reason,
        )
        pending = list(
            BudgetApproval.objects.select_for_update().filter(
                tenant_id=tenant_id, budget=budget, decisions__isnull=True
            )
        )
        for item in pending:
            cancellation_key = f"cancel:{uuid.uuid5(uuid.NAMESPACE_URL, f'{tenant_id}:{budget.id}:{idempotency_key}:{item.id}') }"
            BudgetApprovalDecision.objects.create(
                tenant_id=tenant_id,
                approval=item,
                budget=budget,
                actor_id=actor_id,
                status="cancelled",
                idempotency_key=cancellation_key,
            )
        return BudgetService._apply_transition(
            tenant_id, budget, actor_id, "reject", idempotency_key,
            approval_level=approval.approval_level, _rejected_at=timezone.now(), _rejection_reason=reason,
        )

    @staticmethod
    @transaction.atomic
    def revise_budget(tenant_id: UUID, budget_id: UUID, actor_id: UUID, *, idempotency_key: str, notes: str = "") -> Budget:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        budget = _budget_for_update(tenant_id, budget_id)
        result = BudgetService._apply_transition(tenant_id, budget, actor_id, "revise", idempotency_key, notes=notes)
        result.rejected_at = result.rejected_by = None
        result.rejection_reason, result.updated_by = "", actor_id
        result.save(update_fields=["rejected_at", "rejected_by", "rejection_reason", "updated_by", "updated_at"])
        return result

    @staticmethod
    @transaction.atomic
    def close_budget(
        tenant_id: UUID,
        budget_id: UUID,
        actor_id: UUID,
        *,
        idempotency_key: str,
        effective_date: date | str | None = None,
        policy_authorized: bool = False,
    ) -> Budget:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        budget = _budget_for_update(tenant_id, budget_id)
        effective = _date(effective_date, "effective_date") if effective_date else timezone.localdate()
        if budget.end_date > effective and not policy_authorized:
            raise BudgetDomainError("EARLY_CLOSE_FORBIDDEN", "Budget period has not ended", http_status=409)
        return BudgetService._apply_transition(tenant_id, budget, actor_id, "close", idempotency_key)

    @staticmethod
    def _apply_transition(
        tenant_id: UUID,
        budget: Budget,
        actor_id: UUID,
        command: str,
        idempotency_key: str,
        *,
        notes: str = "",
        **metadata: Any,
    ) -> Budget:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise BudgetDomainError("IDEMPOTENCY_KEY_REQUIRED", "idempotency_key is required")
        existing = BudgetTransition.objects.filter(
            tenant_id=tenant_id, budget=budget, transition_key=idempotency_key.strip()
        ).first()
        try:
            result = BUDGET_STATE_MACHINE.apply(
                budget, command, tenant_id=tenant_id, transition_key=idempotency_key.strip(),
                metadata={"actor_id": str(actor_id), "notes": str(notes).strip(), **metadata},
            )
        except IdempotencyConflictError as exc:
            raise BudgetDomainError("IDEMPOTENCY_CONFLICT", str(exc), http_status=409) from exc
        except IllegalTransitionError as exc:
            raise BudgetDomainError("ILLEGAL_STATE", str(exc), http_status=409) from exc
        if existing is not None:
            return result
        result.updated_by = actor_id
        result.save(update_fields=["updated_by", "updated_at"])
        event = {"submit": "budget.submitted", "approve": "budget.approved", "reject": "budget.rejected", "revise": "budget.revised", "close": "budget.closed"}[command]
        _emit(tenant_id, "budget", result.id, event, {"budget_id": result.id, "actor_id": actor_id, "status": result.status})
        return result


class BudgetControlService:
    """Availability, variance, actuals, and commitment controls."""

    @staticmethod
    def check_budget_availability(
        tenant_id: UUID,
        *,
        account_code: str,
        amount: Decimal | str,
        period: date | str,
        budget_id: UUID | str | None = None,
    ) -> BudgetAvailabilityResult:
        tenant_id = _uuid(tenant_id, "tenant_id")
        code, requested, on_date = _clean_text(account_code, "account_code", upper=True, max_length=50), _decimal(amount, "amount", positive=True), _date(period, "period")
        budgets = Budget.objects.filter(
            tenant_id=tenant_id, is_deleted=False, status="approved", start_date__lte=on_date, end_date__gte=on_date
        )
        if budget_id is not None:
            budgets = budgets.filter(id=_uuid(budget_id, "budget_id"))
        quarter = ((on_date.month - 1) // 3) + 1
        matching_period = models.Q(period_type="annual", period_number=1) | models.Q(
            period_type="monthly", period_number=on_date.month
        ) | models.Q(period_type="quarterly", period_number=quarter)
        totals = BudgetLine.objects.filter(
            matching_period,
            tenant_id=tenant_id,
            is_deleted=False,
            budget__in=budgets,
            account_code=code,
        ).aggregate(
            allocated=models.Sum("budget_amount"),
            committed=models.Sum("committed_amount"),
            actual=models.Sum("actual_amount"),
        )
        allocated = totals["allocated"] or Decimal("0.00")
        committed = totals["committed"] or Decimal("0.00")
        actual = totals["actual"] or Decimal("0.00")
        available = allocated - committed - actual
        unbudgeted = allocated == Decimal("0.00")
        sufficient = not unbudgeted and available >= requested
        deficit = max(requested - available, Decimal("0.00"))
        return BudgetAvailabilityResult(allocated, committed, actual, available, deficit, sufficient, unbudgeted)

    @staticmethod
    def calculate_variance(
        tenant_id: UUID,
        budget_id: UUID,
        *,
        period_type: str | None = None,
        period_number: int | None = None,
        account_code: str | None = None,
        threshold_percentage: Decimal | str = Decimal("10"),
    ) -> VarianceReport:
        tenant_id, threshold = _uuid(tenant_id, "tenant_id"), _percent(threshold_percentage)
        try:
            budget = Budget.objects.get(tenant_id=tenant_id, id=_uuid(budget_id, "budget_id"), is_deleted=False)
        except Budget.DoesNotExist as exc:
            raise BudgetDomainError("NOT_FOUND", "Budget not found", http_status=404) from exc
        lines = BudgetLine.objects.filter(tenant_id=tenant_id, budget=budget, is_deleted=False)
        if period_type is not None:
            if period_type not in {"annual", "monthly", "quarterly"}:
                raise BudgetDomainError("INVALID_PERIOD_TYPE", "Unsupported period_type")
            lines = lines.filter(period_type=period_type)
        if period_number is not None:
            if isinstance(period_number, bool) or not isinstance(period_number, int) or not 1 <= period_number <= 12:
                raise BudgetDomainError("INVALID_PERIOD_NUMBER", "period_number must be from 1 to 12")
            lines = lines.filter(period_number=period_number)
        if account_code is not None:
            lines = lines.filter(account_code=_clean_text(account_code, "account_code", upper=True))
        results: list[VarianceLineResult] = []
        for line in lines.order_by("account_code", "period_type", "period_number"):
            variance = line.budget_amount - line.actual_amount
            percentage = None if line.budget_amount == 0 else (variance / line.budget_amount * 100).quantize(PERCENT)
            threshold_exceeded = (line.actual_amount + line.committed_amount) > line.budget_amount * (
                Decimal("1") + threshold / 100
            )
            results.append(
                VarianceLineResult(
                    line.id,
                    line.account_code,
                    line.account_name,
                    line.period_type,
                    line.period_number,
                    line.budget_amount,
                    line.committed_amount,
                    line.actual_amount,
                    variance,
                    percentage,
                    variance >= 0,
                    threshold_exceeded,
                    threshold_exceeded,
                )
            )
        budgeted = sum((item.budgeted for item in results), Decimal("0.00"))
        committed = sum((item.committed for item in results), Decimal("0.00"))
        actual = sum((item.actual for item in results), Decimal("0.00"))
        variance = budgeted - actual
        percentage = None if budgeted == 0 else (variance / budgeted * 100).quantize(PERCENT)
        return VarianceReport(
            budget.id,
            budget.currency,
            budgeted,
            committed,
            actual,
            variance,
            percentage,
            variance >= 0,
            threshold,
            tuple(results),
        )

    @staticmethod
    @transaction.atomic
    def request_actuals_sync(tenant_id: UUID, budget_id: UUID, actor_id: UUID, *, idempotency_key: str) -> AsyncJob:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        require_accounting()
        budget = _budget_for_update(tenant_id, budget_id)
        return enqueue(
            tenant_id, actor_id, "budget_management.sync_actuals", {"budget_id": str(budget.id)},
            f"budget-sync:{budget.id}:{_clean_text(idempotency_key, 'idempotency_key')}",
        )

    @staticmethod
    @transaction.atomic
    def apply_actuals_snapshot(
        tenant_id: UUID,
        budget_id: UUID,
        snapshot: Sequence[Mapping[str, Any]],
        *,
        source_evidence: str,
    ) -> Budget:
        tenant_id = _uuid(tenant_id, "tenant_id")
        evidence = _clean_text(source_evidence, "source_evidence", max_length=255)
        budget = _budget_for_update(tenant_id, budget_id)
        evidence_id = uuid.uuid5(uuid.NAMESPACE_URL, f"budget-actuals:{tenant_id}:{budget.id}:{evidence}")
        if OutboxEvent.objects.filter(tenant_id=tenant_id, aggregate_id=evidence_id, event_type="budget.actuals_evidence").exists():
            return budget
        seen: set[tuple[str, str, int]] = set()
        for raw in snapshot:
            code = _clean_text(raw.get("account_code"), "account_code", upper=True)
            period_type = str(raw.get("period_type", "")).lower()
            period_number = raw.get("period_number")
            identity = (code, period_type, period_number)
            if identity in seen:
                raise BudgetDomainError("DUPLICATE_ACTUAL", "Actuals snapshot contains a duplicate period")
            seen.add(identity)
            try:
                line = BudgetLine.objects.select_for_update().get(
                    tenant_id=tenant_id, budget=budget, is_deleted=False, account_code=code,
                    period_type=period_type, period_number=period_number,
                )
            except BudgetLine.DoesNotExist as exc:
                raise BudgetDomainError("ACTUAL_IDENTITY_MISMATCH", "Actuals snapshot does not match an allocation") from exc
            actual = _decimal(raw.get("actual_amount"), "actual_amount")
            line.actual_amount, line.variance = actual, line.budget_amount - actual
            line.actuals_as_of, line.source = timezone.now(), "accounting_sync"
            line.save(update_fields=["actual_amount", "variance", "actuals_as_of", "source", "updated_at"])
        OutboxEvent.objects.create(
            tenant_id=tenant_id, aggregate_type="budget_actuals_evidence", aggregate_id=evidence_id,
            event_type="budget.actuals_evidence", payload={"budget_id": str(budget.id), "schema_version": 1},
        )
        _emit(tenant_id, "budget", budget.id, "budget.actuals_synced", {"budget_id": budget.id})
        return budget

    @staticmethod
    def _commitment(
        tenant_id: UUID,
        budget_line_id: UUID,
        amount: Decimal | str,
        *,
        source_id: str,
        idempotency_key: str,
        release: bool,
    ) -> BudgetLine:
        tenant_id, amount_value = _uuid(tenant_id, "tenant_id"), _decimal(amount, "amount", positive=True)
        source, key = _uuid(source_id, "source_id"), _clean_text(idempotency_key, "idempotency_key", max_length=255)
        with transaction.atomic():
            line = _line_for_update(tenant_id, budget_line_id)
            existing = BudgetCommitment.objects.filter(
                tenant_id=tenant_id, source_id=source, idempotency_key=key
            ).first()
            operation = "release" if release else "record"
            if existing is not None:
                if existing.budget_line_id != line.id or existing.operation != operation or existing.amount != amount_value:
                    raise BudgetDomainError(
                        "IDEMPOTENCY_CONFLICT",
                        "Commitment idempotency key was reused for another operation",
                        http_status=409,
                    )
                return line
            updated = line.committed_amount - amount_value if release else line.committed_amount + amount_value
            if updated < 0:
                raise BudgetDomainError("COMMITMENT_UNDERFLOW", "Released amount exceeds the committed amount", http_status=409)
            try:
                with transaction.atomic():
                    BudgetCommitment.objects.create(
                        tenant_id=tenant_id,
                        budget_line=line,
                        source_id=source,
                        idempotency_key=key,
                        operation=operation,
                        amount=amount_value,
                    )
            except IntegrityError:
                winner = BudgetCommitment.objects.get(
                    tenant_id=tenant_id, budget_line=line, source_id=source, idempotency_key=key
                )
                if winner.operation != operation or winner.amount != amount_value:
                    raise BudgetDomainError("IDEMPOTENCY_CONFLICT", "Commitment idempotency conflict", http_status=409)
                return line
            line.committed_amount = updated
            line.save(update_fields=["committed_amount", "updated_at"])
            return line

    @staticmethod
    def record_commitment(tenant_id: UUID, budget_line_id: UUID, amount: Decimal | str, *, source_id: UUID | str, idempotency_key: str) -> BudgetLine:
        return BudgetControlService._commitment(tenant_id, budget_line_id, amount, source_id=source_id, idempotency_key=idempotency_key, release=False)

    @staticmethod
    def release_commitment(tenant_id: UUID, budget_line_id: UUID, amount: Decimal | str, *, source_id: UUID | str, idempotency_key: str) -> BudgetLine:
        return BudgetControlService._commitment(tenant_id, budget_line_id, amount, source_id=source_id, idempotency_key=idempotency_key, release=True)


class VarianceAlertService:
    """Durable generation, delivery, and acknowledgement of variance alerts."""

    @staticmethod
    @transaction.atomic
    def request_alert_generation(
        tenant_id: UUID,
        actor_id: UUID,
        *,
        threshold_percentage: Decimal | str,
        alert_type: str,
        idempotency_key: str,
    ) -> AsyncJob:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        threshold, kind = _percent(threshold_percentage), str(alert_type).strip().lower()
        if kind not in {"over_budget", "approaching_limit", "underspend"}:
            raise BudgetDomainError("INVALID_ALERT_TYPE", "Unsupported alert_type")
        return enqueue(
            tenant_id, actor_id, "budget_management.generate_variance_alerts",
            {"threshold_percentage": str(threshold), "alert_type": kind, "alert_date": timezone.localdate().isoformat()},
            f"budget-alerts:{_clean_text(idempotency_key, 'idempotency_key')}",
        )

    @staticmethod
    @transaction.atomic
    def generate_alerts(
        tenant_id: UUID,
        *,
        threshold_percentage: Decimal | str,
        alert_type: str,
        alert_date: date | str,
    ) -> list[VarianceAlert]:
        tenant_id, threshold, on_date = _uuid(tenant_id, "tenant_id"), _percent(threshold_percentage), _date(alert_date, "alert_date")
        kind = str(alert_type).strip().lower()
        if kind not in {"over_budget", "approaching_limit", "underspend"}:
            raise BudgetDomainError("INVALID_ALERT_TYPE", "Unsupported alert_type")
        lines = BudgetLine.objects.select_related("budget").filter(
            tenant_id=tenant_id, is_deleted=False, budget__tenant_id=tenant_id, budget__is_deleted=False,
            budget__status__in=("approved", "closed"),
        )
        created: list[VarianceAlert] = []
        for line in lines.iterator():
            consumption = line.actual_amount + line.committed_amount
            consumption_ratio = (
                None
                if line.budget_amount == 0
                else (consumption / line.budget_amount * 100).quantize(PERCENT)
            )
            variance_percentage = (
                None
                if line.budget_amount == 0
                else ((line.budget_amount - line.actual_amount) / line.budget_amount * 100).quantize(PERCENT)
            )
            matches = (
                kind == "approaching_limit" and line.budget_amount > 0 and consumption >= line.budget_amount * Decimal("0.80") and consumption <= line.budget_amount
            ) or (
                kind == "over_budget" and consumption > line.budget_amount * (Decimal("1") + threshold / 100)
            ) or (
                kind == "underspend" and line.budget.end_date <= on_date and line.budget_amount > 0 and consumption_ratio is not None and consumption_ratio < threshold
            )
            if not matches:
                continue
            try:
                alert, was_created = VarianceAlert.objects.get_or_create(
                    tenant_id=tenant_id, budget_line=line, alert_type=kind,
                    threshold_percentage=threshold, alert_date=on_date,
                    defaults={
                        "budget": line.budget, "variance_percentage": variance_percentage,
                        "budget_amount": line.budget_amount, "actual_amount": line.actual_amount,
                        "committed_amount": line.committed_amount, "notification_status": "pending",
                    },
                )
            except IntegrityError:
                continue
            if was_created:
                created.append(alert)
                _emit(tenant_id, "variance_alert", alert.id, "budget.variance_alerted", {"budget_id": line.budget_id})
        return created

    @staticmethod
    @transaction.atomic
    def dispatch_alert(tenant_id: UUID, alert_id: UUID, *, idempotency_key: str) -> AsyncJob:
        tenant_id = _uuid(tenant_id, "tenant_id")
        try:
            alert = VarianceAlert.objects.select_for_update().get(tenant_id=tenant_id, id=_uuid(alert_id, "alert_id"))
        except VarianceAlert.DoesNotExist as exc:
            raise BudgetDomainError("NOT_FOUND", "Variance alert not found", http_status=404) from exc
        if get_integrations().notification is None:
            alert.notification_status = "unavailable"
            alert.save(update_fields=["notification_status"])
            raise BudgetDomainError("CAPABILITY_UNAVAILABLE", "Notification capability is not configured", http_status=503)
        job = enqueue(
            tenant_id, uuid.UUID(int=0), "budget_management.dispatch_variance_alert",
            {"alert_id": str(alert.id)}, f"budget-alert-notify:{_clean_text(idempotency_key, 'idempotency_key')}",
        )
        alert.notification_job_id, alert.notification_status = job.id, "pending"
        alert.save(update_fields=["notification_job_id", "notification_status"])
        return job

    @staticmethod
    @transaction.atomic
    def acknowledge_alert(tenant_id: UUID, alert_id: UUID, actor_id: UUID) -> VarianceAlert:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        try:
            alert = VarianceAlert.objects.select_for_update().get(tenant_id=tenant_id, id=_uuid(alert_id, "alert_id"))
        except VarianceAlert.DoesNotExist as exc:
            raise BudgetDomainError("NOT_FOUND", "Variance alert not found", http_status=404) from exc
        if alert.acknowledged_at is None:
            alert.acknowledged_at, alert.acknowledged_by = timezone.now(), actor_id
            alert.save(update_fields=["acknowledged_at", "acknowledged_by"])
        return alert


__all__ = [
    "BudgetAvailabilityResult",
    "BudgetControlService",
    "BudgetDomainError",
    "BudgetService",
    "VarianceAlertService",
    "VarianceLineResult",
    "VarianceReport",
]
