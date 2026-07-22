"""Install domain integrity, query indexes, composite tenant FKs, and RLS."""

from django.db import migrations, models
from django.db.models import Q

TENANT_TABLES = (
    "email_templates",
    "email_campaigns",
    "email_consent_records",
    "email_campaign_recipients",
    "email_delivery_attempts",
    "email_delivery_events",
    "email_suppression_entries",
)

PARENT_UNIQUES = (
    ("email_templates", "em_tmpl_tenant_id_uniq"),
    ("email_campaigns", "em_cmp_tenant_id_uniq"),
    ("email_consent_records", "em_consent_tenant_id_uniq"),
    ("email_campaign_recipients", "em_recipient_tenant_id_uniq"),
    ("email_delivery_attempts", "em_attempt_tenant_id_uniq"),
    ("email_delivery_events", "em_event_tenant_id_uniq"),
)

COMPOSITE_FOREIGN_KEYS = (
    ("email_campaigns", "em_cmp_template_tenant_fk", "tenant_id, template_ref_id", "email_templates"),
    (
        "email_campaign_recipients",
        "em_recipient_campaign_tenant_fk",
        "tenant_id, campaign_id",
        "email_campaigns",
    ),
    (
        "email_campaign_recipients",
        "em_recipient_consent_tenant_fk",
        "tenant_id, consent_record_id",
        "email_consent_records",
    ),
    (
        "email_delivery_attempts",
        "em_attempt_recipient_tenant_fk",
        "tenant_id, recipient_id",
        "email_campaign_recipients",
    ),
    (
        "email_delivery_events",
        "em_event_recipient_tenant_fk",
        "tenant_id, recipient_id",
        "email_campaign_recipients",
    ),
    (
        "email_delivery_events",
        "em_event_attempt_tenant_fk",
        "tenant_id, attempt_id",
        "email_delivery_attempts",
    ),
    (
        "email_suppression_entries",
        "em_suppress_event_tenant_fk",
        "tenant_id, evidence_event_id",
        "email_delivery_events",
    ),
    (
        "email_consent_records",
        "em_consent_supersedes_tenant_fk",
        "tenant_id, supersedes_id",
        "email_consent_records",
    ),
)


def add_composite_foreign_keys(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, constraint, _, _ in COMPOSITE_FOREIGN_KEYS:
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(table)} "
            f"DROP CONSTRAINT IF EXISTS {schema_editor.quote_name(constraint)}"
        )
    for table, constraint in PARENT_UNIQUES:
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(table)} "
            f"DROP CONSTRAINT IF EXISTS {schema_editor.quote_name(constraint)}"
        )
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(table)} "
            f"ADD CONSTRAINT {schema_editor.quote_name(constraint)} UNIQUE (tenant_id, id)"
        )
    for table, constraint, columns, target in COMPOSITE_FOREIGN_KEYS:
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(table)} "
            f"ADD CONSTRAINT {schema_editor.quote_name(constraint)} FOREIGN KEY ({columns}) "
            f"REFERENCES {schema_editor.quote_name(target)} (tenant_id, id) "
            "DEFERRABLE INITIALLY DEFERRED"
        )


def drop_composite_foreign_keys(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, constraint, _, _ in reversed(COMPOSITE_FOREIGN_KEYS):
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(table)} "
            f"DROP CONSTRAINT IF EXISTS {schema_editor.quote_name(constraint)}"
        )
    for table, constraint in reversed(PARENT_UNIQUES):
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(table)} "
            f"DROP CONSTRAINT IF EXISTS {schema_editor.quote_name(constraint)}"
        )


def enable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS)")


