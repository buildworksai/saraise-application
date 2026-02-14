"""
DRF Serializers for Email Marketing module.
"""

from rest_framework import serializers

from .models import EmailCampaign, EmailTemplate


class EmailCampaignSerializer(serializers.ModelSerializer):
    """EmailCampaign serializer."""

    class Meta:
        model = EmailCampaign
        fields = [
            "id",
            "tenant_id",
            "campaign_code",
            "campaign_name",
            "subject",
            "template_id",
            "status",
            "scheduled_at",
            "sent_at",
            "recipient_count",
            "opened_count",
            "clicked_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "sent_at", "recipient_count", "opened_count", "clicked_count", "created_at", "updated_at"]


class EmailTemplateSerializer(serializers.ModelSerializer):
    """EmailTemplate serializer."""

    class Meta:
        model = EmailTemplate
        fields = [
            "id",
            "tenant_id",
            "template_code",
            "template_name",
            "subject",
            "body_html",
            "body_text",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
