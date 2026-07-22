"""Sanitized tenant health probe tests."""

import uuid
from unittest.mock import patch

import pytest

from src.modules.api_management.health import module_health
from src.modules.api_management.models import ApiManagementResource


@pytest.mark.django_db
def test_module_health_reports_sanitized_success():
    payload, status_code = module_health(tenant_id=uuid.uuid4(), cache_ttl_seconds=7)
    assert status_code == 200
    assert payload == {
        "status": "healthy",
        "module": "api-management",
        "checks": {"database": "ok", "cache": "ok", "module_model": "ok"},
    }


@pytest.mark.django_db
def test_module_health_never_discloses_exception_or_counts():
    with (
        patch(
            "src.modules.api_management.health.connection.cursor", side_effect=RuntimeError("secret database detail")
        ),
        patch("src.modules.api_management.health.cache.set", side_effect=RuntimeError("secret cache detail")),
        patch.object(ApiManagementResource.objects, "filter", side_effect=RuntimeError("secret model detail")),
    ):
        payload, status_code = module_health(tenant_id=uuid.uuid4(), cache_ttl_seconds=7)
    assert status_code == 503
    assert payload["checks"] == {
        "database": "dependency_unavailable",
        "cache": "dependency_unavailable",
        "module_model": "dependency_unavailable",
    }
    assert "secret" not in str(payload)


@pytest.mark.django_db
def test_module_health_degrades_on_invalid_cache_round_trip():
    with patch("src.modules.api_management.health.cache.get", return_value=None):
        payload, status_code = module_health(tenant_id=uuid.uuid4(), cache_ttl_seconds=7)
    assert status_code == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["cache"] == "invalid_response"
