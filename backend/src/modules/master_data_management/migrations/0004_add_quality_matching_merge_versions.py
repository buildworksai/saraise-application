"""Create quality, matching, immutable version, and merge evidence tables."""

import decimal
import uuid

import django.db.models.deletion
from django.db import migrations, models


ENTITY_STATUS = [("active", "Active"), ("pending_review", "Pending review"), ("merged", "Merged"), ("archived", "Archived")]
DIMENSIONS = [
    ("completeness", "Completeness"), ("accuracy", "Accuracy"), ("consistency", "Consistency"),
    ("timeliness", "Timeliness"), ("uniqueness", "Uniqueness"), ("conformity", "Conformity"),
]
SEVERITIES = [("info", "Info"), ("warning", "Warning"), ("error", "Error"), ("critical", "Critical")]
INITIAL_VERSION_CORRELATION = "migration-0004-initial-version"


def backfill_initial_versions(apps, schema_editor):
    Entity = apps.get_model("master_data_management", "MasterDataEntity")
    Version = apps.get_model("master_data_management", "MasterDataVersion")
    alias = schema_editor.connection.alias
    for entity in Entity.objects.using(alias).order_by("tenant_id", "id").iterator():
        Version.objects.using(alias).get_or_create(
            tenant_id=entity.tenant_id,
            entity_id=entity.pk,
            version_number=entity.version,
            defaults={
                "entity_type_key": entity.entity_type,
                "entity_code": entity.entity_code,
                "entity_name": entity.entity_name,
                "data_snapshot": entity.data,
                "status_snapshot": entity.status,
                "quality_score_snapshot": entity.quality_score,
                "changed_fields": ["entity_code", "entity_name", "data"],
                "change_reason": "Initial version created during MDM migration.",
                "changed_by": entity.created_by,
                "correlation_id": INITIAL_VERSION_CORRELATION,
            },
        )


