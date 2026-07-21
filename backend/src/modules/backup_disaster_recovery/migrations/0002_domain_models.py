"""Create the canonical disaster-recovery domain without touching legacy data."""

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("backup_disaster_recovery", "0001_initial")]

    operations = [
        # Remove the historical scaffold from Django's runtime state only.  Its
        # table and untrusted ``config`` payload remain untouched on disk.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[migrations.DeleteModel(name="BackupDisasterRecoveryResource")],
        ),
        migrations.CreateModel(
            name="RecoveryPoint",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("backup_job_id", models.UUIDField()),
                ("backup_archive_id", models.UUIDField(blank=True, null=True)),
                ("adapter_key", models.CharField(max_length=64)),
                ("artifact_locator_ref", models.CharField(max_length=255)),
                ("encryption_key_ref", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "scope_type",
                    models.CharField(
                        choices=[("tenant", "Tenant"), ("module", "Module"), ("database", "Database"), ("files", "Files")],
                        max_length=16,
                    ),
                ),
                ("scope_ref", models.CharField(max_length=255)),
                (
                    "backup_type",
                    models.CharField(
                        choices=[("full", "Full"), ("incremental", "Incremental"), ("differential", "Differential")],
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("discovered", "Discovered"),
                            ("verifying", "Verifying"),
                            ("available", "Available"),
                            ("corrupt", "Corrupt"),
                            ("expired", "Expired"),
                            ("deleted", "Deleted"),
                        ],
                        default="discovered",
                        max_length=16,
                    ),
                ),
                ("data_cutoff_at", models.DateTimeField()),
                ("captured_at", models.DateTimeField()),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("size_bytes", models.PositiveBigIntegerField(blank=True, null=True)),
                ("checksum_algorithm", models.CharField(default="sha256", max_length=16)),
                ("checksum_digest", models.CharField(max_length=64)),
                ("verification_evidence", models.JSONField(blank=True, default=dict)),
                ("created_by", models.UUIDField()),
                ("transition_history", models.JSONField(blank=True, default=list)),
            ],
            options={
                "db_table": "bdr_recovery_points",
                "indexes": [
                    models.Index(fields=["tenant_id", "status", "-captured_at"], name="bdr_rp_tenant_status_cap_idx"),
                    models.Index(
                        fields=["tenant_id", "scope_type", "scope_ref", "-captured_at"],
                        name="bdr_rp_tenant_scope_cap_idx",
                    ),
                    models.Index(fields=["tenant_id", "expires_at"], name="bdr_rp_tenant_expiry_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "backup_job_id"), name="bdr_rp_tenant_job_uniq"),
                    models.CheckConstraint(
                        condition=models.Q(("data_cutoff_at__lte", models.F("captured_at"))),
                        name="bdr_rp_cutoff_lte_capture",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("expires_at__isnull", True), ("expires_at__gt", models.F("captured_at")), _connector="OR"),
                        name="bdr_rp_expiry_after_capture",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("size_bytes__isnull", True), ("size_bytes__gte", 0), _connector="OR"),
                        name="bdr_rp_size_nonnegative",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DRRunbook",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.CharField(max_length=120)),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published"), ("retired", "Retired")],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "scope_type",
                    models.CharField(
                        choices=[("tenant", "Tenant"), ("module", "Module"), ("database", "Database"), ("files", "Files")],
                        max_length=16,
                    ),
                ),
                ("scope_ref", models.CharField(max_length=255)),
                ("backup_schedule_id", models.UUIDField(blank=True, null=True)),
                ("adapter_key", models.CharField(max_length=64)),
                ("rpo_target_seconds", models.PositiveBigIntegerField()),
                ("rto_target_seconds", models.PositiveBigIntegerField()),
                ("owner_id", models.UUIDField()),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.UUIDField()),
                ("updated_by", models.UUIDField()),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_by", models.UUIDField(blank=True, null=True)),
                ("transition_history", models.JSONField(blank=True, default=list)),
                (
                    "supersedes",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="successor_versions",
                        to="backup_disaster_recovery.drrunbook",
                    ),
                ),
            ],
            options={
                "db_table": "bdr_runbooks",
                "indexes": [
                    models.Index(fields=["tenant_id", "status", "-updated_at"], name="bdr_rb_tenant_status_upd_idx"),
                    models.Index(fields=["tenant_id", "owner_id", "status"], name="bdr_rb_tenant_owner_st_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "slug", "version"), name="bdr_rb_tenant_slug_ver_uniq"),
                    models.UniqueConstraint(
                        condition=models.Q(("deleted_at__isnull", True), ("status", "published")),
                        fields=("tenant_id", "slug"),
                        name="bdr_rb_one_published_uniq",
                    ),
                    models.CheckConstraint(condition=models.Q(("version__gt", 0)), name="bdr_rb_version_positive"),
                    models.CheckConstraint(condition=models.Q(("rpo_target_seconds__gt", 0)), name="bdr_rb_rpo_positive"),
                    models.CheckConstraint(condition=models.Q(("rto_target_seconds__gt", 0)), name="bdr_rb_rto_positive"),
                ],
            },
        ),
        migrations.CreateModel(
            name="RunbookStep",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("step_key", models.SlugField(db_index=False, max_length=80)),
                ("position", models.PositiveIntegerField()),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("validate_recovery_point", "Validate recovery point"),
                            ("restore", "Restore"),
                            ("verify", "Verify"),
                            ("failover", "Failover"),
                            ("failback", "Failback"),
                            ("manual_approval", "Manual approval"),
                            ("notify", "Notify"),
                            ("extension", "Extension"),
                        ],
                        max_length=32,
                    ),
                ),
                ("extension_action_key", models.CharField(blank=True, max_length=120, null=True)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("timeout_seconds", models.PositiveIntegerField(default=300)),
                ("retry_limit", models.PositiveSmallIntegerField(default=0)),
                (
                    "on_failure",
                    models.CharField(
                        choices=[("stop", "Stop"), ("continue_degraded", "Continue degraded")],
                        default="stop",
                        max_length=24,
                    ),
                ),
                ("approval_permission", models.CharField(blank=True, max_length=255, null=True)),
                ("created_by", models.UUIDField()),
                ("updated_by", models.UUIDField()),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_by", models.UUIDField(blank=True, null=True)),
                (
                    "runbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="steps",
                        to="backup_disaster_recovery.drrunbook",
                    ),
                ),
            ],
            options={
                "db_table": "bdr_runbook_steps",
                "indexes": [models.Index(fields=["tenant_id", "runbook", "position"], name="bdr_step_tenant_rb_pos_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("deleted_at__isnull", True)),
                        fields=("tenant_id", "runbook", "step_key"),
                        name="bdr_step_active_key_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("deleted_at__isnull", True)),
                        fields=("tenant_id", "runbook", "position"),
                        name="bdr_step_active_pos_uniq",
                    ),
                    models.CheckConstraint(condition=models.Q(("position__gt", 0)), name="bdr_step_position_positive"),
                    models.CheckConstraint(
                        condition=models.Q(("timeout_seconds__gte", 1), ("timeout_seconds__lte", 86400)),
                        name="bdr_step_timeout_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("retry_limit__gte", 0), ("retry_limit__lte", 10)),
                        name="bdr_step_retry_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("action_type", "extension"),
                                ("extension_action_key__isnull", False),
                                models.Q(("extension_action_key", ""), _negated=True),
                            ),
                            models.Q(models.Q(("action_type", "extension"), _negated=True), ("extension_action_key__isnull", True)),
                            _connector="OR",
                        ),
                        name="bdr_step_extension_key_shape",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DRExercise",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                (
                    "exercise_type",
                    models.CharField(
                        choices=[("tabletop", "Tabletop"), ("restore", "Restore"), ("failover", "Failover"), ("full", "Full")],
                        max_length=16,
                    ),
                ),
                (
                    "environment",
                    models.CharField(choices=[("isolated", "Isolated"), ("standby", "Standby")], max_length=16),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("scheduled", "Scheduled"),
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="scheduled",
                        max_length=16,
                    ),
                ),
                ("scheduled_for", models.DateTimeField()),
                ("async_job_id", models.UUIDField(blank=True, null=True)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("initiated_by", models.UUIDField()),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("summary", models.TextField(blank=True)),
                ("observed_rpo_seconds", models.PositiveBigIntegerField(blank=True, null=True)),
                ("observed_rto_seconds", models.PositiveBigIntegerField(blank=True, null=True)),
                ("rpo_met", models.BooleanField(blank=True, null=True)),
                ("rto_met", models.BooleanField(blank=True, null=True)),
                ("failed_step_id", models.UUIDField(blank=True, null=True)),
                ("evidence_summary", models.JSONField(blank=True, default=dict)),
                ("transition_history", models.JSONField(blank=True, default=list)),
                (
                    "recovery_point",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="exercises",
                        to="backup_disaster_recovery.recoverypoint",
                    ),
                ),
                (
                    "runbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="exercises",
                        to="backup_disaster_recovery.drrunbook",
                    ),
                ),
            ],
            options={
                "db_table": "bdr_exercises",
                "indexes": [
                    models.Index(fields=["tenant_id", "status", "scheduled_for"], name="bdr_ex_tenant_status_sched_idx"),
                    models.Index(fields=["tenant_id", "runbook", "-created_at"], name="bdr_ex_tenant_rb_created_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="bdr_ex_tenant_idem_uniq"),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("completed_at__isnull", False), ("status__in", ["passed", "failed", "cancelled"])),
                            models.Q(("status__in", ["passed", "failed", "cancelled"]), _negated=True),
                            _connector="OR",
                        ),
                        name="bdr_ex_terminal_completed",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RestoreRun",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "target_environment",
                    models.CharField(
                        choices=[("isolated", "Isolated"), ("standby", "Standby"), ("production", "Production")],
                        max_length=16,
                    ),
                ),
                ("target_ref", models.CharField(max_length=255)),
                (
                    "restore_mode",
                    models.CharField(choices=[("full", "Full"), ("selective", "Selective")], max_length=16),
                ),
                ("selected_components", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("validating", "Validating"),
                            ("ready", "Ready"),
                            ("restoring", "Restoring"),
                            ("verifying", "Verifying"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("async_job_id", models.UUIDField(blank=True, null=True)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("requested_by", models.UUIDField()),
                ("approved_by", models.UUIDField(blank=True, null=True)),
                ("requested_at", models.DateTimeField()),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("validation_evidence", models.JSONField(blank=True, default=dict)),
                ("verification_evidence", models.JSONField(blank=True, default=dict)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("error_message", models.TextField(blank=True)),
                ("achieved_rpo_seconds", models.PositiveBigIntegerField(blank=True, null=True)),
                ("achieved_rto_seconds", models.PositiveBigIntegerField(blank=True, null=True)),
                ("transition_history", models.JSONField(blank=True, default=list)),
                (
                    "exercise",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="restore_runs",
                        to="backup_disaster_recovery.drexercise",
                    ),
                ),
                (
                    "recovery_point",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="restore_runs",
                        to="backup_disaster_recovery.recoverypoint",
                    ),
                ),
                (
                    "runbook",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="restore_runs",
                        to="backup_disaster_recovery.drrunbook",
                    ),
                ),
            ],
            options={
                "db_table": "bdr_restore_runs",
                "indexes": [
                    models.Index(fields=["tenant_id", "status", "-requested_at"], name="bdr_rr_tenant_status_req_idx"),
                    models.Index(fields=["tenant_id", "recovery_point", "-requested_at"], name="bdr_rr_tenant_rp_req_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="bdr_rr_tenant_idem_uniq"),
                    models.CheckConstraint(
                        condition=models.Q(("approved_by__isnull", True), ("target_environment", "production"), _negated=True),
                        name="bdr_rr_prod_approved",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("status__in", ("validating", "ready", "restoring", "verifying"))),
                        fields=("tenant_id", "target_ref"),
                        name="bdr_rr_active_target_uniq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DRStepExecution",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                            ("degraded", "Degraded"),
                            ("skipped", "Skipped"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempt", models.PositiveSmallIntegerField(default=1)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("async_job_id", models.UUIDField(blank=True, null=True)),
                ("provider_operation_id", models.CharField(blank=True, max_length=255)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("error_message", models.TextField(blank=True)),
                ("transition_history", models.JSONField(blank=True, default=list)),
                (
                    "exercise",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="step_executions",
                        to="backup_disaster_recovery.drexercise",
                    ),
                ),
                (
                    "runbook_step",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="executions",
                        to="backup_disaster_recovery.runbookstep",
                    ),
                ),
            ],
            options={
                "db_table": "bdr_step_executions",
                "indexes": [
                    models.Index(fields=["tenant_id", "exercise", "status"], name="bdr_se_tenant_ex_status_idx"),
                    models.Index(fields=["tenant_id", "runbook_step", "-created_at"], name="bdr_se_tenant_step_cr_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "exercise", "runbook_step", "attempt"),
                        name="bdr_se_attempt_uniq",
                    ),
                    models.CheckConstraint(condition=models.Q(("attempt__gt", 0)), name="bdr_se_attempt_positive"),
                ],
            },
        ),
    ]
