"""Audited aggregate state-machine definitions."""

from src.core.state_machine import StateMachine

from .models import Notification, NotificationDelivery, NotificationTemplate

TEMPLATE_STATE_MACHINE = StateMachine(
    name="notifications.template",
    model=NotificationTemplate,
    states=("draft", "active", "archived"),
    terminal_states=(),
    transitions={
        "activate": {"draft": "active", "active": "active"},
        "archive": {"draft": "archived", "active": "archived"},
        "restore": {"archived": "draft"},
        "rollback": {"active": "active"},
    },
)

INBOX_STATE_MACHINE = StateMachine(
    name="notifications.inbox",
    model=Notification,
    states=("unread", "read", "archived"),
    terminal_states=("archived",),
    transitions={
        "mark_read": {"unread": "read"},
        "mark_unread": {"read": "unread"},
        "archive": {"unread": "archived", "read": "archived"},
    },
)

DELIVERY_STATE_MACHINE = StateMachine(
    name="notifications.delivery",
    model=NotificationDelivery,
    states=("pending", "queued", "sending", "sent", "delivered", "retry_wait", "failed", "cancelled", "skipped"),
    terminal_states=("delivered", "cancelled", "skipped"),
    transitions={
        "enqueue": {"pending": "queued"},
        "claim": {"queued": "sending"},
        "acknowledge": {"sending": "sent"},
        "confirm": {"sent": "delivered"},
        "complete_unconfirmed": {"sent": "delivered"},
        "retry": {"sending": "retry_wait"},
        "requeue": {"retry_wait": "queued", "failed": "queued"},
        "cancel": {"pending": "cancelled", "queued": "cancelled", "retry_wait": "cancelled"},
        "exhaust": {"sending": "failed", "retry_wait": "failed"},
        "suppress": {"pending": "skipped"},
    },
)

__all__ = ["DELIVERY_STATE_MACHINE", "INBOX_STATE_MACHINE", "TEMPLATE_STATE_MACHINE"]
