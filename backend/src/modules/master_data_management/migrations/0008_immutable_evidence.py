"""Add immutable rule versions, evidence guards, and merge-reversal evidence."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

MIGRATION_CORRELATION_ID = "migration-0008-immutable-evidence"
NEW_TENANT_TABLES = (
    "mdm_quality_rule_versions",
    "mdm_matching_rule_versions",
    "mdm_merge_reversals",
)
APPEND_ONLY_TABLES = (*NEW_TENANT_TABLES, "mdm_merge_history")


def _quality_snapshot(rule):
    return {
        "entity_type_id": str(rule.entity_type_id),
        "name": rule.name,
        "field_path": rule.field_path,
        "rule_type": rule.rule_type,
        "configuration": rule.configuration,
        "dimension": rule.dimension,
        "severity": rule.severity,
        "weight": str(rule.weight),
        "is_active": rule.is_active,
        "is_deleted": rule.is_deleted,
    }


def _matching_snapshot(rule):
    return {
        "entity_type_id": str(rule.entity_type_id),
        "name": rule.name,
        "algorithm": rule.algorithm,
        "field_weights": rule.field_weights,
        "blocking_fields": rule.blocking_fields,
        "review_threshold": str(rule.review_threshold),
        "auto_confirm_threshold": str(rule.auto_confirm_threshold),
        "is_active": rule.is_active,
        "is_deleted": rule.is_deleted,
    }


def backfill_immutable_evidence(apps, schema_editor):
    QualityRule = apps.get_model("master_data_management", "DataQualityRule")
    QualityVersion = apps.get_model("master_data_management", "DataQualityRuleVersion")
    MatchingRule = apps.get_model("master_data_management", "MatchingRule")
    MatchingVersion = apps.get_model("master_data_management", "MatchingRuleVersion")
    MergeHistory = apps.get_model("master_data_management", "MergeHistory")
    MergeParticipant = apps.get_model("master_data_management", "MergeParticipant")
    MergeReversal = apps.get_model("master_data_management", "MergeReversal")
    alias = schema_editor.connection.alias

    for rule in QualityRule.objects.using(alias).order_by("tenant_id", "id").iterator():
        QualityVersion.objects.using(alias).create(
            tenant_id=rule.tenant_id,
            rule_id=rule.pk,
            version_number=1,
            snapshot=_quality_snapshot(rule),
            changed_by=rule.updated_by or rule.created_by,
            correlation_id=MIGRATION_CORRELATION_ID,
            change_reason="Initial immutable snapshot created during migration.",
        )
    for rule in MatchingRule.objects.using(alias).order_by("tenant_id", "id").iterator():
        MatchingVersion.objects.using(alias).create(
            tenant_id=rule.tenant_id,
            rule_id=rule.pk,
            version_number=1,
            snapshot=_matching_snapshot(rule),
            changed_by=rule.updated_by or rule.created_by,
            correlation_id=MIGRATION_CORRELATION_ID,
            change_reason="Initial immutable snapshot created during migration.",
        )

    reversed_merges = MergeHistory.objects.using(alias).filter(status="reversed").order_by("tenant_id", "id")
    for merge in reversed_merges.iterator():
        participant_versions = {
            str(row["source_entity_id"]): row["source_version"] + 1
            for row in MergeParticipant.objects.using(alias)
            .filter(merge_history_id=merge.pk)
            .values("source_entity_id", "source_version")
        }
        reversal = MergeReversal.objects.using(alias).create(
            tenant_id=merge.tenant_id,
            merge_history_id=merge.pk,
            reversed_by=merge.reversed_by,
            reason=merge.reversal_reason,
            correlation_id=merge.correlation_id or MIGRATION_CORRELATION_ID,
            transition_key=f"migration-0008:{merge.pk}",
            participant_versions=participant_versions,
        )
        if merge.reversed_at is not None:
            MergeReversal.objects.using(alias).filter(pk=reversal.pk).update(created_at=merge.reversed_at)
        MergeHistory.objects.using(alias).filter(pk=merge.pk).update(
            status="applied",
            reversed_by=None,
            reversed_at=None,
            reversal_reason="",
            transition_history=[],
        )


def restore_legacy_reversal_fields(apps, schema_editor):
    QualityVersion = apps.get_model("master_data_management", "DataQualityRuleVersion")
    MatchingVersion = apps.get_model("master_data_management", "MatchingRuleVersion")
    MergeHistory = apps.get_model("master_data_management", "MergeHistory")
    MergeReversal = apps.get_model("master_data_management", "MergeReversal")
    alias = schema_editor.connection.alias
    for reversal in MergeReversal.objects.using(alias).select_related("merge_history").iterator():
        MergeHistory.objects.using(alias).filter(pk=reversal.merge_history_id).update(
            status="reversed",
            reversed_by=reversal.reversed_by,
            reversed_at=reversal.created_at,
            reversal_reason=reversal.reason,
            transition_history=[
                {
                    "transition_key": reversal.transition_key,
                    "command": "reverse",
                    "from_state": "applied",
                    "to_state": "reversed",
                    "occurred_at": reversal.created_at.isoformat(),
                    "metadata": {"correlation_id": reversal.correlation_id},
                }
            ],
        )
    QualityVersion.objects.using(alias).filter(correlation_id=MIGRATION_CORRELATION_ID).delete()
    MatchingVersion.objects.using(alias).filter(correlation_id=MIGRATION_CORRELATION_ID).delete()


def enable_new_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in NEW_TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_new_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    for table_name in reversed(NEW_TENANT_TABLES):
        table = quote(table_name)
        policy = quote(f"tenant_isolation_{table_name}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


def create_immutability_triggers(apps, schema_editor):
    del apps
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        schema_editor.execute("""
            CREATE OR REPLACE FUNCTION mdm_reject_immutable_evidence_change()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'immutable MDM evidence cannot be changed';
            END;
            $$;
            """)
        for table_name in APPEND_ONLY_TABLES:
            schema_editor.execute(f"""
                CREATE TRIGGER {table_name}_append_only
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION mdm_reject_immutable_evidence_change();
                """)
        schema_editor.execute("""
            CREATE OR REPLACE FUNCTION mdm_reject_quality_issue_evidence_change()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.evidence IS DISTINCT FROM OLD.evidence THEN
                    RAISE EXCEPTION 'quality issue evidence is immutable';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER mdm_quality_issue_evidence_immutable
            BEFORE UPDATE ON mdm_quality_issues
            FOR EACH ROW EXECUTE FUNCTION mdm_reject_quality_issue_evidence_change();
            """)
        schema_editor.execute("""
            CREATE OR REPLACE FUNCTION mdm_reject_match_candidate_evidence_change()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.evidence IS DISTINCT FROM OLD.evidence
                   OR NEW.field_scores IS DISTINCT FROM OLD.field_scores THEN
                    RAISE EXCEPTION 'match candidate evidence is immutable';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER mdm_match_candidate_evidence_immutable
            BEFORE UPDATE ON mdm_match_candidates
            FOR EACH ROW EXECUTE FUNCTION mdm_reject_match_candidate_evidence_change();
            """)
    elif vendor == "sqlite":
        for table_name in APPEND_ONLY_TABLES:
            schema_editor.execute(f"""
                CREATE TRIGGER {table_name}_append_only_update
                BEFORE UPDATE ON {table_name}
                BEGIN SELECT RAISE(ABORT, 'immutable MDM evidence cannot be changed'); END;
                """)
        schema_editor.execute("""
            CREATE TRIGGER mdm_quality_issue_evidence_immutable
            BEFORE UPDATE OF evidence ON mdm_quality_issues
            BEGIN SELECT RAISE(ABORT, 'quality issue evidence is immutable'); END;
            """)
        schema_editor.execute("""
            CREATE TRIGGER mdm_match_candidate_evidence_immutable
            BEFORE UPDATE OF evidence, field_scores ON mdm_match_candidates
            BEGIN SELECT RAISE(ABORT, 'match candidate evidence is immutable'); END;
            """)


def drop_immutability_triggers(apps, schema_editor):
    del apps
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        for table_name in APPEND_ONLY_TABLES:
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only ON {table_name};")
        schema_editor.execute("DROP TRIGGER IF EXISTS mdm_quality_issue_evidence_immutable ON mdm_quality_issues;")
        schema_editor.execute("DROP TRIGGER IF EXISTS mdm_match_candidate_evidence_immutable ON mdm_match_candidates;")
        schema_editor.execute("DROP FUNCTION IF EXISTS mdm_reject_immutable_evidence_change();")
        schema_editor.execute("DROP FUNCTION IF EXISTS mdm_reject_quality_issue_evidence_change();")
        schema_editor.execute("DROP FUNCTION IF EXISTS mdm_reject_match_candidate_evidence_change();")
    elif vendor == "sqlite":
        for table_name in APPEND_ONLY_TABLES:
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only_update;")
        schema_editor.execute("DROP TRIGGER IF EXISTS mdm_quality_issue_evidence_immutable;")
        schema_editor.execute("DROP TRIGGER IF EXISTS mdm_match_candidate_evidence_immutable;")


class Migration(migrations.Migration):
    dependencies = [("master_data_management", "0007_enable_domain_rls")]

    operations = [
        migrations.CreateModel(
            name="DataQualityRuleVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version_number", models.PositiveIntegerField()),
                ("snapshot", models.JSONField()),
                ("changed_by", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=64)),
                ("change_reason", models.CharField(max_length=255)),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="master_data_management.dataqualityrule",
                    ),
                ),
            ],
            options={
                "db_table": "mdm_quality_rule_versions",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "rule", "version_number"),
                        name="mdm_quality_rule_version_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("version_number__gte", 1)),
                        name="mdm_quality_rule_version_gte_1_ck",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "rule", "-version_number"],
                        name="mdm_quality_rule_version_idx",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="MatchingRuleVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version_number", models.PositiveIntegerField()),
                ("snapshot", models.JSONField()),
                ("changed_by", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=64)),
                ("change_reason", models.CharField(max_length=255)),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="master_data_management.matchingrule",
                    ),
                ),
            ],
            options={
                "db_table": "mdm_matching_rule_versions",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "rule", "version_number"),
                        name="mdm_matching_rule_version_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("version_number__gte", 1)),
                        name="mdm_matching_rule_version_gte_1_ck",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "rule", "-version_number"],
                        name="mdm_matching_rule_version_idx",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="MergeReversal",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reversed_by", models.UUIDField()),
                ("reason", models.TextField()),
                ("correlation_id", models.CharField(max_length=64)),
                ("transition_key", models.CharField(max_length=255)),
                ("participant_versions", models.JSONField(blank=True)),
                (
                    "merge_history",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversal",
                        to="master_data_management.mergehistory",
                    ),
                ),
            ],
            options={
                "db_table": "mdm_merge_reversals",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "transition_key"),
                        name="mdm_merge_reversal_transition_uniq",
                    )
                ],
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "-created_at"],
                        name="mdm_merge_reversal_created_idx",
                    )
                ],
            },
        ),
        migrations.RunPython(backfill_immutable_evidence, restore_legacy_reversal_fields),
        migrations.RunPython(enable_new_rls, disable_new_rls),
        migrations.RunPython(create_immutability_triggers, drop_immutability_triggers),
    ]
