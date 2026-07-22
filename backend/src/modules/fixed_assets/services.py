"""Transactional authority for the tenant-isolated fixed-assets lifecycle."""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.middleware.correlation import get_correlation_id
from src.core.state_machine import (
    IdempotencyConflictError,
    IllegalTransitionError,
    StateMachine,
    TerminalStateError,
    TransitionRecord,
    UnknownCommandError,
)

from .integrations import (
    AccountingPostingRequest,
    CapabilityUnavailable,
    FixedAssetIntegrationError,
    JournalLeg,
    extension_registry,
)
from .models import (
    ASSET_STATE_MACHINE,
    LINE_STATE_MACHINE,
    SCHEDULE_STATE_MACHINE,
    AssetCategory,
    AssetStatus,
    AssetTransaction,
    DepreciationLine,
    DepreciationMethod,
    DepreciationSchedule,
    FixedAsset,
    LineStatus,
    PRIMARY_BOOK,
    ScheduleStatus,
    TransactionType,
    money,
)

logger = logging.getLogger(__name__)
_LEDGER_AUTHORITY = object()


class FixedAssetServiceError(ValidationError):
    """Validation error carrying a stable domain code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.domain_code = code
        super().__init__(message, code=code)


class StaleVersionError(FixedAssetServiceError):
    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"Expected version {expected}, found {actual}.", code="STALE_VERSION")


def _tenant(value: UUID | str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FixedAssetServiceError("tenant_id must be a valid UUID.", code="INVALID_TENANT") from exc


def _required(value: object, name: str, maximum: int = 255) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise FixedAssetServiceError(f"{name} must be a bounded non-empty string.", code="INVALID_INPUT")
    return normalized


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, (UUID, date, Decimal)):
        return str(value)
    if hasattr(value, "_meta") and hasattr(value, "pk"):
        return str(getattr(value, "pk"))
    return value


def _fingerprint(value: Mapping[str, object]) -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _correlation(identity: str) -> str:
    active = get_correlation_id().strip()
    if active:
        return active[:64]
    # Non-HTTP callers receive a deterministic command-linked correlation.
    return f"cmd-{hashlib.sha256(identity.encode()).hexdigest()[:40]}"


def _version(instance: object, expected: int) -> None:
    actual = int(getattr(instance, "version"))
    if isinstance(expected, bool) or int(expected) < 1 or actual != int(expected):
        raise StaleVersionError(int(expected), actual)


def _event(
    tenant_id: UUID,
    event_type: str,
    aggregate_id: UUID,
    actor_id: str,
    correlation_id: str,
    payload: Mapping[str, object],
) -> OutboxEvent:
    event = OutboxEvent(
        tenant_id=tenant_id,
        aggregate_type="fixed_asset",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload={
            "schema_version": "1.0",
            "event_id": "",
            "event_type": event_type,
            "tenant_id": str(tenant_id),
            "aggregate_id": str(aggregate_id),
            "actor_id": actor_id,
            "correlation_id": correlation_id,
            **_canonical(payload),
        },
    )
    event.payload["event_id"] = str(event.id)
    event.save()
    return event


def _transition(
    machine: StateMachine[Any],
    aggregate: Any,
    command: str,
    transition_key: str,
    actor_id: str,
    correlation_id: str,
    metadata: Mapping[str, object] | None = None,
) -> bool:
    """Apply a machine edge to an already locked aggregate.

    The core engine cannot save disposal fields in the same statement as its
    status edge, so services use the machine's validated graph and recorder
    inside their wider atomic unit.
    """

    key = _required(transition_key, "transition_key")
    existing = machine.recorder.find(aggregate, key)
    if existing is not None:
        if existing.command != command:
            raise IdempotencyConflictError(
                f"Transition key {key!r} already belongs to command {existing.command!r}."
            )
        return False
    current = str(getattr(aggregate, machine.state_field))
    if current in machine.terminal_states:
        raise TerminalStateError(f"{machine.name} is terminal in {current!r}.")
    commands = {edge.command for edge in machine.transitions}
    if command not in commands:
        raise UnknownCommandError(f"{machine.name} has no command {command!r}.")
    edge = next((candidate for candidate in machine.transitions if candidate.command == command and candidate.source == current), None)
    if edge is None:
        raise IllegalTransitionError(f"Command {command!r} is not legal from {current!r}.")
    record = TransitionRecord(
        transition_key=key,
        command=command,
        from_state=current,
        to_state=edge.target,
        occurred_at=timezone.now().isoformat(),
        metadata={
            "actor_id": actor_id,
            "correlation_id": correlation_id,
            "command_metadata": dict(metadata or {}),
        },
    )
    setattr(aggregate, machine.state_field, edge.target)
    machine.recorder.record(aggregate, record)
    return True


def _category_accounts(category: AssetCategory) -> tuple[UUID, ...]:
    values = (
        category.asset_account_id,
        category.accumulated_depreciation_account_id,
        category.depreciation_expense_account_id,
        category.impairment_loss_account_id,
        category.disposal_gain_account_id,
        category.disposal_loss_account_id,
    )
    if any(value is None for value in values):
        raise FixedAssetServiceError("The category account mapping is incomplete.", code="ACCOUNT_MAPPING_INCOMPLETE")
    return tuple(value for value in values if value is not None)


class AssetCategoryService:
    MUTABLE = {
        "code", "name", "description", "default_depreciation_method", "default_useful_life_months",
        "default_residual_value_percent", "default_declining_balance_rate", "asset_account_id",
        "accumulated_depreciation_account_id", "depreciation_expense_account_id", "impairment_loss_account_id",
        "disposal_gain_account_id", "disposal_loss_account_id", "is_active",
    }

    @classmethod
    def validate_account_mapping(cls, tenant_id: UUID | str, category: AssetCategory) -> None:
        tenant = _tenant(tenant_id)
        if category.tenant_id != tenant:
            raise FixedAssetServiceError("Category was not found for this tenant.", code="CROSS_TENANT_REFERENCE")
        extension_registry.accounting_port().validate_accounts(tenant, _category_accounts(category))

    @classmethod
    def create_category(
        cls, tenant_id: UUID | str, actor_id: str, data: Mapping[str, object], idempotency_key: str
    ) -> AssetCategory:
        tenant = _tenant(tenant_id)
        actor = _required(actor_id, "actor_id")
        key = _required(idempotency_key, "idempotency_key")
        values = {name: value for name, value in data.items() if name in cls.MUTABLE}
        values["code"] = _required(values.get("code"), "code", 30).upper()
        fingerprint = _fingerprint(values)
        with transaction.atomic():
            existing = AssetCategory.objects.for_tenant(tenant).filter(creation_idempotency_key=key).first()
            if existing:
                if existing.creation_request_fingerprint != fingerprint:
                    raise IdempotencyConflictError("Category idempotency key payload differs.")
                return existing
            category = AssetCategory(
                tenant_id=tenant,
                creation_idempotency_key=key,
                creation_request_fingerprint=fingerprint,
                **values,
            )
            if category.is_active:
                cls.validate_account_mapping(tenant, category)
            try:
                category.save()
            except IntegrityError:
                existing = AssetCategory.objects.for_tenant(tenant).filter(creation_idempotency_key=key).first()
                if not existing or existing.creation_request_fingerprint != fingerprint:
                    raise
                return existing
            logger.info(
                "Fixed-asset category created",
                extra={
                    "tenant_id": str(tenant),
                    "actor_id": actor,
                    "domain_module": "fixed_assets",
                    "operation": "category.create",
                    "outcome": "success",
                },
            )
            return category

    @classmethod
    def update_category(
        cls, tenant_id: UUID | str, category_id: UUID | str, actor_id: str,
        data: Mapping[str, object], expected_version: int,
    ) -> AssetCategory:
        tenant = _tenant(tenant_id)
        _required(actor_id, "actor_id")
        with transaction.atomic():
            category = AssetCategory.objects.select_for_update().get(pk=category_id, tenant_id=tenant)
            _version(category, expected_version)
            for name, value in data.items():
                if name in cls.MUTABLE:
                    setattr(category, name, value)
            if category.is_active:
                cls.validate_account_mapping(tenant, category)
            category.version += 1
            category.save()
            return category

    @classmethod
    def deactivate_category(cls, tenant_id: UUID | str, category_id: UUID | str, actor_id: str) -> AssetCategory:
        tenant = _tenant(tenant_id)
        _required(actor_id, "actor_id")
        with transaction.atomic():
            category = AssetCategory.objects.select_for_update().get(pk=category_id, tenant_id=tenant)
            if FixedAsset.objects.for_tenant(tenant).filter(category=category, status=AssetStatus.DRAFT).exists():
                raise FixedAssetServiceError("Draft assets require an active category.", code="CATEGORY_IN_USE_BY_DRAFT")
            if category.is_active:
                category.is_active = False
                category.version += 1
                category.save(update_fields={"is_active", "version", "updated_at"})
            return category


class AssetTransactionService:
    @classmethod
    def append_transaction(cls, *, _authority: object | None = None, **values: object) -> AssetTransaction:
        if _authority is not _LEDGER_AUTHORITY:
            raise FixedAssetServiceError("Transactions can only be appended by lifecycle services.", code="LEDGER_INTERNAL_ONLY")
        tenant = _tenant(values["tenant_id"])
        key = _required(values["idempotency_key"], "idempotency_key")
        fingerprint_values = {name: value for name, value in values.items() if name != "request_fingerprint"}
        fingerprint = _fingerprint(fingerprint_values)
        existing = AssetTransaction.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise IdempotencyConflictError("Transaction idempotency key payload differs.")
            return existing
        try:
            with transaction.atomic():
                create_values = dict(values)
                create_values.pop("tenant_id", None)
                create_values.pop("idempotency_key", None)
                create_values.pop("request_fingerprint", None)
                return AssetTransaction.objects.create(
                    **create_values,
                    tenant_id=tenant,
                    idempotency_key=key,
                    request_fingerprint=fingerprint,
                )
        except IntegrityError:
            existing = AssetTransaction.objects.filter(tenant_id=tenant, idempotency_key=key).first()
            if not existing or existing.request_fingerprint != fingerprint:
                raise
            return existing

    @staticmethod
    def get_asset_history(tenant_id: UUID | str, asset_id: UUID | str) -> QuerySet[AssetTransaction]:
        tenant = _tenant(tenant_id)
        if not FixedAsset.objects.for_tenant(tenant).filter(pk=asset_id).exists():
            raise ObjectDoesNotExist("Asset was not found for this tenant.")
        return AssetTransaction.objects.filter(tenant_id=tenant, asset_id=asset_id)


class FixedAssetService:
    CREATE_FIELDS = {
        "asset_code", "asset_name", "description", "category_id", "purchase_date", "purchase_cost", "currency",
        "residual_value", "depreciation_method", "useful_life_months", "declining_balance_rate",
        "expected_total_units", "location", "cost_center", "primary_book_code",
    }
    UPDATE_FIELDS = CREATE_FIELDS - {"primary_book_code"}

    @classmethod
    def create_asset(
        cls, tenant_id: UUID | str, actor_id: str, data: Mapping[str, object], idempotency_key: str
    ) -> FixedAsset:
        tenant = _tenant(tenant_id)
        actor = _required(actor_id, "actor_id")
        key = _required(idempotency_key, "idempotency_key")
        values = {name: value for name, value in data.items() if name in cls.CREATE_FIELDS}
        category_id = values.pop("category_id", None)
        if category_id is None:
            raise FixedAssetServiceError("category_id is required.", code="INVALID_INPUT")
        category = AssetCategory.objects.for_tenant(tenant).filter(pk=category_id, is_active=True).first()
        if category is None:
            raise FixedAssetServiceError("An active same-tenant category is required.", code="CATEGORY_UNAVAILABLE")
        values.setdefault("depreciation_method", category.default_depreciation_method)
        values.setdefault("useful_life_months", category.default_useful_life_months)
        values.setdefault("declining_balance_rate", category.default_declining_balance_rate)
        values.setdefault("expected_total_units", None)
        values.setdefault("residual_value", money(Decimal(values["purchase_cost"]) * category.default_residual_value_percent / Decimal("100")))
        values.setdefault("description", "")
        values.setdefault("location", "")
        values.setdefault("cost_center", "")
        values.setdefault("primary_book_code", PRIMARY_BOOK)
        values["asset_code"] = _required(values.get("asset_code"), "asset_code", 50).upper()
        values["currency"] = _required(values.get("currency"), "currency", 3).upper()
        request = {**values, "category_id": category.id}
        fingerprint = _fingerprint(request)
        with transaction.atomic():
            existing = FixedAsset.objects.for_tenant(tenant).filter(creation_idempotency_key=key).first()
            if existing:
                if existing.creation_request_fingerprint != fingerprint:
                    raise IdempotencyConflictError("Asset idempotency key payload differs.")
                return existing
            asset = FixedAsset(
                tenant_id=tenant, category=category, net_book_value=money(values["purchase_cost"]),
                created_by=actor, updated_by=actor, creation_idempotency_key=key,
                creation_request_fingerprint=fingerprint, **values,
            )
            try:
                asset.save()
            except IntegrityError:
                existing = FixedAsset.objects.for_tenant(tenant).filter(creation_idempotency_key=key).first()
                if not existing or existing.creation_request_fingerprint != fingerprint:
                    raise
                return existing
            correlation = _correlation(key)
            _event(tenant, "fixed_assets.asset.created", asset.id, actor, correlation, {"asset_id": asset.id, "version": asset.version})
            return asset

    @classmethod
    def create_fixed_asset(cls, tenant_id: UUID | str, asset_code: str, asset_name: str, purchase_date: date, purchase_cost: Decimal, **kwargs: object) -> FixedAsset:
        """Legacy service adapter retained while API v1 is deprecated."""
        actor = str(kwargs.pop("actor_id", "legacy-v1"))
        key = str(kwargs.pop("idempotency_key", f"legacy:{asset_code}"))
        category_code = str(kwargs.pop("asset_category", "LEGACY")).upper()
        category = AssetCategory.objects.for_tenant(_tenant(tenant_id)).filter(code=category_code).first()
        if category is None:
            category = AssetCategoryService.create_category(
                tenant_id, actor,
                {"code": category_code, "name": category_code, "default_depreciation_method": kwargs.get("depreciation_method", "straight_line"), "default_useful_life_months": int(kwargs.pop("useful_life_years", 1) or 1) * 12, "is_active": False},
                f"{key}:category",
            )
            category.is_active = True
            category.save(update_fields={"is_active", "updated_at"})
        return cls.create_asset(tenant_id, actor, {"asset_code": asset_code, "asset_name": asset_name, "purchase_date": purchase_date, "purchase_cost": purchase_cost, "category_id": category.id, "currency": kwargs.pop("currency", "USD"), **kwargs}, key)

    @classmethod
    def update_draft(cls, tenant_id: UUID | str, asset_id: UUID | str, actor_id: str, data: Mapping[str, object], expected_version: int) -> FixedAsset:
        tenant = _tenant(tenant_id)
        actor = _required(actor_id, "actor_id")
        with transaction.atomic():
            asset = FixedAsset.objects.select_for_update().get(pk=asset_id, tenant_id=tenant)
            if asset.status != AssetStatus.DRAFT:
                raise FixedAssetServiceError("Only draft assets can be updated.", code="ASSET_NOT_DRAFT")
            _version(asset, expected_version)
            for name, value in data.items():
                if name not in cls.UPDATE_FIELDS:
                    continue
                if name == "category_id":
                    category = AssetCategory.objects.for_tenant(tenant).filter(pk=value, is_active=True).first()
                    if category is None:
                        raise FixedAssetServiceError("An active same-tenant category is required.", code="CATEGORY_UNAVAILABLE")
                    asset.category = category
                else:
                    setattr(asset, name, value)
            asset.net_book_value = money(asset.purchase_cost)
            asset.updated_by = actor
            asset.version += 1
            asset.save()
            return asset

    @staticmethod
    def delete_draft(tenant_id: UUID | str, asset_id: UUID | str, actor_id: str) -> None:
        tenant = _tenant(tenant_id)
        _required(actor_id, "actor_id")
        with transaction.atomic():
            asset = FixedAsset.objects.select_for_update().get(pk=asset_id, tenant_id=tenant)
            if asset.status != AssetStatus.DRAFT:
                raise FixedAssetServiceError("Only draft assets can be deleted.", code="ASSET_NOT_DRAFT")
            if asset.transactions.exists():
                raise FixedAssetServiceError("Asset history prevents deletion.", code="ASSET_HAS_HISTORY")
            asset.delete()

    @classmethod
    def capitalize(
        cls, tenant_id: UUID | str, asset_id: UUID | str, actor_id: str, effective_date: date,
        transition_key: str, *, depreciation_start_date: date | None = None, expected_version: int | None = None,
    ) -> FixedAsset:
        tenant = _tenant(tenant_id)
        actor = _required(actor_id, "actor_id")
        key = _required(transition_key, "transition_key")
        correlation = _correlation(key)
        with transaction.atomic():
            asset = FixedAsset.objects.select_for_update().select_related("category").get(pk=asset_id, tenant_id=tenant)
            existing = AssetTransaction.objects.filter(tenant_id=tenant, idempotency_key=key).first()
            if existing:
                if existing.asset_id != asset.id or existing.transaction_type != TransactionType.CAPITALIZATION:
                    raise IdempotencyConflictError("Capitalization key belongs to another command.")
                return asset
            if expected_version is not None:
                _version(asset, expected_version)
            if effective_date < asset.purchase_date:
                raise FixedAssetServiceError("Capitalization cannot precede purchase.", code="INVALID_EFFECTIVE_DATE")
            start = depreciation_start_date or effective_date
            if start < effective_date:
                raise FixedAssetServiceError("Depreciation cannot precede capitalization.", code="INVALID_EFFECTIVE_DATE")
            AssetCategoryService.validate_account_mapping(tenant, asset.category)
            _transition(ASSET_STATE_MACHINE, asset, "capitalize", key, actor, correlation, {"effective_date": effective_date.isoformat()})
            asset.capitalization_date = effective_date
            asset.depreciation_start_date = start
            asset.updated_by = actor
            asset.version += 1
            asset.save()
            AssetTransactionService.append_transaction(
                _authority=_LEDGER_AUTHORITY, tenant_id=tenant, asset=asset, book_code=asset.primary_book_code,
                transaction_type=TransactionType.CAPITALIZATION, effective_date=effective_date,
                amount=asset.purchase_cost, currency=asset.currency, opening_net_book_value=Decimal("0.00"),
                closing_net_book_value=asset.net_book_value, source_type="asset", source_id=asset.id,
                idempotency_key=key, actor_id=actor, correlation_id=correlation,
                metadata={"resulting_asset_version": asset.version},
            )
            _event(tenant, "fixed_assets.asset.capitalized", asset.id, actor, correlation, {"asset_id": asset.id, "version": asset.version})
            return asset

    @classmethod
    def transfer(cls, tenant_id: UUID | str, asset_id: UUID | str, actor_id: str, effective_date: date, to_location: str, to_cost_center: str, idempotency_key: str) -> FixedAsset:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); key = _required(idempotency_key, "idempotency_key"); correlation = _correlation(key)
        with transaction.atomic():
            asset = FixedAsset.objects.select_for_update().get(pk=asset_id, tenant_id=tenant)
            existing = AssetTransaction.objects.filter(tenant_id=tenant, idempotency_key=key).first()
            if existing:
                if existing.asset_id != asset.id or existing.transaction_type != TransactionType.TRANSFER:
                    raise IdempotencyConflictError("Transfer key belongs to another command.")
                return asset
            if asset.status not in (AssetStatus.ACTIVE, AssetStatus.FULLY_DEPRECIATED):
                raise FixedAssetServiceError("Only capitalized assets can be transferred.", code="TRANSFER_NOT_ALLOWED")
            if asset.capitalization_date and effective_date < asset.capitalization_date:
                raise FixedAssetServiceError("Transfer cannot precede capitalization.", code="INVALID_EFFECTIVE_DATE")
            destination_location = str(to_location or "").strip()
            destination_cost_center = str(to_cost_center or "").strip()
            if destination_location == asset.location and destination_cost_center == asset.cost_center:
                raise FixedAssetServiceError("Transfer must change location or cost center.", code="NO_TRANSFER_CHANGE")
            before_location, before_cost_center = asset.location, asset.cost_center
            asset.location, asset.cost_center = destination_location, destination_cost_center
            asset.updated_by = actor; asset.version += 1; asset.save()
            AssetTransactionService.append_transaction(
                _authority=_LEDGER_AUTHORITY, tenant_id=tenant, asset=asset, book_code=asset.primary_book_code,
                transaction_type=TransactionType.TRANSFER, effective_date=effective_date, amount=Decimal("0.00"),
                currency=asset.currency, opening_net_book_value=asset.net_book_value, closing_net_book_value=asset.net_book_value,
                from_location=before_location, to_location=asset.location, from_cost_center=before_cost_center,
                to_cost_center=asset.cost_center, source_type="asset", source_id=asset.id, idempotency_key=key,
                actor_id=actor, correlation_id=correlation, metadata={"resulting_asset_version": asset.version},
            )
            _event(tenant, "fixed_assets.asset.transferred", asset.id, actor, correlation, {"asset_id": asset.id, "version": asset.version})
            return asset

    @classmethod
    def record_impairment(cls, tenant_id: UUID | str, asset_id: UUID | str, actor_id: str, effective_date: date, recoverable_amount: Decimal, reason: str, idempotency_key: str) -> FixedAsset:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); key = _required(idempotency_key, "idempotency_key"); correlation = _correlation(key)
        with transaction.atomic():
            asset = FixedAsset.objects.select_for_update().get(pk=asset_id, tenant_id=tenant)
            existing = AssetTransaction.objects.filter(tenant_id=tenant, idempotency_key=key).first()
            if existing:
                if existing.asset_id != asset.id or existing.transaction_type != TransactionType.IMPAIRMENT:
                    raise IdempotencyConflictError("Impairment key belongs to another command.")
                return asset
            if asset.status != AssetStatus.ACTIVE:
                raise FixedAssetServiceError("Only active assets can be impaired.", code="IMPAIRMENT_NOT_ALLOWED")
            recoverable = money(recoverable_amount)
            if recoverable < asset.residual_value or recoverable >= asset.net_book_value:
                raise FixedAssetServiceError("Recoverable amount must be below book value and not below residual value.", code="INVALID_RECOVERABLE_AMOUNT")
            opening = asset.net_book_value; loss = money(opening - recoverable)
            asset.accumulated_impairment = money(asset.accumulated_impairment + loss)
            asset.net_book_value = recoverable; asset.updated_by = actor; asset.version += 1; asset.save()
            AssetTransactionService.append_transaction(
                _authority=_LEDGER_AUTHORITY, tenant_id=tenant, asset=asset, book_code=asset.primary_book_code,
                transaction_type=TransactionType.IMPAIRMENT, effective_date=effective_date, amount=loss,
                currency=asset.currency, opening_net_book_value=opening, closing_net_book_value=recoverable,
                source_type="asset", source_id=asset.id, idempotency_key=key, actor_id=actor,
                correlation_id=correlation, metadata={"reason": _required(reason, "reason", 2000), "resulting_asset_version": asset.version},
            )
            for schedule in DepreciationSchedule.objects.select_for_update().filter(tenant_id=tenant, asset=asset, status=ScheduleStatus.ACTIVE):
                _transition(SCHEDULE_STATE_MACHINE, schedule, "supersede", f"{key}:schedule:{schedule.id}", actor, correlation, {"reason": "impairment"})
                schedule.updated_by = actor; schedule.version += 1; schedule.save()
            _event(tenant, "fixed_assets.asset.impaired", asset.id, actor, correlation, {"asset_id": asset.id, "amount": loss, "version": asset.version})
            return asset

    @classmethod
    def dispose(cls, tenant_id: UUID | str, asset_id: UUID | str, actor_id: str, effective_date: date, proceeds: Decimal, reason: str, transition_key: str) -> FixedAsset:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); key = _required(transition_key, "transition_key"); correlation = _correlation(key)
        with transaction.atomic():
            asset = FixedAsset.objects.select_for_update().get(pk=asset_id, tenant_id=tenant)
            existing = AssetTransaction.objects.filter(tenant_id=tenant, idempotency_key=key).first()
            if existing:
                if existing.asset_id != asset.id or existing.transaction_type != TransactionType.DISPOSAL:
                    raise IdempotencyConflictError("Disposal key belongs to another command.")
                return asset
            opening = asset.net_book_value; normalized_proceeds = money(proceeds)
            if normalized_proceeds < 0:
                raise FixedAssetServiceError("Disposal proceeds cannot be negative.", code="INVALID_PROCEEDS")
            _transition(ASSET_STATE_MACHINE, asset, "dispose", key, actor, correlation, {"effective_date": effective_date.isoformat(), "reason": reason})
            asset.disposal_date = effective_date; asset.disposal_proceeds = normalized_proceeds
            asset.disposal_gain_loss = money(normalized_proceeds - opening); asset.net_book_value = Decimal("0.00")
            asset.updated_by = actor; asset.version += 1; asset.save()
            for line in DepreciationLine.objects.select_for_update().filter(tenant_id=tenant, asset=asset, status__in=(LineStatus.PLANNED, LineStatus.FAILED)):
                _transition(LINE_STATE_MACHINE, line, "void", f"{key}:void:{line.id}", actor, correlation, {"reason": "asset_disposed"})
                line.save()
            AssetTransactionService.append_transaction(
                _authority=_LEDGER_AUTHORITY, tenant_id=tenant, asset=asset, book_code=asset.primary_book_code,
                transaction_type=TransactionType.DISPOSAL, effective_date=effective_date, amount=normalized_proceeds,
                currency=asset.currency, opening_net_book_value=opening, closing_net_book_value=Decimal("0.00"),
                source_type="asset", source_id=asset.id, idempotency_key=key, actor_id=actor,
                correlation_id=correlation, metadata={"reason": _required(reason, "reason", 2000), "gain_loss": str(asset.disposal_gain_loss), "resulting_asset_version": asset.version},
            )
            _event(tenant, "fixed_assets.asset.disposed", asset.id, actor, correlation, {"asset_id": asset.id, "gain_loss": asset.disposal_gain_loss, "version": asset.version})
            return asset

    @classmethod
    def mark_fully_depreciated(cls, tenant_id: UUID | str, asset_id: UUID | str, actor_id: str, transition_key: str) -> FixedAsset:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); correlation = _correlation(transition_key)
        with transaction.atomic():
            asset = FixedAsset.objects.select_for_update().get(pk=asset_id, tenant_id=tenant)
            if asset.net_book_value != asset.residual_value:
                raise FixedAssetServiceError("Asset has not reached residual value.", code="NOT_FULLY_DEPRECIATED")
            if _transition(ASSET_STATE_MACHINE, asset, "fully_depreciate", transition_key, actor, correlation):
                asset.updated_by = actor; asset.version += 1; asset.save()
            return asset

    @classmethod
    def _preview(cls, tenant_id: UUID | str, asset_id: UUID | str, command: str, as_of: date, closing: Decimal, blockers: list[dict[str, str]], schedule_status: str, schedule_description: str) -> dict[str, object]:
        asset = FixedAsset.objects.for_tenant(_tenant(tenant_id)).select_related("category").get(pk=asset_id)
        entries: list[dict[str, object]] = []
        try:
            _category_accounts(asset.category)
            journal_status = "ready" if command != "transfer" else "not_required"
        except ValidationError:
            journal_status = "unavailable"
            blockers.append({"code": "ACCOUNT_MAPPING_INCOMPLETE", "message": "Complete category account mapping."})
        return {"command": command, "asset_version": asset.version, "as_of": as_of, "opening_net_book_value": asset.net_book_value, "closing_net_book_value": money(closing), "currency": asset.currency, "warnings": [], "blockers": blockers, "journal_effect": {"status": journal_status, "entries": entries}, "schedule_effect": {"status": schedule_status, "description": schedule_description}}

    @classmethod
    def preview_capitalization(cls, tenant_id: UUID | str, asset_id: UUID | str, effective_date: date, **kwargs: object) -> dict[str, object]:
        del kwargs
        asset = FixedAsset.objects.for_tenant(_tenant(tenant_id)).get(pk=asset_id)
        blockers = [] if asset.status == AssetStatus.DRAFT else [{"code": "ASSET_NOT_DRAFT", "message": "Only draft assets can be capitalized."}]
        return cls._preview(tenant_id, asset_id, "capitalize", effective_date, asset.net_book_value, blockers, "created", "A draft depreciation schedule may be created.")

    @classmethod
    def preview_transfer(cls, tenant_id: UUID | str, asset_id: UUID | str, effective_date: date, **kwargs: object) -> dict[str, object]:
        asset = FixedAsset.objects.for_tenant(_tenant(tenant_id)).get(pk=asset_id)
        changed = str(kwargs.get("to_location", "")).strip() != asset.location or str(kwargs.get("to_cost_center", "")).strip() != asset.cost_center
        blockers = [] if changed else [{"code": "NO_TRANSFER_CHANGE", "message": "Destination must change."}]
        return cls._preview(tenant_id, asset_id, "transfer", effective_date, asset.net_book_value, blockers, "unchanged", "Depreciation assumptions do not change.")

    @classmethod
    def preview_impairment(cls, tenant_id: UUID | str, asset_id: UUID | str, effective_date: date, recoverable_amount: Decimal, **kwargs: object) -> dict[str, object]:
        del kwargs
        asset = FixedAsset.objects.for_tenant(_tenant(tenant_id)).get(pk=asset_id); recoverable = money(recoverable_amount)
        blockers = [] if asset.residual_value <= recoverable < asset.net_book_value else [{"code": "INVALID_RECOVERABLE_AMOUNT", "message": "Recoverable amount is outside the allowed range."}]
        return cls._preview(tenant_id, asset_id, "impair", effective_date, recoverable, blockers, "superseded", "The active schedule will require revision.")

    @classmethod
    def preview_disposal(cls, tenant_id: UUID | str, asset_id: UUID | str, effective_date: date, **kwargs: object) -> dict[str, object]:
        asset = FixedAsset.objects.for_tenant(_tenant(tenant_id)).get(pk=asset_id)
        blockers = [] if asset.status in (AssetStatus.ACTIVE, AssetStatus.FULLY_DEPRECIATED) else [{"code": "DISPOSAL_NOT_ALLOWED", "message": "Asset is not disposable."}]
        return cls._preview(tenant_id, asset_id, "dispose", effective_date, Decimal("0.00"), blockers, "voided", "Unposted depreciation lines will be voided.")


def _add_months(value: date, months: int) -> date:
    zero_based = value.month - 1 + months
    year = value.year + zero_based // 12
    month = zero_based % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _periods(start: date, end: date) -> list[tuple[date, date]]:
    result: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        month_end = date(cursor.year, cursor.month, calendar.monthrange(cursor.year, cursor.month)[1])
        period_end = min(month_end, end)
        result.append((cursor, period_end))
        cursor = period_end + timedelta(days=1)
    return result


class DepreciationService:
    ASSUMPTIONS = {"method", "frequency", "start_date", "end_date", "cost_basis", "residual_value", "declining_balance_rate", "expected_total_units", "book_code"}

    @classmethod
    def create_schedule_draft(cls, tenant_id: UUID | str, asset_id: UUID | str, actor_id: str, assumptions: Mapping[str, object], idempotency_key: str) -> DepreciationSchedule:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); key = _required(idempotency_key, "idempotency_key")
        asset = FixedAsset.objects.for_tenant(tenant).filter(pk=asset_id).first()
        if asset is None or asset.status not in (AssetStatus.ACTIVE, AssetStatus.FULLY_DEPRECIATED):
            raise FixedAssetServiceError("A capitalized same-tenant asset is required.", code="ASSET_NOT_CAPITALIZED")
        values = {name: value for name, value in assumptions.items() if name in cls.ASSUMPTIONS}
        values.setdefault("method", asset.depreciation_method); values.setdefault("frequency", "monthly")
        values.setdefault("start_date", asset.depreciation_start_date or asset.capitalization_date)
        values.setdefault("end_date", _add_months(values["start_date"], asset.useful_life_months) - timedelta(days=1))
        values.setdefault("cost_basis", asset.net_book_value); values.setdefault("residual_value", asset.residual_value)
        values.setdefault("declining_balance_rate", asset.declining_balance_rate); values.setdefault("expected_total_units", asset.expected_total_units)
        values.setdefault("book_code", asset.primary_book_code)
        fingerprint = _fingerprint({**values, "asset_id": asset.id})
        with transaction.atomic():
            existing = DepreciationSchedule.objects.for_tenant(tenant).filter(creation_idempotency_key=key).first()
            if existing:
                if existing.creation_request_fingerprint != fingerprint:
                    raise IdempotencyConflictError("Schedule idempotency key payload differs.")
                return existing
            revision = (DepreciationSchedule.objects.for_tenant(tenant).filter(asset=asset, book_code=values["book_code"]).order_by("-revision").values_list("revision", flat=True).first() or 0) + 1
            schedule = DepreciationSchedule(tenant_id=tenant, asset=asset, schedule_number=f"{asset.asset_code}-{values['book_code']}-R{revision}", revision=revision, depreciable_amount=money(Decimal(values["cost_basis"]) - Decimal(values["residual_value"])), total_planned_depreciation=Decimal("0.00"), created_by=actor, updated_by=actor, creation_idempotency_key=key, creation_request_fingerprint=fingerprint, **values)
            schedule.save(); return schedule

    @classmethod
    def update_schedule_draft(cls, tenant_id: UUID | str, schedule_id: UUID | str, actor_id: str, assumptions: Mapping[str, object], expected_version: int) -> DepreciationSchedule:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id")
        with transaction.atomic():
            schedule = DepreciationSchedule.objects.select_for_update().get(pk=schedule_id, tenant_id=tenant)
            if schedule.status != ScheduleStatus.DRAFT:
                raise FixedAssetServiceError("Only draft schedules can be updated.", code="SCHEDULE_NOT_DRAFT")
            _version(schedule, expected_version)
            for name, value in assumptions.items():
                if name in cls.ASSUMPTIONS:
                    setattr(schedule, name, value)
            schedule.depreciable_amount = money(schedule.cost_basis - schedule.residual_value)
            schedule.updated_by = actor; schedule.version += 1; schedule.save(); return schedule

    @staticmethod
    def delete_schedule_draft(tenant_id: UUID | str, schedule_id: UUID | str, actor_id: str) -> None:
        tenant = _tenant(tenant_id); _required(actor_id, "actor_id")
        with transaction.atomic():
            schedule = DepreciationSchedule.objects.select_for_update().get(pk=schedule_id, tenant_id=tenant)
            if schedule.status != ScheduleStatus.DRAFT or schedule.lines.exists():
                raise FixedAssetServiceError("Only an empty draft schedule can be deleted.", code="SCHEDULE_NOT_DELETABLE")
            schedule.delete()

    @classmethod
    def calculate_schedule(cls, tenant_id: UUID | str, schedule_id: UUID | str, actor_id: str, units_by_period: Mapping[str, Decimal], transition_key: str) -> DepreciationSchedule:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); key = _required(transition_key, "transition_key"); correlation = _correlation(key)
        with transaction.atomic():
            schedule = DepreciationSchedule.objects.select_for_update().select_related("asset").get(pk=schedule_id, tenant_id=tenant)
            if SCHEDULE_STATE_MACHINE.recorder.find(schedule, key):
                return schedule
            if schedule.status != ScheduleStatus.DRAFT:
                raise FixedAssetServiceError("Only draft schedules can be calculated.", code="SCHEDULE_NOT_DRAFT")
            schedule.lines.all().delete()
            periods = _periods(schedule.start_date, schedule.end_date)
            if not periods:
                raise FixedAssetServiceError("Schedule has no depreciation periods.", code="EMPTY_SCHEDULE")
            expected_units = schedule.expected_total_units
            if schedule.method == DepreciationMethod.UNITS_OF_PRODUCTION:
                missing = [start.isoformat() for start, _ in periods if start.isoformat() not in units_by_period]
                if missing:
                    raise FixedAssetServiceError("Units are required for every period.", code="UNITS_REQUIRED")
                total_units = sum((Decimal(units_by_period[start.isoformat()]) for start, _ in periods), Decimal("0"))
                if expected_units is None or total_units != expected_units:
                    raise FixedAssetServiceError("Period units must reconcile to expected total units.", code="UNITS_NOT_RECONCILED")
            opening = money(schedule.cost_basis); accumulated = Decimal("0.00"); raw_amounts: list[Decimal] = []
            for period_start, period_end in periods:
                fraction = Decimal((period_end - period_start).days + 1) / Decimal(calendar.monthrange(period_start.year, period_start.month)[1])
                if schedule.method == DepreciationMethod.STRAIGHT_LINE:
                    raw = schedule.depreciable_amount / Decimal(schedule.asset.useful_life_months) * fraction
                elif schedule.method == DepreciationMethod.DECLINING_BALANCE:
                    if schedule.declining_balance_rate is None:
                        raise FixedAssetServiceError("Declining balance requires a rate.", code="RATE_REQUIRED")
                    raw = opening * (schedule.declining_balance_rate / Decimal("100") / Decimal("12")) * fraction
                else:
                    raw = schedule.depreciable_amount / Decimal(expected_units) * Decimal(units_by_period[period_start.isoformat()])
                amount = min(money(raw), money(opening - schedule.residual_value))
                raw_amounts.append(max(amount, Decimal("0.00"))); opening = money(opening - max(amount, Decimal("0.00")))
            variance = money(schedule.depreciable_amount - sum(raw_amounts, Decimal("0.00")))
            raw_amounts[-1] = money(raw_amounts[-1] + variance)
            opening = money(schedule.cost_basis)
            lines: list[DepreciationLine] = []
            for sequence, ((period_start, period_end), amount) in enumerate(zip(periods, raw_amounts), 1):
                accumulated = money(accumulated + amount); closing = money(opening - amount)
                lines.append(DepreciationLine(tenant_id=tenant, schedule=schedule, asset=schedule.asset, book_code=schedule.book_code, sequence=sequence, period_start=period_start, period_end=period_end, opening_net_book_value=opening, units_consumed=units_by_period.get(period_start.isoformat()) if schedule.method == DepreciationMethod.UNITS_OF_PRODUCTION else None, depreciation_amount=amount, accumulated_depreciation=accumulated, closing_net_book_value=closing, asset_version_snapshot=schedule.asset.version))
                opening = closing
            DepreciationLine.objects.bulk_create(lines)
            schedule.total_planned_depreciation = money(sum(raw_amounts, Decimal("0.00")))
            schedule.calculated_at = timezone.now(); schedule.updated_by = actor; schedule.version += 1
            _transition(SCHEDULE_STATE_MACHINE, schedule, "calculate", key, actor, correlation, {"line_count": len(lines)})
            schedule.save(); _event(tenant, "fixed_assets.schedule.calculated", schedule.id, actor, correlation, {"schedule_id": schedule.id, "asset_id": schedule.asset_id, "revision": schedule.revision}); return schedule

    @classmethod
    def activate_schedule(cls, tenant_id: UUID | str, schedule_id: UUID | str, actor_id: str, transition_key: str) -> DepreciationSchedule:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); correlation = _correlation(transition_key)
        with transaction.atomic():
            schedule = DepreciationSchedule.objects.select_for_update().get(pk=schedule_id, tenant_id=tenant)
            if schedule.lines.count() == 0 or money(sum(schedule.lines.values_list("depreciation_amount", flat=True), Decimal("0.00"))) != schedule.total_planned_depreciation:
                raise FixedAssetServiceError("Schedule lines do not reconcile.", code="SCHEDULE_NOT_RECONCILED")
            if DepreciationSchedule.objects.for_tenant(tenant).filter(asset=schedule.asset, book_code=schedule.book_code, status=ScheduleStatus.ACTIVE).exclude(pk=schedule.pk).exists():
                raise FixedAssetServiceError("Another schedule is active for this book.", code="ACTIVE_SCHEDULE_EXISTS")
            if _transition(SCHEDULE_STATE_MACHINE, schedule, "activate", transition_key, actor, correlation):
                schedule.activated_at = timezone.now(); schedule.updated_by = actor; schedule.version += 1; schedule.save()
                _event(tenant, "fixed_assets.schedule.activated", schedule.id, actor, correlation, {"schedule_id": schedule.id, "asset_id": schedule.asset_id})
            return schedule

    @classmethod
    def supersede_schedule(cls, tenant_id: UUID | str, schedule_id: UUID | str, actor_id: str, reason: str, transition_key: str) -> DepreciationSchedule:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); correlation = _correlation(transition_key)
        with transaction.atomic():
            schedule = DepreciationSchedule.objects.select_for_update().get(pk=schedule_id, tenant_id=tenant)
            if _transition(SCHEDULE_STATE_MACHINE, schedule, "supersede", transition_key, actor, correlation, {"reason": str(reason)}):
                schedule.updated_by = actor; schedule.version += 1; schedule.save()
            return schedule

    @classmethod
    def enqueue_line_posting(cls, tenant_id: UUID | str, line_id: UUID | str, actor_id: str, idempotency_key: str, correlation_id: str) -> AsyncJob:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); key = _required(idempotency_key, "idempotency_key")
        with transaction.atomic():
            line = DepreciationLine.objects.select_for_update().select_related("asset").get(pk=line_id, tenant_id=tenant)
            if line.status not in (LineStatus.PLANNED, LineStatus.FAILED):
                raise FixedAssetServiceError("Line is not available for posting.", code="LINE_NOT_POSTABLE")
            payload = {"line_id": str(line.id), "asset_version": line.asset.version, "correlation_id": correlation_id}
            fingerprint = _fingerprint(payload)
            if line.posting_idempotency_key and line.posting_idempotency_key != key:
                raise FixedAssetServiceError("Line already has a posting identity.", code="POSTING_ALREADY_REQUESTED")
            if line.posting_request_fingerprint and line.posting_request_fingerprint != fingerprint:
                raise IdempotencyConflictError("Posting idempotency payload differs.")
            job = enqueue(tenant, actor, "fixed_assets.post_line", payload, key)
            line.posting_idempotency_key = key; line.posting_request_fingerprint = fingerprint
            line.posting_job_id = job.id; line.asset_version_snapshot = line.asset.version; line.save()
            _event(tenant, "fixed_assets.depreciation.posting_requested", line.id, actor, correlation_id, {"line_id": line.id, "job_id": job.id})
            return job

    @classmethod
    def enqueue_due_posting(cls, tenant_id: UUID | str, through_date: date, actor_id: str, idempotency_key: str, correlation_id: str) -> AsyncJob:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); key = _required(idempotency_key, "idempotency_key")
        payload = {"through_date": through_date.isoformat(), "correlation_id": correlation_id}
        existing = AsyncJob.objects.for_tenant(tenant).filter(idempotency_key=key).first()
        if existing and (existing.command != "fixed_assets.post_due_lines" or existing.payload != payload):
            raise IdempotencyConflictError("Due-posting idempotency payload differs.")
        return enqueue(tenant, actor, "fixed_assets.post_due_lines", payload, key)

    @classmethod
    def post_line(cls, tenant_id: UUID | str, line_id: UUID | str, actor_id: str, job_id: UUID | str, transition_key: str) -> DepreciationLine:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); correlation = _correlation(transition_key); failure: FixedAssetIntegrationError | None = None
        with transaction.atomic():
            line = DepreciationLine.objects.select_for_update().select_related("asset__category", "schedule").get(pk=line_id, tenant_id=tenant)
            asset = FixedAsset.objects.select_for_update().get(pk=line.asset_id, tenant_id=tenant)
            if line.status == LineStatus.POSTED:
                return line
            earlier = DepreciationLine.objects.filter(
                tenant_id=tenant,
                schedule=line.schedule,
                sequence__lt=line.sequence,
            ).exclude(status__in=(LineStatus.POSTED, LineStatus.VOID))
            if earlier.exists():
                raise FixedAssetServiceError("Earlier depreciation periods must be resolved first.", code="POSTING_OUT_OF_ORDER")
            if asset.version != line.asset_version_snapshot:
                raise StaleVersionError(line.asset_version_snapshot, asset.version)
            command = "retry" if line.status == LineStatus.FAILED else "post"
            _transition(LINE_STATE_MACHINE, line, command, f"{transition_key}:begin", actor, correlation, {"job_id": str(job_id)})
            line.posting_job_id = job_id; line.posting_error_code = ""; line.save()
            try:
                accounts = _category_accounts(asset.category)
                port = extension_registry.accounting_port(); port.validate_accounts(tenant, accounts)
                result = port.post_journal(AccountingPostingRequest(schema_version="1.0", tenant_id=tenant, asset_id=asset.id, depreciation_line_id=line.id, posting_date=line.period_end, currency=asset.currency, idempotency_key=str(job_id), correlation_id=correlation, actor_id=actor, legs=(JournalLeg(asset.category.depreciation_expense_account_id, "debit", line.depreciation_amount, asset.currency, asset.cost_center), JournalLeg(asset.category.accumulated_depreciation_account_id, "credit", line.depreciation_amount, asset.currency, asset.cost_center)), metadata={"schedule_id": str(line.schedule_id), "book_code": line.book_code}))
            except FixedAssetIntegrationError as exc:
                failure = exc
                _transition(LINE_STATE_MACHINE, line, "fail", f"{transition_key}:fail", actor, correlation, {"error_code": exc.code})
                line.posting_error_code = exc.code; line.save()
                _event(tenant, "fixed_assets.depreciation.failed", line.id, actor, correlation, {"line_id": line.id, "job_id": str(job_id), "error_code": exc.code})
            else:
                opening = asset.net_book_value
                if opening != line.opening_net_book_value:
                    raise FixedAssetServiceError("Line opening value does not match the asset.", code="OPENING_VALUE_MISMATCH")
                asset.accumulated_depreciation = money(asset.accumulated_depreciation + line.depreciation_amount)
                asset.net_book_value = money(asset.purchase_cost - asset.accumulated_depreciation - asset.accumulated_impairment)
                asset.updated_by = actor; asset.version += 1; asset.save()
                _transition(LINE_STATE_MACHINE, line, "confirm", f"{transition_key}:confirm", actor, correlation, {"journal_entry_id": str(result.journal_entry_id)})
                line.journal_entry_id = result.journal_entry_id; line.posted_at = timezone.now(); line.posting_error_code = ""; line.save()
                AssetTransactionService.append_transaction(_authority=_LEDGER_AUTHORITY, tenant_id=tenant, asset=asset, book_code=line.book_code, transaction_type=TransactionType.DEPRECIATION, effective_date=line.period_end, amount=line.depreciation_amount, currency=asset.currency, opening_net_book_value=opening, closing_net_book_value=asset.net_book_value, journal_entry_id=result.journal_entry_id, source_type="depreciation_line", source_id=line.id, idempotency_key=f"depreciation:{line.id}", actor_id=actor, correlation_id=correlation, metadata={"schedule_id": str(line.schedule_id), "resulting_asset_version": asset.version})
                next_line = DepreciationLine.objects.select_for_update().filter(tenant_id=tenant, schedule=line.schedule, sequence__gt=line.sequence, status__in=(LineStatus.PLANNED, LineStatus.FAILED)).order_by("sequence").first()
                if next_line:
                    next_line.asset_version_snapshot = asset.version; next_line.save(update_fields={"asset_version_snapshot", "updated_at"})
                if asset.net_book_value == asset.residual_value and asset.status == AssetStatus.ACTIVE:
                    _transition(ASSET_STATE_MACHINE, asset, "fully_depreciate", f"{transition_key}:asset-complete", actor, correlation); asset.version += 1; asset.save()
                if not DepreciationLine.objects.filter(
                    tenant_id=tenant,
                    schedule=line.schedule,
                    status__in=(LineStatus.PLANNED, LineStatus.POSTING, LineStatus.FAILED),
                ).exists():
                    schedule = DepreciationSchedule.objects.select_for_update().get(pk=line.schedule_id, tenant_id=tenant)
                    if schedule.status == ScheduleStatus.ACTIVE:
                        _transition(SCHEDULE_STATE_MACHINE, schedule, "complete", f"{transition_key}:schedule-complete", actor, correlation); schedule.completed_at = timezone.now(); schedule.updated_by = actor; schedule.version += 1; schedule.save()
                _event(tenant, "fixed_assets.depreciation.posted", line.id, actor, correlation, {"line_id": line.id, "asset_id": asset.id, "job_id": str(job_id), "journal_entry_id": result.journal_entry_id})
        if failure is not None:
            raise failure
        return line

    @classmethod
    def retry_line(cls, tenant_id: UUID | str, line_id: UUID | str, actor_id: str, idempotency_key: str, correlation_id: str) -> AsyncJob:
        return cls.enqueue_line_posting(tenant_id, line_id, actor_id, idempotency_key, correlation_id)

    @classmethod
    def void_line(cls, tenant_id: UUID | str, line_id: UUID | str, actor_id: str, transition_key: str, reason: str = "") -> DepreciationLine:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id"); correlation = _correlation(transition_key)
        with transaction.atomic():
            line = DepreciationLine.objects.select_for_update().get(pk=line_id, tenant_id=tenant)
            if _transition(LINE_STATE_MACHINE, line, "void", transition_key, actor, correlation, {"reason": reason}):
                line.save()
            return line

    @classmethod
    def post_due_lines(cls, tenant_id: UUID | str, through_date: date, actor_id: str, job_id: UUID | str) -> dict[str, list[str]]:
        tenant = _tenant(tenant_id); actor = _required(actor_id, "actor_id")
        ids = list(
            DepreciationLine.objects.filter(
                tenant_id=tenant,
                status__in=(LineStatus.PLANNED, LineStatus.FAILED),
                period_end__lte=through_date,
                schedule__status=ScheduleStatus.ACTIVE,
            )
            .order_by("period_end", "sequence")
            .values_list("id", flat=True)
        )
        posted: list[str] = []; failed: list[str] = []
        for line_id in ids:
            try:
                cls.post_line(tenant, line_id, actor, job_id, f"{job_id}:{line_id}")
            except (FixedAssetIntegrationError, ValidationError, IllegalTransitionError):
                failed.append(str(line_id))
            else:
                posted.append(str(line_id))
        return {"posted_line_ids": posted, "failed_line_ids": failed}


__all__ = [
    "AssetCategoryService", "AssetTransactionService", "DepreciationService", "FixedAssetService",
    "FixedAssetServiceError", "StaleVersionError",
]
