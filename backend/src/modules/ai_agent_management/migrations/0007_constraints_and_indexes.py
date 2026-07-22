"""Complete numeric/financial checks and verify tenant-leading indexes."""

from django.db import migrations
from django.db import models
from django.db.models import Q


def verify_tenant_indexes(apps, schema_editor):
    """Stop deployment if a documented list model lacks a tenant-leading index."""

    for model in apps.get_app_config("ai_agent_management").get_models():
        if model._meta.proxy or not any(field.name == "tenant_id" for field in model._meta.fields):
            continue
        if not any(index.fields and index.fields[0] == "tenant_id" for index in model._meta.indexes):
            # A single-column db_index on tenant_id is inherited by every
            # tenant model, but domain list paths require a composite index.
            raise ValueError(f"{model._meta.label} has no tenant-leading composite index")


class Migration(migrations.Migration):
    dependencies = [("ai_agent_management", "0006_access_quota_projection")]

    operations = [
        migrations.AlterField(
            model_name="tool",
            name="required_permissions",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddConstraint(
            model_name="quotausage",
            constraint=models.CheckConstraint(condition=Q(usage_value__gt=0), name="ai_quota_usage_positive_ck"),
        ),
        migrations.AddConstraint(
            model_name="costrecord",
            constraint=models.CheckConstraint(condition=Q(currency__regex=r"^[A-Z]{3}$"), name="ai_cost_currency_ck"),
        ),
        migrations.AddConstraint(
            model_name="costrecord",
            constraint=models.CheckConstraint(condition=~Q(pricing_version=""), name="ai_cost_pricing_version_ck"),
        ),
        migrations.AddConstraint(
            model_name="costsummary",
            constraint=models.CheckConstraint(
                condition=Q(currency__regex=r"^[A-Z]{3}$"), name="ai_cost_sum_currency_ck"
            ),
        ),
        migrations.RunPython(verify_tenant_indexes, verify_tenant_indexes),
    ]
