"""Sanitized, fail-closed readiness tests."""

from __future__ import annotations

import uuid

import pytest

from .. import health


def _set_checks(monkeypatch: pytest.MonkeyPatch, *, database: bool = True, jobs: bool = True, outbox: bool = True, extensions: bool = True) -> None:
    monkeypatch.setattr(health, "_database_ready", lambda tenant_id: database)
    monkeypatch.setattr(health, "_handlers_registered", lambda: jobs)
    monkeypatch.setattr(health, "_outbox_fresh", lambda tenant_id: outbox)
    monkeypatch.setattr(health, "_required_extensions_ready", lambda tenant_id: extensions)


def test_readiness_is_healthy_only_when_every_required_capability_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_checks(monkeypatch)
    result = health.module_readiness(uuid.uuid4())
    assert result.healthy is True
    assert set(result.details) == {
        "database_rls",
        "async_handlers",
        "outbox_worker",
        "notifications",
        "required_extensions",
    }


@pytest.mark.parametrize("failed", ["database", "jobs", "outbox", "extensions"])
def test_each_required_dependency_fails_readiness(monkeypatch: pytest.MonkeyPatch, failed: str) -> None:
    values = {"database": True, "jobs": True, "outbox": True, "extensions": True}
    values[failed] = False
    _set_checks(monkeypatch, **values)
    payload, status_code = health.sanitized_health_payload(uuid.uuid4())
    assert status_code == 503
    assert payload["status"] == "not_ready"


def test_health_payload_never_leaks_tenant_counts_urls_or_exception_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_checks(monkeypatch, database=False)
    payload, _ = health.sanitized_health_payload(uuid.uuid4())
    rendered = repr(payload).lower()
    for forbidden in ("tenant_id", "row_count", "exception", "password", "http://", "https://"):
        assert forbidden not in rendered


def test_module_health_registration_is_idempotent() -> None:
    health.register_module_health()
    health.register_module_health()
