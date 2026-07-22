"""Transactional business authority for Asset Management."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from .models import Asset, DepreciationEntry, DepreciationMethod

MONEY_QUANTUM = Decimal("0.01")
logger = logging.getLogger("saraise.asset_management")


def _event(event: str, tenant_id: UUID, asset_id: UUID, correlation_id: str | None, **details: object) -> None:
    """Emit a structured, correlation-friendly lifecycle event."""

    logger.info(
        event,
        extra={
            "event": event,
            "tenant_id": str(tenant_id),
            "asset_id": str(asset_id),
            "correlation_id": correlation_id or "unavailable",
            **details,
        },
    )


class AssetManagementError(ValidationError):
    """Stable domain validation error surfaced by API controllers."""

    def __init__(self, message: str, *, code: str, field: str | None = None) -> None:
        self.domain_code = code
        detail: object = {field: message} if field else message
        super().__init__(detail, code=code)


def _tenant_id(value: UUID | str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise AssetManagementError("tenant_id must be a valid UUID.", code="INVALID_TENANT") from exc


def _money(value: object, field: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AssetManagementError("Enter a valid monetary amount.", code="INVALID_MONEY", field=field) from exc
    return amount


def _asset_values(data: Mapping[str, object]) -> dict[str, object]:
    allowed = {
        "asset_code",
        "asset_name",
        "category",
        "purchase_date",
        "purchase_cost",
        "residual_value",
        "depreciation_method",
        "useful_life_years",
        "declining_balance_rate",
        "location",
        "is_active",
    }
    values = {name: value for name, value in data.items() if name in allowed}
    for field in ("purchase_cost", "residual_value"):
        if field in values:
            values[field] = _money(values[field], field)
    return values


def _validate_asset(asset: Asset, tenant_id: UUID) -> None:
    """Validate an asset while preserving the public duplicate-code error."""

    try:
        asset.full_clean()
    except ValidationError as exc:
        duplicate = (
            Asset.objects.for_tenant(tenant_id).filter(asset_code=asset.asset_code).exclude(pk=asset.pk).exists()
        )
        if duplicate:
            raise AssetManagementError(
                "An asset with this code already exists for the tenant.",
                code="DUPLICATE_ASSET_CODE",
                field="asset_code",
            ) from exc
        raise


class AssetService:
    """Tenant-bound asset CRUD; API controllers never save models directly."""

    @staticmethod
    def get_asset(tenant_id: UUID | str, asset_id: UUID | str, *, include_deleted: bool = False) -> Asset:
        tenant = _tenant_id(tenant_id)
        queryset = Asset.objects.for_tenant(tenant)
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        return queryset.get(pk=asset_id)

    @staticmethod
    def list_assets(tenant_id: UUID | str, *, include_deleted: bool = False) -> QuerySet[Asset]:
        tenant = _tenant_id(tenant_id)
        queryset = Asset.objects.for_tenant(tenant)
        return queryset if include_deleted else queryset.filter(is_deleted=False)

    @staticmethod
    @transaction.atomic
    def create_asset(
        tenant_id: UUID | str,
        asset_code: str,
        asset_name: str,
        purchase_date: date | str,
        purchase_cost: Decimal | str,
        correlation_id: str | None = None,
        **kwargs: object,
    ) -> Asset:
        """Create a validated asset and derive its opening book value."""

        tenant = _tenant_id(tenant_id)
        data: dict[str, object] = {
            **kwargs,
            "asset_code": asset_code,
            "asset_name": asset_name,
            "purchase_date": purchase_date,
            "purchase_cost": purchase_cost,
        }
        values = _asset_values(data)
        values["current_value"] = values["purchase_cost"]
        asset = Asset(tenant_id=tenant, **values)
        _validate_asset(asset, tenant)
        try:
            asset.save(force_insert=True)
        except IntegrityError as exc:
            raise AssetManagementError(
                "An asset with this code already exists for the tenant.",
                code="DUPLICATE_ASSET_CODE",
                field="asset_code",
            ) from exc
        _event("asset.created", tenant, asset.id, correlation_id, asset_code=asset.asset_code)
        return asset

    @staticmethod
    @transaction.atomic
    def update_asset(
        tenant_id: UUID | str,
        asset_id: UUID | str,
        data: Mapping[str, object],
        *,
        correlation_id: str | None = None,
    ) -> Asset:
        """Update a live asset without permitting ownership or ledger rewrites."""

        tenant = _tenant_id(tenant_id)
        asset = Asset.objects.select_for_update().for_tenant(tenant).filter(is_deleted=False).get(pk=asset_id)
        values = _asset_values(data)
        financial_fields = {
            "purchase_date",
            "purchase_cost",
            "residual_value",
            "depreciation_method",
            "useful_life_years",
            "declining_balance_rate",
        }
        has_history = DepreciationEntry.objects.for_tenant(tenant).filter(asset=asset).exists()
        if financial_fields.intersection(values) and has_history:
            raise AssetManagementError(
                "Depreciation settings cannot change after history has been recorded.",
                code="ASSET_HAS_DEPRECIATION_HISTORY",
            )
        for field, value in values.items():
            setattr(asset, field, value)
        if "purchase_cost" in values:
            asset.current_value = values["purchase_cost"]
        _validate_asset(asset, tenant)
        try:
            asset.save()
        except IntegrityError as exc:
            raise AssetManagementError(
                "An asset with this code already exists for the tenant.",
                code="DUPLICATE_ASSET_CODE",
                field="asset_code",
            ) from exc
        _event("asset.updated", tenant, asset.id, correlation_id, changed_fields=sorted(values))
        return asset

    @staticmethod
    @transaction.atomic
    def delete_asset(
        tenant_id: UUID | str,
        asset_id: UUID | str,
        *,
        correlation_id: str | None = None,
    ) -> Asset:
        """Soft-delete an asset while preserving its immutable financial trail."""

        tenant = _tenant_id(tenant_id)
        asset = Asset.objects.select_for_update().for_tenant(tenant).filter(is_deleted=False).get(pk=asset_id)
        asset.is_deleted = True
        asset.is_active = False
        asset.deleted_at = timezone.now()
        asset.full_clean()
        asset.save(update_fields=("is_deleted", "is_active", "deleted_at", "updated_at"))
        _event("asset.archived", tenant, asset.id, correlation_id)
        return asset


class DepreciationService:
    """Create and retrieve immutable monthly depreciation ledger entries."""

    @staticmethod
    def list_entries(tenant_id: UUID | str) -> QuerySet[DepreciationEntry]:
        return DepreciationEntry.objects.for_tenant(_tenant_id(tenant_id)).select_related("asset")

    @staticmethod
    def get_entry(tenant_id: UUID | str, entry_id: UUID | str) -> DepreciationEntry:
        return DepreciationEntry.objects.for_tenant(_tenant_id(tenant_id)).select_related("asset").get(pk=entry_id)

    @staticmethod
    @transaction.atomic
    def calculate_depreciation(
        tenant_id: UUID | str,
        asset_id: UUID | str,
        entry_date: date,
        *,
        correlation_id: str | None = None,
    ) -> DepreciationEntry:
        """Calculate one monthly entry using a locked, tenant-owned asset.

        Straight-line spreads depreciable cost evenly over the useful life.
        Declining balance applies either the configured annual percentage or a
        conventional double-declining annual rate. The final entry is capped at
        residual value and a zero-value ledger row is never fabricated.
        """

        tenant = _tenant_id(tenant_id)
        if not isinstance(entry_date, date):
            raise AssetManagementError("entry_date must be a date.", code="INVALID_ENTRY_DATE", field="entry_date")
        try:
            asset = Asset.objects.select_for_update().for_tenant(tenant).filter(is_deleted=False).get(pk=asset_id)
        except ObjectDoesNotExist:
            raise
        if not asset.is_active:
            raise AssetManagementError("Inactive assets cannot be depreciated.", code="ASSET_INACTIVE")
        if entry_date < asset.purchase_date:
            raise AssetManagementError(
                "Depreciation date cannot precede the purchase date.",
                code="ENTRY_BEFORE_PURCHASE",
                field="entry_date",
            )
        if asset.depreciation_method == DepreciationMethod.NONE:
            raise AssetManagementError("This asset is not depreciable.", code="ASSET_NOT_DEPRECIABLE")
        if not asset.useful_life_years:
            raise AssetManagementError("The asset has no useful life.", code="USEFUL_LIFE_REQUIRED")

        entries = DepreciationEntry.objects.for_tenant(tenant).filter(asset=asset)
        existing = entries.filter(entry_date=entry_date).first()
        if existing is not None:
            return existing
        if entries.filter(entry_date__year=entry_date.year, entry_date__month=entry_date.month).exists():
            raise AssetManagementError(
                "Depreciation has already been recorded for this accounting month.",
                code="DUPLICATE_DEPRECIATION_PERIOD",
                field="entry_date",
            )
        previous = entries.order_by("-entry_date", "-created_at").first()
        if previous and entry_date <= previous.entry_date:
            raise AssetManagementError(
                "Depreciation entries must be recorded in chronological order.",
                code="NON_CHRONOLOGICAL_ENTRY",
                field="entry_date",
            )

        opening_value = _money(asset.current_value, "current_value")
        remaining = _money(opening_value - asset.residual_value, "current_value")
        if remaining <= 0:
            raise AssetManagementError("The asset is already fully depreciated.", code="FULLY_DEPRECIATED")

        if asset.depreciation_method == DepreciationMethod.STRAIGHT_LINE:
            raw_amount = (asset.purchase_cost - asset.residual_value) / Decimal(asset.useful_life_years * 12)
        elif asset.depreciation_method == DepreciationMethod.DECLINING_BALANCE:
            annual_rate = (
                asset.declining_balance_rate / Decimal("100")
                if asset.declining_balance_rate is not None
                else min(Decimal("1"), Decimal("2") / Decimal(asset.useful_life_years))
            )
            raw_amount = opening_value * annual_rate / Decimal("12")
        else:
            raise AssetManagementError("Unsupported depreciation method.", code="UNSUPPORTED_DEPRECIATION_METHOD")

        amount = min(remaining, raw_amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))
        if amount <= 0:
            raise AssetManagementError(
                "The calculated depreciation is below the supported currency precision.",
                code="DEPRECIATION_BELOW_PRECISION",
            )
        book_value = _money(opening_value - amount, "book_value")
        accumulated = _money(
            (previous.accumulated_depreciation if previous else Decimal("0.00")) + amount,
            "accumulated_depreciation",
        )
        entry = DepreciationEntry(
            tenant_id=tenant,
            asset=asset,
            entry_date=entry_date,
            depreciation_amount=amount,
            accumulated_depreciation=accumulated,
            book_value=book_value,
        )
        entry.full_clean()
        try:
            entry.save(force_insert=True)
        except IntegrityError as exc:
            raise AssetManagementError(
                "Depreciation has already been recorded for this date.",
                code="DUPLICATE_DEPRECIATION_DATE",
                field="entry_date",
            ) from exc
        asset.current_value = book_value
        asset.save(update_fields=("current_value", "updated_at"))
        _event(
            "asset.depreciation_recorded",
            tenant,
            asset.id,
            correlation_id,
            depreciation_entry_id=str(entry.id),
            entry_date=entry.entry_date.isoformat(),
            amount=str(entry.depreciation_amount),
            book_value=str(entry.book_value),
        )
        return entry


__all__ = ["AssetManagementError", "AssetService", "DepreciationService"]
