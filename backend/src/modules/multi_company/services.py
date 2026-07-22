"""Transactional business authority for the multi-company domain.

Views are transport adapters only.  Every mutation, tenant reference check,
financial calculation, state transition and configuration change is owned by
this module.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max, Q, QuerySet
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue

from .extensions import ExtensionContext, TransferPricingInputV1, TransferPricingMethodProviderV1, extension_registry
from .models import (
    Company, CompanyAccessGrant, ConfigurationAuditRecord, ConsolidationRun,
    EliminationEntry, IntercompanyApproval, IntercompanyTransaction,
    MultiCompanyConfigurationVersion, TransferPricingRule,
)
from .state_machines import consolidation_state_machine, transaction_state_machine


class DomainError(RuntimeError):
    code = "DOMAIN_ERROR"


class NotFoundError(DomainError):
    code = "NOT_FOUND"


class ConflictError(DomainError):
    code = "CONFLICT"


class StaleVersionError(ConflictError):
    code = "STALE_VERSION"


class ConfigurationUnavailable(DomainError):
    code = "CONFIGURATION_UNAVAILABLE"


class IdempotencyConflict(ConflictError):
    code = "IDEMPOTENCY_CONFLICT"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    errors: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class ConfigurationImpact:
    valid: bool
    changed_keys: tuple[str, ...]
    affected_companies: int
    affected_draft_transactions: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransferPriceResult:
    amount: Decimal
    pricing_method: str
    formula: str
    rule_id: uuid.UUID | None
    rule_version: int | None
    rounding_mode: str
    precision: int
    evidence: Mapping[str, Any]


ALLOWED_CURRENCIES = frozenset(
    {"AED", "AUD", "BRL", "CAD", "CHF", "CNY", "EUR", "GBP", "HKD", "INR", "JPY", "KRW", "MXN", "NZD", "SAR", "SGD", "USD", "ZAR"}
)
ALLOWED_TRANSLATION_METHODS = frozenset(choice for choice, _ in ConsolidationRun.TranslationMethod.choices)
ALLOWED_TRANSACTION_TYPES = frozenset(choice for choice, _ in IntercompanyTransaction._meta.get_field("transaction_type").choices)
ALLOWED_PRICING_METHODS = frozenset(choice for choice, _ in TransferPricingRule.PricingMethod.choices)
ROLE_RANK = {"viewer": 0, "operator": 1, "approver": 2, "controller": 3, "tax_admin": 4}


def runtime_environment() -> str:
    """Resolve the deployment's configuration environment without branching business logic."""
    value = os.environ.get("SARAISE_ENVIRONMENT", "development").strip().lower()
    if value not in {"development", "staging", "production"}:
        raise ConfigurationUnavailable("SARAISE_ENVIRONMENT must be development, staging, or production")
    return value


DEFAULT_SETTINGS: dict[str, Any] = {
    "draft_expiry_hours": 168,
    "minimum_consolidation_company_count": 2,
    "permitted_translation_methods": sorted(ALLOWED_TRANSLATION_METHODS),
    "permitted_transaction_types": sorted(ALLOWED_TRANSACTION_TYPES),
    "permitted_pricing_methods": sorted(ALLOWED_PRICING_METHODS),
    "maximum_transaction_amount_by_currency": {currency: "1000000000.0000" for currency in ALLOWED_CURRENCIES},
    "approval_sides": ["source", "target"],
    "transfer_pricing_tolerance_min": "-100.0000",
    "transfer_pricing_tolerance_max": "1000.0000",
    "allow_consolidation_overlap": False,
    "rounding_mode": "ROUND_HALF_EVEN",
    "money_precision": 4,
    "feature_flags": {},
    "rollout": {"roles": [], "cohorts": []},
    "extension_enablement_keys": [],
    "notification_policy": {"approval": True, "dispute": True, "failure": True, "completion": True},
    "job_max_retries": 3,
    "job_timeout_seconds": 300,
    "default_currency": "USD",
    "default_fiscal_year_start_month": 1,
    "elimination_accounts": {"debit": "INTERCO-DEBIT", "credit": "INTERCO-CREDIT"},
    "ledger_accounts": {"intercompany_receivable": "1200-INTERCO", "intercompany_payable": "2200-INTERCO", "intercompany_revenue": "4100-INTERCO", "intercompany_expense": "5100-INTERCO"},
}


def _tenant_qs(model: type[Any], tenant_id: uuid.UUID | str) -> QuerySet[Any]:
    return model.objects.for_tenant(tenant_id)


def _get(model: type[Any], tenant_id: uuid.UUID | str, object_id: Any, *, deleted: bool = False) -> Any:
    query = _tenant_qs(model, tenant_id)
    if hasattr(model, "is_deleted") and not deleted:
        query = query.filter(is_deleted=False)
    try:
        return query.get(pk=object_id)
    except (ObjectDoesNotExist, ValueError, TypeError) as exc:
        raise NotFoundError(f"{model.__name__} was not found") from exc


def _locked_get(model: type[Any], tenant_id: uuid.UUID | str, object_id: Any, *, deleted: bool = False) -> Any:
    query = _tenant_qs(model, tenant_id).select_for_update()
    if hasattr(model, "is_deleted") and not deleted:
        query = query.filter(is_deleted=False)
    try:
        return query.get(pk=object_id)
    except (ObjectDoesNotExist, ValueError, TypeError) as exc:
        raise NotFoundError(f"{model.__name__} was not found") from exc


def _required_text(value: Any, field: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({field: "This field is required."})
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValidationError({field: f"Must contain at most {maximum} characters."})
    return normalized


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "A valid decimal is required."}) from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValidationError({field: "Must be a finite value greater than zero."})
    return result


def _currency(value: Any) -> str:
    code = _required_text(value, "currency", 3).upper()
    if code not in ALLOWED_CURRENCIES:
        raise ValidationError({"currency": "Unsupported ISO 4217 currency."})
    return code


def _check_version(instance: Any, expected_version: int) -> None:
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
        raise ValidationError({"expected_version": "A positive integer is required."})
    if instance.version != expected_version:
        raise StaleVersionError(f"Expected version {expected_version}; current version is {instance.version}")


def _event(tenant_id: Any, aggregate: Any, event_type: str, actor_id: str, correlation_id: str, **payload: Any) -> OutboxEvent:
    safe_payload = {
        "schema_version": "1.0", "tenant_id": str(tenant_id),
        "aggregate_id": str(aggregate.pk), "aggregate_version": getattr(aggregate, "version", 1),
        "actor_id": actor_id, "correlation_id": correlation_id, **payload,
    }
    return OutboxEvent.objects.create(
        tenant_id=tenant_id, aggregate_type=aggregate._meta.model_name,
        aggregate_id=aggregate.pk, event_type=event_type, payload=safe_payload,
    )


def _transition(machine: Any, instance: Any, command: str, *, tenant_id: Any, actor_id: str, correlation_id: str, transition_key: str) -> Any:
    result = machine.apply(
        instance, command, tenant_id=tenant_id, transition_key=_required_text(transition_key, "transition_key"),
        metadata={"actor_id": actor_id, "correlation_id": correlation_id},
    )
    # StateMachine owns state/history. Its deliberately narrow update_fields
    # does not persist this module's audit/concurrency columns, so update them
    # atomically while its locked transaction is still active.
    type(result).objects.for_tenant(tenant_id).filter(pk=result.pk).update(
        updated_by=actor_id, correlation_id=correlation_id, updated_at=timezone.now()
    )
    result.updated_by = actor_id
    result.correlation_id = correlation_id
    return result


