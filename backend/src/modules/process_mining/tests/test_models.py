"""Persistence invariants for all eleven domain entities."""
import uuid

import pytest
from django.core.exceptions import ValidationError
from src.core.tenancy import TenantScopedModel

from ..models import BottleneckAnalysis, BottleneckFinding, ConformanceCaseMetric, ConformanceCheck, ConformanceDeviation, EventExportJob, ProcessDiscoveryJob, ProcessEvent, ProcessModel, ProcessModelVersion, ProcessVariant, validate_graph
from .factories import AnalysisFactory, DeviationFactory, EventFactory, FindingFactory, ModelFactory, VariantFactory, VersionFactory, graph

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("model", [ProcessEvent, EventExportJob, ProcessDiscoveryJob, ProcessModel, ProcessModelVersion, ConformanceCheck, ConformanceDeviation, ConformanceCaseMetric, BottleneckAnalysis, BottleneckFinding, ProcessVariant])
def test_all_domain_models_use_indexed_uuid_tenant(model):
    assert issubclass(model, TenantScopedModel)
    field = model._meta.get_field("tenant_id")
    assert field.get_internal_type() == "UUIDField" and field.db_index


def test_uuid_identity_and_defaults():
    event = EventFactory()
    model = ModelFactory(tenant_id=event.tenant_id)
    assert isinstance(event.id, uuid.UUID)
    assert model.is_deleted is False and model.reference_version_number is None


@pytest.mark.parametrize("factory", [EventFactory, DeviationFactory, FindingFactory, VariantFactory])
def test_completed_evidence_is_append_only(factory):
    value = factory()
    with pytest.raises(ValidationError, match="immutable"):
        value.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        value.delete()


def test_relationships_fail_closed_across_tenants():
    model = ModelFactory()
    version = VersionFactory.build(process_model=model, tenant_id=uuid.uuid4(), model_data=graph())
    with pytest.raises(ValidationError, match="not found"):
        version.full_clean()


def test_graph_and_variant_validation():
    with pytest.raises(ValidationError, match="at least one node"):
        validate_graph({"schema_version": "1.0", "nodes": [], "edges": []})
    variant = VariantFactory.build(analysis=AnalysisFactory(), activities=[])
    with pytest.raises(ValidationError, match="nonempty"):
        variant.full_clean()
