"""Registered lifecycle authorities for email-marketing aggregates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from django.core.exceptions import ValidationError
from django.db import models

from src.core.state_machine import (
    MachineNotRegisteredError,
    StateMachine,
    StateMachineConfigurationError,
    Transition,
    register,
    registry,
)

from .models import (
    CampaignRecipient,
    CampaignStatus,
    EmailCampaign,
    EmailTemplate,
    RecipientStatus,
    TemplateStatus,
    normalize_email_address,
)

ModelT = TypeVar("ModelT", bound=models.Model)


class AuditedStateMachine(StateMachine[ModelT]):
    """Require stable actor and correlation evidence for every transition."""

    def apply(self, *args: Any, metadata: Mapping[str, Any] | None = None, **kwargs: Any) -> ModelT:
        audit = dict(metadata or {})
        missing = [key for key in ("actor_id", "correlation_id") if key not in audit]
        if "correlation_id" in audit and not audit.get("correlation_id"):
            missing.append("correlation_id")
        if missing:
            raise StateMachineConfigurationError(
                f"Transition audit metadata is missing: {', '.join(missing)}"
            )
        audit["actor_id"] = str(audit["actor_id"]) if audit["actor_id"] is not None else None
        audit["correlation_id"] = str(audit["correlation_id"])
        if "causation_id" in audit and audit["causation_id"] is not None:
            audit["causation_id"] = str(audit["causation_id"])
        return super().apply(*args, metadata=audit, **kwargs)


def _rendered_content_ready(campaign: EmailCampaign, context: Mapping[str, Any]) -> bool:
    del context
    return bool(
        campaign.content_snapshot_subject.strip()
        and (campaign.content_snapshot_html.strip() or campaign.content_snapshot_text.strip())
    )


def _audience_resolution_complete(campaign: EmailCampaign, context: Mapping[str, Any]) -> bool:
    del context
    return campaign.audience_snapshot_at is not None and campaign.resolved_recipient_count > 0


def _eligible_recipient_exists(campaign: EmailCampaign, context: Mapping[str, Any]) -> bool:
    del context
    return campaign.recipients.filter(
        status=RecipientStatus.RESOLVED,
        consent_record__status="granted",
    ).exists()


def _sender_addresses_valid(campaign: EmailCampaign, context: Mapping[str, Any]) -> bool:
    del context
    try:
        normalize_email_address(campaign.from_email)
        if campaign.reply_to_email:
            normalize_email_address(campaign.reply_to_email)
    except ValidationError:
        return False
    return True


def _commercial_capacity_available(campaign: EmailCampaign, context: Mapping[str, Any]) -> bool:
    del campaign
    return context.get("entitlement_available") is True and context.get("quota_available") is True


def _consent_evaluation_complete(campaign: EmailCampaign, context: Mapping[str, Any]) -> bool:
    unevaluated = campaign.recipients.filter(
        status__in=[RecipientStatus.RESOLVED, RecipientStatus.QUEUED],
    ).exclude(consent_record__status="granted")
    return context.get("consent_evaluated") is True and not unevaluated.exists()


CAMPAIGN_STATE_MACHINE = AuditedStateMachine(
    name="email_marketing.campaign",
    model=EmailCampaign,
    states=CampaignStatus.values,
    terminal_states=(CampaignStatus.SENT, CampaignStatus.CANCELLED),
    transitions=(
        Transition("schedule", CampaignStatus.DRAFT, CampaignStatus.SCHEDULED),
        Transition("reschedule", CampaignStatus.SCHEDULED, CampaignStatus.SCHEDULED),
        Transition("unschedule", CampaignStatus.SCHEDULED, CampaignStatus.DRAFT),
        Transition(
            "queue_send",
            CampaignStatus.DRAFT,
            CampaignStatus.QUEUEING,
            (
                _rendered_content_ready,
                _audience_resolution_complete,
                _eligible_recipient_exists,
                _sender_addresses_valid,
                _commercial_capacity_available,
                _consent_evaluation_complete,
            ),
        ),
        Transition(
            "queue_send",
            CampaignStatus.SCHEDULED,
            CampaignStatus.QUEUEING,
            (
                _rendered_content_ready,
                _audience_resolution_complete,
                _eligible_recipient_exists,
                _sender_addresses_valid,
                _commercial_capacity_available,
                _consent_evaluation_complete,
            ),
        ),
        Transition(
            "queue_send",
            CampaignStatus.FAILED,
            CampaignStatus.QUEUEING,
            (
                _rendered_content_ready,
                _audience_resolution_complete,
                _eligible_recipient_exists,
                _sender_addresses_valid,
                _commercial_capacity_available,
                _consent_evaluation_complete,
            ),
        ),
        Transition("start_send", CampaignStatus.QUEUEING, CampaignStatus.SENDING),
        Transition("pause", CampaignStatus.QUEUEING, CampaignStatus.PAUSED),
        Transition("pause", CampaignStatus.SENDING, CampaignStatus.PAUSED),
        Transition("resume", CampaignStatus.PAUSED, CampaignStatus.QUEUEING),
        Transition("complete", CampaignStatus.SENDING, CampaignStatus.SENT),
        Transition("fail", CampaignStatus.QUEUEING, CampaignStatus.FAILED),
        Transition("fail", CampaignStatus.SENDING, CampaignStatus.FAILED),
        Transition("cancel", CampaignStatus.DRAFT, CampaignStatus.CANCELLED),
        Transition("cancel", CampaignStatus.SCHEDULED, CampaignStatus.CANCELLED),
        Transition("cancel", CampaignStatus.QUEUEING, CampaignStatus.CANCELLED),
        Transition("cancel", CampaignStatus.SENDING, CampaignStatus.CANCELLED),
        Transition("cancel", CampaignStatus.PAUSED, CampaignStatus.CANCELLED),
        Transition("cancel", CampaignStatus.FAILED, CampaignStatus.CANCELLED),
    ),
)


TEMPLATE_STATE_MACHINE = AuditedStateMachine(
    name="email_marketing.template",
    model=EmailTemplate,
    states=TemplateStatus.values,
    terminal_states=(TemplateStatus.ARCHIVED,),
    transitions=(
        Transition("activate", TemplateStatus.DRAFT, TemplateStatus.ACTIVE),
        Transition("archive", TemplateStatus.DRAFT, TemplateStatus.ARCHIVED),
        Transition("archive", TemplateStatus.ACTIVE, TemplateStatus.ARCHIVED),
    ),
)


RECIPIENT_STATE_MACHINE = AuditedStateMachine(
    name="email_marketing.recipient",
    model=CampaignRecipient,
    states=RecipientStatus.values,
    terminal_states=(
        RecipientStatus.BOUNCED,
        RecipientStatus.UNSUBSCRIBED,
        RecipientStatus.COMPLAINED,
        RecipientStatus.CANCELLED,
    ),
    transitions=(
        Transition("suppress", RecipientStatus.RESOLVED, RecipientStatus.SUPPRESSED),
        Transition("queue", RecipientStatus.RESOLVED, RecipientStatus.QUEUED),
        Transition("cancel", RecipientStatus.RESOLVED, RecipientStatus.CANCELLED),
        Transition("cancel", RecipientStatus.SUPPRESSED, RecipientStatus.CANCELLED),
        Transition("start_send", RecipientStatus.QUEUED, RecipientStatus.SENDING),
        Transition("suppress", RecipientStatus.QUEUED, RecipientStatus.SUPPRESSED),
        Transition("cancel", RecipientStatus.QUEUED, RecipientStatus.CANCELLED),
        Transition("accepted", RecipientStatus.SENDING, RecipientStatus.ACCEPTED),
        Transition("fail", RecipientStatus.SENDING, RecipientStatus.FAILED),
        Transition("bounce", RecipientStatus.SENDING, RecipientStatus.BOUNCED),
        Transition("cancel", RecipientStatus.SENDING, RecipientStatus.CANCELLED),
        Transition("delivered", RecipientStatus.ACCEPTED, RecipientStatus.DELIVERED),
        Transition("bounce", RecipientStatus.ACCEPTED, RecipientStatus.BOUNCED),
        Transition("fail", RecipientStatus.ACCEPTED, RecipientStatus.FAILED),
        Transition("unsubscribe", RecipientStatus.ACCEPTED, RecipientStatus.UNSUBSCRIBED),
        Transition("complain", RecipientStatus.ACCEPTED, RecipientStatus.COMPLAINED),
        Transition("unsubscribe", RecipientStatus.DELIVERED, RecipientStatus.UNSUBSCRIBED),
        Transition("complain", RecipientStatus.DELIVERED, RecipientStatus.COMPLAINED),
        Transition("retry", RecipientStatus.FAILED, RecipientStatus.QUEUED),
        Transition("cancel", RecipientStatus.FAILED, RecipientStatus.CANCELLED),
        Transition("queue", RecipientStatus.SUPPRESSED, RecipientStatus.QUEUED),
    ),
)


def ensure_state_machines_registered() -> tuple[StateMachine[Any], ...]:
    """Register all machines without silently replacing another extension."""

    registered: list[StateMachine[Any]] = []
    for machine in (CAMPAIGN_STATE_MACHINE, TEMPLATE_STATE_MACHINE, RECIPIENT_STATE_MACHINE):
        name = machine.name or ""
        try:
            existing = registry.get(name)
        except MachineNotRegisteredError:
            registered.append(register(name, machine))
            continue
        if existing is not machine:
            raise StateMachineConfigurationError(f"State machine {name!r} is already registered by another owner")
        registered.append(existing)
    return tuple(registered)


ensure_state_machines_registered()


campaign_state_machine = CAMPAIGN_STATE_MACHINE
template_state_machine = TEMPLATE_STATE_MACHINE
recipient_state_machine = RECIPIENT_STATE_MACHINE

__all__ = [
    "AuditedStateMachine",
    "CAMPAIGN_STATE_MACHINE",
    "RECIPIENT_STATE_MACHINE",
    "TEMPLATE_STATE_MACHINE",
    "campaign_state_machine",
    "ensure_state_machines_registered",
    "recipient_state_machine",
    "template_state_machine",
]
