"""Tenant-governed CRM application services.

All writes, state commands, relationship checks, forecasts, and integration
calls enter the canonical tenant context here.  HTTP views are deliberately
thin adapters over this module.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, QuerySet, Sum
from django.utils import timezone
from rest_framework import status

from src.core.api.results import OperationResult
from src.core.middleware.correlation import get_correlation_id
from src.core.state_machine import StateMachineError
from src.core.tenancy import tenant_context

from .integrations import (
    CRMIntegrationError,
    ExtensionContext,
    IntegrationUnavailable,
    InvalidIntegrationResponse,
    extension_registry,
    get_revenue_prediction_client,
    get_scoring_client,
)
from .jobs import publish_crm_event
from .models import (
    Account,
    AccountType,
    Activity,
    ActivityType,
    Contact,
    Lead,
    LeadScoreSource,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    OpportunityStatus,
    RELATED_MODELS,
    RelatedToType,
)
from .state_machines import apply_lead_command, apply_opportunity_command

logger = logging.getLogger("saraise.crm")


class CRMServiceError(ValidationError):
    """Stable domain failure translated by the governed API boundary."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "CRM_VALIDATION_ERROR",
        http_status: int = status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        self.error_code = code
        self.http_status = http_status
        self.public_message = message
        self.detail = dict(detail or {})
        super().__init__(message, code=code)


class StaleVersionError(CRMServiceError):
    def __init__(self, *, expected: int, current: int) -> None:
        super().__init__(
            "The record changed after it was loaded.",
            code="VERSION_CONFLICT",
            http_status=status.HTTP_409_CONFLICT,
            detail={"expected_version": expected, "current_version": current},
        )


@dataclass(frozen=True, slots=True)
class AccountHierarchyNode:
    id: UUID
    name: str
    account_type: str
    children: tuple["AccountHierarchyNode", ...] = ()


@dataclass(frozen=True, slots=True)
class DuplicateAccountResult:
    local_matches: tuple[Account, ...]
    external_matches: tuple[Mapping[str, object], ...]
    enrichment_status: str


@dataclass(frozen=True, slots=True)
class CurrencyForecast:
    currency: str
    total_pipeline_value: Decimal
    weighted_pipeline_value: Decimal
    opportunity_count: int


@dataclass(frozen=True, slots=True)
class Forecast:
    currencies: tuple[CurrencyForecast, ...]
    period_days: int


@dataclass(frozen=True, slots=True)
class WinRate:
    win_rate: Decimal
    won_count: int
    lost_count: int
    total_closed: int
    period_days: int


@dataclass(frozen=True, slots=True)
class StageForecast:
    stage: str
    currency: str
    total_value: Decimal
    weighted_value: Decimal
    opportunity_count: int


@dataclass(frozen=True, slots=True)
class RevenuePrediction:
    provider: str
    model: str
    amount: Decimal
    currency: str
    confidence: Decimal | None
    factors: Mapping[str, object]
    as_of: str
    period_days: int


@dataclass(frozen=True, slots=True)
class LeadConversionResult:
    lead: Lead
    account: Account
    contact: Contact | None
    opportunity: Opportunity


_IMMUTABLE_COMMON = {
    "id",
    "tenant_id",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "version",
    "is_deleted",
    "deleted_at",
}

_STAGE_PROBABILITY = {
    OpportunityStage.PROSPECTING: 10,
    OpportunityStage.QUALIFICATION: 20,
    OpportunityStage.NEEDS_ANALYSIS: 40,
    OpportunityStage.PROPOSAL: 60,
    OpportunityStage.NEGOTIATION: 80,
    OpportunityStage.CLOSED_WON: 100,
    OpportunityStage.CLOSED_LOST: 0,
}


def _actor(actor_id: str | UUID | None) -> str | None:
    if actor_id is None:
        return None
    value = str(actor_id).strip()
    if not value or len(value) > 255:
        raise CRMServiceError("Actor identifier is invalid.", code="INVALID_ACTOR")
    return value


def _correlation(correlation_id: str | None = None) -> str:
    value = (correlation_id or get_correlation_id() or f"req_{uuid.uuid4().hex[:24]}").strip()
    if not value or len(value) > 64:
        raise CRMServiceError("Correlation identifier is invalid.", code="INVALID_CORRELATION_ID")
    return value


def _validate_version(instance: Any, expected_version: int) -> None:
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
        raise CRMServiceError("Expected version must be a positive integer.", code="INVALID_VERSION")
    if instance.version != expected_version:
        raise StaleVersionError(expected=expected_version, current=instance.version)


def _assign(instance: Any, data: Mapping[str, object], *, forbidden: set[str]) -> list[str]:
    unknown = set(data) - {field.name for field in instance._meta.fields}
    if unknown:
        raise CRMServiceError(
            "One or more fields are not supported.",
            code="UNKNOWN_FIELD",
            detail={"fields": sorted(unknown)},
        )
    denied = set(data) & (_IMMUTABLE_COMMON | forbidden)
    if denied:
        raise CRMServiceError(
            "One or more fields are immutable.",
            code="IMMUTABLE_FIELD",
            detail={"fields": sorted(denied)},
        )
    changed: list[str] = []
    for field, value in data.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed.append(field)
    return changed


def _soft_delete(instance: Any, *, actor_id: str | UUID | None, expected_version: int) -> None:
    _validate_version(instance, expected_version)
    instance.is_deleted = True
    instance.deleted_at = timezone.now()
    instance.updated_by = _actor(actor_id)
    instance.save(update_fields=["is_deleted", "deleted_at", "updated_by"])


def _event(
    tenant_id: UUID,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    actor_id: str | UUID | None,
    correlation_id: str | None,
    payload: Mapping[str, object] | None = None,
) -> None:
    publish_crm_event(
        tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_id=actor_id,
        correlation_id=_correlation(correlation_id),
        payload=payload,
    )


def _log(operation: str, outcome: str, started: float, **context: object) -> None:
    logger.info(
        "crm service operation",
        extra={
            "event": "crm.service.operation",
            "module_name": "crm",
            "operation": operation,
            "outcome": outcome,
            "duration_ms": round((monotonic() - started) * 1000, 3),
            **context,
        },
    )


