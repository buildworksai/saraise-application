"""Small, explicit factories for BI domain tests.

The helpers deliberately require a tenant identifier.  Tests cannot
accidentally create an unowned object or hide tenant setup in a global default.
"""

from __future__ import annotations

import itertools
import uuid
from typing import Any

from src.modules.business_intelligence.models import Dashboard, DashboardWidget, QueryDefinition, Report

_sequence = itertools.count(1)


def query_factory(tenant_id: uuid.UUID, **overrides: Any) -> QueryDefinition:
    number = next(_sequence)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "query_code": f"QUERY_{number}",
        "name": f"Query {number}",
        "dataset_key": "core.operations",
        "dimensions": ["name"],
        "measures": [{"key": "count", "aggregation": "count"}],
        "created_by_id": "tester",
        "updated_by_id": "tester",
    }
    values.update(overrides)
    return QueryDefinition.objects.create(**values)


def report_factory(tenant_id: uuid.UUID, query_definition: QueryDefinition, **overrides: Any) -> Report:
    number = next(_sequence)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "report_code": f"REPORT_{number}",
        "report_name": f"Report {number}",
        "report_type": "table",
        "query_definition": query_definition,
        "created_by_id": "tester",
        "updated_by_id": "tester",
    }
    values.update(overrides)
    return Report.objects.create(**values)


def dashboard_factory(tenant_id: uuid.UUID, **overrides: Any) -> Dashboard:
    number = next(_sequence)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "dashboard_code": f"DASHBOARD_{number}",
        "dashboard_name": f"Dashboard {number}",
        "created_by_id": "tester",
        "updated_by_id": "tester",
    }
    values.update(overrides)
    return Dashboard.objects.create(**values)


def widget_factory(
    tenant_id: uuid.UUID,
    dashboard: Dashboard,
    query_definition: QueryDefinition,
    **overrides: Any,
) -> DashboardWidget:
    number = next(_sequence)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "dashboard": dashboard,
        "query_definition": query_definition,
        "widget_type": "table",
        "title": f"Widget {number}",
        "x": 0,
        "y": number - 1,
        "width": 6,
        "height": 4,
        "display_order": number - 1,
    }
    values.update(overrides)
    return DashboardWidget.objects.create(**values)
