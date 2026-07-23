import uuid

import pytest

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.notifications.models import Notification, NotificationDeliveryAttempt
from src.modules.notifications.services import (
    NotificationConfigurationService, NotificationDispatchService, NotificationTemplateService,
)


@pytest.mark.django_db
def test_in_app_api_domain_job_worker_inbox_flow_has_durable_evidence():
    tenant, actor, recipient = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    template = NotificationTemplateService.create_template(
        tenant, actor,
        {"code": "test.inbox", "name": "Test inbox", "category": "workflow", "channel": "in_app", "locale": "en", "body_template": "Hello {{ name }}", "variables_schema": {"name": {"type": "string", "required": True}}, "content_type": "text/plain"},
        "template-create-1",
    )
    version = template.initial_version
    NotificationTemplateService.activate(tenant, template.id, version.id, actor, "activate-1")
    result = NotificationDispatchService.enqueue(
        tenant, actor,
        {"template_id": template.id, "recipient_type": "user", "recipient_user_id": recipient, "context": {"name": "Operator"}, "environment": "development"},
        "dispatch-1",
    )
    assert result.evidence["outbox_durable"] is True
    assert AsyncJob.objects.for_tenant(tenant).filter(id=result.object.job_id).exists()
    assert OutboxEvent.objects.for_tenant(tenant).filter(aggregate_id=result.object.job_id).exists()
    delivery = NotificationDispatchService.execute_delivery(tenant, result.object.id)
    assert delivery.status == "delivered"
    inbox = Notification.objects.for_tenant(tenant).get(delivery=delivery)
    assert inbox.user_id == recipient
    assert inbox.message == "Hello Operator"


@pytest.mark.django_db
def test_unavailable_provider_records_failure_evidence_without_false_success():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    config = NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    document = dict(config.document)
    document["channels"] = {**document["channels"], "email": {**document["channels"]["email"], "enabled": True, "adapter_key": "not_installed"}}
    NotificationConfigurationService.update(tenant, "development", actor, document, "Exercise explicit provider failure")
    template = NotificationTemplateService.create_template(
        tenant, actor,
        {"code": "test.email", "name": "Test email", "category": "workflow", "channel": "email", "locale": "en", "subject_template": "Subject", "body_template": "Body", "variables_schema": {}, "content_type": "text/plain"},
        "email-template",
    )
    NotificationTemplateService.activate(tenant, template.id, template.initial_version.id, actor, "email-activate")
    operation = NotificationDispatchService.enqueue(tenant, actor, {"template_id": template.id, "recipient_type": "email", "recipient": "operator@example.com", "context": {}, "environment": "development"}, "email-dispatch")
    delivery = NotificationDispatchService.execute_delivery(tenant, operation.object.id)
    assert delivery.status == "failed"
    assert delivery.failure_code == "CAPABILITY_UNAVAILABLE"
    attempt = NotificationDeliveryAttempt.objects.for_tenant(tenant).get(delivery=delivery)
    assert attempt.outcome == "permanent_failure"
    assert attempt.error_code == "CAPABILITY_UNAVAILABLE"
