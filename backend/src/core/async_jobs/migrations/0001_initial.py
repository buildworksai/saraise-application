# Generated for SARAISE's durable async-work foundation.

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Create durable job, immutable transition, and outbox storage."""

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AsyncJob",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("actor_id", models.CharField(db_index=True, max_length=255)),
                ("command", models.CharField(db_index=True, max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("timed_out", "Timed out"),
                            ("retrying", "Retrying"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=255)),
                ("payload", models.JSONField(default=dict)),
                ("result", models.JSONField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "async_jobs",
                "ordering": ("created_at", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "status", "created_at"],
                        name="asyncjob_tenant_status_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "command", "created_at"],
                        name="asyncjob_tenant_cmd_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "idempotency_key"),
                        name="asyncjob_tenant_idem_uniq",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="OutboxEvent",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("aggregate_type", models.CharField(max_length=100)),
                ("aggregate_id", models.UUIDField(db_index=True)),
                ("event_type", models.CharField(db_index=True, max_length=255)),
                ("payload", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("dispatching", "Dispatching"),
                            ("dispatched", "Dispatched"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("available_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("claim_token", models.UUIDField(blank=True, editable=False, null=True)),
                ("claimed_until", models.DateTimeField(blank=True, null=True)),
                ("broker_message_id", models.CharField(blank=True, max_length=255)),
                ("dispatched_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "async_job_outbox_events",
                "ordering": ("created_at", "id"),
                "indexes": [
                    models.Index(fields=["status", "available_at", "created_at"], name="outbox_pending_idx"),
                    models.Index(
                        fields=["tenant_id", "aggregate_type", "aggregate_id"],
                        name="outbox_tenant_agg_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="JobTransition",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "from_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("timed_out", "Timed out"),
                            ("retrying", "Retrying"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "to_status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("timed_out", "Timed out"),
                            ("retrying", "Retrying"),
                        ],
                        max_length=20,
                    ),
                ),
                ("actor_id", models.CharField(blank=True, max_length=255, null=True)),
                ("reason", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transitions",
                        to="async_jobs.asyncjob",
                    ),
                ),
            ],
            options={
                "db_table": "async_job_transitions",
                "ordering": ("created_at", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "job", "created_at"],
                        name="jobtrans_tenant_job_idx",
                    )
                ],
            },
        ),
    ]
