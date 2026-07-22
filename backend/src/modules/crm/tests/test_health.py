"""Sanitized CRM readiness tests."""

from collections.abc import Mapping
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from src.modules.crm import health


def _key_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            names.add(str(key))
            names.update(_key_names(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            names.update(_key_names(item))
    return names


def test_probe_failures_are_sanitized_and_timed() -> None:
    def failure() -> tuple[bool, str]:
        raise RuntimeError("postgres://user:secret@private-host/customer-data")

    check = health._run("database", failure, critical=True)
    assert check.status == "unhealthy"
    assert check.code == "dependency_unavailable"
    assert check.latency_ms >= 0
    assert "secret" not in str(check.as_dict())


def test_module_health_has_healthy_degraded_and_unhealthy_states(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "_database",
        "_schema",
        "_migrations",
        "_rls",
        "_cache",
        "_async_outbox",
        "_state_machines",
        "_optional_extensions",
    ):
        monkeypatch.setattr(health, name, lambda: (True, "ready"))

    assert health.get_module_health().status == "healthy"
    monkeypatch.setattr(health, "_cache", lambda: (False, "roundtrip_failed"))
    assert health.get_module_health().status == "degraded"
    monkeypatch.setattr(health, "_database", lambda: (False, "query_failed"))
    assert health.get_module_health().status == "unhealthy"


def test_health_payload_exposes_no_business_counts_or_dependency_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "_database",
        "_schema",
        "_migrations",
        "_rls",
        "_cache",
        "_async_outbox",
        "_state_machines",
        "_optional_extensions",
    ):
        monkeypatch.setattr(health, name, lambda: (True, "ready"))
    payload = health.get_module_health().as_dict()
    names = _key_names(payload)
    assert not {"leads_count", "opportunities_count", "credentials", "provider_payload"} & names
    assert set(payload["checks"]) >= {
        "database",
        "domain_schema",
        "required_migrations",
        "row_level_security",
        "cache",
        "async_outbox",
        "lead_scoring_provider",
    }
    for check in payload["checks"].values():
        assert {"name", "status", "latency_ms"} <= set(check)


def test_sqlite_rls_probe_is_explicitly_not_applicable(settings: object) -> None:
    del settings
    if health.connection.vendor == "postgresql":
        pytest.skip("This assertion is specific to the SQLite unit-test profile")
    assert health._rls() == (True, "not_applicable")


def test_health_view_binds_only_authenticated_profile_tenant() -> None:
    tenant_id = uuid4()
    user = SimpleNamespace(
        is_authenticated=True,
        profile=SimpleNamespace(tenant_id=str(tenant_id)),
    )
    django_request = APIRequestFactory().get("/api/v2/crm/health/")
    force_authenticate(django_request, user=user)
    request = Request(django_request)
    health.CRMHealthView().perform_authentication(request)
    assert request.tenant_id == tenant_id

    invalid_user = SimpleNamespace(
        is_authenticated=True,
        profile=SimpleNamespace(tenant_id="not-a-uuid"),
    )
    invalid_django_request = APIRequestFactory().get("/api/v2/crm/health/")
    force_authenticate(invalid_django_request, user=invalid_user)
    invalid_request = Request(invalid_django_request)
    health.CRMHealthView().perform_authentication(invalid_request)
    assert not hasattr(invalid_request, "tenant_id")
