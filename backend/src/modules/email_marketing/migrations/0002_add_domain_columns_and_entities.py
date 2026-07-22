# Generated for the additive email-marketing v2 persistence contract.

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models

import src.modules.email_marketing.models


class Migration(migrations.Migration):
    dependencies = [("email_marketing", "0001_initial")]

    operations = [
        # Preserve the three legacy columns under explicit compatibility names
        # without renaming physical data that may already be consumed by v1.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(model_name="emailcampaign", name="template_id"),
                migrations.AddField(
                    model_name="emailcampaign",
                    name="legacy_template_id",
                    field=models.UUIDField(blank=True, db_column="template_id", editable=False, null=True),
                ),
                migrations.RemoveField(model_name="emailcampaign", name="sent_at"),
                migrations.AddField(
                    model_name="emailcampaign",
                    name="legacy_sent_at",
                    field=models.DateTimeField(blank=True, db_column="sent_at", editable=False, null=True),
                ),
                migrations.RemoveField(model_name="emailcampaign", name="recipient_count"),
                migrations.AddField(
                    model_name="emailcampaign",
                    name="legacy_recipient_count",
                    field=models.PositiveIntegerField(db_column="recipient_count", default=0, editable=False),
                ),
            ],
        ),
        migrations.AlterField(
            model_name="emailcampaign",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="emailcampaign",
            name="campaign_code",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="emailcampaign",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("scheduled", "Scheduled"),
                    ("queueing", "Queueing"),
                    ("sending", "Sending"),
                    ("paused", "Paused"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="draft",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="emailcampaign",
            name="opened_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="emailcampaign",
            name="clicked_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="created_by",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="updated_by",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="deleted_by",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="campaign_type",
            field=models.CharField(default="broadcast", max_length=32),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="audience_resolver_key",
            field=models.CharField(default="manual", max_length=100),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="gateway_key",
            field=models.CharField(default="django", max_length=100),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="verifier_key",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="preview_text",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="from_name",
            field=models.CharField(default="Unconfigured sender", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="from_email",
            field=models.EmailField(default="unconfigured@invalid.example", max_length=254),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="reply_to_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="audience_definition",
            field=models.JSONField(
                blank=True,
                default=dict,
                validators=[
                    src.modules.email_marketing.models.BoundedJSONValidator(
                        max_bytes=32768,
                        require_version=True,
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="audience_snapshot_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="audience_snapshot_evidence",
            field=models.JSONField(
                blank=True,
                default=dict,
                validators=[src.modules.email_marketing.models.BoundedJSONValidator(max_bytes=32768)],
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="resolved_recipient_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="timezone",
            field=models.CharField(
                default="UTC",
                max_length=63,
                validators=[src.modules.email_marketing.models.validate_timezone_name],
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="queue_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="send_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="content_snapshot_subject",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="content_snapshot_html",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="content_snapshot_text",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="template_version_snapshot",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="sent_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="delivered_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="unique_opened_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="unique_clicked_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="bounced_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="failed_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="unsubscribed_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="complaint_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="transition_history",
            field=models.JSONField(default=list, blank=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="last_error_code",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="last_error_detail",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="emailtemplate",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="emailtemplate",
            name="template_code",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="emailtemplate",
            name="is_active",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="created_by",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="updated_by",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="deleted_by",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(model_name="emailtemplate", name="description", field=models.TextField(blank=True)),
        migrations.AddField(
            model_name="emailtemplate",
            name="category",
            field=models.CharField(default="general", max_length=64),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="preview_text",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="design_json",
            field=models.JSONField(
                blank=True,
                default=dict,
                validators=[
                    src.modules.email_marketing.models.BoundedJSONValidator(
                        max_bytes=131072,
                        require_version=True,
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="status",
            field=models.CharField(
                choices=[("draft", "Draft"), ("active", "Active"), ("archived", "Archived")],
                db_index=True,
                default="draft",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="transition_history",
            field=models.JSONField(default=list, blank=True),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="usage_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="last_used_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="template",
            field=models.ForeignKey(
                blank=True,
                db_column="template_ref_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaigns",
                to="email_marketing.emailtemplate",
            ),
        ),
        migrations.CreateModel(
            name="ConsentRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(max_length=254)),
                ("purpose", models.CharField(default="marketing", max_length=64)),
                ("status", models.CharField(choices=[("granted", "Granted"), ("revoked", "Revoked")], max_length=16)),
                (
                    "lawful_basis",
                    models.CharField(
                        choices=[
                            ("consent", "Consent"),
                            ("legitimate_interest", "Legitimate interest"),
                            ("contractual", "Contractual"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("form", "Form"),
                            ("import", "Import"),
                            ("api", "API"),
                            ("crm_event", "CRM event"),
                            ("administrator", "Administrator"),
                            ("unsubscribe", "Unsubscribe"),
                        ],
                        max_length=32,
                    ),
                ),
                ("notice_version", models.CharField(max_length=64)),
                ("captured_at", models.DateTimeField(db_index=True)),
                ("actor_id", models.UUIDField(blank=True, null=True)),
                ("ip_hash", models.CharField(blank=True, max_length=64)),
                ("user_agent_hash", models.CharField(blank=True, max_length=64)),
                (
                    "evidence",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        validators=[src.modules.email_marketing.models.BoundedJSONValidator(max_bytes=32768)],
                    ),
                ),
                (
                    "supersedes",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="superseded_by",
                        to="email_marketing.consentrecord",
                    ),
                ),
            ],
            options={"db_table": "email_consent_records"},
        ),
        migrations.CreateModel(
            name="CampaignRecipient",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("recipient_key", models.CharField(blank=True, max_length=255, null=True)),
                ("email", models.EmailField(max_length=254)),
                ("display_name", models.CharField(blank=True, max_length=255)),
                (
                    "personalization_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        validators=[src.modules.email_marketing.models.BoundedJSONValidator(max_bytes=65536)],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("resolved", "Resolved"),
                            ("suppressed", "Suppressed"),
                            ("queued", "Queued"),
                            ("sending", "Sending"),
                            ("accepted", "Accepted"),
                            ("delivered", "Delivered"),
                            ("bounced", "Bounced"),
                            ("failed", "Failed"),
                            ("unsubscribed", "Unsubscribed"),
                            ("complained", "Complained"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="resolved",
                        max_length=16,
                    ),
                ),
                ("suppression_reason", models.CharField(blank=True, max_length=64)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("queued_at", models.DateTimeField(blank=True, null=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=64)),
                ("transition_history", models.JSONField(default=list, blank=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="recipients",
                        to="email_marketing.emailcampaign",
                    ),
                ),
                (
                    "consent_record",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="email_marketing.consentrecord",
                    ),
                ),
            ],
            options={"db_table": "email_campaign_recipients"},
        ),
        migrations.CreateModel(
            name="DeliveryAttempt",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("attempt_number", models.PositiveSmallIntegerField()),
                ("job_id", models.UUIDField()),
                ("idempotency_key", models.CharField(max_length=255)),
                ("gateway_key", models.CharField(max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("sending", "Sending"),
                            ("accepted", "Accepted"),
                            ("deferred", "Deferred"),
                            ("delivered", "Delivered"),
                            ("bounced", "Bounced"),
                            ("failed", "Failed"),
                            ("timed_out", "Timed out"),
                        ],
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("provider_message_id", models.CharField(blank=True, max_length=255)),
                ("provider_status_code", models.CharField(blank=True, max_length=64)),
                (
                    "response_evidence",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        validators=[src.modules.email_marketing.models.validate_non_secret_json],
                    ),
                ),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("error_detail", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="delivery_attempts",
                        to="email_marketing.campaignrecipient",
                    ),
                ),
            ],
            options={"db_table": "email_delivery_attempts"},
        ),
        migrations.CreateModel(
            name="DeliveryEvent",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("provider_event_id", models.CharField(max_length=255)),
                ("gateway_key", models.CharField(max_length=100)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("accepted", "Accepted"),
                            ("delivered", "Delivered"),
                            ("opened", "Opened"),
                            ("clicked", "Clicked"),
                            ("deferred", "Deferred"),
                            ("bounced", "Bounced"),
                            ("complained", "Complained"),
                            ("unsubscribed", "Unsubscribed"),
                        ],
                        max_length=16,
                    ),
                ),
                ("occurred_at", models.DateTimeField(db_index=True)),
                ("link_url_hash", models.CharField(blank=True, max_length=64)),
                (
                    "bounce_class",
                    models.CharField(
                        blank=True,
                        choices=[("hard", "Hard"), ("soft", "Soft"), ("block", "Block")],
                        max_length=32,
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        validators=[src.modules.email_marketing.models.validate_non_secret_json],
                    ),
                ),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                (
                    "attempt",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="events",
                        to="email_marketing.deliveryattempt",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="events",
                        to="email_marketing.campaignrecipient",
                    ),
                ),
            ],
            options={"db_table": "email_delivery_events"},
        ),
        migrations.CreateModel(
            name="SuppressionEntry",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(blank=True, db_index=True, editable=False, null=True)),
                ("updated_by", models.UUIDField(blank=True, db_index=True, editable=False, null=True)),
                ("email", models.EmailField(max_length=254)),
                ("scope", models.CharField(choices=[("marketing", "Marketing"), ("all", "All email")], max_length=16)),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("unsubscribe", "Unsubscribe"),
                            ("hard_bounce", "Hard bounce"),
                            ("complaint", "Complaint"),
                            ("manual", "Manual"),
                            ("legal", "Legal"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("user", "User"),
                            ("provider_event", "Provider event"),
                            ("administrator", "Administrator"),
                            ("migration", "Migration"),
                        ],
                        max_length=16,
                    ),
                ),
                ("active", models.BooleanField(default=True)),
                ("suppressed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("deactivated_at", models.DateTimeField(blank=True, null=True)),
                ("deactivated_by", models.UUIDField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                (
                    "evidence_event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="email_marketing.deliveryevent",
                    ),
                ),
            ],
            options={"db_table": "email_suppression_entries"},
        ),
    ]
