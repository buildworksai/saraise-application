"""Forward/reverse migration and PostgreSQL tenant-policy proofs."""

from __future__ import annotations

import importlib
import uuid

import pytest
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

INITIAL = ("email_marketing", "0001_initial")
LATEST = ("email_marketing", "0007_tenant_configured_model_defaults")


def _migrate(target: tuple[str, str]):
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


@pytest.mark.django_db(transaction=True)
def test_legacy_data_survives_forward_reverse_and_forward_again() -> None:
    """Map both legacy sent spellings and every template-reference case losslessly."""

    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    same_template_id = uuid.uuid4()
    cross_template_id = uuid.uuid4()
    unmatched_template_id = uuid.uuid4()
    completed_campaign_id = uuid.uuid4()
    sent_campaign_id = uuid.uuid4()
    scheduled_campaign_id = uuid.uuid4()
    sent_at = timezone.now()

    try:
        old_apps = _migrate(INITIAL)
        OldTemplate = old_apps.get_model("email_marketing", "EmailTemplate")
        OldCampaign = old_apps.get_model("email_marketing", "EmailCampaign")
        OldTemplate.objects.create(
            id=same_template_id,
            tenant_id=tenant_a,
            template_code="ACTIVE",
            template_name="Active",
            subject="Active",
            body_html="<p>Active</p>",
            is_active=True,
        )
        OldTemplate.objects.create(
            id=cross_template_id,
            tenant_id=tenant_b,
            template_code="ARCHIVED",
            template_name="Archived",
            subject="Archived",
            body_html="<p>Archived</p>",
            is_active=False,
        )
        OldCampaign.objects.create(
            id=completed_campaign_id,
            tenant_id=tenant_a,
            campaign_code="COMPLETED",
            campaign_name="Completed",
            subject="Completed",
            template_id=same_template_id,
            status="completed",
            sent_at=sent_at,
            recipient_count=3,
        )
        OldCampaign.objects.create(
            id=sent_campaign_id,
            tenant_id=tenant_a,
            campaign_code="SENT",
            campaign_name="Sent",
            subject="Sent",
            template_id=cross_template_id,
            status="sent",
            sent_at=sent_at,
            recipient_count=2,
        )
        OldCampaign.objects.create(
            id=scheduled_campaign_id,
            tenant_id=tenant_a,
            campaign_code="SCHEDULED",
            campaign_name="Scheduled",
            subject="Scheduled",
            template_id=unmatched_template_id,
            status="scheduled",
            scheduled_at=sent_at,
            recipient_count=1,
        )

        new_apps = _migrate(LATEST)
        Campaign = new_apps.get_model("email_marketing", "EmailCampaign")
        Template = new_apps.get_model("email_marketing", "EmailTemplate")
        RegistryEntry = new_apps.get_model("core", "ModuleRegistryEntry")

        completed = Campaign.objects.get(pk=completed_campaign_id)
        sent = Campaign.objects.get(pk=sent_campaign_id)
        scheduled = Campaign.objects.get(pk=scheduled_campaign_id)
        assert completed.status == "sent"
        assert completed.template_id == same_template_id
        assert completed.legacy_template_id == same_template_id
        assert completed.resolved_recipient_count == 3
        assert completed.sent_count == 3
        assert completed.completed_at == sent_at
        assert completed.from_email == "unconfigured@invalid.example"
        assert completed.last_error_code == "SENDER_CONFIGURATION_REQUIRED"
        assert sent.status == "sent"
        assert sent.template_id is None
        assert sent.legacy_template_id == cross_template_id
        assert scheduled.status == "scheduled"
        assert scheduled.template_id is None
        assert scheduled.legacy_template_id == unmatched_template_id
        assert Template.objects.get(pk=same_template_id).status == "active"
        assert Template.objects.get(pk=cross_template_id).status == "archived"
        entry = RegistryEntry.objects.get(name="email_marketing", version="2.0.0")
        assert entry.metadata["entitlement"] == "email_marketing"
        assert {item["name"] for item in entry.metadata["quota_resources"]} == {
            "email_marketing.api_reads",
            "email_marketing.api_writes",
            "email_marketing.audience_resolutions",
            "email_marketing.monthly_recipients",
        }
        registration = importlib.import_module(
            "src.modules.email_marketing.migrations.0005_register_email_marketing_contract"
        )
        registration.register_contract(new_apps, None)
        assert RegistryEntry.objects.filter(name="email_marketing", version="2.0.0").count() == 1

        reversed_apps = _migrate(INITIAL)
        ReversedCampaign = reversed_apps.get_model("email_marketing", "EmailCampaign")
        ReversedTemplate = reversed_apps.get_model("email_marketing", "EmailTemplate")
        assert ReversedCampaign.objects.get(pk=completed_campaign_id).status == "completed"
        assert ReversedCampaign.objects.get(pk=sent_campaign_id).status == "sent"
        assert ReversedCampaign.objects.get(pk=completed_campaign_id).template_id == same_template_id
        assert ReversedCampaign.objects.get(pk=sent_campaign_id).template_id == cross_template_id
        assert ReversedTemplate.objects.get(pk=same_template_id).is_active is True
        assert ReversedTemplate.objects.get(pk=cross_template_id).is_active is False

        forward_again_apps = _migrate(LATEST)
        ForwardAgainCampaign = forward_again_apps.get_model("email_marketing", "EmailCampaign")
        assert ForwardAgainCampaign.objects.get(pk=completed_campaign_id).status == "sent"
        assert ForwardAgainCampaign.objects.get(pk=completed_campaign_id).template_id == same_template_id
        assert (
            forward_again_apps.get_model("core", "ModuleRegistryEntry")
            .objects.filter(name="email_marketing", version="2.0.0")
            .count()
            == 1
        )
    finally:
        _migrate(LATEST)


