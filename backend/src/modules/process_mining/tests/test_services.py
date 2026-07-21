"""Deterministic service and algorithm behavior."""
import io
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..adapters import CSVExportFormatter, InductiveMiner, TokenReplayConformance, XESExportFormatter, canonical_events
from ..models import ProcessEvent
from ..services import EventLogService, ProcessModelService
from .factories import EventFactory, event_log, graph

pytestmark = pytest.mark.django_db


def test_ingestion_validates_deduplicates_and_publishes():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    occurred = timezone.now() - timedelta(hours=1)
    payload = {"case_id": "c1", "activity": "Created", "occurred_at": occurred, "source_event_id": "s1"}
    service = EventLogService()
    first = service.ingest_events(tenant, actor, "canonical", "orders", [payload])
    second = service.ingest_events(tenant, actor, "canonical", "orders", [payload])
    assert (first.accepted, first.rejected, first.duplicates) == (1, 0, 0)
    assert second.duplicates == 1 and ProcessEvent.objects.for_tenant(tenant).count() == 1


@pytest.mark.parametrize("occurred", [timezone.now() + timedelta(minutes=1), timezone.now() - timedelta(days=731)])
def test_ingestion_rejects_timestamp_bounds(occurred):
    result = EventLogService().ingest_events(uuid.uuid4(), uuid.uuid4(), "canonical", "orders", [{"case_id": "c", "activity": "a", "occurred_at": occurred}])
    assert result.rejected == 1 and result.accepted == 0


def test_event_query_requires_bounded_range():
    with pytest.raises(ValidationError):
        EventLogService().query_events(uuid.uuid4(), {"process_name": "orders"})


def test_local_algorithms_derive_real_graph_and_conformance():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor)
    events = canonical_events(rows)
    discovered = InductiveMiner().discover(events, {"noise_threshold": 0})
    traces = {f"case-{index}": [event for event in events if event.case_id == f"case-{index}"] for index in range(10)}
    result = TokenReplayConformance().evaluate(discovered, traces)
    assert len(discovered["nodes"]) == 5
    assert result.fitness == 1 and not result.deviations


@pytest.mark.parametrize("formatter", [CSVExportFormatter(), XESExportFormatter()])
def test_exports_are_deterministic_and_count_rows(formatter):
    event = EventFactory()
    first, second = io.StringIO(), io.StringIO()
    assert formatter.write(canonical_events([event]), first) == 1
    formatter.write(canonical_events([event]), second)
    assert first.getvalue() == second.getvalue()


def test_imported_model_publishes_immutable_version():
    model = ProcessModelService().create_imported_model(uuid.uuid4(), uuid.uuid4(), "Reference", "orders", "", graph())
    assert model.versions.count() == 1 and model.versions.get().model_data["schema_version"] == "1.0"
