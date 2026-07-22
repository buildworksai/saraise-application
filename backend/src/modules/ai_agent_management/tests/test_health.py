"""Sanitized fail-closed module readiness tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from src.core.access.permissions import RequiresAccess
from src.core.async_jobs.models import OutboxEvent
from src.core.async_jobs.services import enqueue, register_handler, unregister_handler
from src.modules.ai_agent_management import health
from src.modules.ai_agent_management.registries import runner_registry
from src.modules.ai_agent_management.services import EXECUTE_COMMAND

HEALTH_URL = "/api/v2/ai-agent-management/health/"
REQUIRED_COMPONENTS = {
    "database",
    "rls",
    "cache",
    "execution_handler",
    "outbox",
    "extension_registry",
    "provider",
    "circuit",
}


@pytest.fixture(autouse=True)
def allow_health_access(monkeypatch):
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)


@pytest.fixture
def execution_handler():
    unregister_handler(EXECUTE_COMMAND)
    register_handler(EXECUTE_COMMAND, lambda job: {"execution_id": job.payload.get("execution_id")})
    yield
    unregister_handler(EXECUTE_COMMAND)


@pytest.fixture
def healthy_dependencies(monkeypatch, execution_handler):
    class Cursor:
        result = (1,)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            self.result = (21,) if "pg_class" in sql else (1,)

        def fetchone(self):
            return self.result

    class PostgreSQLConnection:
        vendor = "postgresql"

        def cursor(self):
            return Cursor()

    class ProviderFactory:
        is_configured = True

    class ProviderRegistry:
        def list_providers(self):
            return ["test-provider"]

    runner_registry.unregister("health.runner")
    runner_registry.register("health.runner", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(health, "connection", PostgreSQLConnection())
    monkeypatch.setattr(health, "get_provider_factory", lambda: ProviderFactory())
    monkeypatch.setattr(health, "get_provider_registry", lambda: ProviderRegistry())
    yield
    runner_registry.unregister("health.runner")


def _payload(response):
    body = response.json()
    if set(body) == {"data", "meta"}:
        assert body["meta"]["correlation_id"]
        return body["data"]
    return body


@pytest.mark.django_db
def test_healthy_report_contains_only_status_and_measured_latency(
    authenticated_tenant_a_client,
    healthy_dependencies,
):
    response = authenticated_tenant_a_client.get(HEALTH_URL)
    assert response.status_code == status.HTTP_200_OK
    payload = _payload(response)
    assert payload["status"] == "healthy"
    assert REQUIRED_COMPONENTS <= set(payload["components"])
    for component in payload["components"].values():
        assert set(component) == {"status", "latency_ms"}
        assert component["status"] == "healthy"
        assert isinstance(component["latency_ms"], (int, float))


@pytest.mark.django_db
def test_database_failure_is_503_and_redacted(authenticated_tenant_a_client, execution_handler, monkeypatch):
    class BrokenCursor:
        def __enter__(self):
            raise RuntimeError("postgresql://admin:password@private-db/tenant")

        def __exit__(self, *args):
            return False

        def close(self):
            return None

    class BrokenConnection:
        vendor = "postgresql"

        def cursor(self):
            return BrokenCursor()

    # Replace only the dependency owned by the health probe.  Patching the
    # global Django connection would also prevent session authentication from
    # loading the user, which is not the failure this test exercises.
    monkeypatch.setattr(health, "connection", BrokenConnection())
    response = authenticated_tenant_a_client.get(HEALTH_URL)
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = str(response.data)
    assert "password" not in body
    assert "private-db" not in body
    assert _payload(response)["components"]["database"]["status"] == "unavailable"


@pytest.mark.django_db
def test_cache_failure_is_503_and_redacted(authenticated_tenant_a_client, execution_handler, monkeypatch):
    monkeypatch.setattr(
        health.cache,
        "set",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("redis://secret-host:6379")),
    )
    response = authenticated_tenant_a_client.get(HEALTH_URL)
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "secret-host" not in str(response.data)
    assert _payload(response)["components"]["cache"]["status"] == "unavailable"


@pytest.mark.django_db
def test_missing_handler_is_503(authenticated_tenant_a_client):
    unregister_handler(EXECUTE_COMMAND)
    response = authenticated_tenant_a_client.get(HEALTH_URL)
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    payload = _payload(response)
    assert payload["components"]["execution_handler"]["status"] == "unavailable"


@pytest.mark.django_db
def test_stale_outbox_is_503(authenticated_tenant_a_client, execution_handler, tenant_a, tenant_a_user):
    job = enqueue(tenant_a.id, tenant_a_user.pk, EXECUTE_COMMAND, {"execution_id": "opaque"}, "stale-health")
    OutboxEvent.objects.filter(aggregate_id=job.id).update(
        available_at=timezone.now() - timedelta(hours=2),
        updated_at=timezone.now() - timedelta(hours=2),
    )
    response = authenticated_tenant_a_client.get(HEALTH_URL)
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert _payload(response)["components"]["outbox"]["status"] == "unavailable"


@pytest.mark.django_db
def test_health_never_returns_counts_urls_exceptions_or_tenant_data(
    authenticated_tenant_a_client,
    execution_handler,
    tenant_a,
):
    response = authenticated_tenant_a_client.get(HEALTH_URL)
    serialized = str(response.data).lower()
    for forbidden in (str(tenant_a.id).lower(), "active_agents", "row_count", "exception", "http://", "postgresql://"):
        assert forbidden not in serialized
