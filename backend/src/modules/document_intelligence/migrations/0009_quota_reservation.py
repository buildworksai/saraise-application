"""Add tenant-idempotent quota reservation evidence."""

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("document_intelligence", "0008_template_idempotency")]
    operations = [
        migrations.CreateModel(
            name="QuotaReservation",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("resource", models.CharField(max_length=120)),
                ("operation_key", models.CharField(max_length=255)),
                ("cost", models.PositiveIntegerField()),
            ],
            options={"db_table": "document_intelligence_quota_reservations"},
        ),
        migrations.AddConstraint(
            model_name="quotareservation",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "resource", "operation_key"),
                name="docintel_quota_tenant_resource_key_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="quotareservation",
            constraint=models.CheckConstraint(condition=models.Q(("cost__gt", 0)), name="docintel_quota_cost_gt_zero"),
        ),
    ]
