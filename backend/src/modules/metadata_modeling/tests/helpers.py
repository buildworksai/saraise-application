"""Real domain builders shared by metadata-modeling tests."""

from __future__ import annotations

import uuid

from src.modules.metadata_modeling.models import EntityDefinition
from src.modules.metadata_modeling.services import (
    DynamicResourceService,
    SchemaVersionService,
)

ACTOR_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def text_field(*, required: bool = True, key: str = "title", order: int = 0) -> dict[str, object]:
    return {
        "name": key.replace("_", " ").title(),
        "key": key,
        "field_type": "text",
        "is_required": required,
        "is_searchable": True,
        "validation_rules": {"min_length": 2, "max_length": 80},
        "order": order,
    }


def published_entity(
    tenant_id: uuid.UUID,
    *,
    code: str = "ticket",
    is_submittable: bool = True,
    fields: list[dict[str, object]] | None = None,
) -> tuple[EntityDefinition, object]:
    entity = EntityDefinition.objects.create(
        tenant_id=tenant_id,
        name=code.replace("_", " ").title(),
        plural_name=f"{code.replace('_', ' ').title()}s",
        code=code,
        is_submittable=is_submittable,
        created_by=ACTOR_ID,
        updated_by=ACTOR_ID,
    )
    candidate = SchemaVersionService.create_candidate(
        tenant_id,
        ACTOR_ID,
        entity.id,
        fields or [text_field()],
        based_on_version_id=None,
        change_summary="Initial schema",
        correlation_id="corr-schema",
    )
    published = SchemaVersionService.publish_candidate(
        tenant_id,
        ACTOR_ID,
        entity.id,
        candidate.id,
        idempotency_key=f"publish-{entity.id}",
        correlation_id="corr-schema",
    )
    entity.refresh_from_db()
    return entity, published


def resource_for(tenant_id: uuid.UUID, entity: EntityDefinition, *, title: str = "Incident one"):
    return DynamicResourceService.create_resource(
        tenant_id,
        ACTOR_ID,
        entity.id,
        {"title": title},
        display_name=title,
        idempotency_key=f"create-{entity.id}-{title}",
        correlation_id="corr-resource",
    )