class _FakeConnection:
    def __init__(self, vendor: str) -> None:
        self.vendor = vendor


class _RecordingSchemaEditor:
    def __init__(self, vendor: str) -> None:
        self.connection = _FakeConnection(vendor)
        self.statements: list[str] = []

    @staticmethod
    def quote_name(value: str) -> str:
        return f'"{value}"'

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def test_rls_and_composite_fk_paths_are_explicit_sqlite_noops() -> None:
    migration = importlib.import_module("src.modules.email_marketing.migrations.0004_constraints_indexes_and_rls")
    editor = _RecordingSchemaEditor("sqlite")
    migration.add_composite_foreign_keys(None, editor)
    migration.drop_composite_foreign_keys(None, editor)
    migration.enable_rls(None, editor)
    migration.disable_rls(None, editor)
    assert editor.statements == []


def test_rls_installs_all_tenant_tables_and_reverses_in_dependency_order() -> None:
    migration = importlib.import_module("src.modules.email_marketing.migrations.0004_constraints_indexes_and_rls")
    editor = _RecordingSchemaEditor("postgresql")
    migration.enable_rls(None, editor)
    assert len(editor.statements) == 7
    assert all("saraise_enable_rls" in statement for statement in editor.statements)
    assert [table for table in migration.TENANT_TABLES if any(table in sql for sql in editor.statements)] == list(
        migration.TENANT_TABLES
    )

    editor.statements.clear()
    migration.disable_rls(None, editor)
    assert "email_suppression_entries" in editor.statements[0]
    assert sum("DROP POLICY" in statement for statement in editor.statements) == 7
    assert sum("NO FORCE ROW LEVEL SECURITY" in statement for statement in editor.statements) == 7
    assert sum("DISABLE ROW LEVEL SECURITY" in statement for statement in editor.statements) == 7


