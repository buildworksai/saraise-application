"""Regression proof for readiness, event wiring, and immutable evidence."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.core.async_jobs.services import get_handler
from src.core.notifications.services import NotificationService
from src.modules.performance_monitoring import health, tasks
from src.modules.performance_monitoring import urls as v1_urls
from src.modules.performance_monitoring import v2_urls
from src.modules.performance_monitoring.events import CONSUMER_COMMANDS, register_event_consumers
from src.modules.performance_monitoring.models import Metric, MetricDataPoint, MetricType
from src.modules.performance_monitoring.services import ConfigurationService


def test_notification_readiness_fails_closed_without_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(NotificationService, "readiness_probe", raising=False)
    result = health.notifications_probe()
    assert result.healthy is False
    assert result.details == {"code": "readiness_contract_unavailable"}


def test_notification_readiness_accepts_only_conclusive_healthy_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        NotificationService,
        "readiness_probe",
        staticmethod(lambda: SimpleNamespace(healthy=True)),
        raising=False,
    )
    result = health.notifications_probe()
    assert result.healthy is True
    assert result.details == {"code": "ready"}


@pytest.mark.django_db
def test_evidence_rejects_queryset_mutation() -> None:
    tenant_id = uuid.uuid4()
    metric = Metric.objects.create(
        tenant_id=tenant_id,
        metric_name="integrity.latency",
        metric_type=MetricType.GAUGE,
    )
    point = MetricDataPoint.objects.create(
        tenant_id=tenant_id,
        metric=metric,
        timestamp=timezone.now(),
        value=1,
    )

    with pytest.raises(ValidationError, match="append-only"):
        MetricDataPoint.objects.filter(id=point.id).update(value=2)
    with pytest.raises(ValidationError, match="append-only"):
        MetricDataPoint.objects.filter(id=point.id).delete()
    with pytest.raises(ValidationError, match="append-only"):
        MetricDataPoint._base_manager.filter(id=point.id).update(value=3)
    with pytest.raises(ValidationError, match="append-only"):
        MetricDataPoint._base_manager.filter(id=point.id).delete()

    assert MetricDataPoint.objects.filter(id=point.id).exists()


@pytest.mark.skipif(connection.vendor != "postgresql", reason="Physical trigger is a PostgreSQL production control")
@pytest.mark.django_db(transaction=True)
def test_postgresql_trigger_rejects_database_evidence_mutation() -> None:
    tenant_id = uuid.uuid4()
    metric = Metric.objects.create(
        tenant_id=tenant_id,
        metric_name="integrity.database",
        metric_type=MetricType.GAUGE,
    )
    point = MetricDataPoint.objects.create(
        tenant_id=tenant_id,
        metric=metric,
        timestamp=timezone.now(),
        value=1,
    )
    table = connection.ops.quote_name(MetricDataPoint._meta.db_table)
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table} WHERE id = %s", [point.id.hex])
    assert MetricDataPoint.objects.filter(id=point.id).exists()


@pytest.mark.django_db
def test_retention_creates_cryptographic_archive_request_without_deleting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    metric = Metric.objects.create(
        tenant_id=tenant_id,
        metric_name="integrity.archive",
        metric_type=MetricType.GAUGE,
    )
    point = MetricDataPoint.objects.create(
        tenant_id=tenant_id,
        metric=metric,
        timestamp=timezone.now(),
        value=1,
    )
    monkeypatch.setattr(
        ConfigurationService,
        "effective_document",
        lambda self, tenant_id, environment: {
            "evidence": {
                "retention_days": 30,
                "archival_enabled": True,
                "archive_provider": "governed-test-provider",
            }
        },
    )

    result = tasks.enforce_retention_task(tenant_id=tenant_id, cutoff=timezone.now())

    assert result["status"] == "archive_requested"
    assert result["evidence_counts"]["metric_data_points"] == 1
    assert len(result["evidence_sha256"]) == 64
    assert MetricDataPoint.objects.filter(id=point.id).exists()
    event = OutboxEvent.objects.get(id=result["archive_request_id"])
    assert event.event_type == "performance_monitoring.evidence.archive_requested.v1"
    assert event.payload["evidence_sha256"] == result["evidence_sha256"]


def test_declared_event_consumers_are_registered_idempotently() -> None:
    register_event_consumers()
    register_event_consumers()
    for command in CONSUMER_COMMANDS.values():
        assert callable(get_handler(command))


def test_async_readiness_verifies_every_declared_handler() -> None:
    result = health.async_probe()
    assert result.healthy is True
    assert result.details == {"code": "ready"}


def test_manifest_inventory_matches_models_routers_and_consumers() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    declared_entities = set(manifest["entities"])
    concrete_entities = {
        model.__name__ for model in apps.get_app_config("performance_monitoring").get_models() if not model._meta.proxy
    }
    assert declared_entities == concrete_entities

    for version, router in (("v1", v1_urls.router), ("v2", v2_urls.router)):
        declared_paths = {entry["path"] for entry in manifest["endpoints"] if entry["version"] == version}
        registered_paths = {prefix for prefix, _, _ in router.registry}
        assert registered_paths == declared_paths - {"health"}
        assert "health" in declared_paths

    declared_consumers = {item["event"]: item["handler"] for item in manifest["events"]["consumes"]}
    assert declared_consumers == CONSUMER_COMMANDS