class CompanyRegistryService:
    @staticmethod
    @transaction.atomic
    def create_company(tenant_id: Any, actor_id: str, correlation_id: str, payload: Mapping[str, Any], idempotency_key: str) -> Company:
        data = dict(payload)
        parent = CompanyRegistryService._validated_parent(tenant_id, data.pop("parent_company_id", data.pop("parent_company", None)))
        environment = data.pop("environment", runtime_environment())
        try:
            active = MultiCompanyConfigurationService.get_active(tenant_id, environment)
        except ConfigurationUnavailable:
            # v1 predates the configuration API. Preserve its announced
            # compatibility by materialising the documented defaults as a real,
            # versioned and audited configuration; governed v2 still fails
            # explicitly when operators have not configured the capability.
            if not str(idempotency_key).startswith("v1:"):
                raise
            draft = MultiCompanyConfigurationService.create_draft(
                tenant_id, actor_id, correlation_id, environment, DEFAULT_SETTINGS,
                "Bootstrap defaults for deprecated v1 compatibility",
            )
            active = MultiCompanyConfigurationService.activate(tenant_id, draft.id, actor_id, correlation_id)
        settings = active.settings
        data["company_code"] = _required_text(data.get("company_code"), "company_code", 50).upper()
        data["company_name"] = _required_text(data.get("company_name"), "company_name")
        data["legal_name"] = _required_text(data.get("legal_name") or data["company_name"], "legal_name")
        data["currency"] = _currency(data.get("currency") or settings["default_currency"])
        data["fiscal_year_start_month"] = int(data.get("fiscal_year_start_month") or settings["default_fiscal_year_start_month"])
        if not 1 <= data["fiscal_year_start_month"] <= 12:
            raise ValidationError({"fiscal_year_start_month": "Must be between 1 and 12."})
        data["parent_company"] = parent
        data.update(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, correlation_id=correlation_id)
        try:
            company = Company.objects.create(**data)
        except IntegrityError as exc:
            raise ConflictError("Company code already exists for this tenant") from exc
        _event(tenant_id, company, "multi_company.company.created", actor_id, correlation_id)
        return company

    @staticmethod
    def get_company(tenant_id: Any, company_id: Any) -> Company:
        return _get(Company, tenant_id, company_id)

    @staticmethod
    def list_companies(tenant_id: Any, filters: Mapping[str, Any] | None = None) -> QuerySet[Company]:
        filters = filters or {}
        query = _tenant_qs(Company, tenant_id).filter(is_deleted=False)
        for key in ("company_code", "is_active", "parent_company_id", "consolidation_group", "currency"):
            if key in filters and filters[key] not in (None, ""):
                query = query.filter(**{key: filters[key]})
        if filters.get("search"):
            query = query.filter(Q(company_code__icontains=filters["search"]) | Q(company_name__icontains=filters["search"]) | Q(legal_name__icontains=filters["search"]))
        return query.order_by("company_code")

    @staticmethod
    @transaction.atomic
    def update_company(tenant_id: Any, company_id: Any, actor_id: str, correlation_id: str, expected_version: int, changes: Mapping[str, Any]) -> Company:
        company = _locked_get(Company, tenant_id, company_id)
        _check_version(company, expected_version)
        allowed = {"company_code", "company_name", "legal_name", "tax_id", "currency", "fiscal_year_start_month", "parent_company_id", "consolidation_group", "ownership_percentage", "address", "is_holding"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError({key: "Field cannot be updated." for key in unknown})
        values = dict(changes)
        if "parent_company_id" in values:
            CompanyRegistryService._ensure_no_cycle(tenant_id, company.id, values["parent_company_id"])
            values["parent_company"] = CompanyRegistryService._validated_parent(tenant_id, values.pop("parent_company_id"))
        if "currency" in values: values["currency"] = _currency(values["currency"])
        if "company_code" in values: values["company_code"] = _required_text(values["company_code"], "company_code", 50).upper()
        for key, value in values.items(): setattr(company, key, value)
        company.updated_by, company.correlation_id, company.version = actor_id, correlation_id, company.version + 1
        company.full_clean()
        company.save()
        _event(tenant_id, company, "multi_company.company.updated", actor_id, correlation_id)
        return company

    @staticmethod
    def _validated_parent(tenant_id: Any, parent_id: Any) -> Company | None:
        if not parent_id: return None
        parent = _get(Company, tenant_id, parent_id)
        if not parent.is_active: raise ValidationError({"parent_company_id": "Parent company must be active."})
        return parent

    @staticmethod
    def _ensure_no_cycle(tenant_id: Any, company_id: Any, parent_id: Any) -> None:
        seen = {str(company_id)}
        current = parent_id
        while current:
            if str(current) in seen: raise ValidationError({"parent_company_id": "Company hierarchy cycle detected."})
            seen.add(str(current))
            current = _tenant_qs(Company, tenant_id).filter(pk=current, is_deleted=False).values_list("parent_company_id", flat=True).first()

    @staticmethod
    @transaction.atomic
    def deactivate_company(tenant_id: Any, company_id: Any, actor_id: str, correlation_id: str, expected_version: int, transition_key: str = "") -> Company:
        del transition_key
        company = _locked_get(Company, tenant_id, company_id)
        _check_version(company, expected_version)
        blocked = _tenant_qs(IntercompanyTransaction, tenant_id).filter(
            Q(source_company=company) | Q(target_company=company),
            status__in=["pending_approval", "approved", "posting", "disputed", "posting_failed"], is_deleted=False,
        ).exists()
        if blocked: raise ConflictError("Company has nonterminal financial transactions")
        company.is_active = False; company.updated_by = actor_id; company.correlation_id = correlation_id; company.version += 1; company.save()
        _event(tenant_id, company, "multi_company.company.deactivated", actor_id, correlation_id)
        return company

    @staticmethod
    @transaction.atomic
    def reactivate_company(tenant_id: Any, company_id: Any, actor_id: str, correlation_id: str, expected_version: int, transition_key: str = "") -> Company:
        del transition_key
        company = _locked_get(Company, tenant_id, company_id)
        _check_version(company, expected_version)
        if company.parent_company_id: CompanyRegistryService._validated_parent(tenant_id, company.parent_company_id)
        company.is_active = True; company.updated_by = actor_id; company.correlation_id = correlation_id; company.version += 1; company.save()
        return company

    @staticmethod
    @transaction.atomic
    def delete_company(tenant_id: Any, company_id: Any, actor_id: str, correlation_id: str, expected_version: int) -> None:
        company = _locked_get(Company, tenant_id, company_id)
        _check_version(company, expected_version)
        if company.subsidiaries.filter(is_deleted=False).exists() or company.access_grants.filter(is_deleted=False).exists() or _tenant_qs(IntercompanyTransaction, tenant_id).filter(Q(source_company=company) | Q(target_company=company)).exists():
            raise ConflictError("Company has protected dependent or financial history")
        company.is_deleted = True; company.deleted_at = timezone.now(); company.is_active = False
        company.updated_by = actor_id; company.correlation_id = correlation_id; company.version += 1; company.save()

    @staticmethod
    def get_subsidiaries(tenant_id: Any, company_id: Any, recursive: bool = False) -> list[Company]:
        _get(Company, tenant_id, company_id)
        direct = list(_tenant_qs(Company, tenant_id).filter(parent_company_id=company_id, is_deleted=False).order_by("company_code"))
        if not recursive: return direct
        result, queue, seen = [], direct[:], {str(company_id)}
        while queue:
            item = queue.pop(0)
            if str(item.id) in seen: raise ConflictError("Company hierarchy contains a cycle")
            seen.add(str(item.id)); result.append(item)
            queue.extend(_tenant_qs(Company, tenant_id).filter(parent_company=item, is_deleted=False).order_by("company_code"))
        return result

    @staticmethod
    def get_hierarchy(tenant_id: Any, root_company_id: Any = None) -> list[dict[str, Any]]:
        roots = [_get(Company, tenant_id, root_company_id)] if root_company_id else list(_tenant_qs(Company, tenant_id).filter(parent_company__isnull=True, is_deleted=False).order_by("company_code"))
        def node(company: Company, trail: frozenset[uuid.UUID]) -> dict[str, Any]:
            if company.id in trail: raise ConflictError("Company hierarchy contains a cycle")
            children = _tenant_qs(Company, tenant_id).filter(parent_company=company, is_deleted=False).order_by("company_code")
            return {"id": company.id, "company_code": company.company_code, "company_name": company.company_name, "is_active": company.is_active, "depth": len(trail), "children": [node(child, trail | {company.id}) for child in children]}
        return [node(root, frozenset()) for root in roots]

    @staticmethod
    def get_consolidation_group(tenant_id: Any, group_name: str) -> list[Company]:
        return list(_tenant_qs(Company, tenant_id).filter(consolidation_group=group_name, is_active=True, is_deleted=False).order_by("company_code"))


class CompanyService:
    """Deprecated v1 compatibility facade; new code uses CompanyRegistryService."""
    @staticmethod
    def create_company(tenant_id: Any, company_code: str, company_name: str, **kwargs: Any) -> Company:
        # v1 predates configuration and audit inputs; it remains functional for
        # the announced deprecation period without accepting tenant data in kwargs.
        kwargs.pop("tenant_id", None)
        return Company.objects.create(tenant_id=tenant_id, company_code=company_code, company_name=company_name, legal_name=kwargs.pop("legal_name", company_name), currency=kwargs.pop("currency", ""), **kwargs)


class CompanyAccessService:
    @staticmethod
    def list_grants(tenant_id: Any, company_id: Any = None, subject_id: str | None = None, role: str | None = None, active_at: Any = None) -> QuerySet[CompanyAccessGrant]:
        query = _tenant_qs(CompanyAccessGrant, tenant_id).filter(is_deleted=False)
        if company_id: query = query.filter(company_id=company_id)
        if subject_id: query = query.filter(subject_id=subject_id)
        if role: query = query.filter(role=role)
        if active_at: query = query.filter(valid_from__lte=active_at).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=active_at))
        return query

    @staticmethod
    @transaction.atomic
    def grant_access(tenant_id: Any, actor_id: str, correlation_id: str, payload: Mapping[str, Any]) -> CompanyAccessGrant:
        company = _get(Company, tenant_id, payload.get("company_id"))
        role = payload.get("role")
        if role not in ROLE_RANK: raise ValidationError({"role": "Unsupported company role."})
        valid_from = payload.get("valid_from") or timezone.now(); valid_until = payload.get("valid_until")
        if valid_until and valid_until <= valid_from: raise ValidationError({"valid_until": "Must be later than valid_from."})
        try:
            return CompanyAccessGrant.objects.create(
                tenant_id=tenant_id, company=company, subject_id=_required_text(payload.get("subject_id"), "subject_id"), role=role,
                valid_from=valid_from, valid_until=valid_until, granted_by=actor_id,
                created_by=actor_id, updated_by=actor_id, correlation_id=correlation_id,
            )
        except IntegrityError as exc: raise ConflictError("This company access grant already exists") from exc

    @staticmethod
    @transaction.atomic
    def revoke_access(tenant_id: Any, grant_id: Any, actor_id: str, correlation_id: str, reason: str) -> CompanyAccessGrant:
        _required_text(reason, "reason", 1000)
        grant = _locked_get(CompanyAccessGrant, tenant_id, grant_id)
        grant.revoked_by=actor_id; grant.revoked_at=timezone.now(); grant.valid_until=grant.revoked_at
        grant.is_deleted=True; grant.deleted_at=grant.revoked_at; grant.updated_by=actor_id; grant.correlation_id=correlation_id; grant.version += 1; grant.save()
        return grant

    @staticmethod
    def require_company_access(tenant_id: Any, subject: Any, company_ids: Sequence[Any], required_role: str) -> None:
        subject_id = str(getattr(subject, "id", subject))
        if required_role not in ROLE_RANK: raise ValueError("Unknown required company role")
        now = timezone.now()
        grants = _tenant_qs(CompanyAccessGrant, tenant_id).filter(subject_id=subject_id, company_id__in=company_ids, is_deleted=False, valid_from__lte=now).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        ranks: dict[str, int] = {}
        for grant in grants: ranks[str(grant.company_id)] = max(ranks.get(str(grant.company_id), -1), ROLE_RANK[grant.role])
        missing = [str(company_id) for company_id in company_ids if ranks.get(str(company_id), -1) < ROLE_RANK[required_role]]
        if missing: raise PermissionDenied("A valid company access grant is required")


