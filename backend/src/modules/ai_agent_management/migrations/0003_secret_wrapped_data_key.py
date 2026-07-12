"""Add nullable envelope metadata for staged migration of existing secrets."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai_agent_management", "0002_approvalrequest_ai_approval_tenant__15d886_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="secret",
            name="wrapped_data_key",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Per-secret data key wrapped by the configured KMS backend",
            ),
        ),
    ]
