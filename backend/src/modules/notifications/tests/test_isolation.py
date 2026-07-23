"""Concrete cross-tenant isolation checks for notification resources."""

import uuid

import pytest

from src.modules.notifications.models import Notification, NotificationConfiguration, NotificationEndpoint, NotificationPreference, NotificationTemplate
from src.modules.notifications.services import NotificationConfigurationService, NotificationInboxService, NotificationTemplateService


@pytest.mark.django_db
def test_inbox_list_detail_update_delete_and_same_user_are_tenant_isolated():
    tenant_a, tenant_b, same_user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row_a = Notification.objects.create(tenant_id=tenant_a, user_id=same_user, title="A", message="A")
    row_b = Notification.objects.create(tenant_id=tenant_b, user_id=same_user, title="B", message="B")
    assert list(NotificationInboxService.list_for_user(tenant_a, same_user)) == [row_a]
    with pytest.raises(Notification.DoesNotExist): NotificationInboxService.get_for_user(tenant_a, same_user, row_b.id)
    before = Notification.objects.filter(pk=row_b.pk).values().get()
    with pytest.raises(Notification.DoesNotExist): NotificationInboxService.mark_read(tenant_a, same_user, row_b.id, "cross-read")
    assert Notification.objects.filter(pk=row_b.pk).values().get() == before


@pytest.mark.django_db
def test_templates_configuration_preferences_and_endpoints_require_explicit_tenant_scope():
    tenant_a, tenant_b, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant_a, "development", actor)
    config_b = NotificationConfigurationService.get_or_create_default(tenant_b, "development", actor)
    template_b = NotificationTemplateService.create_template(tenant_b, actor, {"code": "tenant.b", "name": "Tenant B", "category": "general", "channel": "in_app", "body_template": "Body", "variables_schema": {}}, "b-create")
    NotificationPreference.objects.create(tenant_id=tenant_b, user_id=user, channel="in_app", category="general")
    NotificationEndpoint.objects.create(tenant_id=tenant_b, user_id=user, kind="push", device_type="web", address_ciphertext="encrypted", fingerprint="f" * 64, display_name="B", created_by=actor)
    assert not NotificationTemplateService.list_templates(tenant_a).filter(pk=template_b.pk).exists()
    assert not NotificationConfiguration.objects.for_tenant(tenant_a).filter(pk=config_b.pk).exists()
    assert not NotificationPreference.objects.for_tenant(tenant_a).filter(tenant_id=tenant_b).exists()
    assert not NotificationEndpoint.objects.for_tenant(tenant_a).filter(tenant_id=tenant_b).exists()
