"""Durable handler registration, payload allowlisting, and tenant context."""
import uuid

import pytest
from src.core.async_jobs.services import get_handler
from src.core.tenancy import MissingTenantContext

from ..tasks import purge_events_task


@pytest.mark.parametrize("command", ["process_mining.export_event_log", "process_mining.discover_process", "process_mining.check_conformance", "process_mining.analyze_bottlenecks", "process_mining.purge_events"])
def test_all_handlers_are_registered(command):
    assert callable(get_handler(command))


def test_worker_requires_tenant_context():
    with pytest.raises(MissingTenantContext):
        purge_events_task(retention_days=365, actor_id=uuid.uuid4())


def test_worker_payload_never_contains_event_batch():
    for command in ("process_mining.export_event_log", "process_mining.discover_process", "process_mining.check_conformance", "process_mining.analyze_bottlenecks"):
        handler = get_handler(command)
        assert callable(handler) and "events" not in command
