"""Two-tenant isolation contracts for each mutable BI aggregate."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.exceptions import NotFound

from src.modules.business_intelligence.models import DashboardWidget, QueryDefinition, Report
from src.modules.business_intelligence.services import QueryService, _get

from .factories import dashboard_factory, query_factory, report_factory, widget_factory


@pytest.mark.django_db
def test_for_tenant_excludes_every_other_tenant_definition() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    query_a, query_b = query_factory(tenant_a), query_factory(tenant_b)
    report_a, report_b = report_factory(tenant_a, query_a), report_factory(tenant_b, query_b)
    dashboard_a, dashboard_b = dashboard_factory(tenant_a), dashboard_factory(tenant_b)
    widget_a = widget_factory(tenant_a, dashboard_a, query_a)
    widget_b = widget_factory(tenant_b, dashboard_b, query_b)

    assert list(QueryDefinition.objects.for_tenant(tenant_a)) == [query_a]
    assert list(Report.objects.for_tenant(tenant_a)) == [report_a]
    assert list(DashboardWidget.objects.for_tenant(tenant_a)) == [widget_a]
    assert widget_b not in DashboardWidget.objects.for_tenant(tenant_a)
    assert report_b not in Report.objects.for_tenant(tenant_a)


@pytest.mark.django_db
def test_known_cross_tenant_identifier_never_resolves_in_tenant_queryset() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    foreign = query_factory(tenant_b)
    assert QueryDefinition.objects.for_tenant(tenant_a).filter(pk=foreign.pk).first() is None


@pytest.mark.django_db
def test_cross_tenant_list_detail_create_update_and_delete_are_isolated() -> None:
    """A known foreign UUID never widens any CRUD boundary or changes its row."""

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    foreign = query_factory(tenant_b)
    before = {field.attname: getattr(foreign, field.attname) for field in foreign._meta.concrete_fields}

    # list and detail
    assert foreign not in QueryDefinition.objects.for_tenant(tenant_a)
    with pytest.raises(NotFound):
        _get(QueryDefinition, tenant_a, foreign.id)

    # create ignores a spoofed ownership field and binds the accepted tenant.
    created = QueryService.create(
        tenant_a,
        "tenant-a-user",
        {
            "tenant_id": str(tenant_b),
            "query_code": "TENANT_A_QUERY",
            "name": "Tenant A query",
            "dataset_key": "business_intelligence.execution_audit",
            "dimensions": ["status"],
            "measures": [{"key": "execution_count"}],
        },
        "isolation-create",
        "isolation-create",
    )
    assert created.tenant_id == tenant_a

    # update and delete use the same non-disclosing tenant lookup.
    with pytest.raises(NotFound):
        QueryService.update(
            tenant_a,
            foreign.id,
            "tenant-a-user",
            foreign.version,
            {"name": "Compromised"},
            "isolation-update",
            "isolation-update",
        )
    with pytest.raises(NotFound):
        QueryService.soft_delete(
            tenant_a,
            foreign.id,
            "tenant-a-user",
            foreign.version,
            "isolation-delete",
            "isolation-delete",
        )

    foreign.refresh_from_db()
    after = {field.attname: getattr(foreign, field.attname) for field in foreign._meta.concrete_fields}
    assert after == before
