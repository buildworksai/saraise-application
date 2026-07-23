"""Sanitized tenant health probe tests."""

import uuid
from unittest.mock import patch

import pytest
from django.conf import settings

from src.modules.api_management.health import module_health
from src.modules.api_management.models import ApiManagementResource


@pytest.mark.django_db
def test_module_health_reports_sanitized_success():
    payload, status_code = module_health(
        tenant_id=uuid.uuid4(),
        cache_ttl_seconds=7,
        correlation_id="health-success",
    )
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
        payload, status_code = module_health(
            tenant_id=uuid.uuid4(),
            cache_ttl_seconds=7,
            correlation_id="health-failure",
        )
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
        payload, status_code = module_health(
            tenant_id=uuid.uuid4(),
            cache_ttl_seconds=7,
            correlation_id="health-degraded",
        )
    assert status_code == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["cache"] == "invalid_response"


@pytest.mark.django_db
def test_module_health_requires_and_logs_correlation_context():
    with pytest.raises(ValueError, match="correlation_id"):
        module_health(
            tenant_id=uuid.uuid4(),
            cache_ttl_seconds=7,
            correlation_id="",
        )

    with (
        patch(
            "src.modules.api_management.health.connection.cursor",
            side_effect=RuntimeError("database unavailable"),
        ),
        patch(
            "src.modules.api_management.health.cache.set",
            side_effect=RuntimeError("cache unavailable"),
        ),
        patch.object(
            ApiManagementResource.objects,
            "filter",
            side_effect=RuntimeError("model unavailable"),
        ),
        patch("src.modules.api_management.health.logger.exception") as log_exception,
    ):
        module_health(
            tenant_id=uuid.uuid4(),
            cache_ttl_seconds=7,
            correlation_id="health-correlation",
        )

    assert log_exception.call_count == 3
    assert all(call.kwargs["extra"]["correlation_id"] == "health-correlation" for call in log_exception.call_args_list)
    assert settings.LOGGING["formatters"]["json"]["()"] == "src.core.observability.logging.JSONFormatter"