class LeadService:
    """Lead lifecycle, assignment, verified scoring, and conversion."""

    @staticmethod
    def _rule_score(data: Mapping[str, object]) -> tuple[int, str, dict[str, object]]:
        factors: dict[str, int] = {}
        for field, points in (("company", 20), ("email", 15), ("phone", 10), ("title", 10)):
            if data.get(field):
                factors[f"has_{field}"] = points
        source_points = {"referral": 25, "event": 20, "web": 15, "social": 10, "api": 5}
        source = str(data.get("source") or "").lower()
        if source in source_points:
            factors["source"] = source_points[source]
        score = min(sum(factors.values()), 100)
        grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"
        return score, grade, {"method": "rules_v1", "factors": factors, "evidence_count": len(factors)}

    @classmethod
    def create_lead(
        cls,
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str | UUID | None = None,
        correlation_id: str | None = None,
        created_by: str | UUID | None = None,
    ) -> Lead:
        started = monotonic()
        actor = _actor(actor_id if actor_id is not None else created_by)
        correlation = _correlation(correlation_id)
        forbidden = set(data) & (_IMMUTABLE_COMMON | {"status", "score", "grade", "score_source", "score_explanation", "transition_history", "converted_at", "converted_to_opportunity_id"})
        if forbidden:
            raise CRMServiceError("Server-owned lead fields cannot be supplied.", code="IMMUTABLE_FIELD", detail={"fields": sorted(forbidden)})
        score, grade, explanation = cls._rule_score(data)
        with tenant_context(tenant_id), transaction.atomic():
            lead = Lead(
                tenant_id=tenant_id,
                created_by=actor,
                updated_by=actor,
                score=score,
                grade=grade,
                score_source=LeadScoreSource.RULES,
                score_explanation=explanation,
                **dict(data),
            )
            lead.save()
            _event(
                tenant_id,
                event_type="crm.lead.created",
                aggregate_type="lead",
                aggregate_id=lead.id,
                actor_id=actor,
                correlation_id=correlation,
                payload={"source": lead.source, "score": lead.score, "grade": lead.grade, "score_source": lead.score_source, "version": lead.version},
            )
        _log("create_lead", "succeeded", started, tenant_id=str(tenant_id), aggregate_id=str(lead.id), correlation_id=correlation)
        return lead

    @staticmethod
    def update_lead(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        data: Mapping[str, object],
        expected_version: int,
        actor_id: str | UUID | None,
    ) -> Lead:
        with tenant_context(tenant_id), transaction.atomic():
            lead = Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(lead, expected_version)
            changed = _assign(lead, data, forbidden={"status", "score", "grade", "score_source", "score_explanation", "transition_history", "converted_at", "converted_to_opportunity_id"})
            if changed:
                lead.updated_by = _actor(actor_id)
                if set(changed) & {"company", "email", "phone", "title", "source", "metadata"}:
                    lead.score, lead.grade, lead.score_explanation = LeadService._rule_score({field.name: getattr(lead, field.name) for field in lead._meta.fields})
                    lead.score_source = LeadScoreSource.RULES
                    changed += ["score", "grade", "score_explanation", "score_source"]
                lead.save(update_fields=set(changed) | {"updated_by"})
                _event(tenant_id, event_type="crm.lead.updated", aggregate_type="lead", aggregate_id=lead.id, actor_id=actor_id, correlation_id=None, payload={"changed_fields": sorted(set(changed)), "version": lead.version})
            return lead

    @staticmethod
    def delete_lead(tenant_id: UUID, *, lead_id: UUID, expected_version: int, actor_id: str | UUID | None) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            lead = Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            _soft_delete(lead, actor_id=actor_id, expected_version=expected_version)
            _event(tenant_id, event_type="crm.lead.deleted", aggregate_type="lead", aggregate_id=lead.id, actor_id=actor_id, correlation_id=None, payload={"version": lead.version})

    @staticmethod
    def transition_lead(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        command: str,
        transition_key: str,
        context: Mapping[str, object],
        actor_id: str | UUID | None,
        expected_version: int | None = None,
    ) -> Lead:
        with tenant_context(tenant_id), transaction.atomic():
            before = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            try:
                lead = apply_lead_command(
                    tenant_id=tenant_id,
                    lead_id=lead_id,
                    command=command,
                    transition_key=transition_key,
                    context=context,
                    actor_id=_actor(actor_id),
                    correlation_id=_correlation(),
                    expected_version=expected_version,
                )
            except StateMachineError as exc:
                raise CRMServiceError(str(exc), code="ILLEGAL_TRANSITION", http_status=status.HTTP_409_CONFLICT) from exc
            _event(tenant_id, event_type="crm.lead.status_changed", aggregate_type="lead", aggregate_id=lead.id, actor_id=actor_id, correlation_id=None, payload={"from_status": before.status, "to_status": lead.status, "command": command, "transition_key": transition_key, "version": lead.version})
            return lead

    @staticmethod
    def score_lead(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        actor_id: str | UUID | None = None,
        correlation_id: str | None = None,
    ) -> OperationResult[Lead]:
        correlation = _correlation(correlation_id)
        with tenant_context(tenant_id):
            lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            payload = {
                "lead_id": str(lead.id),
                "company_present": bool(lead.company),
                "email_present": bool(lead.email),
                "phone_present": bool(lead.phone),
                "title_present": bool(lead.title),
                "source": lead.source,
                "current_score": lead.score,
            }
            try:
                result = get_scoring_client().score_lead(payload, correlation_id=correlation)
            except IntegrationUnavailable as exc:
                return OperationResult.unavailable(capability="crm.lead_scoring", message="Lead scoring provider is unavailable.", detail={"code": exc.code})
            except (InvalidIntegrationResponse, CRMIntegrationError) as exc:
                return OperationResult.failed(code=exc.code, message="Lead scoring could not be verified.", detail={"provider_status": "invalid"}, http_status=status.HTTP_503_SERVICE_UNAVAILABLE)
            with transaction.atomic():
                lead = Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
                lead.score = result.score
                lead.grade = result.grade
                lead.score_source = LeadScoreSource.PROVIDER
                lead.score_explanation = {"provider": result.provider, "model": result.model, "factors": dict(result.factors), "provider_request_id": result.provider_request_id}
                lead.updated_by = _actor(actor_id)
                lead.save(update_fields=["score", "grade", "score_source", "score_explanation", "updated_by"])
                _event(tenant_id, event_type="crm.lead.scored", aggregate_type="lead", aggregate_id=lead.id, actor_id=actor_id, correlation_id=correlation, payload={"score": lead.score, "grade": lead.grade, "score_source": lead.score_source, "provider": result.provider, "model": result.model, "evidence_factors": sorted(result.factors), "version": lead.version})
            return OperationResult.succeeded(lead, evidence={"persisted_version": lead.version, "provider_request_id": result.provider_request_id or correlation}, provider=result.provider)

    @staticmethod
    def assign_lead(tenant_id: UUID, *, lead_id: UUID, owner_id: UUID, expected_version: int, actor_id: str | UUID | None) -> Lead:
        if not isinstance(owner_id, UUID):
            try:
                owner_id = UUID(str(owner_id))
            except (TypeError, ValueError) as exc:
                raise CRMServiceError("Owner must be a valid assignable UUID.", code="INVALID_OWNER") from exc
        return LeadService.update_lead(tenant_id, lead_id=lead_id, data={"owner_id": owner_id}, expected_version=expected_version, actor_id=actor_id)

    @staticmethod
    def convert_lead(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        data: Mapping[str, object],
        expected_version: int,
        transition_key: str,
        actor_id: str | UUID | None,
        correlation_id: str | None,
    ) -> LeadConversionResult:
        correlation = _correlation(correlation_id)
        amount = Decimal(str(data.get("amount", "0")))
        if amount <= 0:
            raise CRMServiceError("Opportunity amount must be positive.", code="INVALID_AMOUNT")
        with tenant_context(tenant_id), transaction.atomic():
            lead = Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(lead, expected_version)
            if lead.status != LeadStatus.QUALIFIED:
                raise CRMServiceError("Only qualified leads can be converted.", code="ILLEGAL_TRANSITION", http_status=status.HTTP_409_CONFLICT)
            account_id = data.get("account_id")
            create_new = data.get("create_new_account") is True
            if bool(account_id) == create_new:
                raise CRMServiceError("Choose exactly one existing-account or new-account decision.", code="CONVERSION_DECISION_REQUIRED")
            if account_id:
                account = Account.objects.get(id=account_id, tenant_id=tenant_id, is_deleted=False)
            else:
                if not lead.company.strip():
                    raise CRMServiceError("A company is required to create an account.", code="ACCOUNT_REQUIRED")
                existing = Account.objects.filter(tenant_id=tenant_id, is_deleted=False, name__iexact=lead.company.strip()).first()
                account = existing or AccountService.create_account(tenant_id, data={"name": lead.company, "owner_id": lead.owner_id}, actor_id=actor_id, correlation_id=correlation)
            contact = None
            if lead.email:
                contact = Contact.objects.filter(tenant_id=tenant_id, account_id=account.id, email__iexact=lead.email, is_deleted=False).first()
            if contact is None and (lead.email or lead.first_name or lead.last_name):
                contact = ContactService.create_contact(tenant_id, data={"account_id": account.id, "first_name": lead.first_name, "last_name": lead.last_name, "email": lead.email, "phone": lead.phone, "title": lead.title, "owner_id": lead.owner_id}, actor_id=actor_id, correlation_id=correlation)
            opportunity = OpportunityService.create_opportunity(
                tenant_id,
                data={"account_id": account.id, "primary_contact_id": contact.id if contact else None, "name": str(data.get("name") or f"{account.name} opportunity"), "amount": amount, "currency": str(data.get("currency") or "USD"), "stage": OpportunityStage.QUALIFICATION, "probability": _STAGE_PROBABILITY[OpportunityStage.QUALIFICATION], "close_date": data.get("close_date"), "owner_id": lead.owner_id},
                actor_id=actor_id,
                correlation_id=correlation,
            )
            lead = apply_lead_command(
                tenant_id,
                lead_id=lead.id,
                command="convert",
                transition_key=transition_key,
                context={
                    "account_id": account.id,
                    "opportunity_id": opportunity.id,
                    "opportunity_amount": amount,
                },
                actor_id=_actor(actor_id),
                correlation_id=correlation,
                expected_version=lead.version,
                opportunity_id=opportunity.id,
            )
            _event(tenant_id, event_type="crm.lead.converted", aggregate_type="lead", aggregate_id=lead.id, actor_id=actor_id, correlation_id=correlation, payload={"account_id": account.id, "contact_id": contact.id if contact else None, "opportunity_id": opportunity.id, "amount": amount, "currency": opportunity.currency, "transition_key": transition_key, "conversion_decision": "existing" if account_id else "created", "version": lead.version})
            return LeadConversionResult(lead, account, contact, opportunity)


