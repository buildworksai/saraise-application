"""Readiness coverage for inventory management health checks."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied

from src.modules.inventory_management import health


@contextmanager
def _tenant_context(tenant_id):
    yield tenant_id


class _Cursor:
    def __init__(self, *, rows=(), one=(1,), fail=False):
        self.rows = list(rows)
        self.one = one
        self.fail = fail

    def __enter__(self):
        if self.fail:
            raise RuntimeError("private database failure")
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("private query failure")

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, *, vendor="sqlite", rows=(), one=(1,), fail=False):
        self.vendor = vendor
        self._rows = rows
        self._one = one
        self._fail = fail

    def cursor(self):
        return _Cursor(rows=self._rows, one=self._one, fail=self._fail)


class _Config:
    enabled_capabilities = {"events": True}

    def __init__(self, *, invalid=False, enabled=True):
        self.invalid = invalid
        self.enabled_capabilities = {"events": enabled}

    def full_clean(self):
        if self.invalid:
            raise ValidationError("invalid")


class _ConfigQuery:
    def __init__(self, config):
        self.config = config

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.config


class _ConfigManager:
    def __init__(self, config):
        self.query = _ConfigQuery(config)

    def for_tenant(self, tenant_id):
        return self.query


class _OutboxQuery:
    def __init__(self, *, stale=False):
        self.stale = stale

    def exists(self):
        return self.stale


class _OutboxManager:
    def __init__(self, *, stale=False):
        self.query = _OutboxQuery(stale=stale)

    def filter(self, *args, **kwargs):
        return self.query


def _rls_rows(enabled=True):
    return [(table, enabled, enabled, 1 if enabled else 0) for table in health.INVENTORY_TABLES]


def test_rls_status_fails_closed_when_postgresql_is_unavailable(monkeypatch):
    monkeypatch.setattr(health, "connection", _Connection(vendor="sqlite"))

    ready, component = health._rls_status()

    assert ready is False
    assert component == {"status": "unhealthy", "reason_code": "postgresql_rls_unavailable"}


def test_module_health_reports_missing_and_invalid_configuration(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(health, "tenant_context", _tenant_context)
    monkeypatch.setattr(health, "connection", _Connection(vendor="postgresql", rows=_rls_rows()))
    monkeypatch.setattr(health.InventoryConfiguration, "objects", _ConfigManager(None))
    monkeypatch.setattr(health.OutboxEvent, "objects", _OutboxManager())
    monkeypatch.setattr(health, "health_contributors", lambda: ())

    payload, code = health.module_health(tenant_id)

    assert code == 503
    assert payload["status"] == "unhealthy"
    assert payload["components"]["configuration"]["reason_code"] == "active_configuration_missing"

    monkeypatch.setattr(health.InventoryConfiguration, "objects", _ConfigManager(_Config(invalid=True)))
    payload, code = health.module_health(tenant_id)

    assert code == 503
    assert payload["components"]["configuration"]["reason_code"] == "active_configuration_invalid"


def test_module_health_reports_degraded_outbox_and_extensions(monkeypatch):
    tenant_id = uuid.uuid4()
    degraded_result = SimpleNamespace(
        name="valuation",
        healthy=False,
        breaker_state="open",
        reason_code="provider_unavailable",
    )
    monkeypatch.setattr(health, "tenant_context", _tenant_context)
    monkeypatch.setattr(health, "connection", _Connection(vendor="postgresql", rows=_rls_rows()))
    monkeypatch.setattr(health.InventoryConfiguration, "objects", _ConfigManager(_Config(enabled=True)))
    monkeypatch.setattr(health.OutboxEvent, "objects", _OutboxManager(stale=True))
    monkeypatch.setattr(health, "health_contributors", lambda: (SimpleNamespace(check=lambda: degraded_result),))

    payload, code = health.module_health(tenant_id, environment="test")

    assert code == 200
    assert payload["status"] == "degraded"
    assert payload["components"]["async_outbox"]["reason_code"] == "dispatch_delayed"
    assert payload["components"]["extensions"]["dependencies"] == [
        {
            "name": "valuation",
            "status": "degraded",
            "breaker_state": "open",
            "reason_code": "provider_unavailable",
        }
    ]


def test_module_health_sanitizes_database_tenant_and_extension_failures(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(health, "connection", _Connection(fail=True))
    monkeypatch.setattr(health, "tenant_context", _tenant_context)
    monkeypatch.setattr(
        health,
        "health_contributors",
        lambda: (SimpleNamespace(check=lambda: (_ for _ in ()).throw(RuntimeError("private provider detail"))),),
    )

    payload, code = health.module_health(tenant_id)

    assert code == 503
    assert payload["components"]["database"]["reason_code"] == "database_unavailable"
    assert payload["components"]["extensions"]["dependencies"][0]["reason_code"] == "probe_failed"
    assert "private provider detail" not in str(payload)


def test_module_health_reports_healthy_when_configuration_rls_and_extensions_are_ready(monkeypatch):
    tenant_id = uuid.uuid4()
    healthy_result = SimpleNamespace(name="valuation", healthy=True, breaker_state="closed", reason_code="ready")
    monkeypatch.setattr(health, "tenant_context", _tenant_context)
    monkeypatch.setattr(health, "connection", _Connection(vendor="postgresql", rows=_rls_rows()))
    monkeypatch.setattr(health.InventoryConfiguration, "objects", _ConfigManager(_Config(enabled=False)))
    monkeypatch.setattr(health.OutboxEvent, "objects", _OutboxManager())
    monkeypatch.setattr(health, "health_contributors", lambda: (SimpleNamespace(check=lambda: healthy_result),))

    payload, code = health.module_health(tenant_id)

    assert code == 200
    assert payload["status"] == "healthy"
    assert payload["components"]["async_outbox"]["reason_code"] == "not_enabled"
    assert payload["components"]["rls"]["reason_code"] == "ready"


def test_inventory_health_view_requires_uuid_tenant_context():
    view = health.InventoryHealthView()
    view.request = SimpleNamespace(method="GET")

    assert view.get_permissions()

    try:
        view.get(SimpleNamespace(tenant_id="not-a-uuid"))
    except PermissionDenied as exc:
        assert "tenant context" in str(exc)
    else:
        raise AssertionError("PermissionDenied was not raised")
