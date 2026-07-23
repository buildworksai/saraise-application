"""Bounded readiness and sanitized failure evidence for HR."""

from unittest.mock import MagicMock, patch

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
        patch(
            "src.modules.human_resources.services.HumanResourcesConfigurationService.default_document",
            return_value={"operations": {"health_staleness_seconds": 17.0}},
        ),
    ):
        health.register_health_probes()
        health.register_health_probes()
    report = registry.check_readiness()
    assert "human_resources.readiness" in report.components
    assert registry._probes["human_resources.readiness"].staleness_limit.total_seconds() == 17.0


@pytest.mark.parametrize("value", [0, -1, True, "30"])
def test_register_health_probes_rejects_invalid_staleness_configuration(value: object) -> None:
    with patch(
        "src.modules.human_resources.services.HumanResourcesConfigurationService.default_document",
        return_value={"operations": {"health_staleness_seconds": value}},
    ):
        with pytest.raises(ValueError, match="staleness configuration"):
            health.register_health_probes()


def test_domain_readiness_contract_covers_schema_rls_state_machines_and_outbox() -> None:
    assert health.DOMAIN_TABLES == (
        "hr_departments",
        "hr_employees",
        "hr_attendances",
        "hr_attendance_revisions",
        "hr_leave_balances",
        "hr_leave_requests",
        "hr_configurations",
        "hr_configuration_versions",
        "hr_configuration_audits",
        "hr_mutation_commands",
    )
    assert set(health.STATE_MACHINES) == {
        "human_resources.employee_lifecycle",
        "human_resources.leave_request",
    }
    with patch.object(health.connection, "vendor", "sqlite"):
        assert health._row_level_security() == (False, "HR_RLS_UNAVAILABLE")


def test_non_postgresql_runtime_cannot_report_ready() -> None:
    with (
        patch.object(health.connection, "vendor", "sqlite"),
        patch.object(health, "_database", return_value=(True, "READY")),
        patch.object(health, "_schema", return_value=(True, "READY")),
        patch.object(health, "_migrations", return_value=(True, "READY")),
        patch.object(health, "_state_machines", return_value=(True, "READY")),
        patch.object(health, "_outbox", return_value=(True, "READY")),
    ):
        report = health.get_module_health()

    assert report.ready is False
    assert report.status_code == 503
    assert next(check for check in report.checks if check.name == "row_level_security").code == "HR_RLS_UNAVAILABLE"


def test_postgresql_rls_probe_requires_forced_policies_on_every_tenant_table() -> None:
    cursor = MagicMock()
    canonical_expression = "(tenant_id = saraise_current_tenant_id())"
    cursor.fetchall.side_effect = [
        [(table, True, True) for table in health.DOMAIN_TABLES],
        [
            (
                table,
                f"tenant_isolation_{table}",
                "ALL",
                ["public"],
                canonical_expression,
                canonical_expression,
            )
            for table in health.DOMAIN_TABLES
        ],
    ]
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    with (
        patch.object(health.connection, "vendor", "postgresql"),
        patch.object(health.connection, "cursor", return_value=cursor_context),
    ):
        assert health._row_level_security() == (True, "READY")

    cursor.fetchall.side_effect = [
        [(table, True, True) for table in health.DOMAIN_TABLES],
        [
            (
                table,
                f"tenant_isolation_{table}",
                "ALL",
                ["public"],
                canonical_expression,
                canonical_expression,
            )
            for table in health.DOMAIN_TABLES[:-1]
        ],
    ]
    with (
        patch.object(health.connection, "vendor", "postgresql"),
        patch.object(health.connection, "cursor", return_value=cursor_context),
    ):
        assert health._row_level_security() == (False, "HR_RLS_NOT_ENFORCED")


@pytest.mark.django_db
def test_database_probe_performs_a_bounded_constant_query() -> None:
    assert health._database() == (True, "READY")
