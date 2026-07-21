"""Worker boundary and stable async command tests."""

from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from src.core.async_jobs.services import get_handler
from src.core.tenancy import MissingTenantContext

from ..services import EXECUTE_RUN_COMMAND, EXECUTE_TASK_COMMAND, SCAN_SCHEDULES_COMMAND
from ..tasks import execute_run_worker, register_async_handlers, scan_schedules_worker


def test_all_stable_commands_are_registered_idempotently() -> None:
    register_async_handlers()
    register_async_handlers()
    assert callable(get_handler(EXECUTE_RUN_COMMAND))
    assert callable(get_handler(EXECUTE_TASK_COMMAND))
    assert callable(get_handler(SCAN_SCHEDULES_COMMAND))


def test_worker_fails_closed_without_tenant_context() -> None:
    with pytest.raises(MissingTenantContext):
        execute_run_worker(run_id=uuid.uuid4())  # type: ignore[call-arg]


@pytest.mark.django_db
def test_empty_schedule_scan_reports_real_zero_and_marks_health(monkeypatch: pytest.MonkeyPatch) -> None:
    marked: list[bool] = []
    monkeypatch.setattr(
        "src.modules.automation_orchestration.health.mark_schedule_scanner_healthy",
        lambda: marked.append(True),
    )
    result = scan_schedules_worker(tenant_id=uuid.uuid4(), now=timezone.now(), batch_size=10)
    assert result == {"claimed": 0, "enqueued_run_ids": [], "skipped_schedule_ids": []}
    assert marked == [True]
