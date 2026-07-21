import uuid

import pytest
from django.core.exceptions import ValidationError

from src.core.tenancy import TenantScopedModel
from src.modules.performance_monitoring.models import Metric, MetricType, TelemetrySource


@pytest.mark.django_db
def test_domain_models_use_uuid_tenant_and_soft_delete():
    tenant = uuid.uuid4()
    source = TelemetrySource.objects.create(tenant_id=tenant, name="OTLP", source_type="otlp")
    assert isinstance(source, TenantScopedModel)
    assert source._meta.get_field("tenant_id").get_internal_type() == "UUIDField"
    source.delete()
    source.refresh_from_db()
    assert source.is_deleted and source.deleted_at is not None


@pytest.mark.django_db
def test_metric_validates_dot_notation_and_immutable_tenant():
    tenant = uuid.uuid4()
    metric = Metric.objects.create(
        tenant_id=tenant,
        metric_name="api.duration_ms",
        metric_type=MetricType.HISTOGRAM,
    )
    metric.tenant_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        metric.save()
    with pytest.raises(ValidationError):
        Metric.objects.create(tenant_id=tenant, metric_name="invalid name", metric_type=MetricType.GAUGE)
