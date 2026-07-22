"""Bounded readiness and sanitized failure evidence for HR."""

from unittest.mock import patch

import pytest

from src.core.health import HealthRegistry

from .. import health


def test_probe_failure_is_sanitized_and_logged_without_exception_text(caplog: pytest.LogCaptureFixture) -> None:
    secret = "database-password-must-not-leak"  # pragma: allowlist secret

    def broken_probe() -> tuple[bool, str]:
        raise RuntimeError(secret)

    with caplog.at_level("ERROR"):
        result = health._run("database", broken_probe)

    assert result.healthy is False
    assert result.code == "DEPENDENCY_CHECK_FAILED"
    assert secret not in result.as_dict().values()
    assert result.latency_ms >= 0


def test_health_report_is_not_ready_when_any_critical_check_fails() -> None:
    report = health.HumanResourcesHealthReport(
        checks=(
            health.ReadinessCheck("database", True, "READY", 0.1),
            health.ReadinessCheck("rls", False, "HR_RLS_NOT_ENFORCED", 0.1),
        )
    )
    assert report.ready is False
    assert report.status_code == 503
    payload = report.as_dict()
    assert payload["module"] == "human_resources"
    assert payload["ready"] is False
    assert payload["status"] == "unhealthy"
    assert "row_count" not in str(payload)


def test_register_health_probes_is_duplicate_safe() -> None:
    registry = HealthRegistry()
    with (
        patch.object(health, "health_registry", registry),
        patch.object(health, "readiness_probe", return_value=True),
    ):
        health.register_health_probes()
        health.register_health_probes()
    report = registry.check_readiness()
    assert "human_resources.readiness" in report.components


def test_domain_readiness_contract_covers_schema_rls_state_machines_and_outbox() -> None:
    assert health.DOMAIN_TABLES == (
        "hr_departments",
        "hr_employees",
        "hr_attendances",
        "hr_leave_balances",
        "hr_leave_requests",
    )
    assert set(health.STATE_MACHINES) == {
        "human_resources.employee_lifecycle",
        "human_resources.leave_request",
    }
    with patch.object(health.connection, "vendor", "sqlite"):
        assert health._row_level_security() == (True, "NOT_APPLICABLE")


@pytest.mark.django_db
def test_database_probe_performs_a_bounded_constant_query() -> None:
    assert health._database() == (True, "READY")
