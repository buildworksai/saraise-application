"""Contract tests for the complete BI persistence model."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.modules.business_intelligence.models import (
    DashboardShare,
    DashboardWidget,
    QueryDefinition,
    QueryExecution,
    Report,
)

from .factories import dashboard_factory, query_factory, report_factory


@pytest.mark.django_db
def test_all_domain_models_use_canonical_tenant_base() -> None:
    for model in (QueryDefinition, Report, DashboardWidget, DashboardShare, QueryExecution):
        assert issubclass(model, TenantScopedModel)
    assert issubclass(QueryDefinition, TimestampedModel)


@pytest.mark.django_db
def test_definition_defaults_and_code_normalization() -> None:
    query = query_factory(uuid.uuid4(), query_code=" monthly_sales ")
    assert query.query_code == "MONTHLY_SALES"
    assert query.state == "draft"
    assert query.version == 1
    assert query.row_limit == 500
    assert str(query) == f"MONTHLY_SALES - {query.name}"


@pytest.mark.django_db(transaction=True)
def test_live_codes_are_unique_but_soft_deleted_codes_can_be_reused() -> None:
    tenant_id = uuid.uuid4()
    first = query_factory(tenant_id, query_code="SAME")
    with pytest.raises(IntegrityError):
        query_factory(tenant_id, query_code="SAME")
    first.deleted_at = first.created_at
    first.save(update_fields=["deleted_at", "updated_at"])
    assert query_factory(tenant_id, query_code="SAME").pk != first.pk


@pytest.mark.django_db
def test_cross_tenant_relationships_fail_validation() -> None:
    query = query_factory(uuid.uuid4())
    report = Report(
        tenant_id=uuid.uuid4(),
        report_code="CROSS_TENANT",
        report_name="Unsafe",
        report_type="table",
        query_definition=query,
        created_by_id="tester",
        updated_by_id="tester",
    )
    with pytest.raises(ValidationError):
        report.full_clean()


@pytest.mark.django_db
def test_widget_requires_exactly_one_source() -> None:
    tenant_id = uuid.uuid4()
    dashboard = dashboard_factory(tenant_id)
    widget = DashboardWidget(
        tenant_id=tenant_id,
        dashboard=dashboard,
        title="Missing source",
        widget_type="table",
    )
    with pytest.raises(ValidationError):
        widget.full_clean()


@pytest.mark.django_db
def test_published_report_requires_published_definition() -> None:
    tenant_id = uuid.uuid4()
    query = query_factory(tenant_id)
    report = report_factory(tenant_id, query, state="published")
    with pytest.raises(ValidationError):
        report.full_clean()
