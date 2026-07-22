"""Align Django validation with JSON fields whose empty values are valid."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("integration_platform", "0005_domain_rls")]

    operations = [
        migrations.AlterField(
            model_name="connector",
            name="schema",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="connector",
            name="credential_schema",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="connector",
            name="capabilities",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="integration",
            name="config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="integration",
            name="transition_history",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="integrationcredential",
            name="transition_history",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="webhook",
            name="config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="webhook",
            name="transition_history",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="webhookdelivery",
            name="payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="webhookdelivery",
            name="transition_history",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
