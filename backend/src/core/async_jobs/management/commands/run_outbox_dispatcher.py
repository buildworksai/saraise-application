"""Run a local durable outbox dispatcher."""

from __future__ import annotations

import time
import uuid
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from src.core.async_jobs.dispatcher import BrokerAcknowledgement, dispatch_pending
from src.core.async_jobs.models import OutboxEvent
from src.core.async_jobs.services import execute


class LocalOutboxBroker:
    """Dispatch async jobs in-process and acknowledge local domain events."""

    def __init__(self, *, acknowledge_domain_events: bool) -> None:
        self.acknowledge_domain_events = acknowledge_domain_events

    def submit(self, event: OutboxEvent) -> BrokerAcknowledgement:
        if event.aggregate_type == "async_job" and event.event_type in {
            "async_job.enqueued",
            "async_job.retry_requested",
        }:
            execute(event.aggregate_id, event.tenant_id)
            return BrokerAcknowledgement(True, f"local-execute:{event.id}")
        if self.acknowledge_domain_events:
            return BrokerAcknowledgement(True, f"local-domain:{event.id}")
        return BrokerAcknowledgement(False)


class Command(BaseCommand):
    help = "Continuously dispatch durable outbox rows for local development and test stacks."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--interval", type=float, default=1.0)
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--lease-seconds", type=int, default=60)
        parser.add_argument("--once", action="store_true")
        parser.add_argument(
            "--acknowledge-domain-events",
            action="store_true",
            help="Acknowledge non-async domain events after durable local persistence.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        interval = float(options["interval"])
        batch_size = int(options["batch_size"])
        lease_seconds = int(options["lease_seconds"])
        once = bool(options["once"])
        if interval <= 0:
            raise CommandError("interval must be positive")
        if batch_size <= 0:
            raise CommandError("batch-size must be positive")
        if lease_seconds <= 0:
            raise CommandError("lease-seconds must be positive")

        broker = LocalOutboxBroker(acknowledge_domain_events=bool(options["acknowledge_domain_events"]))
        while True:
            result = dispatch_pending(broker, batch_size=batch_size, lease_seconds=lease_seconds)
            self.stdout.write(
                f"outbox dispatch claimed={result.claimed} dispatched={result.dispatched} failed={result.failed}"
            )
            if once:
                return
            time.sleep(interval)


__all__ = ["Command", "LocalOutboxBroker"]
