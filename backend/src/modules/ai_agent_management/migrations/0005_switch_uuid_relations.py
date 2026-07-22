"""Complete the expand/contract switch to canonical UUID execution links."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai_agent_management", "0004_backfill_uuid_and_state")]

    operations = [
        migrations.AlterField(
            model_name="agentexecution",
            name="async_job_id",
            field=models.UUIDField(unique=True),
        ),
    ]
