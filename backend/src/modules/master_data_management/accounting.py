"""Accounting-facing party directory adapter backed by governed MDM records."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from src.modules.accounting_finance.integrations import SPI_VERSION, PartyRecordV1, extension_registry

from .models import EntityStatus, MasterDataEntity, MasterEntityType


class MDMPartyDirectory:
    """Resolve customer and supplier parties through active MDM entities."""

    schema_version = SPI_VERSION

    def resolve_party(
        self,
        tenant_id: UUID,
        party_id: UUID,
        *,
        party_type: Literal["supplier", "customer"],
        requested_amount: Decimal | None = None,
        currency: str | None = None,
    ) -> PartyRecordV1:
        del requested_amount
        entity_type = (
            MasterEntityType.objects.for_tenant(tenant_id)
            .filter(
                key=party_type,
                is_active=True,
                is_deleted=False,
            )
            .first()
        )
        if entity_type is None:
            return PartyRecordV1(SPI_VERSION, tenant_id, party_id, party_type, False)
        entity = (
            MasterDataEntity.objects.for_tenant(tenant_id)
            .filter(
                id=party_id,
                entity_type=entity_type,
                is_deleted=False,
            )
            .first()
        )
        if entity is None:
            return PartyRecordV1(SPI_VERSION, tenant_id, party_id, party_type, False)
        data = entity.data if isinstance(entity.data, dict) else {}
        raw_credit = data.get("available_credit")
        available_credit = Decimal(str(raw_credit)) if raw_credit not in (None, "") else None
        return PartyRecordV1(
            SPI_VERSION,
            tenant_id,
            party_id,
            party_type,
            entity.status == EntityStatus.ACTIVE and entity_type.is_active,
            bool(data.get("credit_approved", True)),
            available_credit,
            str(data.get("currency") or currency) if data.get("currency") or currency else None,
        )


_PARTY_DIRECTORY = MDMPartyDirectory()


def register_accounting_party_directory() -> None:
    """Register the MDM party adapter during Django app startup."""

    extension_registry.register_party_directory(_PARTY_DIRECTORY)
