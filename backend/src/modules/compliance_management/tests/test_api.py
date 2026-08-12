"""Governed API v2 contract tests using real session authentication."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from src.core.access.permissions import RequiresAccess
from src.core.api import OperationFailed
from src.modules.compliance_management import api
from src.modules.compliance_management.models import ComplianceConfigurationRevision
from src.modules.compliance_management.services import (
    ComplianceConflict,
    ComplianceDependencyUnavailable,
    ComplianceNotFound,
    ComplianceValidationError,
)

from .factories import ComplianceConfigurationRevisionFactory, ComplianceFrameworkFactory

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/compliance-management"


@pytest.fixture(autouse=True)
def allow_manifest_access(monkeypatch):
    """Exercise API tenancy after the access pipeline grants an explicit decision."""
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


def test_unauthenticated_request_uses_stable_401_envelope():
    response = APIClient().get(f"{BASE}/frameworks/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"]
    assert response.json()["error"]["correlation_id"]


def test_framework_create_and_paginated_list_are_governed(authenticated_tenant_a_client, tenant_a):
    response = authenticated_tenant_a_client.post(
        f"{BASE}/frameworks/",
        {"code": "ISO", "name": "ISO controls", "version": "1", "category": "General", "source_kind": "custom"},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.content
    payload = response.json()
    assert set(payload) == {"data", "meta"}
    assert "tenant_id" not in payload["data"]

    listed = authenticated_tenant_a_client.get(f"{BASE}/frameworks/?search=ISO&page_size=1")
    assert listed.status_code == status.HTTP_200_OK
    body = listed.json()
    assert body["data"][0]["code"] == "ISO"
    assert body["meta"]["pagination"]["page_size"] == 1


def test_unknown_and_client_lifecycle_fields_are_rejected(authenticated_tenant_a_client):
    response = authenticated_tenant_a_client.post(
        f"{BASE}/frameworks/",
        {
            "code": "FW",
            "name": "Framework",
            "version": "1",
            "category": "General",
            "source_kind": "custom",
            "status": "active",
            "tenant_id": str(uuid.uuid4()),
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    detail = response.json()["error"]["detail"]
    assert "status" in detail and "tenant_id" in detail


def test_foreign_detail_is_exact_404(authenticated_tenant_a_client, tenant_b):
    foreign = ComplianceFrameworkFactory(tenant_id=tenant_b.id)
    response = authenticated_tenant_a_client.get(f"{BASE}/frameworks/{foreign.id}/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_endpoint_matrix_routes_resolve_without_legacy_prefix(authenticated_tenant_a_client):
    for path in (
        "dashboard/",
        "frameworks/",
        "requirements/",
        "policies/",
        "mappings/",
        "assessments/",
        "evidence/",
        "configuration/",
        "activity/",
    ):
        response = authenticated_tenant_a_client.get(f"{BASE}/{path}")
        assert response.status_code != status.HTTP_404_NOT_FOUND, path
    assert APIClient().get("/api/v1/compliance-management/policies/").status_code == status.HTTP_404_NOT_FOUND


def test_compliance_api_helpers_fail_closed_and_translate_domain_errors(tenant_a):
    request = SimpleNamespace(
        tenant_id=str(tenant_a.id),
        user=SimpleNamespace(),
        headers={"Idempotency-Key": " create-framework "},
        correlation_id="not-a-uuid",
    )

    assert api._tenant(request) == tenant_a.id
    assert api._idempotency(request) == "create-framework"
    assert isinstance(api._correlation(request), uuid.UUID)
    assert api._as_of("2026-08-03") is not None
    assert api._as_of("2026-08-03T10:00:00Z") is not None
    assert api._as_of(None) is None

    request.tenant_id = "not-a-uuid"
    with pytest.raises(PermissionDenied):
        api._tenant(request)

    request.headers = {}
    with pytest.raises(ValidationError):
        api._idempotency(request)
    assert api._idempotency(request, required=False) == ""
    request.headers = {"Idempotency-Key": "x" * 256}
    with pytest.raises(ValidationError):
        api._idempotency(request)
    with pytest.raises(ValidationError):
        api._as_of("not-a-date")

    translations = (
        (ComplianceNotFound("missing"), NotFound),
        (ComplianceConflict("conflict"), OperationFailed),
        (ComplianceDependencyUnavailable("down"), OperationFailed),
        (ComplianceValidationError({"field": ["bad"]}), ValidationError),
        (DjangoValidationError({"field": ["bad"]}), ValidationError),
        (IntegrityError("duplicate"), OperationFailed),
    )
    for exc, expected in translations:
        translated = api._translate(exc)
        assert isinstance(translated, expected)

    with pytest.raises(NotFound):
        api._call(lambda: (_ for _ in ()).throw(ComplianceNotFound("missing")))
    with pytest.raises(OperationFailed):
        api._call(lambda: (_ for _ in ()).throw(IntegrityError("duplicate")))


def test_governed_tenant_viewset_sets_access_metadata_and_requires_pagination(tenant_a):
    request = SimpleNamespace(
        tenant_id=str(tenant_a.id),
        user=SimpleNamespace(is_authenticated=True),
        method="GET",
        query_params={},
    )
    view = api.FrameworkViewSet()
    view.request = request
    view.action = "list"
    view.paginate_queryset = lambda queryset: None

    permissions = view.get_permissions()

    assert permissions
    assert view.required_permission == "compliance.framework:read"
    with pytest.raises(RuntimeError):
        view.paginated([], api.FrameworkListSerializer)


def test_configuration_lookup_is_tenant_bounded_and_invalid_ids_translate_to_not_found(tenant_a, tenant_b):
    local = ComplianceConfigurationRevisionFactory(tenant_id=tenant_a.id)
    foreign = ComplianceConfigurationRevisionFactory(tenant_id=tenant_b.id)

    assert api._get_configuration(tenant_a.id, local.id) == local
    with pytest.raises(api.ComplianceNotFound):
        api._get_configuration(tenant_a.id, foreign.id)
    with pytest.raises(api.ComplianceNotFound):
        api._get_configuration(tenant_a.id, "not-a-uuid")
    assert ComplianceConfigurationRevision.objects.filter(id=foreign.id).exists()
