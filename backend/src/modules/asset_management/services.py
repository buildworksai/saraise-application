"""Transactional business authority for Asset Management."""

from __future__ import annotations

import logging
import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound

from src.core.middleware.correlation import get_correlation_id

from .models import (
    Asset,
    AssetCategory,
    AssetIdempotencyRecord,
    AssetManagementConfiguration,
    AssetManagementConfigurationAudit,
    AssetManagementConfigurationVersion,
    DepreciationEntry,
    DepreciationMethod,
)

logger = logging.getLogger("saraise.asset_management")

DEFAULT_CONFIGURATION: dict[str, object] = {
    "environment": "default",
    "enabled": True,
    "rollout_roles": [],
    "rollout_cohorts": [],
    "asset_code_max_length": 50,
    "asset_name_max_length": 255,
    "location_max_length": 255,
    "monetary_max_digits": 15,
    "monetary_decimal_places": 2,
    "minimum_purchase_cost": "0.01",
    "default_residual_value": "0.00",
    "default_current_value": "0.00",
    "new_asset_active_default": True,
    "allowed_categories": ["fixed", "intangible", "current"],
    "default_category": "fixed",
    "allowed_depreciation_methods": ["straight_line", "declining_balance", "none"],
    "default_depreciation_method": "none",
    "non_depreciable_categories": ["current"],
    "useful_life_min_years": 1,
    "useful_life_max_years": 100,
    "default_useful_life_years": 5,
    "declining_rate_min": "0.0001",
    "declining_rate_max": "100.0000",
    "percentage_divisor": "100",
    "double_declining_factor": "2",
    "annual_cap": "1",
    "accounting_periods_per_year": 12,
    "posting_frequency": "monthly",
    "require_chronological_depreciation": True,
    "require_useful_life_for_depreciation": True,
    "declining_rate_requires_declining_method": True,
    "inactive_assets_depreciable": False,
    "allow_depreciation_before_purchase": False,
    "lock_financial_fields_after_history": True,
    "archive_sets_inactive": True,
    "archive_confirmation": "asset_code",
    "asset_list_page_size": 25,
    "asset_list_max_page_size": 100,
    "asset_list_default_ordering": "asset_code",
    "asset_detail_history_page_size": 12,
    "asset_search_fields": ["asset_code", "asset_name", "location"],
    "asset_ordering_fields": ["asset_code", "asset_name", "purchase_date", "purchase_cost", "current_value", "created_at"],
    "tenant_throttle_rate": "240/minute",
    "health_interval_seconds": 60,
}

INTEGER_LIMITS = {
    "asset_code_max_length": (1, 128),
    "asset_name_max_length": (1, 512),
    "location_max_length": (0, 512),
    "monetary_max_digits": (3, 18),
    "monetary_decimal_places": (0, 4),
    "useful_life_min_years": (1, 100),
    "useful_life_max_years": (1, 200),
    "default_useful_life_years": (1, 200),
    "accounting_periods_per_year": (1, 365),
    "asset_list_page_size": (1, 100),
    "asset_list_max_page_size": (1, 500),
    "asset_detail_history_page_size": (1, 100),
    "health_interval_seconds": (1, 3600),
}
DECIMAL_LIMITS = {
    "minimum_purchase_cost": (Decimal("0.0001"), Decimal("1000000000")),
    "default_residual_value": (Decimal("0"), Decimal("1000000000")),
    "default_current_value": (Decimal("0"), Decimal("1000000000")),
    "declining_rate_min": (Decimal("0.0001"), Decimal("100.0000")),
    "declining_rate_max": (Decimal("0.0001"), Decimal("500.0000")),
    "percentage_divisor": (Decimal("1"), Decimal("1000")),
    "double_declining_factor": (Decimal("0.0001"), Decimal("10")),
    "annual_cap": (Decimal("0.0001"), Decimal("1")),
}
MONEY_QUANTUM = Decimal("0.01")


