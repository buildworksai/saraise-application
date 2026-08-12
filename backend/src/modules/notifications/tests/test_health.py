import uuid
from types import SimpleNamespace

import pytest

from src.modules.notifications import health
from src.modules.notifications.adapters import AdapterHealth, AdapterNotRegistered
from src.modules.notifications.health import ComponentStatus, liveness, readiness


def test_liveness_proves_process_only():
    payload = liveness()
    assert payload["module"] == "notifications"
    assert payload["status"] == "live"
    assert payload["live"] is True
    assert payload["checked_at"]


@pytest.mark.django_db
def test_readiness_fails_closed_without_configuration():
    payload, http_status = readiness(uuid.uuid4())
    assert http_status == 503
    assert payload["ready"] is False
    assert "exception" not in str(payload).lower()


def test_adapter_statuses_fail_closed_for_missing_or_invalid_configuration():
    tenant_id = uuid.uuid4()

    missing, missing_details = health._adapter_statuses(tenant_id, None)
    assert missing.healthy is False
    assert missing.code == "configuration_missing"
    assert missing_details == {}

    empty, empty_details = health._adapter_statuses(tenant_id, {"channels": {}})
    assert empty.healthy is False
    assert empty.code == "channel_configuration_missing"
    assert empty_details == {}

    invalid, details = health._adapter_statuses(
        tenant_id,
        {
            "channels": {
                "email": {"enabled": "yes"},
                "sms": "not-a-channel-document",
                42: {"enabled": True},
            }
        },
    )
    assert invalid.healthy is False
    assert invalid.code == "required_adapter_unavailable"
    assert details["email"]["code"] == "channel_configuration_invalid"
    assert details["sms"]["code"] == "channel_configuration_invalid"
    assert details["42"]["code"] == "channel_configuration_invalid"


def test_adapter_statuses_reports_disabled_missing_unavailable_and_failed_adapters(monkeypatch):
    tenant_id = uuid.uuid4()

    class EmailAdapter:
        channel = "email"

        def health(self, tenant_id_arg, configuration):
            assert tenant_id_arg == tenant_id
            assert configuration["adapter_key"] == "smtp"
            return AdapterHealth(True, "ready", "ready", {"backend_configured": True})

    class SmsAdapter:
        channel = "sms"

        def health(self, tenant_id_arg, configuration):
            raise RuntimeError("provider detail must not leak")

    class PushAdapter:
        channel = "email"

        def health(self, tenant_id_arg, configuration):
            return AdapterHealth(True, "ready", "ready")

    def fake_get(key):
        if key == "smtp":
            return EmailAdapter()
        if key == "sms-provider":
            return SmsAdapter()
        if key == "push-provider":
            return PushAdapter()
        raise AdapterNotRegistered(key)

    monkeypatch.setattr(health.adapter_registry, "get", fake_get)

    status, details = health._adapter_statuses(
        tenant_id,
        {
            "channels": {
                "email": {"enabled": True, "adapter_key": "smtp"},
                "in_app": {"enabled": False},
                "sms": {"enabled": True, "adapter_key": "sms-provider"},
                "push": {"enabled": True, "adapter_key": "push-provider"},
                "webhook": {"enabled": True, "adapter_key": "missing-provider"},
            }
        },
    )

    assert status.healthy is False
    assert status.code == "required_adapter_unavailable"
    assert details["email"]["status"] == "ready"
    assert details["in_app"] == {"status": "disabled", "code": "disabled"}
    assert details["sms"]["code"] == "adapter_health_failed"
    assert details["push"]["code"] == "adapter_health_failed"
    assert details["webhook"]["code"] == "adapter_unavailable"
    assert "provider detail" not in str(details)


def test_request_tenant_prefers_direct_context_then_contextvars_then_user(monkeypatch):
    direct = uuid.uuid4()
    contextual = uuid.uuid4()
    user_tenant = uuid.uuid4()

    monkeypatch.setattr(health, "get_current_tenant_id", lambda: contextual)
    monkeypatch.setattr(health, "get_user_tenant_id", lambda user: user_tenant)

    assert health._request_tenant(SimpleNamespace(tenant_id=str(direct), user=object())) == direct
    assert health._request_tenant(SimpleNamespace(tenant_id=None, user=object())) == contextual

    monkeypatch.setattr(health, "get_current_tenant_id", lambda: None)
    assert health._request_tenant(SimpleNamespace(user=object())) == user_tenant

    monkeypatch.setattr(health, "get_user_tenant_id", lambda user: "not-a-uuid")
    assert health._request_tenant(SimpleNamespace(user=object())) is None


def test_readiness_assembles_sanitized_success_payload(monkeypatch):
    tenant_id = uuid.uuid4()

    monkeypatch.setattr(
        health,
        "_database_status",
        lambda tenant: ComponentStatus(True, "ready", details={"rls_context": "not_applicable"}),
    )
    monkeypatch.setattr(
        health,
        "_outbox_status",
        lambda tenant: ComponentStatus(True, "ready", details={"pending": 3, "oldest_age_seconds": 17}),
    )
    monkeypatch.setattr(health, "_handlers_status", lambda: ComponentStatus(True, "ready", details={"registered": 5}))
    monkeypatch.setattr(
        health,
        "_configuration",
        lambda tenant: (
            ComponentStatus(True, "ready", details={"environment": "development", "active_version": 2}),
            {"channels": {"email": {"enabled": True, "adapter_key": "smtp"}}},
        ),
    )
    monkeypatch.setattr(
        health,
        "_adapter_statuses",
        lambda tenant, document: (
            ComponentStatus(True, "ready"),
            {"email": {"status": "ready", "code": "ready"}},
        ),
    )

    class BrokenApps:
        def get_model(self, *args, **kwargs):
            raise RuntimeError("private ORM detail")

    monkeypatch.setattr(health, "apps", BrokenApps())

    payload, http_status = health.readiness(str(tenant_id))

    assert http_status == 200
    assert payload["ready"] is True
    assert payload["queue_backlog"] == 3
    assert payload["oldest_queued_age_seconds"] == 17
    assert payload["components"]["database"]["details"]["rls_context"] == "not_applicable"
    assert payload["last_successful_delivery_at"] is None
    assert "private ORM detail" not in str(payload)


def test_readiness_check_and_liveness_check_return_json_responses(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(health, "_request_tenant", lambda request: tenant_id)
    monkeypatch.setattr(
        health,
        "readiness",
        lambda tenant: ({"module": "notifications", "ready": False, "code": "dependency_unavailable"}, 503),
    )

    ready_response = health.readiness_check(SimpleNamespace())
    live_response = health.liveness_check(SimpleNamespace())

    assert ready_response.status_code == 503
    assert b"dependency_unavailable" in ready_response.content
    assert live_response.status_code == 200
    assert b"notifications" in live_response.content