def test_postgresql_composite_foreign_keys_cover_every_relationship() -> None:
    migration = importlib.import_module("src.modules.email_marketing.migrations.0004_constraints_indexes_and_rls")
    editor = _RecordingSchemaEditor("postgresql")
    migration.add_composite_foreign_keys(None, editor)
    additions = [statement for statement in editor.statements if "FOREIGN KEY" in statement]
    assert len(additions) == len(migration.COMPOSITE_FOREIGN_KEYS) == 8
    assert all("tenant_id" in statement for statement in additions)
    assert all("DEFERRABLE INITIALLY DEFERRED" in statement for statement in additions)

    editor.statements.clear()
    migration.drop_composite_foreign_keys(None, editor)
    assert all("DROP CONSTRAINT IF EXISTS" in statement for statement in editor.statements)


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgresql
def test_postgresql_17_rls_blocks_cross_tenant_crud_for_non_bypass_role() -> None:
    """Prove policy behavior with a role that is neither owner nor bypass-RLS."""

    if connection.vendor != "postgresql":
        pytest.skip("Dedicated PostgreSQL 17 migration lane required")
    if connection.pg_version // 10000 != 17:
        pytest.fail(f"PostgreSQL 17 is required, found server version {connection.pg_version}")

    role = f"em_rls_{uuid.uuid4().hex[:16]}"
    quoted_role = connection.ops.quote_name(role)
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    row_a = uuid.uuid4()
    row_b = uuid.uuid4()
    now = timezone.now()

    with connection.cursor() as cursor:
        cursor.execute(f"CREATE ROLE {quoted_role} NOSUPERUSER NOBYPASSRLS NOLOGIN")
        try:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, false)",
                [str(tenant_a)],
            )
            cursor.execute(
                """
                INSERT INTO email_templates
                    (id, tenant_id, created_at, updated_at, template_code, template_name,
                     description, category, subject, preview_text, body_html, body_text,
                     design_json, status, transition_history, version, usage_count,
                     is_active, is_deleted)
                VALUES (%s, %s, %s, %s, 'A', 'A', '', 'general', 'A', '', '<p>A</p>', '',
                        '{}', 'draft', '[]', 1, 0, FALSE, FALSE)
                """,
                [row_a, tenant_a, now, now],
            )
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, false)",
                [str(tenant_b)],
            )
            cursor.execute(
                """
                INSERT INTO email_templates
                    (id, tenant_id, created_at, updated_at, template_code, template_name,
                     description, category, subject, preview_text, body_html, body_text,
                     design_json, status, transition_history, version, usage_count,
                     is_active, is_deleted)
                VALUES (%s, %s, %s, %s, 'B', 'B', '', 'general', 'B', '', '<p>B</p>', '',
                        '{}', 'draft', '[]', 1, 0, FALSE, FALSE)
                """,
                [row_b, tenant_b, now, now],
            )
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {quoted_role}")
            cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON email_templates TO {quoted_role}")
            cursor.execute(f"SET ROLE {quoted_role}")
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, false)",
                [str(tenant_a)],
            )
            cursor.execute("SELECT id FROM email_templates ORDER BY id")
            assert [row[0] for row in cursor.fetchall()] == [row_a]

            with pytest.raises(DatabaseError), transaction.atomic():
                cursor.execute(
                    """
                    INSERT INTO email_templates
                        (id, tenant_id, created_at, updated_at, template_code, template_name,
                         description, category, subject, preview_text, body_html, body_text,
                         design_json, status, transition_history, version, usage_count,
                         is_active, is_deleted)
                    VALUES (%s, %s, %s, %s, 'CROSS', 'Cross', '', 'general', 'Cross', '',
                            '<p>Cross</p>', '', '{}', 'draft', '[]', 1, 0, FALSE, FALSE)
                    """,
                    [uuid.uuid4(), tenant_b, now, now],
                )
            cursor.execute(
                "UPDATE email_templates SET template_name = 'Changed' WHERE id = %s",
                [row_b],
            )
            assert cursor.rowcount == 0
            cursor.execute("DELETE FROM email_templates WHERE id = %s", [row_b])
            assert cursor.rowcount == 0
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {quoted_role}")
            cursor.execute(f"DROP ROLE IF EXISTS {quoted_role}")
