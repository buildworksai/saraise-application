from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.accounting_finance.integrations import (
    AccountingExtensionRegistry,
    CapabilityUnavailable,
    DimensionProviderV1,
    ExtensionValidationError,
    FixedAssetAccountingFacade,
    InvalidProviderResult,
    JournalLegV1,
    JournalPostingRequestV1,
    JournalPostingResultV1,
    PartyDirectoryPortV1,
    PartyRecordV1,
    RegistrationConflict,
    SchemaVersionRejected,
    extension_registry,
)


class PartyDirectory:
    schema_version = "1.0"

    def resolve_party(self, tenant_id, party_id, *, party_type, requested_amount=None, currency=None):
        return PartyRecordV1(
            "1.0",
            tenant_id,
            party_id,
            party_type,
            True,
            available_credit=Decimal("100.00"),
            currency=currency,
        )


class Dimensions:
    schema_version = "1.0"
    namespace = "project"

    def validate(self, tenant_id, values):
        del tenant_id
        return {key: value.upper() for key, value in values.items()}


def test_protocol_compatibility() -> None:
    assert isinstance(PartyDirectory(), PartyDirectoryPortV1)
    assert isinstance(Dimensions(), DimensionProviderV1)


def test_journal_contract_rejects_float_and_unbalanced_legs() -> None:
    account = uuid4()
    with pytest.raises(ExtensionValidationError):
        JournalLegV1(account, "debit", 1.2, "USD")
    with pytest.raises(ExtensionValidationError, match="balance"):
        JournalPostingRequestV1(
            schema_version="1.0",
            tenant_id=uuid4(),
            posting_date=date.today(),
            currency="USD",
            source_module="fixed_assets",
            entry_number="FA-1",
            source_reference="asset:1",
            idempotency_key="posting-1",
            correlation_id=str(uuid4()),
            actor_id="actor-1",
            legs=(
                JournalLegV1(account, "debit", Decimal("10"), "USD"),
                JournalLegV1(uuid4(), "credit", Decimal("9"), "USD"),
            ),
        )


def test_registry_fails_closed_and_rejects_duplicate_registration() -> None:
    registry = AccountingExtensionRegistry()
    with pytest.raises(CapabilityUnavailable):
        registry.party_directory()
    provider = PartyDirectory()
    registry.register_party_directory(provider)
    registry.register_party_directory(provider)  # idempotent app autoreload
    with pytest.raises(RegistrationConflict):
        registry.register_party_directory(PartyDirectory())


def test_registry_rejects_schema_version_and_invalid_provider_result() -> None:
    registry = AccountingExtensionRegistry()
    invalid = PartyDirectory()
    invalid.schema_version = "2.0"
    with pytest.raises(SchemaVersionRejected):
        registry.register_party_directory(invalid)

    class WrongTenant(PartyDirectory):
        def resolve_party(self, tenant_id, party_id, **kwargs):
            return PartyRecordV1("1.0", uuid4(), party_id, kwargs["party_type"], True)

    registry.register_party_directory(WrongTenant())
    with pytest.raises(InvalidProviderResult):
        registry.resolve_party(uuid4(), uuid4(), party_type="supplier")


def test_customer_credit_and_tenant_identity_are_enforced() -> None:
    registry = AccountingExtensionRegistry()
    registry.register_party_directory(PartyDirectory())
    tenant, customer = uuid4(), uuid4()
    result = registry.resolve_party(
        tenant,
        customer,
        party_type="customer",
        requested_amount=Decimal("100.00"),
        currency="USD",
    )
    assert result.tenant_id == tenant
    with pytest.raises(ExtensionValidationError, match="insufficient"):
        registry.resolve_party(
            tenant,
            customer,
            party_type="customer",
            requested_amount=Decimal("100.01"),
            currency="USD",
        )


def test_dimension_validation_is_namespaced_and_provider_backed() -> None:
    registry = AccountingExtensionRegistry()
    assert registry.validate_dimensions(uuid4(), {}) == {}
    with pytest.raises(CapabilityUnavailable):
        registry.validate_dimensions(uuid4(), {"project.code": "alpha"})
    registry.register_dimension_provider("project", Dimensions())
    assert registry.validate_dimensions(uuid4(), {"project.code": "alpha"}) == {"project.code": "ALPHA"}
    with pytest.raises(ExtensionValidationError):
        registry.validate_dimensions(uuid4(), {"code": "alpha"})


@pytest.mark.django_db
def test_fixed_asset_facade_returns_exact_fixed_assets_result(monkeypatch) -> None:
    from src.modules.fixed_assets.integrations import (
        AccountingPostingRequest,
        AccountingPostingResult,
        JournalLeg,
    )

    tenant, asset, line = uuid4(), uuid4(), uuid4()
    captured = {}

    class PostingPort:
        schema_version = "1.0"

        def post_journal(self, request):
            captured["request"] = request
            return JournalPostingResultV1("1.0", uuid4(), request.entry_number, "2026-07-23T00:00:00Z")

    monkeypatch.setattr(extension_registry, "_posting", PostingPort())
    request = AccountingPostingRequest(
        schema_version="1.0",
        tenant_id=tenant,
        asset_id=asset,
        depreciation_line_id=line,
        posting_date=date(2026, 7, 23),
        currency="USD",
        idempotency_key="asset-post-1",
        correlation_id="cmd-fixed-asset-1",
        actor_id="actor-1",
        legs=(
            JournalLeg(uuid4(), "debit", Decimal("12.50"), "USD"),
            JournalLeg(uuid4(), "credit", Decimal("12.50"), "USD"),
        ),
        metadata={"schedule_id": str(uuid4())},
    )
    result = FixedAssetAccountingFacade.post_fixed_asset_journal(request)
    assert isinstance(result, AccountingPostingResult)
    assert captured["request"].metadata["fixed_assets.asset_id"] == asset
    assert "fixed_assets.schedule_id" in captured["request"].metadata


def test_fixed_asset_facade_rejects_unknown_schema() -> None:
    with pytest.raises(SchemaVersionRejected):
        FixedAssetAccountingFacade.validate_fixed_asset_accounts(
            tenant_id=uuid4(),
            account_ids=(uuid4(),),
            schema_version="9.0",
        )
