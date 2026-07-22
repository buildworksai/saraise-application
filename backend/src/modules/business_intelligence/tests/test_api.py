"""Public v2 route and authentication contracts."""

from __future__ import annotations

import pytest
from django.urls import resolve
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_protected_v2_collection_challenges_unauthenticated_clients() -> None:
    response = APIClient().get("/api/v2/business-intelligence/queries/")
    assert response.status_code == 401
    assert "Session" in response.headers["WWW-Authenticate"]


@pytest.mark.django_db
def test_health_is_public_and_sanitized() -> None:
    response = APIClient().get("/api/v2/business-intelligence/health/")
    assert response.status_code in {200, 503}
    rendered = response.content.decode()
    assert "Traceback" not in rendered
    assert "password" not in rendered.lower()


def test_all_resource_routers_are_mounted_under_v2() -> None:
    for path in ("datasets/", "queries/", "reports/", "dashboards/", "executions/"):
        match = resolve(f"/api/v2/business-intelligence/{path}")
        assert match.url_name.endswith("-list")


def test_legacy_v1_mount_is_removed() -> None:
    from django.urls import Resolver404

    with pytest.raises(Resolver404):
        resolve("/api/v1/business-intelligence/reports/")