class IntercompanyTransactionService:
    @staticmethod
    @transaction.atomic
    def create_transaction(tenant_id: Any, actor_id: str, correlation_id: str, payload: Mapping[str, Any], idempotency_key: str = "") -> IntercompanyTransaction:
        del idempotency_key
        data = dict(payload); source = _get(Company, tenant_id, data.pop("source_company_id")); target = _get(Company, tenant_id, data.pop("target_company_id"))
        pricing_rule_id = data.pop("transfer_pricing_rule_id", None)
        if pricing_rule_id is not None:
            pricing_rule = _get(TransferPricingRule, tenant_id, pricing_rule_id)
            if pricing_rule.source_company_id != source.id or pricing_rule.target_company_id != target.id:
                raise ValidationError({"transfer_pricing_rule_id": "Rule does not apply to this company pair."})
            data["transfer_pricing_rule"] = pricing_rule
        if source.id == target.id: raise ValidationError({"target_company_id": "Source and target must differ."})
        if not source.is_active or not target.is_active: raise ValidationError("Both companies must be active.")
        CompanyAccessService.require_company_access(
            tenant_id, actor_id, (source.id, target.id), "operator"
        )
        config = MultiCompanyConfigurationService.get_active(tenant_id, data.pop("environment", runtime_environment())).settings
        tx_type = data.get("transaction_type")
        if tx_type not in config["permitted_transaction_types"]: raise ValidationError({"transaction_type": "Transaction type is disabled."})
        currency = _currency(data.get("currency")); amount = _decimal(data.get("amount", data.get("original_amount")), "amount", positive=True)
        limit = _decimal(config["maximum_transaction_amount_by_currency"].get(currency, "0"), "maximum_transaction_amount")
        if amount > limit: raise ValidationError({"amount": f"Exceeds configured {currency} limit."})
        data.update(
            source_company=source, target_company=target, amount=amount,
            original_amount=_decimal(data.get("original_amount", amount), "original_amount", positive=True), currency=currency,
            tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, correlation_id=correlation_id,
        )
        if data.get("exchange_rate") is not None:
            data["exchange_rate"] = _decimal(data["exchange_rate"], "exchange_rate", positive=True)
            data["target_amount"] = (amount * data["exchange_rate"]).quantize(Decimal("0.0001"), rounding=_rounding(config))
        try: record = IntercompanyTransaction.objects.create(**data)
        except IntegrityError as exc: raise ConflictError("Transaction reference already exists") from exc
        _event(tenant_id, record, "multi_company.transaction.created", actor_id, correlation_id)
        return record

    @staticmethod
    def get_transaction(tenant_id: Any, transaction_id: Any) -> IntercompanyTransaction: return _get(IntercompanyTransaction, tenant_id, transaction_id)

    @staticmethod
    def list_transactions(tenant_id: Any, filters: Mapping[str, Any] | None = None) -> QuerySet[IntercompanyTransaction]:
        filters=filters or {}; query=_tenant_qs(IntercompanyTransaction, tenant_id).filter(is_deleted=False)
        for key in ("source_company_id", "target_company_id", "transaction_type", "status", "currency"):
            if filters.get(key) not in (None, ""): query=query.filter(**{key:filters[key]})
        if filters.get("date_from"): query=query.filter(transaction_date__gte=filters["date_from"])
        if filters.get("date_to"): query=query.filter(transaction_date__lte=filters["date_to"])
        if filters.get("search"): query=query.filter(Q(reference__icontains=filters["search"]) | Q(description__icontains=filters["search"]))
        return query.order_by("-transaction_date", "reference")

    @staticmethod
    @transaction.atomic
    def update_draft(tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, expected_version: int, changes: Mapping[str, Any]) -> IntercompanyTransaction:
        record=_locked_get(IntercompanyTransaction,tenant_id,transaction_id); _check_version(record,expected_version)
        if record.status != "draft": raise ConflictError("Only draft transactions can be updated")
        allowed={"reference","transaction_type","product_category","original_amount","amount","currency","exchange_rate","description","transaction_date"}
        if set(changes)-allowed: raise ValidationError("One or more fields cannot be updated.")
        for key,value in changes.items(): setattr(record,key,_currency(value) if key=="currency" else _decimal(value,key,positive=True) if key in {"amount","original_amount","exchange_rate"} else value)
        record.updated_by=actor_id;record.correlation_id=correlation_id;record.version+=1;record.full_clean();record.save();return record

    @staticmethod
    def _command(tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, command: str, transition_key: str) -> IntercompanyTransaction:
        record=_get(IntercompanyTransaction,tenant_id,transaction_id)
        result=_transition(transaction_state_machine,record,command,tenant_id=tenant_id,actor_id=actor_id,correlation_id=correlation_id,transition_key=transition_key)
        _event(tenant_id,result,f"multi_company.transaction.{ {'posting_succeeded':'posted','posting_failed':'failed','resolve':'submitted'}.get(command,command) }",actor_id,correlation_id)
        return result

    @classmethod
    @transaction.atomic
    def submit(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, transition_key: str) -> IntercompanyTransaction:
        return cls._command(tenant_id,transaction_id,actor_id,correlation_id,"submit",transition_key)

    @classmethod
    @transaction.atomic
    def dispute(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, reason: str, transition_key: str) -> IntercompanyTransaction:
        reason=_required_text(reason,"reason",2000); result=cls._command(tenant_id,transaction_id,actor_id,correlation_id,"dispute",transition_key)
        IntercompanyTransaction.objects.filter(pk=result.pk).update(dispute_reason=reason); result.dispute_reason=reason; return result

    @classmethod
    @transaction.atomic
    def resolve_dispute(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, resolution: str, transition_key: str) -> IntercompanyTransaction:
        _required_text(resolution,"resolution",2000)
        _tenant_qs(IntercompanyApproval,tenant_id).filter(transaction_id=transaction_id)  # evidence remains append-only; next attempt supersedes
        return cls._command(tenant_id,transaction_id,actor_id,correlation_id,"resolve",transition_key)

    @classmethod
    @transaction.atomic
    def cancel(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, reason: str, transition_key: str) -> IntercompanyTransaction:
        reason=_required_text(reason,"reason",2000); result=cls._command(tenant_id,transaction_id,actor_id,correlation_id,"cancel",transition_key)
        IntercompanyTransaction.objects.filter(pk=result.pk).update(cancellation_reason=reason); result.cancellation_reason=reason; return result

    @classmethod
    @transaction.atomic
    def record_approval(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, side: str, decision: str, reason: str="", workflow_reference: str="", transition_key: str="") -> IntercompanyTransaction:
        record=_locked_get(IntercompanyTransaction,tenant_id,transaction_id)
        if record.status != "pending_approval": raise ConflictError("Transaction is not pending approval")
        if actor_id == record.created_by: raise PermissionDenied("Transaction creator cannot approve the transaction")
        if side not in {"source","target"} or decision not in {"approved","rejected"}: raise ValidationError("Invalid approval decision.")
        approval_company_id = record.source_company_id if side == "source" else record.target_company_id
        CompanyAccessService.require_company_access(
            tenant_id, actor_id, (approval_company_id,), "approver"
        )
        if decision=="rejected" and not reason.strip(): raise ValidationError({"reason":"Rejection reason is required."})
        other=_tenant_qs(IntercompanyApproval,tenant_id).filter(transaction=record,decision="approved").exclude(side=side).order_by("-attempt").first()
        if other and other.approver_id==actor_id: raise PermissionDenied("Source and target approvals require different subjects")
        attempt=(_tenant_qs(IntercompanyApproval,tenant_id).filter(transaction=record,side=side).aggregate(value=Max("attempt"))["value"] or 0)+1
        IntercompanyApproval.objects.create(tenant_id=tenant_id,transaction=record,side=side,attempt=attempt,approver_id=actor_id,decision=decision,reason=reason,workflow_reference=workflow_reference,decided_at=timezone.now(),correlation_id=correlation_id)
        if decision=="rejected": return cls.dispute(tenant_id,transaction_id,actor_id,correlation_id,reason,transition_key)
        approved_sides=set(_tenant_qs(IntercompanyApproval,tenant_id).filter(transaction=record,decision="approved").values_list("side",flat=True))
        config=MultiCompanyConfigurationService.get_active(tenant_id,runtime_environment()).settings
        if set(config["approval_sides"]).issubset(approved_sides): return cls._command(tenant_id,transaction_id,actor_id,correlation_id,"approve",transition_key)
        return record

    @classmethod
    @transaction.atomic
    def post(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, idempotency_key: str, transition_key: str) -> AsyncJob:
        pending = cls.get_transaction(tenant_id, transaction_id)
        CompanyAccessService.require_company_access(
            tenant_id,
            actor_id,
            (pending.source_company_id, pending.target_company_id),
            "controller",
        )
        record=cls._command(tenant_id,transaction_id,actor_id,correlation_id,"post",transition_key)
        job=enqueue(tenant_id,actor_id,"multi_company.transaction.post",{"transaction_id":str(record.id),"tenant_id":str(tenant_id),"correlation_id":correlation_id},idempotency_key)
        if job.command != "multi_company.transaction.post" or job.payload.get("transaction_id") != str(record.id): raise IdempotencyConflict("Idempotency key belongs to another command")
        IntercompanyTransaction.objects.filter(pk=record.pk).update(job_id=job.id); return job

    @classmethod
    def retry_posting(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, idempotency_key: str, transition_key: str) -> AsyncJob:
        return cls.post(tenant_id,transaction_id,actor_id,correlation_id,idempotency_key,transition_key)

    @classmethod
    @transaction.atomic
    def reverse(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, reason: str, idempotency_key: str) -> IntercompanyTransaction:
        original=_get(IntercompanyTransaction,tenant_id,transaction_id)
        if original.status != "posted": raise ConflictError("Only posted transactions can be reversed")
        reference=f"REV-{original.reference}-{idempotency_key[:12]}"
        existing=_tenant_qs(IntercompanyTransaction,tenant_id).filter(reference=reference).first()
        if existing: return existing
        reversal=IntercompanyTransaction.objects.create(tenant_id=tenant_id,reference=reference,source_company=original.target_company,target_company=original.source_company,transaction_type=original.transaction_type,product_category=original.product_category,original_amount=original.original_amount,amount=original.amount,currency=original.currency,exchange_rate=original.exchange_rate,target_amount=original.target_amount,description=f"Reversal: {reason}",transaction_date=timezone.localdate(),status="approved",reversed_transaction=original,created_by=actor_id,updated_by=actor_id,correlation_id=correlation_id)
        enqueue(tenant_id,actor_id,"multi_company.transaction.reverse",{"transaction_id":str(reversal.id),"original_transaction_id":str(original.id),"tenant_id":str(tenant_id),"correlation_id":correlation_id},idempotency_key)
        _event(tenant_id,reversal,"multi_company.transaction.reversed",actor_id,correlation_id,original_transaction_id=str(original.id)); return reversal

    @classmethod
    @transaction.atomic
    def apply_transfer_pricing(cls, tenant_id: Any, transaction_id: Any, actor_id: str, correlation_id: str, rule_id: Any=None) -> IntercompanyTransaction:
        record=_locked_get(IntercompanyTransaction,tenant_id,transaction_id)
        if record.status != "draft": raise ConflictError("Transfer pricing applies only to drafts")
        rule=_get(TransferPricingRule,tenant_id,rule_id) if rule_id else TransferPricingService.resolve_rule(tenant_id,record.source_company_id,record.target_company_id,record.product_category,record.transaction_type,record.transaction_date)
        result=TransferPricingService.calculate_price(tenant_id,{"rule_id":rule.id,"amount":record.original_amount,"environment":runtime_environment()})
        record.amount=result.amount; record.transfer_pricing_rule=rule; record.transfer_pricing_snapshot={"rule_id":str(rule.id),"rule_key":str(rule.rule_key),"rule_version":rule.rule_version,"pricing_method":result.pricing_method,"formula":result.formula,"amount":str(result.amount),"evidence":dict(result.evidence)}
        record.updated_by=actor_id;record.correlation_id=correlation_id;record.version+=1;record.save();return record

    @staticmethod
    def get_reconciliation(tenant_id: Any, filters: Mapping[str, Any] | None=None) -> list[dict[str, Any]]:
        rows=[]
        for item in IntercompanyTransactionService.list_transactions(tenant_id,filters):
            expected=item.target_amount if item.target_amount is not None else item.amount
            rows.append({"transaction_id":item.id,"reference":item.reference,"source_company_id":item.source_company_id,"target_company_id":item.target_company_id,"currency":item.currency,"source_amount":item.amount,"target_amount":item.target_amount,"variance":expected-item.amount,"status":item.status})
        return rows


