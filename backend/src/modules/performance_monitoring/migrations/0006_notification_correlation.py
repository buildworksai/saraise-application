"""Carry request correlation through immutable notification outcomes."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("performance_monitoring", "0005_evidence_immutability")]

    operations = [
        migrations.AddField(
            model_name="alertnotificationoutcome",
            name="correlation_id",
            field=models.CharField(db_index=True, default="legacy-unavailable", max_length=128),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="alertnotificationoutcome",
            constraint=models.CheckConstraint(
                condition=~models.Q(correlation_id=""),
                name="pm_notify_correlation_present",
            ),
        ),
    ]
