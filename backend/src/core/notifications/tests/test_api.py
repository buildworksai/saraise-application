"""Tests for the legacy core notification API controllers."""

from __future__ import annotations

import uuid

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from src.core.notifications import api


class _User:
    is_authenticated = True


def _request(method: str = "get", path: str = "/", data: dict[str, object] | None = None):
    factory = APIRequestFactory()
    request = getattr(factory, method)(path, data or {}, format="json")
    request.user = _User()
    request.query_params = request.GET
    return request


@pytest.fixture
def tenant_and_user(monkeypatch):
    tenant_id = uuid.uuid4()
    user_id = "42"
    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: str(tenant_id))
    monkeypatch.setattr(api, "get_user_id", lambda user: user_id)
    return tenant_id, api._convert_user_id_to_uuid(user_id)


class _QueryRecorder:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object] | tuple[object, ...]]] = []

    def filter(self, **kwargs):
        self.calls.append(("filter", kwargs))
        return self

    def order_by(self, *fields):
        self.calls.append(("order_by", fields))
        return self


class _ManagerRecorder:
    def __init__(self):
        self.query = _QueryRecorder()
        self.none_called = False
        self.filter_kwargs: dict[str, object] | None = None

    def filter(self, **kwargs):
        self.filter_kwargs = kwargs
        return self.query

    def none(self):
        self.none_called = True
        return []


def test_notification_queryset_filters_tenant_user_unread_and_invalid_context(monkeypatch, tenant_and_user):
    tenant_id, user_uuid = tenant_and_user
    manager = _ManagerRecorder()
    monkeypatch.setattr(api.Notification, "objects", manager)

    view = api.NotificationViewSet()
    view.request = _request(path="/?unread_only=true")

    assert view.get_queryset() is manager.query
    assert manager.filter_kwargs == {"tenant_id": tenant_id, "user_id": user_uuid}
    assert manager.query.calls == [("filter", {"read": False}), ("order_by", ("-created_at",))]

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "not-a-uuid")
    assert list(view.get_queryset()) == []
    assert manager.none_called is True

    manager.none_called = False
    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: str(tenant_id))
    monkeypatch.setattr(api, "get_user_id", lambda user: "")
    assert list(view.get_queryset()) == []
    assert manager.none_called is True


def test_notification_actions_translate_identity_and_service_results(monkeypatch, tenant_and_user):
    tenant_id, user_uuid = tenant_and_user
    calls: list[tuple[object, ...]] = []

    def mark_as_read(notification_id, tenant_arg, user_arg):
        calls.append((notification_id, tenant_arg, user_arg))
        return notification_id == "existing"

    monkeypatch.setattr(api.NotificationService, "mark_as_read", mark_as_read)

    view = api.NotificationViewSet()
    ok = view.mark_read(_request("post"), pk="existing")
    missing = view.mark_read(_request("post"), pk="missing")

    assert ok.status_code == status.HTTP_200_OK
    assert ok.data == {"success": True}
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert calls == [
        ("existing", str(tenant_id), str(user_uuid)),
        ("missing", str(tenant_id), str(user_uuid)),
    ]

    monkeypatch.setattr(api, "get_user_id", lambda user: "")
    no_user = view.mark_read(_request("post"), pk="existing")
    assert no_user.status_code == status.HTTP_403_FORBIDDEN

    monkeypatch.setattr(api, "get_user_id", lambda user: "42")
    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "invalid-tenant")
    malformed = view.mark_read(_request("post"), pk="existing")
    assert malformed.status_code == status.HTTP_400_BAD_REQUEST


def test_notification_bulk_actions_handle_missing_and_malformed_identity(monkeypatch, tenant_and_user):
    tenant_id, user_uuid = tenant_and_user
    monkeypatch.setattr(api.NotificationService, "mark_all_read", lambda tenant_arg, user_arg: 3)
    monkeypatch.setattr(
        api.NotificationService,
        "get_user_notifications",
        lambda tenant_arg, user_arg, unread_only: ["one", "two"],
    )

    view = api.NotificationViewSet()
    mark_all = view.mark_all_read(_request("post"))
    unread = view.unread_count(_request())

    assert mark_all.status_code == status.HTTP_200_OK
    assert mark_all.data == {"count": 3}
    assert unread.data == {"count": 2}

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: None)
    assert view.mark_all_read(_request("post")).status_code == status.HTTP_403_FORBIDDEN
    assert view.unread_count(_request()).data == {"count": 0}

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "invalid-tenant")
    monkeypatch.setattr(api, "get_user_id", lambda user: "42")
    malformed = view.mark_all_read(_request("post"))
    assert malformed.status_code == status.HTTP_400_BAD_REQUEST
    assert view.unread_count(_request()).data == {"count": 0}


def test_preference_queryset_and_create_bind_authenticated_identity(monkeypatch, tenant_and_user):
    tenant_id, user_uuid = tenant_and_user
    manager = _ManagerRecorder()
    monkeypatch.setattr(api.NotificationPreference, "objects", manager)

    view = api.NotificationPreferenceViewSet()
    view.request = _request()

    assert view.get_queryset() is manager.query
    assert manager.filter_kwargs == {"tenant_id": tenant_id, "user_id": user_uuid}

    class Serializer:
        saved: dict[str, uuid.UUID] | None = None

        def save(self, **kwargs):
            self.saved = kwargs

    serializer = Serializer()
    view.perform_create(serializer)
    assert serializer.saved == {"tenant_id": tenant_id, "user_id": user_uuid}

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "")
    assert list(view.get_queryset()) == []
    with pytest.raises(ValidationError):
        view.perform_create(Serializer())

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "invalid-tenant")
    monkeypatch.setattr(api, "get_user_id", lambda user: "42")
    assert list(view.get_queryset()) == []
    with pytest.raises(ValidationError):
        view.perform_create(Serializer())


def test_user_id_conversion_is_deterministic_and_rejects_empty_values():
    existing = uuid.uuid4()
    assert api._convert_user_id_to_uuid(str(existing)) == existing
    assert api._convert_user_id_to_uuid("42") == api._convert_user_id_to_uuid("42")
    with pytest.raises(ValueError, match="cannot be empty"):
        api._convert_user_id_to_uuid("")