def _rounding(settings: Mapping[str, Any]) -> str:
    return {"ROUND_HALF_EVEN":ROUND_HALF_EVEN,"ROUND_HALF_UP":ROUND_HALF_UP}[settings["rounding_mode"]]


class TransferPricingService:
    @staticmethod
    def get_rule(tenant_id: Any, rule_id: Any) -> TransferPricingRule: return _get(TransferPricingRule,tenant_id,rule_id)
    @staticmethod
    def list_rules(tenant_id: Any, filters: Mapping[str,Any]|None=None) -> QuerySet[TransferPricingRule]:
        query=_tenant_qs(TransferPricingRule,tenant_id).filter(is_deleted=False); filters=filters or {}
        for key in ("source_company_id","target_company_id","product_category","transaction_type","pricing_method","is_active"):
            if filters.get(key) not in (None,""): query=query.filter(**{key:filters[key]})
        return query.order_by("name","-rule_version")
    @staticmethod
    def _validate(data: Mapping[str,Any]) -> None:
        method=data.get("pricing_method")
        if method not in ALLOWED_PRICING_METHODS: raise ValidationError({"pricing_method":"Unsupported pricing method."})
        if method=="extension" and not data.get("extension_key"): raise ValidationError({"extension_key":"Required for extension method."})
        if method=="cost_plus" and data.get("markup_percentage") is None: raise ValidationError({"markup_percentage":"Required for cost-plus."})
        minimum=data.get("margin_range_min"); maximum=data.get("margin_range_max")
        if minimum is not None and maximum is not None and _decimal(minimum,"margin_range_min")>_decimal(maximum,"margin_range_max"): raise ValidationError({"margin_range_max":"Must not be below minimum."})
    @classmethod
    @transaction.atomic
    def create_rule(cls, tenant_id: Any, actor_id: str, correlation_id: str, payload: Mapping[str,Any], idempotency_key: str = "") -> TransferPricingRule:
        del idempotency_key
        data=dict(payload); cls._validate(data); data["source_company"]=_get(Company,tenant_id,data.pop("source_company_id"));data["target_company"]=_get(Company,tenant_id,data.pop("target_company_id"))
        if data["source_company"].id==data["target_company"].id: raise ValidationError("Source and target must differ.")
        data.update(tenant_id=tenant_id,created_by=actor_id,updated_by=actor_id,correlation_id=correlation_id)
        record=TransferPricingRule.objects.create(**data);_event(tenant_id,record,"multi_company.transfer_pricing.rule_activated",actor_id,correlation_id);return record
    @classmethod
    @transaction.atomic
    def create_rule_version(cls, tenant_id: Any, rule_id: Any, actor_id: str, correlation_id: str, expected_version: int, changes: Mapping[str,Any]) -> TransferPricingRule:
        prior=_locked_get(TransferPricingRule,tenant_id,rule_id);_check_version(prior,expected_version)
        values={field.name:getattr(prior,field.name) for field in TransferPricingRule._meta.fields if field.name not in {"id","tenant_id","created_at","updated_at","version","is_deleted","deleted_at","created_by","updated_by","correlation_id","supersedes","rule_version"}}
        values.update(changes);cls._validate(values);prior.is_active=False;prior.updated_by=actor_id;prior.correlation_id=correlation_id;prior.version+=1;prior.save()
        values.update(tenant_id=tenant_id,rule_key=prior.rule_key,rule_version=prior.rule_version+1,supersedes=prior,created_by=actor_id,updated_by=actor_id,correlation_id=correlation_id,is_active=True)
        return TransferPricingRule.objects.create(**values)
    @staticmethod
    def resolve_rule(tenant_id: Any, source_company_id: Any,target_company_id: Any,product_category: str,transaction_type: str,effective_date: date) -> TransferPricingRule:
        record=_tenant_qs(TransferPricingRule,tenant_id).filter(source_company_id=source_company_id,target_company_id=target_company_id,product_category=product_category,transaction_type=transaction_type,is_active=True,is_deleted=False,effective_from__lte=effective_date).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=effective_date)).order_by("-effective_from","-rule_version").first()
        if not record: raise NotFoundError("No effective transfer-pricing rule matches")
        return record
    @classmethod
    def calculate_price(cls, tenant_id: Any, payload: Mapping[str,Any]) -> TransferPriceResult:
        rule_id=payload.get("rule_id")
        rule=cls.get_rule(tenant_id,rule_id) if rule_id else cls.resolve_rule(tenant_id,payload["source_company_id"],payload["target_company_id"],payload["product_category"],payload["transaction_type"],payload["effective_date"])
        config=MultiCompanyConfigurationService.get_active(tenant_id,payload.get("environment",runtime_environment())).settings
        amount=_decimal(payload.get("amount"),"amount",positive=True); method=rule.pricing_method; formula=""; evidence:dict[str,Any]={}
        if method=="cost_plus": markup=_decimal(rule.markup_percentage,"markup_percentage"); calculated=amount*(Decimal("1")+markup/Decimal("100"));formula="base × (1 + markup / 100)";evidence={"markup_percentage":str(markup)}
        elif method=="resale_minus": margin=_decimal(rule.parameters.get("margin_percentage"),"parameters.margin_percentage");calculated=amount*(Decimal("1")-margin/Decimal("100"));formula="resale × (1 - margin / 100)";evidence={"margin_percentage":str(margin)}
        elif method=="comparable_uncontrolled": calculated=_decimal(rule.parameters.get("comparable_price"),"parameters.comparable_price",positive=True);formula="validated comparable uncontrolled price"
        elif method=="transactional_net_margin": margin=_decimal(rule.parameters.get("net_margin_percentage"),"parameters.net_margin_percentage");calculated=amount*(Decimal("1")+margin/Decimal("100"));formula="base × (1 + net margin / 100)"
        elif method=="profit_split": share=_decimal(rule.parameters.get("target_share_percentage"),"parameters.target_share_percentage");calculated=amount*share/Decimal("100");formula="combined profit × target share / 100"
        else:
            provider=extension_registry.get(rule.extension_key)
            if not callable(getattr(provider,"calculate",None)): raise ValidationError("Registered extension does not implement transfer pricing.")
            context=payload.get("extension_context")
            if not isinstance(context,ExtensionContext): raise ValidationError({"extension_context":"Governed extension context is required."})
            request=payload.get("extension_request")
            if not isinstance(request,TransferPricingInputV1): raise ValidationError({"extension_request":"Typed extension input is required."})
            output=extension_registry.invoke(rule.extension_key,"calculate",context,request);calculated=output.calculated_amount;formula=output.formula;evidence=dict(output.evidence)
        precision=int(config["money_precision"]); quantum=Decimal(1).scaleb(-precision);rounded=calculated.quantize(quantum,rounding=_rounding(config))
        return TransferPriceResult(rounded,method,formula,rule.id,rule.rule_version,config["rounding_mode"],precision,evidence)
    @classmethod
    def preview_rule(cls, tenant_id: Any,payload: Mapping[str,Any],scenarios: Sequence[Mapping[str,Any]]) -> list[TransferPriceResult]: return [cls.calculate_price(tenant_id,{**payload,**scenario}) for scenario in scenarios]
    @staticmethod
    @transaction.atomic
    def deactivate_rule(tenant_id: Any,rule_id: Any,actor_id: str,correlation_id: str,expected_version: int) -> TransferPricingRule:
        rule=_locked_get(TransferPricingRule,tenant_id,rule_id);_check_version(rule,expected_version);rule.is_active=False;rule.updated_by=actor_id;rule.correlation_id=correlation_id;rule.version+=1;rule.save();return rule
    @staticmethod
    @transaction.atomic
    def delete_unused_draft_rule(tenant_id: Any,rule_id: Any,actor_id: str,correlation_id: str,expected_version: int|None=None) -> None:
        rule=_locked_get(TransferPricingRule,tenant_id,rule_id)
        if expected_version is not None:_check_version(rule,expected_version)
        if _tenant_qs(IntercompanyTransaction,tenant_id).filter(transfer_pricing_rule=rule).exists(): raise ConflictError("Rule is referenced by financial history")
        rule.is_deleted=True;rule.deleted_at=timezone.now();rule.is_active=False;rule.updated_by=actor_id;rule.correlation_id=correlation_id;rule.version+=1;rule.save()


