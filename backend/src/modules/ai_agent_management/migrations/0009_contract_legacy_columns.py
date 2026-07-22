"""Contract legacy ORM columns after canonical compatibility reads shipped.

The columns are removed from Django's state while retained physically for a
lossless emergency rollback. A later, separately validated maintenance change
may reclaim them after the documented rollback window closes.
"""

from django.db import migrations, models

LEGACY_FIELDS = (
    ("agent", "framework"),
    ("agent", "is_active"),
    ("agentexecution", "metadata"),
    ("auditevent", "created_at"),
    ("auditevent", "updated_at"),
    ("costrecord", "created_at"),
    ("costrecord", "updated_at"),
    ("egressrequest", "created_at"),
    ("egressrequest", "updated_at"),
    ("killswitch", "is_active"),
    ("quotausage", "created_at"),
    ("quotausage", "updated_at"),
    ("secretaccess", "created_at"),
    ("secretaccess", "updated_at"),
    ("shardsaturation", "created_at"),
    ("shardsaturation", "updated_at"),
    ("sodviolation", "created_at"),
    ("sodviolation", "updated_at"),
    ("tokenusage", "created_at"),
    ("tokenusage", "updated_at"),
    ("toolinvocation", "success"),
    ("secret", "encrypted_value"),
    ("secret", "encryption_key_id"),
)


def prepare_reverse(apps, schema_editor):
    """Populate retained compatibility columns before restoring NOT NULL."""

    Agent = apps.get_model("ai_agent_management", "Agent")
    for row in Agent.objects.all().iterator(chunk_size=500):
        row.framework = row.runner_key
        row.is_active = row.status == "active"
        row.save(update_fields=("framework", "is_active"))

    Execution = apps.get_model("ai_agent_management", "AgentExecution")
    for row in Execution.objects.all().iterator(chunk_size=500):
        row.metadata = row.input_metadata
        row.save(update_fields=("metadata",))

    timestamp_fields = (
        ("AuditEvent", "event_timestamp"),
        ("CostRecord", "cost_timestamp"),
        ("EgressRequest", "requested_at"),
        ("QuotaUsage", "usage_timestamp"),
        ("SecretAccess", "accessed_at"),
        ("ShardSaturation", "measured_at"),
        ("SoDViolation", "violation_at"),
        ("TokenUsage", "usage_timestamp"),
    )
    for model_name, source_field in timestamp_fields:
        Model = apps.get_model("ai_agent_management", model_name)
        for row in Model.objects.all().iterator(chunk_size=500):
            timestamp = getattr(row, source_field)
            row.created_at = timestamp
            row.updated_at = timestamp
            row.save(update_fields=("created_at", "updated_at"))

    KillSwitch = apps.get_model("ai_agent_management", "KillSwitch")
    for row in KillSwitch.objects.all().iterator(chunk_size=500):
        row.is_active = row.status == "active"
        row.save(update_fields=("is_active",))

    ToolInvocation = apps.get_model("ai_agent_management", "ToolInvocation")
    for row in ToolInvocation.objects.all().iterator(chunk_size=500):
        row.success = row.status == "succeeded"
        row.save(update_fields=("success",))

    Secret = apps.get_model("ai_agent_management", "Secret")
    for row in Secret.objects.all().iterator(chunk_size=500):
        row.encrypted_value = row.ciphertext
        row.encryption_key_id = row.key_id
        row.save(update_fields=("encrypted_value", "encryption_key_id"))


def retain_compatibility_columns(apps, schema_editor):
    """Forward data is already populated by the expand migration."""


class Migration(migrations.Migration):
    dependencies = [("ai_agent_management", "0008_tenant_guards_and_rls")]

    operations = [
        migrations.AlterField(model_name="agent", name="framework", field=models.CharField(max_length=50, null=True)),
        migrations.AlterField(model_name="agent", name="is_active", field=models.BooleanField(null=True)),
        migrations.AlterField(model_name="agentexecution", name="metadata", field=models.JSONField(null=True)),
        *[
            migrations.AlterField(
                model_name=model_name,
                name=field_name,
                field=models.DateTimeField(null=True),
            )
            for model_name, field_name in (
                ("auditevent", "created_at"),
                ("auditevent", "updated_at"),
                ("costrecord", "created_at"),
                ("costrecord", "updated_at"),
                ("egressrequest", "created_at"),
                ("egressrequest", "updated_at"),
                ("quotausage", "created_at"),
                ("quotausage", "updated_at"),
                ("secretaccess", "created_at"),
                ("secretaccess", "updated_at"),
                ("shardsaturation", "created_at"),
                ("shardsaturation", "updated_at"),
                ("sodviolation", "created_at"),
                ("sodviolation", "updated_at"),
                ("tokenusage", "created_at"),
                ("tokenusage", "updated_at"),
            )
        ],
        migrations.AlterField(model_name="killswitch", name="is_active", field=models.BooleanField(null=True)),
        migrations.AlterField(model_name="toolinvocation", name="success", field=models.BooleanField(null=True)),
        migrations.AlterField(model_name="secret", name="encrypted_value", field=models.TextField(null=True)),
        migrations.AlterField(
            model_name="secret", name="encryption_key_id", field=models.CharField(max_length=255, null=True)
        ),
        migrations.RunPython(retain_compatibility_columns, prepare_reverse),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(model_name=model_name, name=field_name)
                for model_name, field_name in LEGACY_FIELDS
            ],
        ),
    ]
