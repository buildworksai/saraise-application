"""Move legacy module quota authority into the canonical access projection."""

from __future__ import annotations

from django.db import migrations

BATCH_SIZE = 500
SOURCE = "ai_agent_management.legacy_quota"


def project_quotas(apps, schema_editor):
    LegacyQuota = apps.get_model("ai_agent_management", "TenantQuota")
    AccessQuota = apps.get_model("core", "Quota")
    for legacy in LegacyQuota.objects.all().iterator(chunk_size=BATCH_SIZE):
        resource = f"ai.{legacy.quota_type}.{legacy.period}"
        remaining = max(0, legacy.limit_value - legacy.current_usage)
        quota, created = AccessQuota.objects.get_or_create(
            tenant_id=legacy.tenant_id,
            resource=resource,
            defaults={
                "limit": legacy.limit_value,
                "remaining": remaining,
                "reset_at": legacy.reset_at,
                "metadata": {"projection_source": SOURCE, "legacy_id": str(legacy.id)},
            },
        )
        if not created and (quota.limit != legacy.limit_value or quota.remaining != remaining):
            raise ValueError(f"Conflicting canonical quota for tenant={legacy.tenant_id} resource={resource}")


def reverse_quotas(apps, schema_editor):
    """Remove only projections created from the retained legacy authority."""

    AccessQuota = apps.get_model("core", "Quota")
    for quota in AccessQuota.objects.all().iterator(chunk_size=BATCH_SIZE):
        metadata = quota.metadata if isinstance(quota.metadata, dict) else {}
        if metadata.get("projection_source") == SOURCE:
            quota.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_access_entitlement_quota"),
        ("ai_agent_management", "0005_switch_uuid_relations"),
    ]

    operations = [
        migrations.RunPython(project_quotas, reverse_quotas),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(model_name="quotausage", name="quota"),
                migrations.DeleteModel(name="TenantQuota"),
            ],
        ),
    ]