class ConsolidationService:
    @staticmethod
    @transaction.atomic
    def create_run(tenant_id: Any,actor_id: str,correlation_id: str,payload: Mapping[str,Any],idempotency_key: str="") -> ConsolidationRun:
        del idempotency_key
        data=dict(payload);config=MultiCompanyConfigurationService.get_active(tenant_id,data.pop("environment",runtime_environment())).settings
        members=CompanyRegistryService.get_consolidation_group(tenant_id,data["consolidation_group"])
        if len(members)<int(config["minimum_consolidation_company_count"]): raise ValidationError("Consolidation group has too few active companies.")
        if data["translation_method"] not in config["permitted_translation_methods"]: raise ValidationError({"translation_method":"Method is disabled."})
        if not config["allow_consolidation_overlap"] and _tenant_qs(ConsolidationRun,tenant_id).filter(consolidation_group=data["consolidation_group"],period_start__lte=data["period_end"],period_end__gte=data["period_start"],is_deleted=False).exists(): raise ConflictError("Consolidation period overlaps an existing run")
        data.update(total_companies=len(members),reporting_currency=_currency(data["reporting_currency"]),tenant_id=tenant_id,created_by=actor_id,updated_by=actor_id,correlation_id=correlation_id)
        return ConsolidationRun.objects.create(**data)
    @staticmethod
    def get_run(tenant_id: Any,run_id: Any) -> ConsolidationRun:return _get(ConsolidationRun,tenant_id,run_id)
    @staticmethod
    def list_runs(tenant_id: Any,filters: Mapping[str,Any]|None=None) -> QuerySet[ConsolidationRun]:
        query=_tenant_qs(ConsolidationRun,tenant_id).filter(is_deleted=False);filters=filters or {}
        for key in ("consolidation_group","status","reporting_currency"):
            if filters.get(key) not in (None,""):query=query.filter(**{key:filters[key]})
        return query.order_by("-period_end","name")
    @staticmethod
    @transaction.atomic
    def update_draft(tenant_id: Any,run_id: Any,actor_id: str,correlation_id: str,expected_version: int,changes: Mapping[str,Any]) -> ConsolidationRun:
        run=_locked_get(ConsolidationRun,tenant_id,run_id);_check_version(run,expected_version)
        if run.status!="draft":raise ConflictError("Only draft runs can be updated")
        for key,value in changes.items():setattr(run,key,value)
        run.updated_by=actor_id;run.correlation_id=correlation_id;run.version+=1;run.full_clean();run.save();return run
    @staticmethod
    @transaction.atomic
    def execute(tenant_id: Any,run_id: Any,actor_id: str,correlation_id: str,idempotency_key: str,transition_key: str) -> AsyncJob:
        run=_get(ConsolidationRun,tenant_id,run_id);run=_transition(consolidation_state_machine,run,"queue",tenant_id=tenant_id,actor_id=actor_id,correlation_id=correlation_id,transition_key=transition_key)
        job=enqueue(tenant_id,actor_id,"multi_company.consolidation.execute",{"run_id":str(run.id),"tenant_id":str(tenant_id),"correlation_id":correlation_id},idempotency_key)
        if job.command!="multi_company.consolidation.execute" or job.payload.get("run_id")!=str(run.id):raise IdempotencyConflict("Idempotency key belongs to another command")
        ConsolidationRun.objects.filter(pk=run.pk).update(job_id=job.id,executed_by=actor_id);_event(tenant_id,run,"multi_company.consolidation.queued",actor_id,correlation_id);return job
    @staticmethod
    @transaction.atomic
    def retry(tenant_id: Any,run_id: Any,actor_id: str,correlation_id: str,idempotency_key: str,transition_key: str) -> AsyncJob:
        run=_get(ConsolidationRun,tenant_id,run_id);run=_transition(consolidation_state_machine,run,"retry",tenant_id=tenant_id,actor_id=actor_id,correlation_id=correlation_id,transition_key=transition_key)
        job=enqueue(tenant_id,actor_id,"multi_company.consolidation.execute",{"run_id":str(run.id),"tenant_id":str(tenant_id),"correlation_id":correlation_id},idempotency_key)
        if job.command!="multi_company.consolidation.execute" or job.payload.get("run_id")!=str(run.id):raise IdempotencyConflict("Idempotency key belongs to another command")
        ConsolidationRun.objects.filter(pk=run.pk).update(job_id=job.id,executed_by=actor_id);return job
    @staticmethod
    def list_eliminations(tenant_id: Any,run_id: Any,filters: Mapping[str,Any]|None=None) -> QuerySet[EliminationEntry]:
        _get(ConsolidationRun,tenant_id,run_id);query=_tenant_qs(EliminationEntry,tenant_id).filter(consolidation_run_id=run_id);filters=filters or {}
        for key in ("elimination_type","source_company_id","target_company_id","is_auto_generated"):
            if filters.get(key) not in (None,""):query=query.filter(**{key:filters[key]})
        return query.order_by("sequence")
    @staticmethod
    @transaction.atomic
    def create_manual_elimination(tenant_id: Any,run_id: Any,actor_id: str,correlation_id: str,payload: Mapping[str,Any]) -> EliminationEntry:
        run=_get(ConsolidationRun,tenant_id,run_id)
        if run.status not in {"draft","running","completed"}:raise ConflictError("Manual eliminations are not allowed in this state")
        data=dict(payload);source=_get(Company,tenant_id,data.pop("source_company_id"));target=_get(Company,tenant_id,data.pop("target_company_id"))
        if source.id==target.id:raise ValidationError("Source and target must differ.")
        source_tx=None
        if data.pop("source_transaction_id",None):source_tx=_get(IntercompanyTransaction,tenant_id,payload["source_transaction_id"])
        sequence=(_tenant_qs(EliminationEntry,tenant_id).filter(consolidation_run=run).aggregate(value=Max("sequence"))["value"] or 0)+1
        auto_generated=bool(data.pop("is_auto_generated",False))
        data.update(tenant_id=tenant_id,consolidation_run=run,source_company=source,target_company=target,source_transaction=source_tx,created_by=actor_id,correlation_id=correlation_id,sequence=sequence,is_auto_generated=auto_generated,currency=_currency(data["currency"]),amount=_decimal(data["amount"],"amount",positive=True))
        return EliminationEntry.objects.create(**data)
    @classmethod
    def generate_eliminations(cls,tenant_id: Any,run_id: Any,actor_id: str,correlation_id: str) -> list[EliminationEntry]:
        # Core auto-elimination is deterministic and keyed by source tx; replay skips existing evidence.
        run=_get(ConsolidationRun,tenant_id,run_id);created=[]
        config=MultiCompanyConfigurationService.get_active(tenant_id,runtime_environment()).settings
        accounts=config["elimination_accounts"]
        transactions=_tenant_qs(IntercompanyTransaction,tenant_id).filter(status="posted",transaction_date__range=(run.period_start,run.period_end),source_company__consolidation_group=run.consolidation_group,target_company__consolidation_group=run.consolidation_group)
        for item in transactions:
            if _tenant_qs(EliminationEntry,tenant_id).filter(consolidation_run=run,source_transaction=item).exists():continue
            created.append(cls.create_manual_elimination(tenant_id,run_id,actor_id,correlation_id,{"elimination_type":"intercompany_balance","source_company_id":item.source_company_id,"target_company_id":item.target_company_id,"debit_account":accounts["debit"],"credit_account":accounts["credit"],"amount":item.amount,"currency":item.currency,"description":f"Eliminate {item.reference}","source_transaction_id":item.id,"rule_key":"core.intercompany.balance","is_auto_generated":True}))
        return created
    @staticmethod
    @transaction.atomic
    def approve(tenant_id: Any,run_id: Any,actor_id: str,correlation_id: str,transition_key: str) -> ConsolidationRun:
        run=_get(ConsolidationRun,tenant_id,run_id)
        if run.executed_by==actor_id:raise PermissionDenied("Consolidation executor cannot approve the same run")
        result=_transition(consolidation_state_machine,run,"approve",tenant_id=tenant_id,actor_id=actor_id,correlation_id=correlation_id,transition_key=transition_key);ConsolidationRun.objects.filter(pk=result.pk).update(approved_by=actor_id,approved_at=timezone.now());_event(tenant_id,result,"multi_company.consolidation.approved",actor_id,correlation_id);return result
    @staticmethod
    @transaction.atomic
    def publish(tenant_id: Any,run_id: Any,actor_id: str,correlation_id: str,transition_key: str) -> ConsolidationRun:
        run=_get(ConsolidationRun,tenant_id,run_id)
        if run.executed_by==actor_id:raise PermissionDenied("Consolidation executor cannot publish the same run")
        result=_transition(consolidation_state_machine,run,"publish",tenant_id=tenant_id,actor_id=actor_id,correlation_id=correlation_id,transition_key=transition_key);ConsolidationRun.objects.filter(pk=result.pk).update(published_by=actor_id,published_at=timezone.now());_event(tenant_id,result,"multi_company.consolidation.published",actor_id,correlation_id);return result
    @staticmethod
    def cancel(tenant_id: Any,run_id: Any,actor_id: str,correlation_id: str,reason: str,transition_key: str) -> ConsolidationRun:
        _required_text(reason,"reason",2000);return _transition(consolidation_state_machine,_get(ConsolidationRun,tenant_id,run_id),"cancel",tenant_id=tenant_id,actor_id=actor_id,correlation_id=correlation_id,transition_key=transition_key)
    @staticmethod
    def get_report(tenant_id: Any,run_id: Any) -> Mapping[str,Any]:
        run=_get(ConsolidationRun,tenant_id,run_id)
        if run.status not in {"completed","approved","published"} or run.report_snapshot is None:raise ConflictError("Consolidated report is not available")
        return run.report_snapshot