class AccountService:
    @staticmethod
    def create_account(tenant_id: UUID, *, data: Mapping[str, object], actor_id: str | UUID | None = None, correlation_id: str | None = None, created_by: str | UUID | None = None) -> Account:
        actor = _actor(actor_id if actor_id is not None else created_by)
        if set(data) & _IMMUTABLE_COMMON:
            raise CRMServiceError("Server-owned account fields cannot be supplied.", code="IMMUTABLE_FIELD")
        name = str(data.get("name") or "").strip()
        with tenant_context(tenant_id), transaction.atomic():
            if Account.objects.filter(tenant_id=tenant_id, name__iexact=name, is_deleted=False).exists():
                raise CRMServiceError("An active account with this name already exists.", code="DUPLICATE_ACCOUNT", http_status=status.HTTP_409_CONFLICT)
            account = Account(tenant_id=tenant_id, created_by=actor, updated_by=actor, **dict(data))
            account.save()
            _event(tenant_id, event_type="crm.account.created", aggregate_type="account", aggregate_id=account.id, actor_id=actor, correlation_id=correlation_id, payload={"version": account.version, "owner_id": account.owner_id})
            return account

    @staticmethod
    def update_account(tenant_id: UUID, *, account_id: UUID, data: Mapping[str, object], expected_version: int, actor_id: str | UUID | None) -> Account:
        with tenant_context(tenant_id), transaction.atomic():
            account = Account.objects.select_for_update().get(id=account_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(account, expected_version)
            changed = _assign(account, data, forbidden=set())
            if changed:
                account.updated_by = _actor(actor_id)
                account.save(update_fields=set(changed) | {"updated_by"})
                _event(tenant_id, event_type="crm.account.updated", aggregate_type="account", aggregate_id=account.id, actor_id=actor_id, correlation_id=None, payload={"changed_fields": changed, "version": account.version})
            return account

    @staticmethod
    def delete_account(tenant_id: UUID, *, account_id: UUID, expected_version: int, actor_id: str | UUID | None) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            account = Account.objects.select_for_update().get(id=account_id, tenant_id=tenant_id, is_deleted=False)
            if Account.objects.filter(tenant_id=tenant_id, parent_account_id=account.id, is_deleted=False).exists():
                raise CRMServiceError("Cannot delete an account with active child accounts.", code="ACCOUNT_HAS_CHILDREN", http_status=status.HTTP_409_CONFLICT)
            if Opportunity.objects.filter(tenant_id=tenant_id, account_id=account.id, status=OpportunityStatus.OPEN, is_deleted=False).exists():
                raise CRMServiceError("Cannot delete account with open opportunities.", code="ACCOUNT_HAS_OPEN_OPPORTUNITIES", http_status=status.HTTP_409_CONFLICT)
            _soft_delete(account, actor_id=actor_id, expected_version=expected_version)
            _event(tenant_id, event_type="crm.account.deleted", aggregate_type="account", aggregate_id=account.id, actor_id=actor_id, correlation_id=None, payload={"version": account.version})

    @staticmethod
    def get_hierarchy(tenant_id: UUID, *, account_id: UUID) -> AccountHierarchyNode:
        with tenant_context(tenant_id):
            accounts = list(Account.objects.filter(tenant_id=tenant_id, is_deleted=False).only("id", "name", "account_type", "parent_account_id"))
            by_id = {item.id: item for item in accounts}
            if account_id not in by_id:
                raise Account.DoesNotExist
            children: dict[UUID, list[Account]] = {}
            for item in accounts:
                if item.parent_account_id:
                    children.setdefault(item.parent_account_id, []).append(item)
            def node(item: Account, depth: int = 1) -> AccountHierarchyNode:
                if depth > 3:
                    raise CRMServiceError("Stored hierarchy exceeds the supported depth.", code="INVALID_HIERARCHY")
                return AccountHierarchyNode(item.id, item.name, item.account_type, tuple(node(child, depth + 1) for child in sorted(children.get(item.id, []), key=lambda value: value.name.casefold())))
            return node(by_id[account_id])

    get_account_hierarchy = get_hierarchy

    @staticmethod
    def find_duplicates(tenant_id: UUID, *, name: str, website: str = "") -> DuplicateAccountResult:
        normalized = name.strip()
        with tenant_context(tenant_id):
            predicate = Q(name__iexact=normalized)
            if website.strip():
                predicate |= Q(website__iexact=website.strip())
            local = tuple(Account.objects.filter(predicate, tenant_id=tenant_id, is_deleted=False).order_by("name", "id"))
            providers = extension_registry.resolve("account_enrichment")
            if not providers:
                return DuplicateAccountResult(local, (), "unavailable")
            context = ExtensionContext(tenant_id, None, _correlation(), f"duplicates:{normalized.casefold()}")
            external: list[Mapping[str, object]] = []
            domain = urlsplit(website).hostname if website else None
            try:
                for provider in providers:
                    for match in provider.find_matches(context, normalized_name=normalized.casefold(), website_domain=domain):
                        external.append({"external_reference": match.external_reference, "confidence": str(match.confidence) if match.confidence is not None else None, "evidence_codes": list(match.evidence_codes)})
            except CRMIntegrationError:
                return DuplicateAccountResult(local, (), "unavailable")
            return DuplicateAccountResult(local, tuple(external), "available")


class ContactService:
    @staticmethod
    def create_contact(tenant_id: UUID, *, data: Mapping[str, object], actor_id: str | UUID | None = None, correlation_id: str | None = None, created_by: str | UUID | None = None, allow_domain_override: bool = False) -> Contact:
        actor = _actor(actor_id if actor_id is not None else created_by)
        if set(data) & (_IMMUTABLE_COMMON | {"engagement_score", "last_contacted_at"}):
            raise CRMServiceError("Server-owned contact fields cannot be supplied.", code="IMMUTABLE_FIELD")
        with tenant_context(tenant_id), transaction.atomic():
            contact = Contact(tenant_id=tenant_id, created_by=actor, updated_by=actor, **dict(data))
            contact._allow_domain_override = allow_domain_override
            contact.save()
            _event(tenant_id, event_type="crm.contact.created", aggregate_type="contact", aggregate_id=contact.id, actor_id=actor, correlation_id=correlation_id, payload={"account_id": contact.account_id, "owner_id": contact.owner_id, "version": contact.version})
            return contact

    @staticmethod
    def update_contact(tenant_id: UUID, *, contact_id: UUID, data: Mapping[str, object], expected_version: int, actor_id: str | UUID | None, allow_domain_override: bool = False) -> Contact:
        with tenant_context(tenant_id), transaction.atomic():
            contact = Contact.objects.select_for_update().get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(contact, expected_version)
            changed = _assign(contact, data, forbidden={"engagement_score", "last_contacted_at"})
            if changed:
                contact._allow_domain_override = allow_domain_override
                contact.updated_by = _actor(actor_id)
                contact.save(update_fields=set(changed) | {"updated_by"})
                _event(tenant_id, event_type="crm.contact.updated", aggregate_type="contact", aggregate_id=contact.id, actor_id=actor_id, correlation_id=None, payload={"changed_fields": changed, "version": contact.version})
            return contact

    @staticmethod
    def delete_contact(tenant_id: UUID, *, contact_id: UUID, expected_version: int, actor_id: str | UUID | None) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            contact = Contact.objects.select_for_update().get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
            _soft_delete(contact, actor_id=actor_id, expected_version=expected_version)
            _event(tenant_id, event_type="crm.contact.deleted", aggregate_type="contact", aggregate_id=contact.id, actor_id=actor_id, correlation_id=None, payload={"version": contact.version})

    @staticmethod
    def recalculate_engagement(tenant_id: UUID, *, contact_id: UUID, as_of: datetime, actor_id: str | UUID | None) -> Contact:
        if timezone.is_naive(as_of):
            raise CRMServiceError("as_of must include a timezone.", code="INVALID_DATETIME")
        with tenant_context(tenant_id), transaction.atomic():
            contact = Contact.objects.select_for_update().get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
            interactions = Activity.objects.filter(tenant_id=tenant_id, related_to_type=RelatedToType.CONTACT, related_to_id=contact.id, activity_type__in=[ActivityType.CALL, ActivityType.EMAIL, ActivityType.MEETING], created_at__lte=as_of, created_at__gte=as_of - timedelta(days=90), is_deleted=False)
            evidence = interactions.aggregate(count=Count("id"))
            contact.engagement_score = min(int(evidence["count"]) * 10, 100)
            latest = interactions.order_by("-completed_at", "-created_at").first()
            if latest:
                contact.last_contacted_at = latest.completed_at or latest.created_at
            contact.updated_by = _actor(actor_id)
            contact.save(update_fields=["engagement_score", "last_contacted_at", "updated_by"])
            return contact

    update_engagement_score = recalculate_engagement

    @staticmethod
    def get_timeline(tenant_id: UUID, *, contact_id: UUID, page: int = 1) -> QuerySet[Activity]:
        if page < 1:
            raise CRMServiceError("Page must be positive.", code="INVALID_PAGE")
        with tenant_context(tenant_id):
            Contact.objects.get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
            return Activity.objects.filter(tenant_id=tenant_id, related_to_type=RelatedToType.CONTACT, related_to_id=contact_id, is_deleted=False).order_by("-created_at", "-id")


class OpportunityService:
    @staticmethod
    def create_opportunity(tenant_id: UUID, *, data: Mapping[str, object], actor_id: str | UUID | None = None, correlation_id: str | None = None, created_by: str | UUID | None = None) -> Opportunity:
        actor = _actor(actor_id if actor_id is not None else created_by)
        forbidden = set(data) & (_IMMUTABLE_COMMON | {"status", "closed_at", "loss_reason", "converted_to_order_id", "last_activity_at", "transition_history"})
        if forbidden:
            raise CRMServiceError("Server-owned opportunity fields cannot be supplied.", code="IMMUTABLE_FIELD", detail={"fields": sorted(forbidden)})
        values = dict(data)
        stage_value = str(values.get("stage") or OpportunityStage.PROSPECTING)
        values["stage"] = stage_value
        values["probability"] = int(values.get("probability", _STAGE_PROBABILITY.get(stage_value, 10)))
        if stage_value not in _STAGE_PROBABILITY or stage_value in {OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST}:
            raise CRMServiceError("New opportunities must use an open stage.", code="INVALID_STAGE")
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity(tenant_id=tenant_id, created_by=actor, updated_by=actor, **values)
            opportunity.save()
            _event(tenant_id, event_type="crm.opportunity.created", aggregate_type="opportunity", aggregate_id=opportunity.id, actor_id=actor, correlation_id=correlation_id, payload={"account_id": opportunity.account_id, "amount": opportunity.amount, "currency": opportunity.currency, "close_date": opportunity.close_date, "owner_id": opportunity.owner_id, "version": opportunity.version})
            return opportunity

    @staticmethod
    def update_opportunity(tenant_id: UUID, *, opportunity_id: UUID, data: Mapping[str, object], expected_version: int, actor_id: str | UUID | None) -> Opportunity:
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity.objects.select_for_update().get(id=opportunity_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(opportunity, expected_version)
            changed = _assign(opportunity, data, forbidden={"stage", "status", "probability", "closed_at", "loss_reason", "converted_to_order_id", "transition_history"})
            if changed:
                opportunity.updated_by = _actor(actor_id)
                opportunity.save(update_fields=set(changed) | {"updated_by"})
                _event(tenant_id, event_type="crm.opportunity.updated", aggregate_type="opportunity", aggregate_id=opportunity.id, actor_id=actor_id, correlation_id=None, payload={"changed_fields": changed, "version": opportunity.version})
            return opportunity

    @staticmethod
    def delete_opportunity(tenant_id: UUID, *, opportunity_id: UUID, expected_version: int, actor_id: str | UUID | None) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity.objects.select_for_update().get(id=opportunity_id, tenant_id=tenant_id, is_deleted=False)
            _soft_delete(opportunity, actor_id=actor_id, expected_version=expected_version)
            _event(tenant_id, event_type="crm.opportunity.deleted", aggregate_type="opportunity", aggregate_id=opportunity.id, actor_id=actor_id, correlation_id=None, payload={"version": opportunity.version})

    @staticmethod
    def transition_stage(tenant_id: UUID, *, opportunity_id: UUID, command: str, transition_key: str, expected_version: int, actor_id: str | UUID | None, reason: str | None = None, allow_backward: bool = False) -> Opportunity:
        with tenant_context(tenant_id), transaction.atomic():
            before = Opportunity.objects.get(id=opportunity_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(before, expected_version)
            if command.startswith("reopen_to_") and not allow_backward:
                raise CRMServiceError("Backward stage movement requires reopen-stage permission.", code="REOPEN_PERMISSION_REQUIRED", http_status=status.HTTP_403_FORBIDDEN)
            try:
                opportunity = apply_opportunity_command(
                    tenant_id,
                    opportunity_id=opportunity_id,
                    command=command,
                    transition_key=transition_key,
                    actor_id=_actor(actor_id),
                    correlation_id=_correlation(),
                    expected_version=expected_version,
                    reason=reason,
                    allow_backward_transition=allow_backward,
                )
            except StateMachineError as exc:
                raise CRMServiceError(str(exc), code="ILLEGAL_TRANSITION", http_status=status.HTTP_409_CONFLICT) from exc
            _event(tenant_id, event_type="crm.opportunity.stage_changed", aggregate_type="opportunity", aggregate_id=opportunity.id, actor_id=actor_id, correlation_id=None, payload={"from_stage": before.stage, "to_stage": opportunity.stage, "command": command, "transition_key": transition_key, "version": opportunity.version})
            return opportunity

    @staticmethod
    def close_won(tenant_id: UUID, *, opportunity_id: UUID, transition_key: str, expected_version: int, actor_id: str | UUID | None) -> Opportunity:
        with tenant_context(tenant_id), transaction.atomic():
            before = Opportunity.objects.select_for_update().get(id=opportunity_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(before, expected_version)
            opportunity = apply_opportunity_command(
                tenant_id,
                opportunity_id=opportunity_id,
                command="close_won",
                transition_key=transition_key,
                actor_id=_actor(actor_id),
                correlation_id=_correlation(),
                expected_version=expected_version,
                confirmed=True,
            )
            account = Account.objects.select_for_update().get(id=opportunity.account_id, tenant_id=tenant_id, is_deleted=False)
            if account.account_type != AccountType.CUSTOMER:
                account.account_type = AccountType.CUSTOMER
                account.updated_by = _actor(actor_id)
                account.save(update_fields=["account_type", "updated_by"])
            ActivityService.create_activity(tenant_id, data={"activity_type": ActivityType.NOTE, "related_to_type": RelatedToType.OPPORTUNITY, "related_to_id": opportunity.id, "subject": "Opportunity closed as won", "owner_id": opportunity.owner_id}, actor_id=actor_id, correlation_id=None, allow_closed_parent=True)
            _event(tenant_id, event_type="crm.opportunity.closed_won", aggregate_type="opportunity", aggregate_id=opportunity.id, actor_id=actor_id, correlation_id=None, payload={"account_id": account.id, "amount": opportunity.amount, "currency": opportunity.currency, "transition_key": transition_key, "version": opportunity.version})
            return opportunity

    @staticmethod
    def close_lost(tenant_id: UUID, *, opportunity_id: UUID, loss_reason: str, transition_key: str, expected_version: int, actor_id: str | UUID | None) -> Opportunity:
        reason = loss_reason.strip()
        if not reason:
            raise CRMServiceError("Loss reason is required.", code="LOSS_REASON_REQUIRED")
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity.objects.select_for_update().get(id=opportunity_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(opportunity, expected_version)
            opportunity = apply_opportunity_command(
                tenant_id,
                opportunity_id=opportunity_id,
                command="close_lost",
                transition_key=transition_key,
                actor_id=_actor(actor_id),
                correlation_id=_correlation(),
                expected_version=expected_version,
                reason=reason,
            )
            ActivityService.create_activity(tenant_id, data={"activity_type": ActivityType.NOTE, "related_to_type": RelatedToType.OPPORTUNITY, "related_to_id": opportunity.id, "subject": "Opportunity closed as lost", "outcome": "lost", "owner_id": opportunity.owner_id}, actor_id=actor_id, correlation_id=None, allow_closed_parent=True)
            _event(tenant_id, event_type="crm.opportunity.closed_lost", aggregate_type="opportunity", aggregate_id=opportunity.id, actor_id=actor_id, correlation_id=None, payload={"account_id": opportunity.account_id, "amount": opportunity.amount, "currency": opportunity.currency, "loss_code": "seller_recorded", "transition_key": transition_key, "version": opportunity.version})
            return opportunity

    @staticmethod
    def acknowledge_sales_order(
        tenant_id: UUID,
        *,
        opportunity_id: UUID,
        order_id: UUID,
        acknowledgement_id: UUID,
        idempotency_key: str,
        actor_id: str | UUID | None,
        correlation_id: str | None,
    ) -> Opportunity:
        """Link a won deal only after a verified durable acknowledgement."""

        if not idempotency_key.strip():
            raise CRMServiceError("Acknowledgement idempotency key is required.", code="INVALID_IDEMPOTENCY_KEY")
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity.objects.select_for_update().get(
                id=opportunity_id, tenant_id=tenant_id, is_deleted=False
            )
            if opportunity.status != OpportunityStatus.WON:
                raise CRMServiceError(
                    "Only a won opportunity can be linked to a sales order.",
                    code="OPPORTUNITY_NOT_WON",
                    http_status=status.HTTP_409_CONFLICT,
                )
            stored_ack = str(opportunity.metadata.get("sales_order_acknowledgement_id") or "")
            stored_key = str(opportunity.metadata.get("sales_order_idempotency_key") or "")
            if opportunity.converted_to_order_id is not None:
                if (
                    opportunity.converted_to_order_id == order_id
                    and stored_ack == str(acknowledgement_id)
                    and stored_key == idempotency_key
                ):
                    return opportunity
                raise CRMServiceError(
                    "Opportunity is already linked to another verified acknowledgement.",
                    code="ORDER_ACKNOWLEDGEMENT_CONFLICT",
                    http_status=status.HTTP_409_CONFLICT,
                )
            opportunity.converted_to_order_id = order_id
            opportunity.metadata = {
                **opportunity.metadata,
                "sales_order_acknowledgement_id": str(acknowledgement_id),
                "sales_order_idempotency_key": idempotency_key,
            }
            opportunity.updated_by = _actor(actor_id)
            opportunity.save(update_fields=["converted_to_order_id", "metadata", "updated_by"])
            _event(
                tenant_id,
                event_type="crm.opportunity.order_acknowledged",
                aggregate_type="opportunity",
                aggregate_id=opportunity.id,
                actor_id=actor_id,
                correlation_id=correlation_id,
                payload={
                    "order_id": order_id,
                    "acknowledgement_id": acknowledgement_id,
                    "opportunity_id": opportunity.id,
                    "version": opportunity.version,
                },
            )
            return opportunity


class ActivityService:
    @staticmethod
    def _validate_parent(tenant_id: UUID, related_type: str, related_id: UUID, *, allow_closed: bool = False) -> Any:
        model = RELATED_MODELS.get(related_type)
        if model is None:
            raise CRMServiceError("Unsupported related entity type.", code="INVALID_RELATION_TYPE")
        parent = model.objects.filter(id=related_id, tenant_id=tenant_id, is_deleted=False).first()
        if parent is None:
            raise CRMServiceError("Related CRM record was not found.", code="RELATED_RECORD_NOT_FOUND", http_status=status.HTTP_404_NOT_FOUND)
        if isinstance(parent, Opportunity) and parent.status != OpportunityStatus.OPEN and not allow_closed:
            raise CRMServiceError("Activities on closed opportunities are immutable.", code="ACTIVITY_IMMUTABLE", http_status=status.HTTP_409_CONFLICT)
        return parent

    @staticmethod
    def create_activity(tenant_id: UUID, *, data: Mapping[str, object], actor_id: str | UUID | None = None, correlation_id: str | None = None, created_by: str | UUID | None = None, allow_closed_parent: bool = False) -> Activity:
        actor = _actor(actor_id if actor_id is not None else created_by)
        if set(data) & (_IMMUTABLE_COMMON | {"completed", "completed_at"}):
            raise CRMServiceError("Server-owned activity fields cannot be supplied.", code="IMMUTABLE_FIELD")
        related_type = str(data.get("related_to_type") or "")
        related_id = data.get("related_to_id")
        with tenant_context(tenant_id), transaction.atomic():
            parent = ActivityService._validate_parent(tenant_id, related_type, related_id, allow_closed=allow_closed_parent)
            activity = Activity(tenant_id=tenant_id, created_by=actor, updated_by=actor, **dict(data))
            activity.save()
            now = timezone.now()
            if isinstance(parent, Opportunity):
                Opportunity.objects.filter(pk=parent.pk, tenant_id=tenant_id).update(last_activity_at=now, updated_at=now, version=F("version") + 1)
            elif isinstance(parent, Contact) and activity.activity_type in {ActivityType.CALL, ActivityType.EMAIL, ActivityType.MEETING}:
                ContactService.recalculate_engagement(tenant_id, contact_id=parent.id, as_of=now, actor_id=actor)
            _event(tenant_id, event_type="crm.activity.created", aggregate_type="activity", aggregate_id=activity.id, actor_id=actor, correlation_id=correlation_id, payload={"activity_type": activity.activity_type, "related_to_type": activity.related_to_type, "related_to_id": activity.related_to_id, "owner_id": activity.owner_id, "version": activity.version})
            return activity

    @staticmethod
    def update_activity(tenant_id: UUID, *, activity_id: UUID, data: Mapping[str, object], expected_version: int, actor_id: str | UUID | None) -> Activity:
        with tenant_context(tenant_id), transaction.atomic():
            activity = Activity.objects.select_for_update().get(id=activity_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(activity, expected_version)
            if activity.completed:
                raise CRMServiceError("Completed activities cannot be edited.", code="ACTIVITY_IMMUTABLE", http_status=status.HTTP_409_CONFLICT)
            ActivityService._validate_parent(tenant_id, activity.related_to_type, activity.related_to_id)
            changed = _assign(activity, data, forbidden={"related_to_type", "related_to_id", "completed", "completed_at"})
            if changed:
                activity.updated_by = _actor(actor_id)
                activity.save(update_fields=set(changed) | {"updated_by"})
                _event(tenant_id, event_type="crm.activity.updated", aggregate_type="activity", aggregate_id=activity.id, actor_id=actor_id, correlation_id=None, payload={"changed_fields": changed, "version": activity.version})
            return activity

    @staticmethod
    def complete_activity(tenant_id: UUID, *, activity_id: UUID, transition_key: str, expected_version: int, actor_id: str | UUID | None) -> Activity:
        with tenant_context(tenant_id), transaction.atomic():
            activity = Activity.objects.select_for_update().get(id=activity_id, tenant_id=tenant_id, is_deleted=False)
            existing_key = activity.metadata.get("completion_transition_key")
            if activity.completed:
                if existing_key == transition_key:
                    return activity
                raise CRMServiceError("Activity is already completed under another key.", code="IDEMPOTENCY_CONFLICT", http_status=status.HTTP_409_CONFLICT)
            _validate_version(activity, expected_version)
            activity.completed = True
            activity.completed_at = timezone.now()
            activity.updated_by = _actor(actor_id)
            activity.metadata = {**activity.metadata, "completion_transition_key": transition_key}
            activity.save(update_fields=["completed", "completed_at", "updated_by", "metadata"])
            _event(tenant_id, event_type="crm.activity.completed", aggregate_type="activity", aggregate_id=activity.id, actor_id=actor_id, correlation_id=None, payload={"completed": True, "transition_key": transition_key, "version": activity.version})
            return activity

    @staticmethod
    def delete_activity(tenant_id: UUID, *, activity_id: UUID, expected_version: int, actor_id: str | UUID | None, is_administrator: bool = False) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            activity = Activity.objects.select_for_update().get(id=activity_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(activity, expected_version)
            activity._allow_admin_delete = is_administrator
            activity.is_deleted = True
            activity.deleted_at = timezone.now()
            activity.updated_by = _actor(actor_id)
            activity.save(update_fields=["is_deleted", "deleted_at", "updated_by"])
            _event(tenant_id, event_type="crm.activity.deleted", aggregate_type="activity", aggregate_id=activity.id, actor_id=actor_id, correlation_id=None, payload={"version": activity.version})

    @staticmethod
    def get_timeline(tenant_id: UUID, *, related_to_type: str, related_to_id: UUID) -> QuerySet[Activity]:
        with tenant_context(tenant_id):
            ActivityService._validate_parent(tenant_id, related_to_type, related_to_id, allow_closed=True)
            return Activity.objects.filter(tenant_id=tenant_id, related_to_type=related_to_type, related_to_id=related_to_id, is_deleted=False).order_by("-created_at", "-id")

    get_activity_timeline = get_timeline

    @staticmethod
    def sync_external_activity(tenant_id: UUID, *, event: Mapping[str, object], idempotency_key: str, correlation_id: str) -> Activity:
        required = {"activity_type", "related_to_type", "related_to_id", "subject", "external_id"}
        missing = required - set(event)
        if missing:
            raise CRMServiceError("External activity event is incomplete.", code="INVALID_EXTERNAL_EVENT", detail={"missing": sorted(missing)})
        with tenant_context(tenant_id), transaction.atomic():
            existing = Activity.objects.select_for_update().filter(tenant_id=tenant_id, activity_type=event["activity_type"], external_id=event["external_id"], is_deleted=False).first()
            if existing:
                stored_key = existing.metadata.get("external_idempotency_key")
                if stored_key == idempotency_key:
                    return existing
                raise CRMServiceError("External activity identity was reused with different delivery evidence.", code="IDEMPOTENCY_CONFLICT", http_status=status.HTTP_409_CONFLICT)
            data = dict(event)
            data["metadata"] = {**dict(data.get("metadata") or {}), "external_idempotency_key": idempotency_key}
            activity = ActivityService.create_activity(tenant_id, data=data, actor_id=None, correlation_id=correlation_id)
            _event(tenant_id, event_type="crm.activity.external_synced", aggregate_type="activity", aggregate_id=activity.id, actor_id=None, correlation_id=correlation_id, payload={"activity_type": activity.activity_type, "external_id": activity.external_id, "related_to_type": activity.related_to_type, "related_to_id": activity.related_to_id, "version": activity.version})
            return activity


class ForecastingService:
    @staticmethod
    def _period(period_days: int) -> int:
        if isinstance(period_days, bool) or not isinstance(period_days, int) or not 1 <= period_days <= 365:
            raise CRMServiceError("Period must be from 1 to 365 days.", code="INVALID_PERIOD", http_status=status.HTTP_400_BAD_REQUEST)
        return period_days

    @staticmethod
    def _open_queryset(tenant_id: UUID, owner_id: UUID | None, period_days: int) -> QuerySet[Opportunity]:
        queryset = Opportunity.objects.filter(tenant_id=tenant_id, status=OpportunityStatus.OPEN, is_deleted=False, close_date__lte=timezone.localdate() + timedelta(days=period_days))
        return queryset.filter(owner_id=owner_id) if owner_id else queryset

    @classmethod
    def get_weighted_pipeline(cls, tenant_id: UUID, *, owner_id: UUID | None = None, period_days: int = 90) -> Forecast:
        period = cls._period(period_days)
        weighted = ExpressionWrapper(F("amount") * F("probability") / Decimal("100"), output_field=DecimalField(max_digits=19, decimal_places=4))
        with tenant_context(tenant_id):
            rows = cls._open_queryset(tenant_id, owner_id, period).values("currency").annotate(total=Sum("amount"), weighted=Sum(weighted), count=Count("id")).order_by("currency")
            return Forecast(tuple(CurrencyForecast(row["currency"], row["total"] or Decimal("0"), row["weighted"] or Decimal("0"), row["count"]) for row in rows), period)

    @classmethod
    def get_win_rate(cls, tenant_id: UUID, *, owner_id: UUID | None = None, period_days: int = 90) -> WinRate:
        period = cls._period(period_days)
        since = timezone.now() - timedelta(days=period)
        with tenant_context(tenant_id):
            queryset = Opportunity.objects.filter(tenant_id=tenant_id, is_deleted=False, closed_at__gte=since, status__in=[OpportunityStatus.WON, OpportunityStatus.LOST])
            if owner_id:
                queryset = queryset.filter(owner_id=owner_id)
            counts = queryset.aggregate(total=Count("id"), won=Count("id", filter=Q(status=OpportunityStatus.WON)), lost=Count("id", filter=Q(status=OpportunityStatus.LOST)))
            total = counts["total"]
            win_rate = (Decimal(counts["won"]) * Decimal("100") / Decimal(total)).quantize(Decimal("0.01")) if total else Decimal("0")
            return WinRate(win_rate, counts["won"], counts["lost"], total, period)

    @classmethod
    def get_pipeline_by_stage(cls, tenant_id: UUID, *, owner_id: UUID | None = None, period_days: int = 90) -> list[StageForecast]:
        period = cls._period(period_days)
        weighted = ExpressionWrapper(F("amount") * F("probability") / Decimal("100"), output_field=DecimalField(max_digits=19, decimal_places=4))
        with tenant_context(tenant_id):
            rows = cls._open_queryset(tenant_id, owner_id, period).values("stage", "currency").annotate(total=Sum("amount"), weighted=Sum(weighted), count=Count("id")).order_by("stage", "currency")
            return [StageForecast(row["stage"], row["currency"], row["total"] or Decimal("0"), row["weighted"] or Decimal("0"), row["count"]) for row in rows]

    @classmethod
    def predict_revenue(cls, tenant_id: UUID, *, period_days: int, actor_id: str | UUID | None, correlation_id: str | None) -> OperationResult[RevenuePrediction]:
        period = cls._period(period_days)
        correlation = _correlation(correlation_id)
        with tenant_context(tenant_id):
            pipeline = cls.get_weighted_pipeline(tenant_id, period_days=period)
            payload = {"period_days": period, "pipeline_by_currency": [asdict(item) for item in pipeline.currencies], "as_of": timezone.now().isoformat()}
            try:
                result = get_revenue_prediction_client().predict_revenue(payload, correlation_id=correlation)
            except IntegrationUnavailable as exc:
                return OperationResult.unavailable(capability="crm.revenue_prediction", message="Revenue prediction provider is unavailable.", detail={"code": exc.code})
            except (InvalidIntegrationResponse, CRMIntegrationError) as exc:
                return OperationResult.failed(code=exc.code, message="Revenue prediction could not be verified.", http_status=status.HTTP_503_SERVICE_UNAVAILABLE)
            prediction = RevenuePrediction(result.provider, result.model, result.amount, result.currency, result.confidence, dict(result.factors), result.as_of, period)
            return OperationResult.succeeded(prediction, evidence={"provider_request_id": result.provider_request_id or correlation, "as_of": result.as_of}, provider=result.provider)


class IntegrationService:
    """Compatibility facade retained for open-source v1 consumers."""

    @staticmethod
    def convert_lead_to_opportunity(lead_id: UUID, tenant_id: UUID, opportunity_data: Mapping[str, object], user_id: str | UUID | None) -> dict[str, object]:
        lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
        if lead.status != LeadStatus.QUALIFIED:
            LeadService.transition_lead(tenant_id, lead_id=lead.id, command="qualify", transition_key=f"legacy-qualify:{lead.id}", context={}, actor_id=user_id)
            lead.refresh_from_db()
        result = LeadService.convert_lead(tenant_id, lead_id=lead_id, data={**dict(opportunity_data), "create_new_account": True}, expected_version=lead.version, transition_key=f"legacy-convert:{lead.id}", actor_id=user_id, correlation_id=None)
        return {"lead": result.lead, "account": result.account, "contact": result.contact, "opportunity": result.opportunity}


__all__ = [
    "AccountHierarchyNode",
    "AccountService",
    "ActivityService",
    "CRMServiceError",
    "ContactService",
    "CurrencyForecast",
    "DuplicateAccountResult",
    "Forecast",
    "ForecastingService",
    "IntegrationService",
    "LeadConversionResult",
    "LeadService",
    "OpportunityService",
    "RevenuePrediction",
    "StageForecast",
    "StaleVersionError",
    "WinRate",
]
