"""Run the local orchestration schedule scanner."""

from __future__ import annotations

import time
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from src.modules.automation_orchestration.health import mark_schedule_scanner_healthy
from src.modules.automation_orchestration.models import OrchestrationSchedule, ScheduleStatus
from src.modules.automation_orchestration.tasks import scan_schedules_worker


class Command(BaseCommand):
    help = "Continuously scan due orchestration schedules and refresh readiness heartbeat."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--interval", type=float, default=30.0)
        parser.add_argument("--batch-size", type=int, default=None)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        interval = float(options["interval"])
        batch_size = options["batch_size"]
        once = bool(options["once"])
        if interval <= 0:
            raise ValueError("interval must be positive")
        while True:
            self._scan_once(batch_size=batch_size)
            if once:
                return
            time.sleep(interval)

    def _scan_once(self, *, batch_size: int | None) -> None:
        try:
            if "automation_orchestration_schedules" not in connection.introspection.table_names():
                return
            mark_schedule_scanner_healthy(None)
            # The scheduler must discover tenants with active schedules before entering tenant-scoped workers.
            tenants = (
                OrchestrationSchedule.objects.filter(  # nosemgrep: semgrep.tenant-id-required-in-queries
                    status=ScheduleStatus.ACTIVE, is_deleted=False
                )
                .values_list("tenant_id", flat=True)
                .distinct()
            )
            now = timezone.now()
            for tenant_id in tenants:
                scan_schedules_worker(tenant_id=tenant_id, now=now, batch_size=batch_size)
        except Exception as exc:
            self.stderr.write(f"schedule scan failed: {exc.__class__.__name__}")
