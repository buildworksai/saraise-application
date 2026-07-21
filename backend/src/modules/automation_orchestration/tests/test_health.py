"""Readiness remains truthful and non-leaking."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ..health import module_readiness, sanitized_health_payload


@pytest.mark.parametrize("failed_check", ["database", "outbox", "handlers", "scanner", "workflow"])
def test_each_required_dependency_failure_returns_503(failed_check: str) -> None:
    values = {
        "database": True,
        "outbox": True,
        "handlers": True,
        "scanner": True,
        "workflow": True,
    }
    values[failed_check] = False
    with (
        patch("src.modules.automation_orchestration.health._database_ready", return_value=values["database"]),
        patch("src.modules.automation_orchestration.health._outbox_fresh", return_value=values["outbox"]),
        patch("src.modules.automation_orchestration.health._handlers_ready", return_value=values["handlers"]),
        patch("src.modules.automation_orchestration.health._scanner_fresh", return_value=values["scanner"]),
        patch(
            "src.modules.automation_orchestration.health.workflow_adapter_available", return_value=values["workflow"]
        ),
    ):
        payload, status_code = sanitized_health_payload()
    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert "exception" not in str(payload).lower()


def test_ready_probe_exposes_only_component_states() -> None:
    with (
        patch("src.modules.automation_orchestration.health._database_ready", return_value=True),
        patch("src.modules.automation_orchestration.health._outbox_fresh", return_value=True),
        patch("src.modules.automation_orchestration.health._handlers_ready", return_value=True),
        patch("src.modules.automation_orchestration.health._scanner_fresh", return_value=True),
        patch("src.modules.automation_orchestration.health.workflow_adapter_available", return_value=True),
    ):
        result = module_readiness()
    assert result.healthy is True
    assert set(result.details) == {"database", "outbox", "async_handlers", "schedule_scanner", "workflow_adapter"}
    assert "count" not in str(result.details).lower()
