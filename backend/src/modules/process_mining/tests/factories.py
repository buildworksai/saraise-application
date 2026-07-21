"""Concrete factories and deterministic event logs for process-mining tests."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from ..models import BottleneckAnalysis, BottleneckFinding, ConformanceCaseMetric, ConformanceCheck, ConformanceDeviation, EventExportJob, ProcessDiscoveryJob, ProcessEvent, ProcessModel, ProcessModelVersion, ProcessVariant


def graph() -> dict[str, object]:
    return {"schema_version": "1.0", "nodes": [{"id": "start", "label": "Start", "type": "start", "frequency": 10}, {"id": "a", "label": "Approve", "type": "activity", "frequency": 10}, {"id": "end", "label": "End", "type": "end", "frequency": 10}], "edges": [{"id": "sa", "source": "start", "target": "a", "frequency": 10, "duration_seconds": 0}, {"id": "ae", "source": "a", "target": "end", "frequency": 10, "duration_seconds": 0}], "extensions": {}}


class EventFactory(factory.django.DjangoModelFactory):
    class Meta: model = ProcessEvent
    tenant_id = factory.LazyFunction(uuid.uuid4); created_by = factory.LazyFunction(uuid.uuid4); process_name = "order_to_cash"; source_module = "canonical"; source_event_id = factory.Sequence(lambda n: f"event-{n}"); case_id = factory.Sequence(lambda n: f"case-{n}"); activity = "Approve"; occurred_at = factory.LazyFunction(timezone.now); resource = "team-a"; attributes = factory.LazyFunction(dict); event_hash = factory.LazyFunction(lambda: hashlib.sha256(uuid.uuid4().bytes).hexdigest())


class ExportFactory(factory.django.DjangoModelFactory):
    class Meta: model = EventExportJob
    tenant_id = factory.LazyFunction(uuid.uuid4); created_by = factory.LazyFunction(uuid.uuid4); process_name = "order_to_cash"; format = "json"; event_filter = factory.LazyFunction(dict); idempotency_key = factory.LazyFunction(lambda: str(uuid.uuid4()))


class DiscoveryFactory(factory.django.DjangoModelFactory):
    class Meta: model = ProcessDiscoveryJob
    tenant_id = factory.LazyFunction(uuid.uuid4); created_by = factory.LazyFunction(uuid.uuid4); process_name = factory.Sequence(lambda n: f"order_to_cash_{n}"); algorithm = "inductive_miner"; parameters = factory.LazyFunction(dict); idempotency_key = factory.LazyFunction(lambda: str(uuid.uuid4()))


class ModelFactory(factory.django.DjangoModelFactory):
    class Meta: model = ProcessModel
    tenant_id = factory.LazyFunction(uuid.uuid4); created_by = factory.LazyFunction(uuid.uuid4); name = factory.Sequence(lambda n: f"Reference {n}"); process_name = "order_to_cash"; source_kind = "imported"


class VersionFactory(factory.django.DjangoModelFactory):
    class Meta: model = ProcessModelVersion
    process_model = factory.SubFactory(ModelFactory); tenant_id = factory.SelfAttribute("process_model.tenant_id"); created_by = factory.SelfAttribute("process_model.created_by"); version = factory.Sequence(lambda n: n + 1); parameters = factory.LazyFunction(dict); model_data = factory.LazyFunction(graph); event_count = 100; case_count = 10; activity_count = 1; avg_case_duration_seconds = Decimal("60.00"); published_at = factory.LazyFunction(timezone.now)


class ConformanceFactory(factory.django.DjangoModelFactory):
    class Meta: model = ConformanceCheck
    process_model_version = factory.SubFactory(VersionFactory); tenant_id = factory.SelfAttribute("process_model_version.tenant_id"); created_by = factory.SelfAttribute("process_model_version.created_by"); event_filter = factory.LazyFunction(dict); idempotency_key = factory.LazyFunction(lambda: str(uuid.uuid4()))


class DeviationFactory(factory.django.DjangoModelFactory):
    class Meta: model = ConformanceDeviation
    conformance_check = factory.SubFactory(ConformanceFactory); tenant_id = factory.SelfAttribute("conformance_check.tenant_id"); created_by = factory.SelfAttribute("conformance_check.created_by"); case_id = "case-1"; deviation_type = "unexpected_activity"; actual = "Reject"; position = 1


class CaseMetricFactory(factory.django.DjangoModelFactory):
    class Meta: model = ConformanceCaseMetric
    conformance_check = factory.SubFactory(ConformanceFactory); tenant_id = factory.SelfAttribute("conformance_check.tenant_id"); created_by = factory.SelfAttribute("conformance_check.created_by"); case_id = "case-1"; fitness = Decimal("0.5000"); is_conformant = False; deviation_count = 1; trace_length = 2


class AnalysisFactory(factory.django.DjangoModelFactory):
    class Meta: model = BottleneckAnalysis
    tenant_id = factory.LazyFunction(uuid.uuid4); created_by = factory.LazyFunction(uuid.uuid4); process_name = "order_to_cash"; time_range_start = factory.LazyFunction(lambda: timezone.now() - timedelta(days=1)); time_range_end = factory.LazyFunction(timezone.now); idempotency_key = factory.LazyFunction(lambda: str(uuid.uuid4()))


class FindingFactory(factory.django.DjangoModelFactory):
    class Meta: model = BottleneckFinding
    analysis = factory.SubFactory(AnalysisFactory); tenant_id = factory.SelfAttribute("analysis.tenant_id"); created_by = factory.SelfAttribute("analysis.created_by"); from_activity = "Create"; to_activity = "Approve"; avg_duration_seconds = Decimal("20"); median_duration_seconds = Decimal("10"); p95_duration_seconds = Decimal("100"); case_count = 20; severity = "high"; rank = 1


class VariantFactory(factory.django.DjangoModelFactory):
    class Meta: model = ProcessVariant
    analysis = factory.SubFactory(AnalysisFactory); tenant_id = factory.SelfAttribute("analysis.tenant_id"); created_by = factory.SelfAttribute("analysis.created_by"); variant_key = factory.LazyFunction(lambda: hashlib.sha256(uuid.uuid4().bytes).hexdigest()); activities = factory.LazyFunction(lambda: ["Create", "Approve"]); case_count = 20; percentage = Decimal("100"); avg_duration_seconds = Decimal("20"); is_happy_path = True; is_grouped_other = False


def event_log(tenant_id: uuid.UUID, actor_id: uuid.UUID, cases: int = 10) -> list[ProcessEvent]:
    start = timezone.now() - timedelta(days=1)
    rows = []
    for case in range(cases):
        for position, activity in enumerate(("Create", "Approve", "Complete")):
            rows.append(EventFactory(tenant_id=tenant_id, created_by=actor_id, case_id=f"case-{case}", source_event_id=f"{case}-{position}", activity=activity, occurred_at=start + timedelta(minutes=case * 10 + position)))
    return rows
