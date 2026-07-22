"""Sanitized readiness behavior for database, cache, and outbox failures."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.modules.metadata_modeling.api import MetadataHealthView

pytest_plugins = ["src.core.testing.factories"]


@pytest.mark.django_db
def test_health_is_tenant_bounded_and_does_not_expose_counts():
    tenant_id = uuid.uuid4()
    request = SimpleNamespace()
    with (
        patch("src.modules.metadata_modeling.api._tenant_id", return_value=tenant_id),
        patch("src.modules.metadata_modeling.api._correlation_id", return_value="corr-health"),
    ):
        response = MetadataHealthView().get(request)
    assert response.status_code == 200
    assert response.data == {
        "status": "healthy",
        "module": "metadata-modeling",
        "checks": {"database": "ok", "cache": "ok", "outbox": "ok"},
    }
    assert response["X-Correlation-ID"] == "corr-health"
    assert "count" not in str(response.data).lower()


@pytest.mark.django_db
def test_health_failures_are_503_and_never_expose_raw_exception_text():
    tenant_id = uuid.uuid4()
    request = SimpleNamespace()
    with (
        patch("src.modules.metadata_modeling.api._tenant_id", return_value=tenant_id),
        patch("src.modules.metadata_modeling.api._correlation_id", return_value="corr-failed"),
        patch("src.modules.metadata_modeling.api.connection.cursor", side_effect=RuntimeError("db-password")),
        patch("src.modules.metadata_modeling.api.cache.set", side_effect=RuntimeError("redis-secret")),
    ):
        response = MetadataHealthView().get(request)
    assert response.status_code == 503
    assert response.data["status"] == "unhealthy"
    assert response.data["checks"]["database"] == "unavailable"
    assert response.data["checks"]["cache"] == "unavailable"
    assert "password" not in str(response.data)
    assert "secret" not in str(response.data)