def _event(event: str, tenant_id: UUID, asset_id: UUID, correlation_id: str | None, **details: object) -> None:
    """Emit a structured, correlation-friendly lifecycle event."""

    correlation = _correlation_id(correlation_id)
    logger.info(
        event,
        extra={
            "event": event,
            "tenant_id": str(tenant_id),
            "asset_id": str(asset_id),
            "correlation_id": correlation,
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


def _actor_id(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid5(NAMESPACE_URL, f"saraise:user:{value}")


def _correlation_id(value: str | None = None) -> str:
    correlation = value or get_correlation_id() or str(uuid4())
    if not isinstance(correlation, str) or not correlation.strip():
        raise AssetManagementError("correlation_id is required.", code="CORRELATION_ID_REQUIRED")
    if len(correlation.strip()) > 128:
        raise AssetManagementError("correlation_id must not exceed 128 characters.", code="INVALID_CORRELATION_ID")
    return correlation.strip()


def _configuration(tenant_id: UUID) -> dict[str, object]:
    return AssetConfigurationService().resolve(tenant_id)


def _money(value: object, field: str, configuration: Mapping[str, object] | None = None) -> Decimal:
    places = int((configuration or DEFAULT_CONFIGURATION)["monetary_decimal_places"])
    quantum = Decimal("1").scaleb(-places)
    try:
        amount = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AssetManagementError("Enter a valid monetary amount.", code="INVALID_MONEY", field=field) from exc
    return amount


def _asset_values(data: Mapping[str, object], configuration: Mapping[str, object]) -> dict[str, object]:
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
    }
    values = {name: value for name, value in data.items() if name in allowed}
    for field in ("purchase_cost", "residual_value"):
        if field in values:
            values[field] = _money(values[field], field, configuration)
    return values


def _validate_asset(asset: Asset, tenant_id: UUID, configuration: Mapping[str, object]) -> None:
    """Validate an asset while preserving the public duplicate-code error."""

    minimum_purchase_cost = Decimal(str(configuration["minimum_purchase_cost"]))
    if len(asset.asset_code.strip()) > int(configuration["asset_code_max_length"]):
        raise AssetManagementError("Asset code exceeds configured length.", code="ASSET_CODE_TOO_LONG", field="asset_code")
    if len(asset.asset_name.strip()) > int(configuration["asset_name_max_length"]):
        raise AssetManagementError("Asset name exceeds configured length.", code="ASSET_NAME_TOO_LONG", field="asset_name")
    if len(asset.location.strip()) > int(configuration["location_max_length"]):
        raise AssetManagementError("Location exceeds configured length.", code="LOCATION_TOO_LONG", field="location")
    if asset.category not in configuration["allowed_categories"]:
        raise AssetManagementError("Unsupported asset category.", code="UNSUPPORTED_CATEGORY", field="category")
    if asset.depreciation_method not in configuration["allowed_depreciation_methods"]:
        raise AssetManagementError("Unsupported depreciation method.", code="UNSUPPORTED_DEPRECIATION_METHOD", field="depreciation_method")
    if asset.purchase_cost < minimum_purchase_cost:
        raise AssetManagementError("Purchase cost is below the configured minimum.", code="PURCHASE_COST_TOO_LOW", field="purchase_cost")
    if asset.residual_value < Decimal("0") or asset.residual_value > asset.purchase_cost:
        raise AssetManagementError("Residual value must stay between zero and purchase cost.", code="INVALID_RESIDUAL_VALUE", field="residual_value")
    if asset.category in configuration["non_depreciable_categories"] and asset.depreciation_method != DepreciationMethod.NONE:
        raise AssetManagementError("This category is not depreciable.", code="CATEGORY_NOT_DEPRECIABLE", field="depreciation_method")
    if configuration["require_useful_life_for_depreciation"] and asset.depreciation_method != DepreciationMethod.NONE:
        if not asset.useful_life_years:
            raise AssetManagementError("A useful life is required for depreciable assets.", code="USEFUL_LIFE_REQUIRED", field="useful_life_years")
        if not int(configuration["useful_life_min_years"]) <= asset.useful_life_years <= int(configuration["useful_life_max_years"]):
            raise AssetManagementError("Useful life is outside configured bounds.", code="USEFUL_LIFE_OUT_OF_RANGE", field="useful_life_years")
    if configuration["declining_rate_requires_declining_method"] and asset.depreciation_method != DepreciationMethod.DECLINING_BALANCE and asset.declining_balance_rate is not None:
        raise AssetManagementError("A declining-balance rate is only valid with declining balance.", code="INVALID_DECLINING_RATE", field="declining_balance_rate")
    if asset.declining_balance_rate is not None:
        if not Decimal(str(configuration["declining_rate_min"])) <= asset.declining_balance_rate <= Decimal(str(configuration["declining_rate_max"])):
            raise AssetManagementError("Declining-balance rate is outside configured bounds.", code="DECLINING_RATE_OUT_OF_RANGE", field="declining_balance_rate")
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


class AssetConfigurationService:
    """Validate, version, audit, preview, import/export, and roll back tenant policy."""

    @staticmethod
    def validate_document(document: object) -> dict[str, object]:
        if not isinstance(document, dict):
            raise ValidationError({"document": "Configuration must be an object."})
        missing = set(DEFAULT_CONFIGURATION) - set(document)
        unknown = set(document) - set(DEFAULT_CONFIGURATION)
        if missing or unknown:
            detail: dict[str, object] = {}
            if missing:
                detail["missing"] = sorted(missing)
            if unknown:
                detail["unknown"] = sorted(unknown)
            raise ValidationError({"document": detail})
        normalized = deepcopy(document)
        for field, (minimum, maximum) in INTEGER_LIMITS.items():
            value = normalized[field]
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValidationError({field: f"Must be an integer from {minimum} through {maximum}."})
        for field, (minimum, maximum) in DECIMAL_LIMITS.items():
            try:
                value = Decimal(str(normalized[field]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError({field: "Must be a decimal string."}) from exc
            if not minimum <= value <= maximum:
                raise ValidationError({field: f"Must be from {minimum} through {maximum}."})
            normalized[field] = str(value)
        if normalized["useful_life_min_years"] > normalized["useful_life_max_years"]:
            raise ValidationError({"useful_life_max_years": "Must be at least useful_life_min_years."})
        if not normalized["useful_life_min_years"] <= normalized["default_useful_life_years"] <= normalized["useful_life_max_years"]:
            raise ValidationError({"default_useful_life_years": "Must be inside useful-life bounds."})
        if normalized["asset_list_page_size"] > normalized["asset_list_max_page_size"]:
            raise ValidationError({"asset_list_page_size": "Must not exceed asset_list_max_page_size."})
        for field, allowed in (
            ("allowed_categories", AssetCategory.values),
            ("allowed_depreciation_methods", DepreciationMethod.values),
        ):
            value = normalized[field]
            if not isinstance(value, list) or not value or not set(value).issubset(set(allowed)):
                raise ValidationError({field: "Contains unsupported values."})
        if normalized["default_category"] not in normalized["allowed_categories"]:
            raise ValidationError({"default_category": "Must be an allowed category."})
        if normalized["default_depreciation_method"] not in normalized["allowed_depreciation_methods"]:
            raise ValidationError({"default_depreciation_method": "Must be an allowed method."})
        if not set(normalized["non_depreciable_categories"]).issubset(set(normalized["allowed_categories"])):
            raise ValidationError({"non_depreciable_categories": "Must use allowed categories."})
        if Decimal(normalized["declining_rate_min"]) > Decimal(normalized["declining_rate_max"]):
            raise ValidationError({"declining_rate_max": "Must be at least declining_rate_min."})
        for field in ("enabled", "new_asset_active_default", "require_chronological_depreciation", "require_useful_life_for_depreciation", "declining_rate_requires_declining_method", "inactive_assets_depreciable", "allow_depreciation_before_purchase", "lock_financial_fields_after_history", "archive_sets_inactive"):
            if not isinstance(normalized[field], bool):
                raise ValidationError({field: "Must be a boolean."})
        for field in ("asset_search_fields", "asset_ordering_fields", "rollout_roles", "rollout_cohorts"):
            value = normalized[field]
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                raise ValidationError({field: "Must be a list of nonempty strings."})
        if normalized["posting_frequency"] not in {"monthly", "exact_date"}:
            raise ValidationError({"posting_frequency": "Unsupported posting frequency."})
        if normalized["archive_confirmation"] not in {"asset_code", "asset_name"}:
            raise ValidationError({"archive_confirmation": "Unsupported archive confirmation mode."})
        if normalized["environment"] not in {"default", "development", "self-hosted", "saas"}:
            raise ValidationError({"environment": "Unsupported environment."})
        if not isinstance(normalized["tenant_throttle_rate"], str) or "/" not in normalized["tenant_throttle_rate"]:
            raise ValidationError({"tenant_throttle_rate": "Use DRF rate syntax, for example 240/minute."})
        return normalized

    def get_configuration(self, tenant_id: UUID | str, actor_id: object | None = None, correlation_id: str | None = None) -> AssetManagementConfiguration:
        tenant = _tenant_id(tenant_id)
        existing = AssetManagementConfiguration.objects.for_tenant(tenant).first()
        if existing is not None:
            self.validate_document(existing.document)
            return existing
        actor = _actor_id(actor_id or UUID(int=0))
        correlation = _correlation_id(correlation_id)
        document = self.validate_document(deepcopy(DEFAULT_CONFIGURATION))
        with transaction.atomic():
            configuration, created = AssetManagementConfiguration.objects.get_or_create(
                tenant_id=tenant,
                defaults={"document": document, "version": 1, "updated_by": actor},
            )
            if created:
                self._record(configuration, actor, correlation, {}, document, "initialize", "default")
        return configuration

    def resolve(self, tenant_id: UUID | str) -> dict[str, object]:
        return deepcopy(self.get_configuration(tenant_id).document)

    def preview(self, tenant_id: UUID | str, document: object) -> dict[str, object]:
        current = self.get_configuration(tenant_id)
        normalized = self.validate_document(document)
        changes = {key: {"from": current.document[key], "to": normalized[key]} for key in normalized if current.document[key] != normalized[key]}
        return {"valid": True, "current_version": current.version, "changes": changes, "document": normalized}

    def update(self, tenant_id: UUID | str, actor_id: object, correlation_id: str, document: object, *, source: str = "api", action: str = "update") -> AssetManagementConfiguration:
        tenant = _tenant_id(tenant_id)
        actor = _actor_id(actor_id)
        correlation = _correlation_id(correlation_id)
        normalized = self.validate_document(document)
        with transaction.atomic():
            current = AssetManagementConfiguration.objects.select_for_update().for_tenant(tenant).first()
            if current is None:
                current = self.get_configuration(tenant, actor, correlation)
            previous = deepcopy(current.document)
            if previous == normalized:
                return current
            current.document = normalized
            current.version += 1
            current.updated_by = actor
            current.save(update_fields=("document", "version", "updated_by", "updated_at"))
            self._record(current, actor, correlation, previous, normalized, action, source)
        return current

    def history(self, tenant_id: UUID | str) -> QuerySet[AssetManagementConfigurationVersion]:
        configuration = self.get_configuration(tenant_id)
        return AssetManagementConfigurationVersion.objects.for_tenant(configuration.tenant_id).filter(configuration=configuration).order_by("-version", "-created_at")

    def rollback(self, tenant_id: UUID | str, actor_id: object, correlation_id: str, version: int) -> AssetManagementConfiguration:
        configuration = self.get_configuration(tenant_id, actor_id, correlation_id)
        snapshot = AssetManagementConfigurationVersion.objects.for_tenant(configuration.tenant_id).filter(configuration=configuration, version=version).first()
        if snapshot is None:
            raise NotFound("Configuration version was not found.")
        return self.update(tenant_id, actor_id, correlation_id, snapshot.document, source=f"rollback:{version}", action="rollback")

    def export_document(self, tenant_id: UUID | str) -> dict[str, object]:
        configuration = self.get_configuration(tenant_id)
        return {"schema_version": "1.0", "module": "asset_management", "version": configuration.version, "document": deepcopy(configuration.document)}

    def import_document(self, tenant_id: UUID | str, actor_id: object, correlation_id: str, payload: object) -> AssetManagementConfiguration:
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0" or payload.get("module") != "asset_management":
            raise ValidationError({"configuration": "Expected an asset_management configuration document with schema_version 1.0."})
        return self.update(tenant_id, actor_id, correlation_id, payload.get("document"), source="import", action="import")

    @staticmethod
    def _record(configuration: AssetManagementConfiguration, actor_id: UUID, correlation_id: str, previous: dict[str, object], current: dict[str, object], action: str, source: str) -> None:
        common = {"tenant_id": configuration.tenant_id, "created_by": actor_id, "configuration": configuration, "version": configuration.version, "correlation_id": correlation_id}
        AssetManagementConfigurationVersion.objects.create(**common, document=deepcopy(current), source=source)
        AssetManagementConfigurationAudit.objects.create(**common, action=action, previous_document=deepcopy(previous), current_document=deepcopy(current))


def _fingerprint(operation: str, data: Mapping[str, object]) -> str:
    payload = json.dumps({"operation": operation, "data": data}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        idempotency_key: str | None = None,
        **kwargs: object,
    ) -> Asset:
        """Create a validated asset and derive its opening book value."""

        tenant = _tenant_id(tenant_id)
        correlation = _correlation_id(correlation_id)
        if not idempotency_key:
            raise AssetManagementError("idempotency_key is required for asset creation.", code="IDEMPOTENCY_KEY_REQUIRED")
        configuration = _configuration(tenant)
        data: dict[str, object] = {
            **kwargs,
            "asset_code": asset_code,
            "asset_name": asset_name,
            "purchase_date": purchase_date,
            "purchase_cost": purchase_cost,
        }
        values = _asset_values(data, configuration)
        values.setdefault("category", configuration["default_category"])
        values.setdefault("residual_value", _money(configuration["default_residual_value"], "residual_value", configuration))
        values.setdefault("depreciation_method", configuration["default_depreciation_method"])
        values.setdefault("useful_life_years", configuration["default_useful_life_years"] if values["depreciation_method"] != DepreciationMethod.NONE else None)
        values.setdefault("location", "")
        values["is_active"] = bool(configuration["new_asset_active_default"])
        values["current_value"] = values["purchase_cost"]
        fingerprint = _fingerprint("asset.create", values)
        existing = AssetIdempotencyRecord.objects.for_tenant(tenant).filter(key=idempotency_key).first()
        if existing is not None:
            if existing.fingerprint != fingerprint or existing.operation != "asset.create":
                raise AssetManagementError("Idempotency key was reused with a different request.", code="IDEMPOTENCY_CONFLICT")
            return Asset.objects.for_tenant(tenant).get(pk=existing.result_id)
        asset = Asset(tenant_id=tenant, **values)
        _validate_asset(asset, tenant, configuration)
        try:
            asset.save(force_insert=True)
            AssetIdempotencyRecord.objects.create(
                tenant_id=tenant,
                key=idempotency_key,
                fingerprint=fingerprint,
                operation="asset.create",
                result_model="asset",
                result_id=asset.id,
                status_code=201,
                correlation_id=correlation,
            )
        except IntegrityError as exc:
            raise AssetManagementError(
                "An asset with this code already exists for the tenant.",
                code="DUPLICATE_ASSET_CODE",
                field="asset_code",
            ) from exc
        _event("asset.created", tenant, asset.id, correlation, asset_code=asset.asset_code)
        return asset

    @staticmethod
    @transaction.atomic
    def update_asset(
        tenant_id: UUID | str,
        asset_id: UUID | str,
        data: Mapping[str, object],
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Asset:
        """Update a live asset without permitting ownership or ledger rewrites."""

        tenant = _tenant_id(tenant_id)
        correlation = _correlation_id(correlation_id)
        if not idempotency_key:
            raise AssetManagementError("idempotency_key is required for asset updates.", code="IDEMPOTENCY_KEY_REQUIRED")
        configuration = _configuration(tenant)
        fingerprint = _fingerprint("asset.update", {"asset_id": asset_id, "data": data})
        existing = AssetIdempotencyRecord.objects.for_tenant(tenant).filter(key=idempotency_key).first()
        if existing is not None:
            if existing.fingerprint != fingerprint or existing.operation != "asset.update":
                raise AssetManagementError("Idempotency key was reused with a different request.", code="IDEMPOTENCY_CONFLICT")
            return Asset.objects.for_tenant(tenant).get(pk=existing.result_id)
        asset = Asset.objects.select_for_update().for_tenant(tenant).filter(is_deleted=False).get(pk=asset_id)
        values = _asset_values(data, configuration)
        financial_fields = {
            "purchase_date",
            "purchase_cost",
            "residual_value",
            "depreciation_method",
            "useful_life_years",
            "declining_balance_rate",
        }
        has_history = DepreciationEntry.objects.for_tenant(tenant).filter(asset=asset).exists()
        if configuration["lock_financial_fields_after_history"] and financial_fields.intersection(values) and has_history:
            raise AssetManagementError(
                "Depreciation settings cannot change after history has been recorded.",
                code="ASSET_HAS_DEPRECIATION_HISTORY",
            )
        for field, value in values.items():
            setattr(asset, field, value)
        if "purchase_cost" in values:
            asset.current_value = values["purchase_cost"]
        _validate_asset(asset, tenant, configuration)
        try:
            asset.save()
            AssetIdempotencyRecord.objects.create(
                tenant_id=tenant,
                key=idempotency_key,
                fingerprint=fingerprint,
                operation="asset.update",
                result_model="asset",
                result_id=asset.id,
                status_code=200,
                correlation_id=correlation,
            )
        except IntegrityError as exc:
            raise AssetManagementError(
                "An asset with this code already exists for the tenant.",
                code="DUPLICATE_ASSET_CODE",
                field="asset_code",
            ) from exc
        _event("asset.updated", tenant, asset.id, correlation, changed_fields=sorted(values))
        return asset

    @staticmethod
    @transaction.atomic
    def delete_asset(
        tenant_id: UUID | str,
        asset_id: UUID | str,
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Asset:
        """Soft-delete an asset while preserving its immutable financial trail."""

        tenant = _tenant_id(tenant_id)
        correlation = _correlation_id(correlation_id)
        if not idempotency_key:
            raise AssetManagementError("idempotency_key is required for asset archive.", code="IDEMPOTENCY_KEY_REQUIRED")
        configuration = _configuration(tenant)
        existing = AssetIdempotencyRecord.objects.for_tenant(tenant).filter(key=idempotency_key).first()
        if existing is not None:
            requested_asset_id = asset_id if isinstance(asset_id, UUID) else UUID(str(asset_id))
            if existing.operation != "asset.archive" or existing.result_id != requested_asset_id:
                raise AssetManagementError("Idempotency key was reused with a different request.", code="IDEMPOTENCY_CONFLICT")
            return Asset.objects.for_tenant(tenant).get(pk=existing.result_id)
        asset = Asset.objects.select_for_update().for_tenant(tenant).filter(pk=asset_id).first()
        if asset is None:
            raise ObjectDoesNotExist()
        if asset.is_deleted:
            return asset
        asset.is_deleted = True
        if configuration["archive_sets_inactive"]:
            asset.is_active = False
        asset.deleted_at = timezone.now()
        asset.full_clean()
        asset.save(update_fields=("is_deleted", "is_active", "deleted_at", "updated_at"))
        AssetIdempotencyRecord.objects.create(
            tenant_id=tenant,
            key=idempotency_key,
            fingerprint=_fingerprint("asset.archive", {"asset_id": asset.id}),
            operation="asset.archive",
            result_model="asset",
            result_id=asset.id,
            status_code=204,
            correlation_id=correlation,
        )
        _event("asset.archived", tenant, asset.id, correlation)
        return asset

    @staticmethod
    @transaction.atomic
    def set_active_state(
        tenant_id: UUID | str,
        asset_id: UUID | str,
        *,
        is_active: bool,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Asset:
        """Perform an explicit lifecycle transition with correlated evidence."""

        tenant = _tenant_id(tenant_id)
        correlation = _correlation_id(correlation_id)
        if not idempotency_key:
            raise AssetManagementError("idempotency_key is required for lifecycle transitions.", code="IDEMPOTENCY_KEY_REQUIRED")
        fingerprint = _fingerprint("asset.active_state", {"asset_id": asset_id, "is_active": is_active})
        existing = AssetIdempotencyRecord.objects.for_tenant(tenant).filter(key=idempotency_key).first()
        if existing is not None:
            if existing.fingerprint != fingerprint or existing.operation != "asset.active_state":
                raise AssetManagementError("Idempotency key was reused with a different request.", code="IDEMPOTENCY_CONFLICT")
            return Asset.objects.for_tenant(tenant).get(pk=existing.result_id)
        asset = Asset.objects.select_for_update().for_tenant(tenant).filter(is_deleted=False).get(pk=asset_id)
        if asset.is_active == is_active:
            AssetIdempotencyRecord.objects.create(
                tenant_id=tenant,
                key=idempotency_key,
                fingerprint=fingerprint,
                operation="asset.active_state",
                result_model="asset",
                result_id=asset.id,
                status_code=200,
                correlation_id=correlation,
            )
            return asset
        asset.is_active = is_active
        asset.full_clean()
        asset.save(update_fields=("is_active", "updated_at"))
        AssetIdempotencyRecord.objects.create(
            tenant_id=tenant,
            key=idempotency_key,
            fingerprint=fingerprint,
            operation="asset.active_state",
            result_model="asset",
            result_id=asset.id,
            status_code=200,
            correlation_id=correlation,
        )
        _event("asset.activated" if is_active else "asset.deactivated", tenant, asset.id, correlation)
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
        correlation = _correlation_id(correlation_id)
        configuration = _configuration(tenant)
        if not isinstance(entry_date, date):
            raise AssetManagementError("entry_date must be a date.", code="INVALID_ENTRY_DATE", field="entry_date")
        try:
            asset = Asset.objects.select_for_update().for_tenant(tenant).filter(is_deleted=False).get(pk=asset_id)
        except ObjectDoesNotExist:
            raise
        if not configuration["inactive_assets_depreciable"] and not asset.is_active:
            raise AssetManagementError("Inactive assets cannot be depreciated.", code="ASSET_INACTIVE")
        if not configuration["allow_depreciation_before_purchase"] and entry_date < asset.purchase_date:
            raise AssetManagementError(
                "Depreciation date cannot precede the purchase date.",
                code="ENTRY_BEFORE_PURCHASE",
                field="entry_date",
            )
        if asset.depreciation_method == DepreciationMethod.NONE:
            raise AssetManagementError("This asset is not depreciable.", code="ASSET_NOT_DEPRECIABLE")
        if configuration["require_useful_life_for_depreciation"] and not asset.useful_life_years:
            raise AssetManagementError("The asset has no useful life.", code="USEFUL_LIFE_REQUIRED")

        entries = DepreciationEntry.objects.for_tenant(tenant).filter(asset=asset)
        existing = entries.filter(entry_date=entry_date).first()
        if existing is not None:
            return existing
        if configuration["posting_frequency"] == "monthly" and entries.filter(entry_date__year=entry_date.year, entry_date__month=entry_date.month).exists():
            raise AssetManagementError(
                "Depreciation has already been recorded for this accounting month.",
                code="DUPLICATE_DEPRECIATION_PERIOD",
                field="entry_date",
            )
        previous = entries.order_by("-entry_date", "-created_at").first()
        if configuration["require_chronological_depreciation"] and previous and entry_date <= previous.entry_date:
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
            raw_amount = (asset.purchase_cost - asset.residual_value) / Decimal(asset.useful_life_years * int(configuration["accounting_periods_per_year"]))
        elif asset.depreciation_method == DepreciationMethod.DECLINING_BALANCE:
            annual_rate = (
                asset.declining_balance_rate / Decimal(str(configuration["percentage_divisor"]))
                if asset.declining_balance_rate is not None
                else min(Decimal(str(configuration["annual_cap"])), Decimal(str(configuration["double_declining_factor"])) / Decimal(asset.useful_life_years))
            )
            raw_amount = opening_value * annual_rate / Decimal(int(configuration["accounting_periods_per_year"]))
        else:
            raise AssetManagementError("Unsupported depreciation method.", code="UNSUPPORTED_DEPRECIATION_METHOD")

        amount = min(remaining, raw_amount.quantize(Decimal("1").scaleb(-int(configuration["monetary_decimal_places"])), rounding=ROUND_HALF_UP))
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
            correlation,
            depreciation_entry_id=str(entry.id),
            entry_date=entry.entry_date.isoformat(),
            amount=str(entry.depreciation_amount),
            book_value=str(entry.book_value),
        )
        return entry


__all__ = ["AssetConfigurationService", "AssetManagementError", "AssetService", "DepreciationService", "DEFAULT_CONFIGURATION", "INTEGER_LIMITS", "DECIMAL_LIMITS"]