class MultiCompanyConfigurationService:
    @staticmethod
    def get_active(tenant_id: Any,environment: str) -> MultiCompanyConfigurationVersion:
        record=_tenant_qs(MultiCompanyConfigurationVersion,tenant_id).filter(environment=environment,status="active").first()
        if not record:raise ConfigurationUnavailable(f"No active multi-company configuration for {environment}")
        return record
    @staticmethod
    def list_versions(tenant_id: Any,environment: str) -> QuerySet[MultiCompanyConfigurationVersion]:return _tenant_qs(MultiCompanyConfigurationVersion,tenant_id).filter(environment=environment).order_by("-version")
    @staticmethod
    def validate_settings(settings: Mapping[str,Any]) -> ValidationResult:
        errors:dict[str,list[str]]={}
        def error(key:str,message:str)->None:errors.setdefault(key,[]).append(message)
        if not isinstance(settings,Mapping):return ValidationResult(False,{"settings":("Must be an object.",)})
        missing=set(DEFAULT_SETTINGS)-set(settings)
        for key in sorted(missing):error(key,"Required setting is missing.")
        try:
            expiry=int(settings.get("draft_expiry_hours",0));
            if not 1<=expiry<=8760:error("draft_expiry_hours","Must be between 1 and 8760.")
            minimum=int(settings.get("minimum_consolidation_company_count",0));
            if not 2<=minimum<=1000:error("minimum_consolidation_company_count","Must be between 2 and 1000.")
            retries=int(settings.get("job_max_retries",-1));
            if not 0<=retries<=10:error("job_max_retries","Must be between 0 and 10.")
            timeout=int(settings.get("job_timeout_seconds",0));
            if not 10<=timeout<=3600:error("job_timeout_seconds","Must be between 10 and 3600.")
            precision=int(settings.get("money_precision",-1));
            if not 0<=precision<=4:error("money_precision","Must be between 0 and 4.")
        except (TypeError,ValueError):error("settings","Numeric bounds contain invalid values.")
        if settings.get("rounding_mode") not in {"ROUND_HALF_EVEN","ROUND_HALF_UP"}:error("rounding_mode","Unsupported rounding mode.")
        for key,allowed in (("permitted_translation_methods",ALLOWED_TRANSLATION_METHODS),("permitted_transaction_types",ALLOWED_TRANSACTION_TYPES),("permitted_pricing_methods",ALLOWED_PRICING_METHODS)):
            value=settings.get(key,[])
            if not isinstance(value,list) or not value or set(value)-allowed:error(key,"Contains unsupported or no values.")
        sides=settings.get("approval_sides")
        if not isinstance(sides,list) or not sides or set(sides)-{"source","target"}:error("approval_sides","Must contain source and/or target.")
        limits=settings.get("maximum_transaction_amount_by_currency",{})
        if not isinstance(limits,Mapping) or not limits:error("maximum_transaction_amount_by_currency","At least one limit is required.")
        else:
            for code,value in limits.items():
                if code not in ALLOWED_CURRENCIES:error("maximum_transaction_amount_by_currency",f"Unsupported currency {code}.")
                else:
                    try:
                        if _decimal(value,"limit",positive=True)>Decimal("999999999999999.9999"):error("maximum_transaction_amount_by_currency",f"Limit for {code} is unsafe.")
                    except ValidationError:error("maximum_transaction_amount_by_currency",f"Limit for {code} must be positive.")
        if settings.get("default_currency") not in ALLOWED_CURRENCIES:error("default_currency","Unsupported currency.")
        ledger=settings.get("ledger_accounts")
        required_accounts={"intercompany_receivable","intercompany_payable","intercompany_revenue","intercompany_expense"}
        if not isinstance(ledger,Mapping) or set(ledger)!=required_accounts or any(not isinstance(value,str) or not value.strip() or len(value)>20 for value in ledger.values()):error("ledger_accounts","All four account mappings are required and limited to 20 characters.")
        elimination=settings.get("elimination_accounts")
        if not isinstance(elimination,Mapping) or set(elimination)!={"debit","credit"} or any(not isinstance(value,str) or not value.strip() or len(value)>20 for value in elimination.values()) or (isinstance(elimination,Mapping) and elimination.get("debit")==elimination.get("credit")):error("elimination_accounts","Distinct debit and credit accounts are required.")
        return ValidationResult(not errors,{key:tuple(value) for key,value in errors.items()})
    @classmethod
    @transaction.atomic
    def create_draft(cls,tenant_id: Any,actor_id: str,correlation_id: str,environment: str|Mapping[str,Any],settings: Mapping[str,Any]|None=None,change_summary: str|None=None,schema_version: str="1.0") -> MultiCompanyConfigurationVersion:
        if isinstance(environment,Mapping):
            payload=dict(environment);environment=str(payload["environment"]);settings=payload["settings"];change_summary=str(payload["change_summary"]);schema_version=str(payload.get("schema_version","1.0"))
        if settings is None or change_summary is None:raise ValidationError("Configuration settings and change summary are required.")
        result=cls.validate_settings(settings)
        if not result.valid:raise ValidationError(result.errors)
        version=(_tenant_qs(MultiCompanyConfigurationVersion,tenant_id).filter(environment=environment).aggregate(value=Max("version"))["value"] or 0)+1
        return MultiCompanyConfigurationVersion.objects.create(tenant_id=tenant_id,created_by=actor_id,correlation_id=correlation_id,environment=environment,version=version,status="draft",schema_version=schema_version,settings=dict(settings),change_summary=_required_text(change_summary,"change_summary",2000))
    @classmethod
    @transaction.atomic
    def update_draft(cls,tenant_id: Any,version_id: Any,actor_id: str,correlation_id: str,settings: Mapping[str,Any]|int,change_summary: str|Mapping[str,Any]|None=None) -> MultiCompanyConfigurationVersion:
        record=_locked_get(MultiCompanyConfigurationVersion,tenant_id,version_id,deleted=True)
        if record.status!="draft":raise ConflictError("Only draft configuration can be edited")
        if isinstance(settings,int):
            expected_version=settings
            if record.version!=expected_version:raise StaleVersionError(f"Expected version {expected_version}; current version is {record.version}")
            payload=dict(change_summary) if isinstance(change_summary,Mapping) else {}
            settings=payload.get("settings",record.settings);change_summary=payload.get("change_summary")
        result=cls.validate_settings(settings)
        if not result.valid:raise ValidationError(result.errors)
        record.settings=dict(settings);record.correlation_id=correlation_id
        if change_summary is not None:record.change_summary=_required_text(change_summary,"change_summary",2000)
        record.save();return record
    @classmethod
    def validate_draft(cls,tenant_id: Any,version_id: Any) -> ValidationResult:
        record=_get(MultiCompanyConfigurationVersion,tenant_id,version_id,deleted=True)
        if record.status!="draft":raise ConflictError("Only draft configuration can be validated")
        return cls.validate_settings(record.settings)
    @classmethod
    def preview_impact(cls,tenant_id: Any,version_id: Any) -> ConfigurationImpact:
        draft=_get(MultiCompanyConfigurationVersion,tenant_id,version_id,deleted=True);validation=cls.validate_settings(draft.settings)
        active=_tenant_qs(MultiCompanyConfigurationVersion,tenant_id).filter(environment=draft.environment,status="active").first();before=active.settings if active else {}
        changed=tuple(sorted(key for key in set(before)|set(draft.settings) if before.get(key)!=draft.settings.get(key)))
        return ConfigurationImpact(validation.valid,changed,_tenant_qs(Company,tenant_id).filter(is_deleted=False).count(),_tenant_qs(IntercompanyTransaction,tenant_id).filter(status="draft",is_deleted=False).count(),tuple("Existing drafts will be revalidated." for _ in [0] if "maximum_transaction_amount_by_currency" in changed))
    @classmethod
    @transaction.atomic
    def activate(cls,tenant_id: Any,version_id: Any,actor_id: str,correlation_id: str) -> MultiCompanyConfigurationVersion:
        draft=_locked_get(MultiCompanyConfigurationVersion,tenant_id,version_id,deleted=True)
        if draft.status!="draft":raise ConflictError("Only draft configuration can be activated")
        if draft.environment=="production" and draft.created_by==actor_id:raise PermissionDenied("Production configuration author cannot activate their own draft")
        validation=cls.validate_settings(draft.settings)
        if not validation.valid:raise ValidationError(validation.errors)
        active=_tenant_qs(MultiCompanyConfigurationVersion,tenant_id).select_for_update().filter(environment=draft.environment,status="active").first()
        if active:MultiCompanyConfigurationVersion.objects.filter(pk=active.pk).update(status="superseded")
        MultiCompanyConfigurationVersion.objects.filter(pk=draft.pk).update(status="active",activated_by=actor_id,activated_at=timezone.now())
        draft.status="active";draft.activated_by=actor_id;draft.activated_at=timezone.now()
        ConfigurationAuditRecord.objects.create(tenant_id=tenant_id,actor_id=actor_id,environment=draft.environment,action="activate",from_version=active.version if active else None,to_version=draft.version,before=active.settings if active else None,after=draft.settings,correlation_id=correlation_id)
        _event(tenant_id,draft,"multi_company.configuration.activated",actor_id,correlation_id,environment=draft.environment);return draft
    @classmethod
    @transaction.atomic
    def rollback(cls,tenant_id: Any,version_id: Any,actor_id: str,correlation_id: str,payload: Mapping[str,Any]|None=None) -> MultiCompanyConfigurationVersion:
        target=_get(MultiCompanyConfigurationVersion,tenant_id,version_id,deleted=True);active=cls.get_active(tenant_id,target.environment)
        if payload and payload.get("environment")!=target.environment:raise ValidationError({"environment":"Must match the target version."})
        summary=str(payload.get("change_summary")) if payload and payload.get("change_summary") else f"Rollback to version {target.version}"
        new=cls.create_draft(tenant_id,actor_id,correlation_id,target.environment,target.settings,summary,target.schema_version)
        now=timezone.now()
        MultiCompanyConfigurationVersion.objects.filter(pk=active.pk).update(status="superseded")
        MultiCompanyConfigurationVersion.objects.filter(pk=new.pk).update(
            supersedes=active,status="active",activated_by=actor_id,activated_at=now
        )
        new.supersedes=active;new.status="active";new.activated_by=actor_id;new.activated_at=now
        MultiCompanyConfigurationVersion.objects.filter(pk=target.pk).exclude(status="active").update(status="rolled_back")
        activated=new
        ConfigurationAuditRecord.objects.create(tenant_id=tenant_id,actor_id=actor_id,environment=target.environment,action="rollback",from_version=active.version,to_version=activated.version,before=active.settings,after=target.settings,correlation_id=correlation_id)
        _event(tenant_id,activated,"multi_company.configuration.rolled_back",actor_id,correlation_id,target_version=target.version);return activated
    @staticmethod
    def _sign(document: Mapping[str,Any]) -> str:
        key=os.environ.get("MULTI_COMPANY_EXPORT_SIGNING_KEY")
        if not key:raise ConfigurationUnavailable("Configuration export signing key is unavailable")
        canonical=json.dumps(document,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        return hmac.new(key.encode(),canonical,hashlib.sha256).hexdigest()
    @classmethod
    def export_document(cls,tenant_id: Any,environment: str,version: int|None=None,actor_id: str="system",correlation_id: str="system") -> Mapping[str,Any]:
        record=_tenant_qs(MultiCompanyConfigurationVersion,tenant_id).filter(environment=environment,**({"version":version} if version else {"status":"active"})).first()
        if not record:raise NotFoundError("Configuration version was not found")
        body={"format":"saraise.multi-company.configuration","format_version":"1.0","environment":environment,"schema_version":record.schema_version,"source_version":record.version,"settings":record.settings,"change_summary":record.change_summary}
        document={**body,"signature":cls._sign(body)}
        ConfigurationAuditRecord.objects.create(tenant_id=tenant_id,actor_id=actor_id,environment=environment,action="export",from_version=record.version,to_version=record.version,before=None,after=None,correlation_id=correlation_id)
        return document
    @classmethod
    @transaction.atomic
    def import_document(cls,tenant_id: Any,actor_id: str,correlation_id: str,document: Mapping[str,Any]) -> MultiCompanyConfigurationVersion:
        if "document" in document:
            wrapper=dict(document);document=wrapper["document"]
            if not isinstance(document,Mapping):raise ValidationError({"document":"Must be an object."})
            if wrapper.get("environment") and document.get("environment")!=wrapper["environment"]:raise ValidationError({"environment":"Does not match the signed document."})
        if document.get("format")!="saraise.multi-company.configuration" or document.get("format_version")!="1.0":raise ValidationError("Unsupported configuration document.")
        body={key:value for key,value in document.items() if key!="signature"}
        if not hmac.compare_digest(str(document.get("signature","")),cls._sign(body)):raise ValidationError("Configuration document signature is invalid.")
        draft=cls.create_draft(tenant_id,actor_id,correlation_id,body["environment"],body["settings"],f"Imported: {body.get('change_summary','configuration')}",body["schema_version"])
        ConfigurationAuditRecord.objects.create(tenant_id=tenant_id,actor_id=actor_id,environment=draft.environment,action="import",from_version=None,to_version=draft.version,before=None,after=draft.settings,correlation_id=correlation_id);return draft


__all__=[name for name in globals() if not name.startswith("_")]
