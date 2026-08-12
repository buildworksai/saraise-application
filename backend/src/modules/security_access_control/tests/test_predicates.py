"""Closed predicate DSL validation, compilation, and preview evaluation."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db.models import Q

from src.modules.security_access_control.models import SecurityConfiguration
from src.modules.security_access_control.predicates import compile_predicate, predicate_matches, validate_predicate


def test_validate_predicate_requires_explicit_limits_without_tenant_configuration() -> None:
    with pytest.raises(ValidationError, match="Tenant predicate limits are required"):
        validate_predicate({"op": "eq", "field": "owner_id", "value": "a"})


@pytest.fixture
def predicate_configuration(tenant_a) -> SecurityConfiguration:
    return SecurityConfiguration.objects.create(
        tenant_id=tenant_a.id,
        environment="development",
        version=1,
        document={
            "limits": {
                "predicate_max_nodes": 20,
                "predicate_max_depth": 8,
                "predicate_max_in_values": 5,
            }
        },
        rollout={"enabled": True},
        updated_by=uuid.uuid4(),
        correlation_id="predicate-test",
    )


@pytest.mark.parametrize(
    ("predicate", "message"),
    (
        ("not-object", "Every predicate node"),
        ({"op": "raw_sql", "field": "owner_id"}, "operator"),
        ({"op": "and", "args": []}, "non-empty args"),
        ({"op": "or", "args": "bad"}, "must be an array"),
        ({"op": "not", "args": []}, "exactly one arg"),
        ({"op": "eq", "field": "owner_id__contains", "value": "x"}, "registered simple identifier"),
        ({"op": "eq", "field": "unknown", "value": "x"}, "not registered"),
        ({"op": "eq", "field": "owner_id", "value": []}, "literal type"),
        ({"op": "in", "field": "status", "value": []}, "requires 1 to 2"),
        ({"op": "in", "field": "status", "value": ["new", "open", "closed"]}, "requires 1 to 2"),
        ({"op": "is_null", "field": "owner_id", "value": None}, "unexpected or missing keys"),
    ),
)
def test_validate_predicate_rejects_unsafe_shapes(predicate: object, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validate_predicate(
            predicate,
            allowed_fields=("owner_id", "status"),
            max_nodes=4,
            max_depth=3,
            max_in_values=2,
        )


def test_validate_predicate_enforces_complexity_limits() -> None:
    too_many_nodes = {
        "op": "and",
        "args": [
            {"op": "eq", "field": "status", "value": "open"},
            {"op": "eq", "field": "owner_id", "value": "u-1"},
        ],
    }
    with pytest.raises(ValidationError, match="safe complexity"):
        validate_predicate(
            too_many_nodes,
            allowed_fields=("owner_id", "status"),
            max_nodes=2,
            max_depth=4,
            max_in_values=2,
        )

    too_deep = {"op": "not", "arg": {"op": "not", "arg": {"op": "eq", "field": "status", "value": "open"}}}
    with pytest.raises(ValidationError, match="safe complexity"):
        validate_predicate(
            too_deep,
            allowed_fields=("owner_id", "status"),
            max_nodes=5,
            max_depth=2,
            max_in_values=2,
        )


@pytest.mark.django_db
def test_compile_predicate_covers_all_operations(tenant_a, predicate_configuration) -> None:
    tenant_id = tenant_a.id
    subject_id = uuid.uuid4()
    predicate = {
        "op": "and",
        "args": [
            {"op": "tenant", "field": "tenant_id"},
            {"op": "owner", "field": "owner_id"},
            {"op": "is_null", "field": "deleted_at"},
            {
                "op": "or",
                "args": [
                    {"op": "eq", "field": "status", "value": {"subject": "preferred_status"}},
                    {"op": "in", "field": "status", "value": ["open", "review"]},
                ],
            },
            {"op": "not", "arg": {"op": "eq", "field": "status", "value": "blocked"}},
        ],
    }

    compiled = compile_predicate(
        predicate,
        allowed_fields=("tenant_id", "owner_id", "deleted_at", "status"),
        subject_attributes={"id": subject_id, "preferred_status": "approved"},
        tenant_id=tenant_id,
    )

    assert isinstance(compiled, Q)
    assert "tenant_id" in str(compiled)
    assert "owner_id" in str(compiled)
    assert "deleted_at__isnull" in str(compiled)
    assert "status__in" in str(compiled)


@pytest.mark.django_db
def test_compile_owner_without_subject_id_returns_empty_q(tenant_a, predicate_configuration) -> None:
    compiled = compile_predicate(
        {"op": "owner", "field": "owner_id"},
        allowed_fields=("owner_id",),
        subject_attributes={},
        tenant_id=tenant_a.id,
    )

    assert "pk__in" in str(compiled)


@pytest.mark.django_db
def test_predicate_matches_evaluates_all_operations(tenant_a, predicate_configuration) -> None:
    subject_id = uuid.uuid4()
    record = {
        "tenant_id": str(tenant_a.id),
        "owner_id": str(subject_id),
        "status": "approved",
        "deleted_at": None,
    }

    predicate = {
        "op": "and",
        "args": [
            {"op": "tenant", "field": "tenant_id"},
            {"op": "owner", "field": "owner_id"},
            {"op": "is_null", "field": "deleted_at"},
            {"op": "eq", "field": "status", "value": {"subject": "preferred_status"}},
            {"op": "not", "arg": {"op": "in", "field": "status", "value": ["blocked", "closed"]}},
        ],
    }

    assert predicate_matches(
        predicate,
        record=record,
        allowed_fields=("tenant_id", "owner_id", "status", "deleted_at"),
        subject_attributes={"id": subject_id, "preferred_status": "approved"},
        tenant_id=tenant_a.id,
    )
    assert not predicate_matches(
        {"op": "owner", "field": "owner_id"},
        record={**record, "owner_id": str(uuid.uuid4())},
        allowed_fields=("owner_id",),
        subject_attributes={"id": subject_id},
        tenant_id=tenant_a.id,
    )
    assert not predicate_matches(
        {"op": "or", "args": [{"op": "eq", "field": "status", "value": "new"}]},
        record=record,
        allowed_fields=("status",),
        subject_attributes={"id": subject_id},
        tenant_id=tenant_a.id,
    )


@pytest.mark.django_db
def test_compile_and_preview_reject_untrusted_subject_references(tenant_a, predicate_configuration) -> None:
    bad_mapping = {"op": "eq", "field": "owner_id", "value": {"tenant": "id"}}
    missing_subject = {"op": "eq", "field": "owner_id", "value": {"subject": "missing"}}

    with pytest.raises(ValidationError, match="trusted subject"):
        compile_predicate(
            bad_mapping,
            allowed_fields=("owner_id",),
            subject_attributes={"id": uuid.uuid4()},
            tenant_id=tenant_a.id,
        )

    with pytest.raises(ValidationError, match="unavailable"):
        predicate_matches(
            missing_subject,
            record={"owner_id": uuid.uuid4()},
            allowed_fields=("owner_id",),
            subject_attributes={"id": uuid.uuid4()},
            tenant_id=tenant_a.id,
        )
