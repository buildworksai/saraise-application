"""Safely recognize declarative legacy queries while preserving source bytes."""

import json

from django.db import migrations


def _parse_definition(value):
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("dataset_key"), str)
        or not parsed["dataset_key"].strip()
        or {"sql", "query", "expression", "python", "script"} & set(parsed)
    ):
        return None
    list_fields = ("dimensions", "measures", "filters", "grouping", "ordering")
    if any(not isinstance(parsed.get(field, []), list) for field in list_fields):
        return None
    if not isinstance(parsed.get("parameters_schema", {}), dict):
        return None
    return parsed


def _bounded_integer(value, default, lower, upper):
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(converted, lower), upper)


def forwards(apps, schema_editor):
    Report = apps.get_model("business_intelligence", "Report")
    QueryDefinition = apps.get_model("business_intelligence", "QueryDefinition")
    Dashboard = apps.get_model("business_intelligence", "Dashboard")
    DashboardWidget = apps.get_model("business_intelligence", "DashboardWidget")

    for report in Report.objects.all().iterator():
        parsed = _parse_definition(report.legacy_query)
        if parsed is None:
            report.state = "archived"
            report.save(update_fields=["state"])
            continue
        base_code = f"{report.report_code}_QUERY"[:64].upper()
        query_code = base_code
        suffix = 1
        while QueryDefinition.objects.filter(tenant_id=report.tenant_id, query_code=query_code, deleted_at__isnull=True).exists():
            marker = f"_{suffix}"
            query_code = f"{base_code[:64-len(marker)]}{marker}"
            suffix += 1
        query = QueryDefinition.objects.create(
            tenant_id=report.tenant_id,
            query_code=query_code,
            name=f"{report.report_name} query",
            description="Migrated declarative report definition",
            dataset_key=parsed["dataset_key"],
            dimensions=parsed.get("dimensions", []),
            measures=parsed.get("measures", []),
            filters=parsed.get("filters", []),
            grouping=parsed.get("grouping", []),
            ordering=parsed.get("ordering", []),
            parameters_schema=parsed.get("parameters_schema", {}),
            row_limit=_bounded_integer(parsed.get("row_limit", 500), 500, 1, 10_000),
            cache_ttl_seconds=_bounded_integer(parsed.get("cache_ttl_seconds", 300), 300, 0, 86_400),
            state="draft",
            created_by_id="migration",
            updated_by_id="migration",
        )
        report.query_definition_id = query.id
        report.state = "draft" if report.is_active else "archived"
        report.save(update_fields=["query_definition", "state"])

    for dashboard in Dashboard.objects.all().iterator():
        dashboard.state = "draft" if dashboard.is_active else "archived"
        dashboard.save(update_fields=["state"])
        layout = dashboard.legacy_layout
        widgets = layout.get("widgets") if isinstance(layout, dict) else layout if isinstance(layout, list) else None
        if not isinstance(widgets, list):
            continue
        for position, item in enumerate(widgets):
            if not isinstance(item, dict):
                continue
            report = None
            query = None
            if item.get("report_code"):
                report = Report.objects.filter(tenant_id=dashboard.tenant_id, report_code=item["report_code"]).first()
            elif item.get("query_code"):
                query = QueryDefinition.objects.filter(tenant_id=dashboard.tenant_id, query_code=item["query_code"]).first()
            if bool(report) == bool(query):
                continue
            widget_type = item.get("widget_type", "table")
            if widget_type not in {"kpi", "table", "bar", "line", "area", "pie", "funnel"}:
                continue
            DashboardWidget.objects.create(
                tenant_id=dashboard.tenant_id,
                dashboard_id=dashboard.id,
                query_definition_id=query.id if query else None,
                report_id=report.id if report else None,
                widget_type=widget_type,
                title=str(item.get("title") or "Migrated widget")[:255],
                description=str(item.get("description") or ""),
                x=_bounded_integer(item.get("x", 0), 0, 0, 1_000_000),
                y=_bounded_integer(item.get("y", 0), 0, 0, 1_000_000),
                width=_bounded_integer(item.get("width", 4), 4, 1, 12),
                height=_bounded_integer(item.get("height", 4), 4, 1, 24),
                visualization=item.get("visualization", {}) if isinstance(item.get("visualization", {}), dict) else {},
                filters=item.get("filters", []) if isinstance(item.get("filters", []), list) else [],
                display_order=position,
            )


def backwards(apps, schema_editor):
    Report = apps.get_model("business_intelligence", "Report")
    # ``is_active``, ``legacy_query`` and ``legacy_layout`` are deliberately
    # untouched by the forward migration, so reversing preserves their exact
    # pre-migration values instead of attempting to infer them from lifecycle.
    Report.objects.all().update(query_definition=None)


class Migration(migrations.Migration):
    dependencies = [("business_intelligence", "0002_domain_schema")]
    operations = [migrations.RunPython(forwards, backwards)]
