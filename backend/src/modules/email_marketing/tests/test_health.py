"""Readiness is comprehensive, tenant-bound, and sanitized."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.modules.email_marketing import health

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


def _healthy(code: str = "ready") -> tuple[bool, str]:
    return True, code


def test_outbox_freshness_is_tenant_scoped(tenant_a, tenant_b) -> None:
    stale = OutboxEvent.objects.create(
        tenant_id=tenant_b.id,
        aggregate_type="email_campaign",
        aggregate_id=uuid4(),
        event_type="email_marketing.campaign.send_queued.v1",
        payload={},
    )
    OutboxEvent.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(minutes=10))
    assert health._outbox(tenant_a.id) == (True, "fresh")
    assert health._outbox(tenant_b.id) == (False, "stale_pending_evidence")


@pytest.mark.parametrize(
    "failed_probe",
    [
        "database",
        "schema",
        "migrations",
        "rls",
        "state",
        "handlers",
        "outbox",
        "renderer",
        "gateway",
    ],
)
def test_each_critical_failure_returns_sanitized_503(failed_probe: str, tenant_a) -> None:
    values = {
        name: True
        for name in (
            "database",
            "schema",
            "migrations",
            "rls",
            "state",
            "handlers",
            "outbox",
            "renderer",
            "gateway",
        )
    }
    values[failed_probe] = False

    def basic(name: str) -> tuple[bool, str]:
        return values[name], ("ready" if values[name] else "dependency_unavailable")

    def gateway(tenant_id=None) -> tuple[bool, str, str]:
        del tenant_id
        return (
            values["gateway"],
            "ready" if values["gateway"] else "dependency_unavailable",
            "closed" if values["gateway"] else "open",
        )

    with (
        patch.object(health, "_database", side_effect=lambda: basic("database")),
        patch.object(health, "_schema", side_effect=lambda: basic("schema")),
        patch.object(health, "_migrations", side_effect=lambda: basic("migrations")),
        patch.object(health, "_rls", side_effect=lambda: basic("rls")),
        patch.object(health, "_state_machines", side_effect=lambda: basic("state")),
        patch.object(health, "_handlers", side_effect=lambda: basic("handlers")),
        patch.object(health, "_outbox", side_effect=lambda tenant: basic("outbox")),
        patch.object(health, "_renderer", side_effect=lambda: basic("renderer")),
        patch.object(health, "_gateway", side_effect=gateway),
        patch.object(health, "_audience_resolver", return_value=(True, "ready")),
    ):
        report = health.get_module_health(tenant_a.id)
    assert report.status_code == 503
    rendered = repr(report.as_dict()).lower()
    assert "traceback" not in rendered
    assert "exception" not in rendered
    assert "password" not in rendered
    assert str(tenant_a.id) not in rendered


def test_optional_resolver_failure_is_degraded_with_http_200(tenant_a) -> None:
    with (
        patch.object(health, "_database", return_value=_healthy()),
        patch.object(health, "_schema", return_value=_healthy()),
        patch.object(health, "_migrations", return_value=_healthy()),
        patch.object(health, "_rls", return_value=_healthy()),
        patch.object(health, "_state_machines", return_value=_healthy()),
        patch.object(health, "_handlers", return_value=_healthy()),
        patch.object(health, "_outbox", return_value=_healthy("fresh")),
        patch.object(health, "_renderer", return_value=_healthy()),
        patch.object(health, "_gateway", return_value=(True, "ready", "closed")),
        patch.object(
            health,
            "_audience_resolver",
            return_value=(False, "resolver_not_registered"),
        ),
    ):
        report = health.get_module_health(tenant_a.id)
    assert report.status == "degraded"
    assert report.status_code == 200


def test_probe_exception_text_is_never_returned(tenant_a) -> None:
    with patch.object(
        health,
        "_database",
        side_effect=RuntimeError("postgres://user:password@secret"),
    ):
        report = health.get_module_health(tenant_a.id)
    rendered = repr(report.as_dict()).lower()
    assert "postgres" not in rendered
    assert "password" not in rendered
    assert "secret" not in rendered
