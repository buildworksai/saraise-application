"""Create the process-mining domain and quarantine the legacy scaffold."""

import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


RELATIONSHIPS = (
    ("process_mining_model_versions", "process_model_id", "process_mining_models"),
    ("process_mining_model_versions", "discovery_job_id", "process_mining_discovery_jobs"),
    ("process_mining_conformance_checks", "process_model_version_id", "process_mining_model_versions"),
    ("process_mining_conformance_deviations", "conformance_check_id", "process_mining_conformance_checks"),
    ("process_mining_conformance_case_metrics", "conformance_check_id", "process_mining_conformance_checks"),
    ("process_mining_bottleneck_findings", "analysis_id", "process_mining_bottleneck_analyses"),
    ("process_mining_variants", "analysis_id", "process_mining_bottleneck_analyses"),
)


def quarantine_legacy(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(r"""
        CREATE FUNCTION process_mining_legacy_reject_write() RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'legacy process mining resources are read-only' USING ERRCODE = '55000';
        END;
        $$;
        CREATE TRIGGER process_mining_legacy_read_only BEFORE INSERT OR UPDATE OR DELETE
        ON process_mining_resources FOR EACH ROW EXECUTE FUNCTION process_mining_legacy_reject_write();
    """)


def restore_legacy_writes(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS process_mining_legacy_read_only ON process_mining_resources; DROP FUNCTION IF EXISTS process_mining_legacy_reject_write();")


def install_same_tenant_guards(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(r"""
        CREATE FUNCTION process_mining_require_same_tenant() RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE parent_id UUID; parent_tenant UUID;
        BEGIN
            parent_id := (to_jsonb(NEW) ->> TG_ARGV[0])::UUID;
            IF parent_id IS NULL THEN RETURN NEW; END IF;
            EXECUTE format('SELECT tenant_id FROM %I WHERE id = $1', TG_ARGV[1]) INTO parent_tenant USING parent_id;
            IF parent_tenant IS NULL OR parent_tenant <> NEW.tenant_id THEN
                RAISE EXCEPTION 'cross-tenant process-mining relationship rejected' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    for child, column, parent in RELATIONSHIPS:
        trigger = f"pm_same_tenant_{column}_{child[-8:]}"
        schema_editor.execute(
            f"CREATE TRIGGER {schema_editor.quote_name(trigger)} BEFORE INSERT OR UPDATE OF tenant_id, "
            f"{schema_editor.quote_name(column)} ON {schema_editor.quote_name(child)} FOR EACH ROW "
            f"EXECUTE FUNCTION process_mining_require_same_tenant('{column}', '{parent}');"
        )


def remove_same_tenant_guards(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for child, column, _parent in reversed(RELATIONSHIPS):
        trigger = f"pm_same_tenant_{column}_{child[-8:]}"
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {schema_editor.quote_name(trigger)} ON {schema_editor.quote_name(child)};")
    schema_editor.execute("DROP FUNCTION IF EXISTS process_mining_require_same_tenant();")


def mutable_fields():
    return [
        ("tenant_id", models.UUIDField(db_index=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_by", models.UUIDField(db_index=True, editable=False)),
        ("is_deleted", models.BooleanField(db_index=True, default=False)),
        ("deleted_at", models.DateTimeField(blank=True, null=True)),
    ]


def append_fields():
    return [
        ("tenant_id", models.UUIDField(db_index=True)),
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_by", models.UUIDField(db_index=True, editable=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
    ]


ANALYSIS_CHOICES = [("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed"), ("timed_out", "Timed out"), ("cancelled", "Cancelled")]
EXPORT_CHOICES = [*ANALYSIS_CHOICES, ("expired", "Expired")]
ALGORITHM_CHOICES = [("alpha_miner", "Alpha miner"), ("heuristic_miner", "Heuristic miner"), ("inductive_miner", "Inductive miner")]


class Migration(migrations.Migration):
    dependencies = [("process_mining", "0001_initial")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(quarantine_legacy, restore_legacy_writes)],
            state_operations=[migrations.DeleteModel(name="ProcessMiningResource")],
        ),
        migrations.CreateModel(
            name="ProcessEvent",
            fields=[*append_fields(), ("process_name", models.CharField(max_length=255)), ("source_module", models.CharField(max_length=100)), ("source_event_id", models.CharField(blank=True, max_length=255, null=True)), ("case_id", models.CharField(max_length=255)), ("activity", models.CharField(max_length=255)), ("occurred_at", models.DateTimeField()), ("resource", models.CharField(blank=True, max_length=255, null=True)), ("attributes", models.JSONField(blank=True, default=dict)), ("ingested_at", models.DateTimeField(auto_now_add=True)), ("event_hash", models.CharField(max_length=64))],
            options={"db_table": "process_mining_events", "constraints": [models.UniqueConstraint(fields=("tenant_id", "event_hash"), name="pm_event_tenant_hash_uniq"), models.UniqueConstraint(condition=models.Q(("source_event_id__isnull", False), ~models.Q(("source_event_id", ""))), fields=("tenant_id", "source_module", "source_event_id"), name="pm_event_source_id_uniq")], "indexes": [models.Index(fields=["tenant_id", "process_name", "occurred_at"], name="pm_evt_process_time"), models.Index(fields=["tenant_id", "process_name", "case_id", "occurred_at"], name="pm_evt_case_time"), models.Index(fields=["tenant_id", "activity", "occurred_at"], name="pm_evt_activity_time"), models.Index(fields=["tenant_id", "resource", "occurred_at"], name="pm_evt_resource_time")]},
        ),
        migrations.CreateModel(
            name="EventExportJob",
            fields=[*mutable_fields(), ("process_name", models.CharField(max_length=255)), ("format", models.CharField(choices=[("xes", "XES"), ("csv", "CSV"), ("json", "JSON")], max_length=32)), ("event_filter", models.JSONField(default=dict)), ("status", models.CharField(choices=EXPORT_CHOICES, default="queued", max_length=24)), ("transition_history", models.JSONField(default=list, editable=False)), ("async_job_id", models.UUIDField(db_index=True, null=True, unique=True)), ("idempotency_key", models.CharField(max_length=255)), ("artifact_key", models.CharField(blank=True, max_length=1024)), ("content_type", models.CharField(blank=True, max_length=100)), ("row_count", models.PositiveBigIntegerField(null=True)), ("byte_size", models.PositiveBigIntegerField(null=True)), ("sha256", models.CharField(blank=True, max_length=64)), ("expires_at", models.DateTimeField(null=True)), ("completed_at", models.DateTimeField(null=True)), ("error_code", models.CharField(blank=True, max_length=100)), ("error_message", models.TextField(blank=True))],
            options={"db_table": "process_mining_export_jobs", "constraints": [models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="pm_export_idem_uniq")], "indexes": [models.Index(fields=["tenant_id", "status", "created_at"], name="pm_export_status_time"), models.Index(fields=["tenant_id", "process_name", "created_at"], name="pm_export_process_time")]},
        ),
        migrations.CreateModel(
            name="ProcessDiscoveryJob",
            fields=[*mutable_fields(), ("process_name", models.CharField(max_length=255)), ("algorithm", models.CharField(choices=ALGORITHM_CHOICES, max_length=160)), ("parameters", models.JSONField(default=dict)), ("status", models.CharField(choices=ANALYSIS_CHOICES, default="queued", max_length=24)), ("transition_history", models.JSONField(default=list, editable=False)), ("async_job_id", models.UUIDField(db_index=True, null=True, unique=True)), ("idempotency_key", models.CharField(max_length=255)), ("event_count", models.PositiveBigIntegerField(default=0)), ("case_count", models.PositiveBigIntegerField(default=0)), ("activity_count", models.PositiveBigIntegerField(default=0)), ("started_at", models.DateTimeField(null=True)), ("completed_at", models.DateTimeField(null=True)), ("error_code", models.CharField(blank=True, max_length=100)), ("error_message", models.TextField(blank=True))],
            options={"db_table": "process_mining_discovery_jobs", "constraints": [models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="pm_discovery_idem_uniq"), models.UniqueConstraint(condition=models.Q(("status__in", ["queued", "running"])), fields=("tenant_id", "process_name", "algorithm"), name="pm_discovery_active_uniq"), models.CheckConstraint(condition=models.Q(("event_count__gte", 0)), name="pm_disc_event_nonneg"), models.CheckConstraint(condition=models.Q(("case_count__gte", 0)), name="pm_disc_case_nonneg"), models.CheckConstraint(condition=models.Q(("activity_count__gte", 0)), name="pm_disc_activity_nonneg")], "indexes": [models.Index(fields=["tenant_id", "process_name", "status", "created_at"], name="pm_disc_status_time")]},
        ),
        migrations.CreateModel(
            name="ProcessModel",
            fields=[*mutable_fields(), ("name", models.CharField(max_length=255)), ("process_name", models.CharField(max_length=255)), ("description", models.TextField(blank=True)), ("source_kind", models.CharField(choices=[("discovered", "Discovered"), ("imported", "Imported")], max_length=24)), ("current_version_number", models.PositiveIntegerField(default=1)), ("reference_version_number", models.PositiveIntegerField(null=True))],
            options={"db_table": "process_mining_models", "constraints": [models.UniqueConstraint(condition=models.Q(("is_deleted", False)), fields=("tenant_id", "name"), name="pm_model_active_name_uniq"), models.CheckConstraint(condition=models.Q(("reference_version_number__isnull", True), ("reference_version_number__gt", 0), _connector="OR"), name="pm_model_ref_positive")], "indexes": [models.Index(fields=["tenant_id", "process_name", "created_at"], name="pm_model_process_time")]},
        ),
        migrations.CreateModel(
            name="BottleneckAnalysis",
            fields=[*mutable_fields(), ("process_name", models.CharField(max_length=255)), ("time_range_start", models.DateTimeField()), ("time_range_end", models.DateTimeField()), ("status", models.CharField(choices=ANALYSIS_CHOICES, default="queued", max_length=24)), ("transition_history", models.JSONField(default=list, editable=False)), ("async_job_id", models.UUIDField(db_index=True, null=True, unique=True)), ("idempotency_key", models.CharField(max_length=255)), ("total_cases", models.PositiveBigIntegerField(default=0)), ("total_variants", models.PositiveBigIntegerField(default=0)), ("avg_case_duration_seconds", models.DecimalField(decimal_places=2, max_digits=14, null=True)), ("started_at", models.DateTimeField(null=True)), ("completed_at", models.DateTimeField(null=True)), ("error_code", models.CharField(blank=True, max_length=100)), ("error_message", models.TextField(blank=True))],
            options={"db_table": "process_mining_bottleneck_analyses", "constraints": [models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="pm_bneck_idem_uniq"), models.CheckConstraint(condition=models.Q(("time_range_end__gt", models.F("time_range_start"))), name="pm_bneck_time_order")], "indexes": [models.Index(fields=["tenant_id", "process_name", "status", "created_at"], name="pm_bneck_status_time")]},
        ),
        migrations.CreateModel(
            name="ProcessModelVersion",
            fields=[*append_fields(), ("version", models.PositiveIntegerField()), ("algorithm", models.CharField(blank=True, choices=ALGORITHM_CHOICES, max_length=160, null=True)), ("parameters", models.JSONField(blank=True, default=dict)), ("model_data", models.JSONField()), ("event_count", models.PositiveBigIntegerField(default=0)), ("case_count", models.PositiveBigIntegerField(default=0)), ("activity_count", models.PositiveBigIntegerField(default=0)), ("avg_case_duration_seconds", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)), ("is_reference", models.BooleanField(default=False)), ("published_at", models.DateTimeField()), ("discovery_job", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="model_versions", to="process_mining.processdiscoveryjob")), ("process_model", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="process_mining.processmodel"))],
            options={"db_table": "process_mining_model_versions", "constraints": [models.UniqueConstraint(fields=("tenant_id", "process_model", "version"), name="pm_model_version_uniq"), models.UniqueConstraint(condition=models.Q(("is_reference", True)), fields=("tenant_id", "process_model"), name="pm_model_reference_uniq"), models.CheckConstraint(condition=models.Q(("event_count__gte", 0)), name="pm_ver_event_nonneg"), models.CheckConstraint(condition=models.Q(("case_count__gte", 0)), name="pm_ver_case_nonneg"), models.CheckConstraint(condition=models.Q(("activity_count__gte", 0)), name="pm_ver_activity_nonneg"), models.CheckConstraint(condition=models.Q(("avg_case_duration_seconds__isnull", True), ("avg_case_duration_seconds__gte", 0), _connector="OR"), name="pm_ver_duration_nonneg")], "indexes": [models.Index(fields=["tenant_id", "process_model", "published_at"], name="pm_version_model_time")]},
        ),
        migrations.CreateModel(
            name="ConformanceCheck",
            fields=[*mutable_fields(), ("event_filter", models.JSONField(default=dict)), ("status", models.CharField(choices=ANALYSIS_CHOICES, default="queued", max_length=24)), ("transition_history", models.JSONField(default=list, editable=False)), ("async_job_id", models.UUIDField(db_index=True, null=True, unique=True)), ("idempotency_key", models.CharField(max_length=255)), ("fitness", models.DecimalField(decimal_places=4, max_digits=5, null=True)), ("precision", models.DecimalField(decimal_places=4, max_digits=5, null=True)), ("generalization", models.DecimalField(decimal_places=4, max_digits=5, null=True)), ("total_cases", models.PositiveBigIntegerField(null=True)), ("conformant_cases", models.PositiveBigIntegerField(null=True)), ("deviating_cases", models.PositiveBigIntegerField(null=True)), ("started_at", models.DateTimeField(null=True)), ("completed_at", models.DateTimeField(null=True)), ("error_code", models.CharField(blank=True, max_length=100)), ("error_message", models.TextField(blank=True)), ("process_model_version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="checks", to="process_mining.processmodelversion"))],
            options={"db_table": "process_mining_conformance_checks", "constraints": [models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="pm_conf_idem_uniq"), models.UniqueConstraint(condition=models.Q(("status__in", ["queued", "running"])), fields=("tenant_id", "process_model_version"), name="pm_conf_active_uniq"), *[models.CheckConstraint(condition=models.Q((f"{field}__isnull", True), models.Q((f"{field}__gte", Decimal("0")), (f"{field}__lte", Decimal("1"))), _connector="OR"), name=f"pm_conf_{field}_range") for field in ("fitness", "precision", "generalization")], models.CheckConstraint(condition=models.Q(models.Q(("status", "completed"), _negated=True), ("total_cases", models.F("conformant_cases") + models.F("deviating_cases")), _connector="OR"), name="pm_conf_case_totals")], "indexes": [models.Index(fields=["tenant_id", "process_model_version", "status", "created_at"], name="pm_conf_status_time")]},
        ),
        migrations.CreateModel(
            name="ConformanceDeviation",
            fields=[*append_fields(), ("case_id", models.CharField(max_length=255)), ("deviation_type", models.CharField(choices=[("missing_activity", "Missing activity"), ("unexpected_activity", "Unexpected activity"), ("wrong_order", "Wrong order"), ("skipped_path", "Skipped path")], max_length=32)), ("expected", models.CharField(blank=True, max_length=255)), ("actual", models.CharField(blank=True, max_length=255)), ("position", models.PositiveIntegerField(null=True)), ("description", models.TextField(blank=True)), ("conformance_check", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="deviations", to="process_mining.conformancecheck"))],
            options={"db_table": "process_mining_conformance_deviations", "constraints": [models.UniqueConstraint(fields=("tenant_id", "conformance_check", "case_id", "position", "deviation_type"), name="pm_deviation_evidence_uniq")], "indexes": [models.Index(fields=["tenant_id", "conformance_check", "deviation_type"], name="pm_dev_check_type"), models.Index(fields=["tenant_id", "case_id"], name="pm_dev_case")]},
        ),
        migrations.CreateModel(
            name="ConformanceCaseMetric",
            fields=[*append_fields(), ("case_id", models.CharField(max_length=255)), ("fitness", models.DecimalField(decimal_places=4, max_digits=5)), ("is_conformant", models.BooleanField()), ("deviation_count", models.PositiveIntegerField()), ("trace_length", models.PositiveIntegerField()), ("conformance_check", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="case_metrics", to="process_mining.conformancecheck"))],
            options={"db_table": "process_mining_conformance_case_metrics", "constraints": [models.UniqueConstraint(fields=("tenant_id", "conformance_check", "case_id"), name="pm_case_metric_uniq"), models.CheckConstraint(condition=models.Q(("fitness__gte", Decimal("0")), ("fitness__lte", Decimal("1"))), name="pm_case_fitness_range")], "indexes": [models.Index(fields=["tenant_id", "conformance_check", "fitness"], name="pm_case_fit_check")]},
        ),
        migrations.CreateModel(
            name="BottleneckFinding",
            fields=[*append_fields(), ("from_activity", models.CharField(max_length=255)), ("to_activity", models.CharField(max_length=255)), ("avg_duration_seconds", models.DecimalField(decimal_places=2, max_digits=14)), ("median_duration_seconds", models.DecimalField(decimal_places=2, max_digits=14)), ("p95_duration_seconds", models.DecimalField(decimal_places=2, max_digits=14)), ("case_count", models.PositiveBigIntegerField()), ("severity", models.CharField(choices=[("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low")], max_length=16)), ("resource_bottleneck", models.CharField(blank=True, max_length=255)), ("rank", models.PositiveIntegerField()), ("analysis", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="findings", to="process_mining.bottleneckanalysis"))],
            options={"db_table": "process_mining_bottleneck_findings", "constraints": [models.UniqueConstraint(fields=("tenant_id", "analysis", "from_activity", "to_activity"), name="pm_find_transition_uniq"), models.UniqueConstraint(fields=("tenant_id", "analysis", "rank"), name="pm_find_rank_uniq"), models.CheckConstraint(condition=models.Q(("avg_duration_seconds__gte", 0)), name="pm_find_avg_nonneg"), models.CheckConstraint(condition=models.Q(("median_duration_seconds__gte", 0)), name="pm_find_median_nonneg"), models.CheckConstraint(condition=models.Q(("p95_duration_seconds__gte", 0)), name="pm_find_p95_nonneg")], "indexes": [models.Index(fields=["tenant_id", "analysis", "severity", "rank"], name="pm_find_severity_rank")]},
        ),
        migrations.CreateModel(
            name="ProcessVariant",
            fields=[*append_fields(), ("variant_key", models.CharField(max_length=64)), ("activities", models.JSONField()), ("case_count", models.PositiveBigIntegerField()), ("percentage", models.DecimalField(decimal_places=4, max_digits=7)), ("avg_duration_seconds", models.DecimalField(decimal_places=2, max_digits=14)), ("is_happy_path", models.BooleanField(default=False)), ("is_grouped_other", models.BooleanField(default=False)), ("analysis", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="variants", to="process_mining.bottleneckanalysis"))],
            options={"db_table": "process_mining_variants", "constraints": [models.UniqueConstraint(fields=("tenant_id", "analysis", "variant_key"), name="pm_variant_key_uniq"), models.UniqueConstraint(condition=models.Q(("is_happy_path", True)), fields=("tenant_id", "analysis"), name="pm_variant_happy_uniq"), models.CheckConstraint(condition=models.Q(("percentage__gte", 0), ("percentage__lte", 100)), name="pm_variant_pct_range"), models.CheckConstraint(condition=models.Q(("avg_duration_seconds__gte", 0)), name="pm_variant_duration_nonneg")], "indexes": [models.Index(fields=["tenant_id", "analysis", "case_count"], name="pm_variant_case_count")]},
        ),
        migrations.RunPython(install_same_tenant_guards, remove_same_tenant_guards),
    ]