def disable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table}"[:63])
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table}")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("email_marketing", "0003_backfill_domain_state"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="emailcampaign", name="unique_campaign_code_per_tenant"),
        migrations.RemoveConstraint(model_name="emailtemplate", name="unique_template_code_per_tenant"),
        migrations.RemoveIndex(model_name="emailcampaign", name="email_campa_tenant__5e44e2_idx"),
        migrations.RemoveIndex(model_name="emailcampaign", name="email_campa_tenant__1171af_idx"),
        migrations.RemoveIndex(model_name="emailcampaign", name="email_campa_tenant__1e2888_idx"),
        migrations.RemoveIndex(model_name="emailtemplate", name="email_templ_tenant__d13d5d_idx"),
        migrations.AddConstraint(
            model_name="emailcampaign",
            constraint=models.UniqueConstraint(
                condition=Q(is_deleted=False),
                fields=("tenant_id", "campaign_code"),
                name="em_cmp_tenant_code_live_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailcampaign",
            constraint=models.CheckConstraint(
                condition=~Q(status="scheduled") | Q(scheduled_at__isnull=False),
                name="em_cmp_scheduled_at_required_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailcampaign",
            constraint=models.CheckConstraint(
                condition=~Q(status="sent") | Q(completed_at__isnull=False),
                name="em_cmp_completed_at_required_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailcampaign",
            constraint=models.CheckConstraint(
                condition=Q(resolved_recipient_count__gte=0)
                & Q(legacy_recipient_count__gte=0)
                & Q(sent_count__gte=0)
                & Q(delivered_count__gte=0)
                & Q(opened_count__gte=0)
                & Q(unique_opened_count__gte=0)
                & Q(clicked_count__gte=0)
                & Q(unique_clicked_count__gte=0)
                & Q(bounced_count__gte=0)
                & Q(failed_count__gte=0)
                & Q(unsubscribed_count__gte=0)
                & Q(complaint_count__gte=0),
                name="em_cmp_counters_nonnegative_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailcampaign",
            constraint=models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "draft",
                        "scheduled",
                        "queueing",
                        "sending",
                        "paused",
                        "sent",
                        "failed",
                        "cancelled",
                    ]
                ),
                name="em_cmp_status_valid_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="emailcampaign",
            index=models.Index(fields=["tenant_id", "status", "-created_at"], name="em_cmp_tenant_status_created"),
        ),
        migrations.AddIndex(
            model_name="emailcampaign",
            index=models.Index(
                condition=Q(status="scheduled"),
                fields=["tenant_id", "scheduled_at"],
                name="em_cmp_tenant_scheduled",
            ),
        ),
        migrations.AddIndex(
            model_name="emailcampaign",
            index=models.Index(fields=["tenant_id", "template", "-created_at"], name="em_cmp_tenant_tmpl_created"),
        ),
        migrations.AddConstraint(
            model_name="emailtemplate",
            constraint=models.UniqueConstraint(
                condition=Q(is_deleted=False),
                fields=("tenant_id", "template_code"),
                name="em_tmpl_tenant_code_live_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailtemplate",
            constraint=models.CheckConstraint(condition=Q(version__gte=1), name="em_tmpl_version_positive_ck"),
        ),
        migrations.AddConstraint(
            model_name="emailtemplate",
            constraint=models.CheckConstraint(condition=Q(usage_count__gte=0), name="em_tmpl_usage_nonnegative_ck"),
        ),
        migrations.AddConstraint(
            model_name="emailtemplate",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["draft", "active", "archived"]),
                name="em_tmpl_status_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailtemplate",
            constraint=models.CheckConstraint(
                condition=~Q(status="active") | (Q(subject__gt="") & (Q(body_html__gt="") | Q(body_text__gt=""))),
                name="em_tmpl_active_content_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="emailtemplate",
            index=models.Index(fields=["tenant_id", "status", "category"], name="em_tmpl_tenant_status_cat"),
        ),
        migrations.AddConstraint(
            model_name="consentrecord",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["granted", "revoked"]),
                name="em_consent_status_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="consentrecord",
            constraint=models.CheckConstraint(
                condition=Q(lawful_basis__in=["consent", "legitimate_interest", "contractual"]),
                name="em_consent_basis_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="consentrecord",
            constraint=models.CheckConstraint(
                condition=Q(source__in=["form", "import", "api", "crm_event", "administrator", "unsubscribe"]),
                name="em_consent_source_valid_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="consentrecord",
            index=models.Index(
                fields=["tenant_id", "email", "purpose", "-captured_at"],
                name="em_consent_tenant_email_time",
            ),
        ),
        migrations.AddConstraint(
            model_name="campaignrecipient",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "campaign", "email"),
                name="em_recipient_campaign_email_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="campaignrecipient",
            constraint=models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "resolved",
                        "suppressed",
                        "queued",
                        "sending",
                        "accepted",
                        "delivered",
                        "bounced",
                        "failed",
                        "unsubscribed",
                        "complained",
                        "cancelled",
                    ]
                ),
                name="em_recipient_status_valid_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="campaignrecipient",
            index=models.Index(fields=["tenant_id", "campaign", "status"], name="em_recipient_cmp_status"),
        ),
        migrations.AddIndex(
            model_name="campaignrecipient",
            index=models.Index(fields=["tenant_id", "email", "-created_at"], name="em_recipient_email_created"),
        ),
        migrations.AddConstraint(
            model_name="deliveryattempt",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="em_attempt_idempotency_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliveryattempt",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "recipient", "attempt_number"),
                name="em_attempt_recipient_number_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliveryattempt",
            constraint=models.CheckConstraint(
                condition=Q(attempt_number__gte=1),
                name="em_attempt_number_positive_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliveryattempt",
            constraint=models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "queued",
                        "sending",
                        "accepted",
                        "deferred",
                        "delivered",
                        "bounced",
                        "failed",
                        "timed_out",
                    ]
                ),
                name="em_attempt_status_valid_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="deliveryattempt",
            index=models.Index(fields=["tenant_id", "status", "created_at"], name="em_attempt_status_created"),
        ),
        migrations.AddIndex(
            model_name="deliveryattempt",
            index=models.Index(
                condition=~Q(provider_message_id=""),
                fields=["tenant_id", "provider_message_id"],
                name="em_attempt_provider_message",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliveryevent",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "gateway_key", "provider_event_id"),
                name="em_event_provider_id_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliveryevent",
            constraint=models.CheckConstraint(
                condition=Q(
                    event_type__in=[
                        "accepted",
                        "delivered",
                        "opened",
                        "clicked",
                        "deferred",
                        "bounced",
                        "complained",
                        "unsubscribed",
                    ]
                ),
                name="em_event_type_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliveryevent",
            constraint=models.CheckConstraint(
                condition=(Q(event_type="bounced") & Q(bounce_class__in=["hard", "soft", "block"]))
                | (~Q(event_type="bounced") & Q(bounce_class="")),
                name="em_event_bounce_class_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="deliveryevent",
            index=models.Index(fields=["tenant_id", "recipient", "occurred_at"], name="em_event_recipient_time"),
        ),
        migrations.AddIndex(
            model_name="deliveryevent",
            index=models.Index(fields=["tenant_id", "event_type", "occurred_at"], name="em_event_type_time"),
        ),
        migrations.AddConstraint(
            model_name="suppressionentry",
            constraint=models.UniqueConstraint(
                condition=Q(active=True),
                fields=("tenant_id", "email", "scope"),
                name="em_suppress_email_scope_live_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="suppressionentry",
            constraint=models.CheckConstraint(
                condition=~Q(reason__in=["unsubscribe", "complaint", "legal"]) | Q(expires_at__isnull=True),
                name="em_suppress_permanent_no_expiry_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="suppressionentry",
            constraint=models.CheckConstraint(
                condition=Q(active=True) | Q(deactivated_at__isnull=False),
                name="em_suppress_deactivated_at_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="suppressionentry",
            constraint=models.CheckConstraint(
                condition=Q(scope__in=["marketing", "all"]),
                name="em_suppress_scope_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="suppressionentry",
            constraint=models.CheckConstraint(
                condition=Q(reason__in=["unsubscribe", "hard_bounce", "complaint", "manual", "legal"]),
                name="em_suppress_reason_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="suppressionentry",
            constraint=models.CheckConstraint(
                condition=Q(source__in=["user", "provider_event", "administrator", "migration"]),
                name="em_suppress_source_valid_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="suppressionentry",
            index=models.Index(
                fields=["tenant_id", "active", "reason", "-suppressed_at"],
                name="em_suppress_active_reason_time",
            ),
        ),
        migrations.RunPython(add_composite_foreign_keys, drop_composite_foreign_keys),
        migrations.RunPython(enable_rls, disable_rls),
    ]
