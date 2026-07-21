"""Health-check tests for the API Management module."""

import json
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from src.modules.api_management.health import health_check
from src.modules.api_management.models import ApiManagementResource


@pytest.mark.django_db
def test_health_check_reports_healthy_dependencies() -> None:
    """The health check reports successful database, cache, and model probes."""
    request = RequestFactory().get("/api/v1/api-management/health/")

    response = health_check(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {
        "status": "healthy",
        "module": "api-management",
        "checks": {
            "database": "ok",
            "cache": "ok",
            "module_model": {"status": "ok", "total_count": 0},
        },
    }


@pytest.mark.django_db
def test_health_check_fails_when_dependencies_raise() -> None:
    """Dependency exceptions produce an unhealthy response without escaping."""
    request = RequestFactory().get("/api/v1/api-management/health/")

    with (
        patch("src.modules.api_management.health.connection.cursor", side_effect=RuntimeError("database down")),
        patch("src.modules.api_management.health.cache.set", side_effect=RuntimeError("cache down")),
        patch.object(ApiManagementResource.objects, "count", side_effect=RuntimeError("model unavailable")),
    ):
        response = health_check(request)
    payload = json.loads(response.content)

    assert response.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["checks"] == {
        "database": "error: database down",
        "cache": "error: cache down",
        "module_model": "error: model unavailable",
    }


@pytest.mark.django_db
def test_health_check_reports_degraded_cache_response() -> None:
    """A cache round trip returning the wrong value degrades health."""
    request = RequestFactory().get("/api/v1/api-management/health/")

    with patch("src.modules.api_management.health.cache.get", return_value=None):
        response = health_check(request)
    payload = json.loads(response.content)

    assert response.status_code == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["cache"] == "not responding correctly"
