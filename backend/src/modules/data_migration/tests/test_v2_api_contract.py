"""Focused executable contracts for the governed data-migration API v2."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.urls import resolve, reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.modules.data_migration import api
from src.modules.data_migration.health import readiness
from src.modules.data_migration.permissions import (
    CONNECTION_ACTION_PERMISSIONS,
    JOB_ACTION_PERMISSIONS,
    PERMISSIONS,
    ActionAccessMixin,
)
from src.modules.data_migration.serializers import (
    DataMigrationConfigurationUpdateSerializer,
    ExternalConnectionManagementSerializer,
    MigrationJobCreateSerializer,
    safe_source_config,
)


def test_all_domain_permissions_are_specific_and_unique() -> None:
    assert len(PERMISSIONS) == len(set(PERMISSIONS)) == 15
    assert all(value.startswith("data_migration.") and ":" in value for value in PERMISSIONS)
    assert JOB_ACTION_PERMISSIONS["request_dry_run"] == "data_migration.run:execute"
    assert CONNECTION_ACTION_PERMISSIONS["test_connection"] == "data_migration.connection:test"


def test_access_boundary_uses_governed_profile_and_fail_closed_pipeline() -> None:
    assert issubclass(api.TenantGovernedViewSet, GovernedAPIViewMixin)
    assert api.TenantGovernedViewSet.pagination_class is GovernedPageNumberPagination
    assert RequiresAccess in ActionAccessMixin.permission_classes
    boundary = api.MigrationJobViewSet()
    boundary.action = "undeclared"
    boundary.request = SimpleNamespace(
        method="POST",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid.uuid4())),
    )
    permissions = boundary.get_permissions()
    assert isinstance(permissions[-1], RequiresAccess)
    assert boundary.required_permission is None


@pytest.mark.parametrize(
    ("path", "view_name"),
    (
        ("/api/v2/data-migration/jobs/", "data_migration:job-list"),
        ("/api/v2/data-migration/health/live/", "data_migration:health-live"),
        ("/api/v2/data-migration/health/ready/", "data_migration:health-ready"),
        ("/api/v2/data-migration/configuration/", "data_migration:configuration"),
    ),
)
def test_required_v2_routes_resolve(path: str, view_name: str) -> None:
    assert resolve(path).view_name == view_name
    assert reverse(view_name).startswith("/api/v2/data-migration/")


def test_sensitive_source_keys_never_serialize() -> None:
    assert safe_source_config(
        {
            "connection_id": "safe",
            "table": "customers",
            "password": "secret",
            "headers": {"Authorization": "secret"},
            "absolute_url": "https://example.test",
        }
    ) == {"connection_id": "safe", "table": "customers"}


def test_job_serializer_rejects_tenant_and_actor_spoofing() -> None:
    serializer = MigrationJobCreateSerializer(
        data={
            "tenant_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "name": "Import",
            "source_type": "csv",
            "source_artifact_id": str(uuid.uuid4()),
            "source_config": {"batch_size": 25},
            "target_adapter": "crm.customer",
            "target_entity": "customer",
            "write_mode": "create",
            "lookup_fields": [],
        }
    )
    assert not serializer.is_valid()
    assert serializer.errors["tenant_id"] == "Unknown field."
    assert serializer.errors["created_by"] == "Unknown field."


def test_connection_serializer_never_accepts_tenant_or_actor_fields() -> None:
    serializer = ExternalConnectionManagementSerializer(
        data={"tenant_id": str(uuid.uuid4()), "created_by": str(uuid.uuid4()), "name": "source", "kind": "http"}
    )
    assert not serializer.is_valid()
    assert set(serializer.errors) >= {"tenant_id", "created_by"}


@pytest.mark.parametrize(
    "field,value",
    (
        ("batch_size", 0),
        ("batch_size", 10_001),
        ("retry_count", 11),
        ("preview_row_limit", 101),
        ("rollout_percentage", 101),
    ),
)
def test_configuration_safe_limits_are_unsavable(field: str, value: int) -> None:
    serializer = DataMigrationConfigurationUpdateSerializer(data={"expected_version": 1, field: value})
    assert not serializer.is_valid()
    assert field in serializer.errors


def test_idempotency_header_is_required_and_bounded() -> None:
    request = APIRequestFactory().post("/runs")
    with pytest.raises(ValidationError):
        api._idempotency_key(request)
    request = APIRequestFactory().post("/runs", HTTP_IDEMPOTENCY_KEY="run:tenant-1:42")
    assert api._idempotency_key(request) == "run:tenant-1:42"


def test_health_readiness_redacts_dependency_exception() -> None:
    def failure() -> bool:
        raise RuntimeError("postgres://admin:secret@internal.example/private")

    payload, status_code = readiness({"database": failure})
    assert status_code == 503
    assert payload["components"] == {"database": "UNAVAILABLE"}
    assert "secret" not in str(payload)