def remove_backfilled_initial_versions(apps, schema_editor):
    Version = apps.get_model("master_data_management", "MasterDataVersion")
    Version.objects.using(schema_editor.connection.alias).filter(
        correlation_id=INITIAL_VERSION_CORRELATION,
        change_reason="Initial version created during MDM migration.",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("master_data_management", "0003_backfill_entity_types")]

    operations = [
        migrations.CreateModel(
            name="MasterDataVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version_number", models.PositiveIntegerField()),
                ("entity_type_key", models.CharField(max_length=64)),
                ("entity_code", models.CharField(max_length=100)),
                ("entity_name", models.CharField(max_length=255)),
                ("data_snapshot", models.JSONField()),
                ("status_snapshot", models.CharField(choices=ENTITY_STATUS, max_length=24)),
                ("quality_score_snapshot", models.DecimalField(decimal_places=2, max_digits=5)),
                ("changed_fields", models.JSONField(blank=True, default=list)),
                ("change_reason", models.CharField(max_length=255)),
                ("changed_by", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=64)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="master_data_management.masterdataentity")),
            ],
            options={
                "db_table": "mdm_entity_versions",
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "entity", "version_number"), name="mdm_version_entity_number_uniq"),
                    models.CheckConstraint(condition=models.Q(("version_number__gte", 1)), name="mdm_version_number_gte_1_ck"),
                    models.CheckConstraint(condition=models.Q(("quality_score_snapshot__gte", decimal.Decimal("0.00")), ("quality_score_snapshot__lte", decimal.Decimal("100.00"))), name="mdm_version_quality_0_100_ck"),
                ],
                "indexes": [models.Index(fields=["tenant_id", "entity", "-version_number"], name="mdm_version_entity_desc_idx")],
            },
        ),
        migrations.CreateModel(
            name="DataQualityRule",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)), ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)), ("updated_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("is_deleted", models.BooleanField(default=False, editable=False)), ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("name", models.CharField(max_length=120)), ("field_path", models.CharField(blank=True, default="", max_length=255)),
                ("rule_type", models.CharField(choices=[("required", "Required"), ("format", "Format"), ("range", "Range"), ("uniqueness", "Uniqueness"), ("referential", "Referential"), ("timeliness", "Timeliness")], max_length=20)),
                ("configuration", models.JSONField(blank=True, default=dict)), ("dimension", models.CharField(choices=DIMENSIONS, max_length=20)),
                ("severity", models.CharField(choices=SEVERITIES, max_length=12)),
                ("weight", models.DecimalField(decimal_places=4, default=decimal.Decimal("1.0000"), max_digits=7)),
                ("is_active", models.BooleanField(default=True)),
                ("entity_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="quality_rules", to="master_data_management.masterentitytype")),
            ],
            options={
                "db_table": "mdm_quality_rules",
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("is_deleted", False)), fields=("tenant_id", "entity_type", "name"), name="mdm_quality_rule_live_name_uniq"),
                    models.CheckConstraint(condition=models.Q(("weight__gt", 0)), name="mdm_quality_rule_weight_gt_0_ck"),
                ],
                "indexes": [models.Index(fields=["tenant_id", "entity_type", "is_active"], name="mdm_quality_rule_active_idx")],
            },
        ),
        migrations.CreateModel(
            name="DataQualityIssue",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)), ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)), ("updated_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("field_path", models.CharField(blank=True, default="", max_length=255)), ("dimension", models.CharField(choices=DIMENSIONS, max_length=20)),
                ("severity", models.CharField(choices=SEVERITIES, max_length=12)), ("message", models.CharField(max_length=500)),
                ("evidence", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("open", "Open"), ("in_review", "In review"), ("resolved", "Resolved"), ("waived", "Waived")], default="open", editable=False, max_length=16)),
                ("assigned_to", models.UUIDField(blank=True, null=True)), ("resolution", models.TextField(blank=True, default="", editable=False)),
                ("resolved_by", models.UUIDField(blank=True, editable=False, null=True)), ("resolved_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("transition_history", models.JSONField(blank=True, default=list, editable=False)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="quality_issues", to="master_data_management.masterdataentity")),
                ("rule", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="issues", to="master_data_management.dataqualityrule")),
            ],
            options={
                "db_table": "mdm_quality_issues",
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("rule__isnull", False), ("status", "open")), fields=("tenant_id", "entity", "rule", "field_path"), name="mdm_issue_open_rule_field_uniq"),
                    models.UniqueConstraint(condition=models.Q(("rule__isnull", True), ("status", "open")), fields=("tenant_id", "entity", "field_path"), name="mdm_issue_open_null_rule_uniq"),
                    models.CheckConstraint(condition=(models.Q(("resolution", ""), ("resolved_at__isnull", True), ("resolved_by__isnull", True), ("status__in", ("open", "in_review"))) | (models.Q(("resolved_at__isnull", False), ("resolved_by__isnull", False), ("status__in", ("resolved", "waived"))) & ~models.Q(("resolution", "")))), name="mdm_issue_resolution_state_ck"),
                ],
                "indexes": [
                    models.Index(fields=["tenant_id", "status", "severity", "created_at"], name="mdm_issue_status_severity_idx"),
                    models.Index(fields=["tenant_id", "entity", "status"], name="mdm_issue_entity_status_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MatchingRule",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)), ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)), ("updated_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("is_deleted", models.BooleanField(default=False, editable=False)), ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("name", models.CharField(max_length=120)),
                ("algorithm", models.CharField(choices=[("exact", "Exact"), ("normalized", "Normalized"), ("fuzzy", "Fuzzy"), ("phonetic", "Phonetic")], max_length=16)),
                ("field_weights", models.JSONField(default=dict)), ("blocking_fields", models.JSONField(blank=True, default=list)),
                ("review_threshold", models.DecimalField(decimal_places=4, max_digits=5)), ("auto_confirm_threshold", models.DecimalField(decimal_places=4, max_digits=5)),
                ("is_active", models.BooleanField(default=True)),
                ("entity_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matching_rules", to="master_data_management.masterentitytype")),
            ],
            options={
                "db_table": "mdm_matching_rules",
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("is_deleted", False)), fields=("tenant_id", "entity_type", "name"), name="mdm_matching_rule_live_name_uniq"),
                    models.CheckConstraint(condition=models.Q(("review_threshold__gte", 0), ("review_threshold__lte", 1)), name="mdm_match_review_threshold_ck"),
                    models.CheckConstraint(condition=models.Q(("auto_confirm_threshold__gte", 0), ("auto_confirm_threshold__lte", 1)), name="mdm_match_confirm_threshold_ck"),
                    models.CheckConstraint(condition=models.Q(("review_threshold__lte", models.F("auto_confirm_threshold"))), name="mdm_match_threshold_order_ck"),
                ],
                "indexes": [models.Index(fields=["tenant_id", "entity_type", "is_active"], name="mdm_matching_rule_active_idx")],
            },
        ),
        migrations.CreateModel(
            name="MergeHistory",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)), ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("status", models.CharField(choices=[("applied", "Applied"), ("reversed", "Reversed")], default="applied", editable=False, max_length=12)),
                ("survivorship_policy", models.JSONField(default=dict)), ("golden_snapshot_before", models.JSONField(default=dict)), ("golden_snapshot_after", models.JSONField(default=dict)),
                ("reason", models.TextField()), ("merged_by", models.UUIDField()), ("reversed_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("reversed_at", models.DateTimeField(blank=True, editable=False, null=True)), ("reversal_reason", models.TextField(blank=True, default="", editable=False)),
                ("idempotency_key", models.CharField(max_length=255)), ("correlation_id", models.CharField(max_length=64)),
                ("transition_history", models.JSONField(blank=True, default=list, editable=False)),
                ("golden_record", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="merge_histories", to="master_data_management.masterdataentity")),
            ],
            options={
                "db_table": "mdm_merge_history",
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="mdm_merge_idempotency_uniq"),
                    models.CheckConstraint(condition=(models.Q(("reversal_reason", ""), ("reversed_at__isnull", True), ("reversed_by__isnull", True), ("status", "applied")) | (models.Q(("reversed_at__isnull", False), ("reversed_by__isnull", False), ("status", "reversed")) & ~models.Q(("reversal_reason", "")))), name="mdm_merge_reversal_state_ck"),
                ],
                "indexes": [
                    models.Index(fields=["tenant_id", "golden_record", "-created_at"], name="mdm_merge_golden_created_idx"),
                    models.Index(fields=["tenant_id", "status", "-created_at"], name="mdm_merge_status_created_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MatchCandidate",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("created_by", models.UUIDField(editable=False)),
                ("updated_by", models.UUIDField(blank=True, editable=False, null=True)), ("confidence", models.DecimalField(decimal_places=4, max_digits=5)),
                ("field_scores", models.JSONField(default=dict)), ("evidence", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("confirmed", "Confirmed"), ("rejected", "Rejected"), ("merged", "Merged")], default="pending", editable=False, max_length=16)),
                ("reviewed_by", models.UUIDField(blank=True, editable=False, null=True)), ("reviewed_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("review_note", models.TextField(blank=True, default="", editable=False)), ("transition_history", models.JSONField(blank=True, default=list, editable=False)),
                ("left_entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matches_as_left", to="master_data_management.masterdataentity")),
                ("right_entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matches_as_right", to="master_data_management.masterdataentity")),
                ("matching_rule", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="candidates", to="master_data_management.matchingrule")),
                ("merge_history", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidates", to="master_data_management.mergehistory")),
            ],
            options={
                "db_table": "mdm_match_candidates",
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("left_entity_id__lt", models.F("right_entity_id"))), name="mdm_candidate_canonical_order_ck"),
                    models.UniqueConstraint(fields=("tenant_id", "matching_rule", "left_entity", "right_entity"), name="mdm_candidate_pair_uniq"),
                    models.CheckConstraint(condition=models.Q(("confidence__gte", 0), ("confidence__lte", 1)), name="mdm_candidate_confidence_ck"),
                    models.CheckConstraint(condition=(models.Q(("reviewed_at__isnull", True), ("reviewed_by__isnull", True), ("status", "pending")) | models.Q(("reviewed_at__isnull", False), ("reviewed_by__isnull", False), ("status__in", ("confirmed", "rejected", "merged")))), name="mdm_candidate_review_state_ck"),
                    models.CheckConstraint(condition=models.Q(("merge_history__isnull", False), ("status", "merged")) | ~models.Q(("status", "merged")), name="mdm_candidate_merged_history_ck"),
                ],
                "indexes": [
                    models.Index(fields=["tenant_id", "status", "-confidence"], name="mdm_candidate_status_score_idx"),
                    models.Index(fields=["tenant_id", "left_entity", "right_entity"], name="mdm_candidate_pair_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MergeParticipant",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)), ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("source_version", models.PositiveIntegerField()),
                ("source_snapshot", models.JSONField()), ("role", models.CharField(choices=[("survivor", "Survivor"), ("merged_source", "Merged source")], max_length=16)),
                ("merge_history", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="master_data_management.mergehistory")),
                ("source_entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="merge_participations", to="master_data_management.masterdataentity")),
            ],
            options={
                "db_table": "mdm_merge_participants",
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "merge_history", "source_entity"), name="mdm_participant_source_uniq"),
                    models.UniqueConstraint(condition=models.Q(("role", "survivor")), fields=("tenant_id", "merge_history"), name="mdm_participant_one_survivor_uniq"),
                    models.CheckConstraint(condition=models.Q(("source_version__gte", 1)), name="mdm_participant_version_gte_1_ck"),
                ],
                "indexes": [models.Index(fields=["tenant_id", "source_entity", "-created_at"], name="mdm_participant_source_idx")],
            },
        ),
        migrations.RunPython(backfill_initial_versions, remove_backfilled_initial_versions),
    ]
