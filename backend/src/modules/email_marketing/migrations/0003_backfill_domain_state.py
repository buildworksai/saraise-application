"""Losslessly map v1 campaign/template projections into the v2 domain."""

from django.db import migrations

MIGRATION_MARKER = "email_marketing.0003.completed"


def _append_marker(history, legacy_status, occurred_at):
    normalized = list(history) if isinstance(history, list) else []
    if not any(item.get("transition_key") == MIGRATION_MARKER for item in normalized if isinstance(item, dict)):
        normalized.append(
            {
                "transition_key": MIGRATION_MARKER,
                "command": "migrate_legacy_status",
                "from_state": legacy_status,
                "to_state": "sent",
                "occurred_at": occurred_at.isoformat(),
                "metadata": {"migration": MIGRATION_MARKER, "legacy_status": legacy_status},
            }
        )
    return normalized


def _remove_marker(history):
    if not isinstance(history, list):
        return []
    return [
        item
        for item in history
        if not (isinstance(item, dict) and item.get("transition_key") == MIGRATION_MARKER)
    ]


def forwards(apps, schema_editor):
    del schema_editor
    EmailCampaign = apps.get_model("email_marketing", "EmailCampaign")
    EmailTemplate = apps.get_model("email_marketing", "EmailTemplate")

    for template in EmailTemplate.objects.all().iterator():
        template.status = "active" if template.is_active else "archived"
        template.save(update_fields=["status"])

    for campaign in EmailCampaign.objects.all().iterator():
        update_fields = []
        legacy_status = campaign.status
        if campaign.from_email == "unconfigured@invalid.example":
            campaign.last_error_code = "SENDER_CONFIGURATION_REQUIRED"
            campaign.last_error_detail = "A verified sender must be configured before delivery."
            update_fields.extend(["last_error_code", "last_error_detail"])
        if legacy_status == "completed":
            campaign.status = "sent"
            campaign.transition_history = _append_marker(
                campaign.transition_history,
                legacy_status,
                campaign.updated_at,
            )
            update_fields.extend(["status", "transition_history"])

        campaign.resolved_recipient_count = max(campaign.legacy_recipient_count, 0)
        update_fields.append("resolved_recipient_count")
        if legacy_status in {"sent", "completed"}:
            campaign.sent_count = max(campaign.legacy_recipient_count, 0)
            campaign.completed_at = campaign.legacy_sent_at
            update_fields.extend(["sent_count", "completed_at"])

        if campaign.legacy_template_id:
            matching_template = EmailTemplate.objects.filter(
                tenant_id=campaign.tenant_id,
                id=campaign.legacy_template_id,
            ).first()
            if matching_template is not None:
                campaign.template_id = matching_template.id
                update_fields.append("template")

        if update_fields:
            campaign.save(update_fields=sorted(set(update_fields)))


def backwards(apps, schema_editor):
    del schema_editor
    EmailCampaign = apps.get_model("email_marketing", "EmailCampaign")
    EmailTemplate = apps.get_model("email_marketing", "EmailTemplate")

    for campaign in EmailCampaign.objects.all().iterator():
        history = campaign.transition_history if isinstance(campaign.transition_history, list) else []
        completed_marker = any(
            isinstance(item, dict)
            and item.get("transition_key") == MIGRATION_MARKER
            and isinstance(item.get("metadata"), dict)
            and item["metadata"].get("legacy_status") == "completed"
            for item in history
        )
        if campaign.status == "sent" and completed_marker:
            campaign.status = "completed"
        campaign.transition_history = _remove_marker(history)
        campaign.resolved_recipient_count = 0
        campaign.sent_count = 0
        campaign.completed_at = None
        if campaign.last_error_code == "SENDER_CONFIGURATION_REQUIRED":
            campaign.last_error_code = ""
            campaign.last_error_detail = ""
        if campaign.template_id and campaign.template_id == campaign.legacy_template_id:
            campaign.template_id = None
        campaign.save(
            update_fields=[
                "status",
                "transition_history",
                "resolved_recipient_count",
                "sent_count",
                "completed_at",
                "last_error_code",
                "last_error_detail",
                "template",
            ]
        )

    for template in EmailTemplate.objects.all().iterator():
        template.is_active = template.status == "active"
        template.save(update_fields=["is_active"])


class Migration(migrations.Migration):
    dependencies = [("email_marketing", "0002_add_domain_columns_and_entities")]

    operations = [migrations.RunPython(forwards, backwards)]
