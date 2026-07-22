"""Governed API v2 contract tests using real session authentication."""

from __future__ import annotations

import uuid

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from src.core.access.permissions import RequiresAccess

from .factories import ComplianceFrameworkFactory

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
        {"code": "FW", "name": "Framework", "version": "1", "category": "General", "source_kind": "custom", "status": "active", "tenant_id": str(uuid.uuid4())},
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
    for path in ("dashboard/", "frameworks/", "requirements/", "policies/", "mappings/", "assessments/", "evidence/", "configuration/", "activity/"):
        response = authenticated_tenant_a_client.get(f"{BASE}/{path}")
        assert response.status_code != status.HTTP_404_NOT_FOUND, path
    assert APIClient().get("/api/v1/compliance-management/policies/").status_code == status.HTTP_404_NOT_FOUND
