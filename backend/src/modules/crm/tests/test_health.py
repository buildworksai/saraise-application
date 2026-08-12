"""Sanitized CRM readiness tests."""

from collections.abc import Mapping
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from src.modules.crm import health


class _Cursor:
    def __init__(self, *, one=(1,), rows=()):
        self.one = one
        self.rows = list(rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class _Introspection:
    def __init__(self, tables):
        self._tables = tables

    def table_names(self):
        return list(self._tables)


class _Connection:
    def __init__(self, *, vendor="sqlite", one=(1,), rows=(), tables=()):
        self.vendor = vendor
        self.one = one
        self.rows = rows
        self.introspection = _Introspection(tables)

    def cursor(self):
        return _Cursor(one=self.one, rows=self.rows)


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


def test_rls_probe_fails_closed_when_postgresql_catalog_is_unavailable(settings: object) -> None:
    del settings
    if health.connection.vendor == "postgresql":
        pytest.skip("This assertion is specific to the SQLite unit-test profile")
    assert health._rls() == (False, "rls_unverifiable")
    result = health.rls_readiness_probe()
    assert result.healthy is False
    assert result.message == "rls_unverifiable"


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


def test_database_schema_cache_and_async_probes_use_sanitized_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "connection", _Connection(one=(1,), tables=health.DOMAIN_TABLES + health.ASYNC_TABLES))
    assert health._database() == (True, "ready")
    assert health._schema() == (True, "ready")
    assert health._async_outbox() == (True, "ready")

    monkeypatch.setattr(health, "connection", _Connection(one=(0,), tables=()))
    assert health._database() == (False, "query_failed")
    assert health._schema() == (False, "schema_missing")
    assert health._async_outbox() == (False, "schema_missing")

    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}),
    )
    assert health._cache() == (True, "disabled")

    marker_store: dict[str, str] = {}
    monkeypatch.setattr(health, "settings", SimpleNamespace(CACHES={"default": {"BACKEND": "locmem"}}))
    monkeypatch.setattr(health, "effective_configuration", lambda tenant_id: health.DEFAULT_CRM_CONFIGURATION)
    monkeypatch.setattr(health.cache, "set", lambda key, value, timeout: marker_store.update({key: value}))
    monkeypatch.setattr(health.cache, "get", lambda key: marker_store.get(key))
    assert health._cache(uuid4()) == (True, "ready")

    monkeypatch.setattr(health.cache, "get", lambda key: "different")
    assert health._cache(uuid4()) == (False, "roundtrip_failed")


def test_migration_rls_state_machine_provider_and_extension_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    class Loader:
        graph = SimpleNamespace(leaf_nodes=lambda app_label: (("crm", "0005"),))
        applied_migrations = {("crm", "0005")}

    monkeypatch.setattr(health, "MigrationExecutor", lambda connection: SimpleNamespace(loader=Loader()))
    assert health._migrations() == (True, "ready")

    class PendingLoader:
        graph = SimpleNamespace(leaf_nodes=lambda app_label: (("crm", "0005"),))
        applied_migrations = set()

    monkeypatch.setattr(health, "MigrationExecutor", lambda connection: SimpleNamespace(loader=PendingLoader()))
    assert health._migrations() == (False, "migration_pending")

    rls_rows = [(table, True, True) for table in health.DOMAIN_TABLES]
    policy_rows = [(table, "tenant_id", "tenant_id") for table in health.DOMAIN_TABLES]

    class RlsConnection(_Connection):
        def __init__(self):
            super().__init__(vendor="postgresql")
            self.calls = 0

        def cursor(self):
            connection = self

            class Cursor(_Cursor):
                def fetchall(self):
                    connection.calls += 1
                    return rls_rows if connection.calls == 1 else policy_rows

            return Cursor()

    monkeypatch.setattr(health, "connection", RlsConnection())
    assert health._rls() == (True, "ready")

    monkeypatch.setattr(health.state_machine_registry, "names", lambda: health.STATE_MACHINES)
    assert health._state_machines() == (True, "ready")
    monkeypatch.setattr(health.state_machine_registry, "names", lambda: ())
    assert health._state_machines() == (False, "registration_missing")

    provider_health = SimpleNamespace(available=True, code="ready", circuit_state="closed")
    monkeypatch.setattr(health, "settings", SimpleNamespace(CRM_LEAD_SCORING_PROVIDER={"enabled": True}))
    assert health._provider(lambda: SimpleNamespace(health=lambda: provider_health), "CRM_LEAD_SCORING_PROVIDER") == (
        True,
        "ready",
        "closed",
    )
    assert health._provider(lambda: object(), "MISSING_PROVIDER") == (True, "disabled", "not_applicable")

    monkeypatch.setattr(health, "settings", SimpleNamespace(CRM_OPTIONAL_DEPENDENCIES={"sales_management": True}))
    monkeypatch.setattr(health.extension_registry, "resolve", lambda capability: object())
    assert health._optional_extensions() == (True, "ready")

    monkeypatch.setattr(health.extension_registry, "resolve", lambda capability: None)
    assert health._optional_extensions() == (False, "adapter_not_registered")

    monkeypatch.setattr(health, "settings", SimpleNamespace(CRM_OPTIONAL_DEPENDENCIES={"unknown-module": True}))
    monkeypatch.setattr(health.apps, "is_installed", lambda app_label: False)
    assert health._optional_extensions() == (False, "module_not_installed")


def test_health_probe_registration_and_view_response(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: dict[str, object] = {}
    monkeypatch.setattr(
        health.health_registry,
        "register",
        lambda name, probe, critical, replace: registered.update({name: (probe, critical, replace)}),
    )

    health.register_health_probes()

    assert set(registered) == {"crm.database", "crm.rls", "crm.async_outbox"}
    assert all(item[1:] == (True, True) for item in registered.values())

    report = health.ModuleHealthReport("healthy", (health.Check("database", "healthy", "ready", 0, True),))
    monkeypatch.setattr(health, "get_module_health", lambda tenant_id=None: report)

    response = health.CRMHealthView().get(SimpleNamespace(tenant_id=uuid4()))

    assert response.status_code == 200
    assert response.data["module"] == "crm"
    assert response.data["ready"] is True
