"""
Business logic services for Email Marketing module.
"""

from .models import EmailCampaign, EmailTemplate


class EmailCampaignService:
    """Service for email campaign operations."""

    @staticmethod
    def create_campaign(tenant_id: str, campaign_code: str, campaign_name: str, subject: str, **kwargs) -> EmailCampaign:
        """Create a new email campaign."""
        return EmailCampaign.objects.create(
            tenant_id=tenant_id,
            campaign_code=campaign_code,
            campaign_name=campaign_name,
            subject=subject,
            **kwargs,
        )


class EmailTemplateService:
    """Service for email template operations."""

    @staticmethod
    def create_template(tenant_id: str, template_code: str, template_name: str, subject: str, body_html: str, **kwargs) -> EmailTemplate:
        """Create a new email template."""
        return EmailTemplate.objects.create(
            tenant_id=tenant_id,
            template_code=template_code,
            template_name=template_name,
            subject=subject,
            body_html=body_html,
            **kwargs,
        )
