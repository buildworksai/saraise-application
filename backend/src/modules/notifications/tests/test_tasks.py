from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import HandlerAlreadyRegistered, get_handler
from src.core.tenancy import MissingTenantContext
from src.modules.notifications import tasks


def job(command: str, **payload: object) -> AsyncJob:
    tenant = uuid.uuid4()
    return AsyncJob(
        tenant_id=tenant,
        actor_id=str(uuid.uuid4()),
        command=command,
        idempotency_key="test",
        payload={"tenant_id": str(tenant), **payload},
        correlation_id=str(uuid.uuid4()),
    )


def test_every_command_is_registered_idempotently():
    tasks.register_async_handlers()
    tasks.register_async_handlers()
    assert all(callable(get_handler(command)) for command in tasks.COMMANDS)


def test_registration_rejects_different_owner(monkeypatch):
    monkeypatch.setattr(tasks, "get_handler", lambda command: object())
    with pytest.raises(HandlerAlreadyRegistered):
        tasks.register_async_handlers()


@pytest.mark.parametrize("field", ["recipient", "body", "rendered_subject", "token", "credential"])
def test_registered_handler_rejects_sensitive_payload(field):
    value = job(tasks.EXECUTE_DELIVERY_COMMAND, delivery_id=str(uuid.uuid4()), **{field: "secret"})
    with pytest.raises(ValueError, match="sensitive"):
        get_handler(tasks.EXECUTE_DELIVERY_COMMAND)(value)


def test_handler_rejects_wrong_command_payload_shape_and_tenant():
    value = job(tasks.EXECUTE_DELIVERY_COMMAND, delivery_id=str(uuid.uuid4()))
    value.command = "wrong"
    with pytest.raises(ValueError, match="accepts only"):
        tasks._execute_handler(value)
    value.command = tasks.EXECUTE_DELIVERY_COMMAND
    value.payload = []
    with pytest.raises(ValueError, match="object"):
        tasks._execute_handler(value)
    value.payload = {"tenant_id": str(uuid.uuid4()), "delivery_id": str(uuid.uuid4())}
    with pytest.raises(PermissionError, match="tenant"):
        tasks._execute_handler(value)


@pytest.mark.parametrize("value", [None, "bad", "", 0, 501, True])
def test_process_due_rejects_invalid_limits(value):
    with pytest.raises(ValueError, match="limit"):
        tasks._process_due_handler(job(tasks.PROCESS_DUE_COMMAND, limit=value))


def test_handlers_validate_identifiers_dates_and_provider_event():
    with pytest.raises(ValueError, match="delivery_id"):
        tasks._execute_handler(job(tasks.EXECUTE_DELIVERY_COMMAND, delivery_id="bad"))
    with pytest.raises(ValueError, match="cutoff"):
        tasks._purge_handler(job(tasks.PURGE_RETENTION_COMMAND, cutoff="2025-01-01"))
    with pytest.raises(ValueError, match="provider_event"):
        tasks._confirm_handler(job(tasks.CONFIRM_DELIVERY_COMMAND, delivery_id=str(uuid.uuid4()), provider_event=[]))
    with pytest.raises(ValueError, match="non-canonical"):
        tasks._confirm_handler(job(tasks.CONFIRM_DELIVERY_COMMAND, delivery_id=str(uuid.uuid4()), provider_event={"secret": "x"}, idempotency_key="k"))
    with pytest.raises(ValueError, match="idempotency_key"):
        tasks._confirm_handler(job(tasks.CONFIRM_DELIVERY_COMMAND, delivery_id=str(uuid.uuid4()), provider_event={}, idempotency_key=""))


def test_handlers_delegate_only_normalized_values(monkeypatch):
    delivery_id = uuid.uuid4(); endpoint_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "execute_delivery_worker", lambda **kwargs: kwargs)
    assert tasks._execute_handler(job(tasks.EXECUTE_DELIVERY_COMMAND, delivery_id=str(delivery_id)))["delivery_id"] == delivery_id
    monkeypatch.setattr(tasks, "process_due_worker", lambda **kwargs: kwargs)
    assert tasks._process_due_handler(job(tasks.PROCESS_DUE_COMMAND, limit=500))["limit"] == 500
    monkeypatch.setattr(tasks, "purge_retention_worker", lambda **kwargs: kwargs)
    result = tasks._purge_handler(job(tasks.PURGE_RETENTION_COMMAND, cutoff="2025-01-01T00:00:00+00:00"))
    assert result["cutoff"].tzinfo is not None
    monkeypatch.setattr(tasks, "verify_endpoint_worker", lambda **kwargs: kwargs)
    assert tasks._verify_endpoint_handler(job(tasks.VERIFY_ENDPOINT_COMMAND, endpoint_id=str(endpoint_id)))["endpoint_id"] == endpoint_id
    monkeypatch.setattr(tasks, "confirm_delivery_worker", lambda **kwargs: kwargs)
    confirmed = tasks._confirm_handler(job(tasks.CONFIRM_DELIVERY_COMMAND, delivery_id=str(delivery_id), provider_event={"provider_message_id": "p", "signature_verified": True}, idempotency_key="key"))
    assert confirmed["provider_event"]["signature_verified"] is True


def test_workers_require_and_install_tenant_context(monkeypatch):
    with pytest.raises(MissingTenantContext):
        tasks.execute_delivery_worker(delivery_id=uuid.uuid4())
    tenant = uuid.uuid4(); delivery_id = uuid.uuid4(); endpoint_id = uuid.uuid4(); actor = uuid.uuid4()
    from src.modules.notifications.services import NotificationDispatchService, NotificationEndpointService, OperationResult
    monkeypatch.setattr(NotificationDispatchService, "execute_delivery", lambda tenant, identifier: SimpleNamespace(id=identifier, status="delivered"))
    monkeypatch.setattr(NotificationDispatchService, "process_due", lambda tenant, limit: [OperationResult(delivery_id, "queued", uuid.uuid4())])
    monkeypatch.setattr(NotificationDispatchService, "confirm_delivery", lambda *args: SimpleNamespace(id=delivery_id, status="delivered"))
    monkeypatch.setattr(NotificationDispatchService, "purge_expired", lambda tenant, cutoff: {"inbox_deleted": 2})
    monkeypatch.setattr(NotificationEndpointService, "verify", lambda *args: SimpleNamespace(id=endpoint_id, last_verified_at=datetime.now(timezone.utc)))
    assert tasks.execute_delivery_worker(tenant_id=tenant, delivery_id=delivery_id)["status"] == "delivered"
    assert tasks.process_due_worker(tenant_id=tenant, limit=1)["processed"] == 1
    assert tasks.confirm_delivery_worker(tenant_id=tenant, delivery_id=delivery_id, provider_event={}, idempotency_key="k")["status"] == "delivered"
    assert tasks.purge_retention_worker(tenant_id=tenant, cutoff=datetime.now(timezone.utc))["inbox_deleted"] == 2
    assert tasks.verify_endpoint_worker(tenant_id=tenant, endpoint_id=endpoint_id, actor_id=actor)["verified"] is True
