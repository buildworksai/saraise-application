"""Sole lifecycle command authority for integration aggregates."""

from src.core.state_machine import StateMachine, Transition

from .models import (
    CredentialStatus,
    DeliveryStatus,
    Integration,
    IntegrationCredential,
    IntegrationStatus,
    Webhook,
    WebhookDelivery,
    WebhookStatus,
)


INTEGRATION_STATE_MACHINE = StateMachine(
    name="integration_platform.integration",
    model=Integration,
    states=IntegrationStatus.values,
    transitions=(
        Transition("request_test", IntegrationStatus.INACTIVE, IntegrationStatus.TESTING),
        Transition("request_test", IntegrationStatus.ERROR, IntegrationStatus.TESTING),
        Transition("test_succeeded", IntegrationStatus.TESTING, IntegrationStatus.ACTIVE),
        Transition("test_failed", IntegrationStatus.TESTING, IntegrationStatus.ERROR),
        Transition("runtime_failed", IntegrationStatus.ACTIVE, IntegrationStatus.ERROR),
        Transition("deactivate", IntegrationStatus.ACTIVE, IntegrationStatus.INACTIVE),
        Transition("deactivate", IntegrationStatus.ERROR, IntegrationStatus.INACTIVE),
    ),
)

CREDENTIAL_STATE_MACHINE = StateMachine(
    name="integration_platform.credential",
    model=IntegrationCredential,
    states=CredentialStatus.values,
    terminal_states=(CredentialStatus.REVOKED, CredentialStatus.EXPIRED),
    transitions=(
        Transition("rotate", CredentialStatus.ACTIVE, CredentialStatus.REVOKED),
        Transition("revoke", CredentialStatus.ACTIVE, CredentialStatus.REVOKED),
        Transition("expire", CredentialStatus.ACTIVE, CredentialStatus.EXPIRED),
    ),
)

WEBHOOK_STATE_MACHINE = StateMachine(
    name="integration_platform.webhook",
    model=Webhook,
    states=WebhookStatus.values,
    transitions=(
        Transition("activate", WebhookStatus.INACTIVE, WebhookStatus.ACTIVE),
        Transition("activate", WebhookStatus.ERROR, WebhookStatus.ACTIVE),
        Transition("deactivate", WebhookStatus.ACTIVE, WebhookStatus.INACTIVE),
        Transition("delivery_failed", WebhookStatus.ACTIVE, WebhookStatus.ERROR),
    ),
)

DELIVERY_STATE_MACHINE = StateMachine(
    name="integration_platform.delivery",
    model=WebhookDelivery,
    states=DeliveryStatus.values,
    terminal_states=(DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED),
    transitions=(
        Transition("start", DeliveryStatus.QUEUED, DeliveryStatus.DELIVERING),
        Transition("succeed", DeliveryStatus.DELIVERING, DeliveryStatus.DELIVERED),
        Transition("retry", DeliveryStatus.DELIVERING, DeliveryStatus.RETRYING),
        Transition("requeue", DeliveryStatus.RETRYING, DeliveryStatus.QUEUED),
        Transition("exhaust", DeliveryStatus.DELIVERING, DeliveryStatus.DEAD_LETTER),
        Transition("cancel", DeliveryStatus.QUEUED, DeliveryStatus.CANCELLED),
        Transition("cancel", DeliveryStatus.RETRYING, DeliveryStatus.CANCELLED),
        Transition("redrive", DeliveryStatus.DEAD_LETTER, DeliveryStatus.QUEUED),
    ),
)

# Ergonomic aliases for extension modules and tests.
integration_state_machine = INTEGRATION_STATE_MACHINE
credential_state_machine = CREDENTIAL_STATE_MACHINE
webhook_state_machine = WEBHOOK_STATE_MACHINE
delivery_state_machine = DELIVERY_STATE_MACHINE

__all__ = [
    "CREDENTIAL_STATE_MACHINE", "DELIVERY_STATE_MACHINE", "INTEGRATION_STATE_MACHINE",
    "WEBHOOK_STATE_MACHINE", "credential_state_machine", "delivery_state_machine",
    "integration_state_machine", "webhook_state_machine",
]
