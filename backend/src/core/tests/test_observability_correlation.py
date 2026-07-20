"""Tests for HTTP and Celery correlation boundaries."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from src.core.observability.correlation import (
    CORRELATION_HEADER,
    REQUEST_HEADER,
    TASK_ACTOR_HEADER,
    TASK_CAUSATION_HEADER,
    TASK_CORRELATION_HEADER,
    TASK_JOB_HEADER,
    TASK_TENANT_HEADER,
    CorrelationContext,
    CorrelationMiddleware,
    ObservabilityIdentityMiddleware,
    TaskContext,
    bind_correlation_context,
    bind_task_context,
    clear_task_context,
    get_correlation_context,
    get_correlation_id,
    get_task_context,
    inject_task_context,
    restore_task_context,
)


def test_correlation_middleware_generates_uuid_echoes_headers_and_cleans_context() -> None:
    observed: dict[str, object] = {}

    def get_response(request: HttpRequest) -> HttpResponse:
        observed["request_correlation_id"] = request.correlation_id  # type: ignore[attr-defined]
        observed["context"] = get_correlation_context()
        return HttpResponse(status=204)

    response = CorrelationMiddleware(get_response)(RequestFactory().get("/health"))
    generated = uuid.UUID(response[CORRELATION_HEADER])

    assert str(generated) == observed["request_correlation_id"]
    assert isinstance(observed["context"], CorrelationContext)
    assert response[REQUEST_HEADER] != response[CORRELATION_HEADER]
    assert uuid.UUID(response[REQUEST_HEADER])
    assert get_correlation_context() is None
    assert get_correlation_id() == ""


def test_correlation_middleware_reuses_valid_inbound_uuid_and_replaces_invalid_id() -> None:
    inbound = uuid.uuid4()
    factory = RequestFactory()
    middleware = CorrelationMiddleware(lambda request: HttpResponse(status=200))

    reused = middleware(factory.get("/", HTTP_X_CORRELATION_ID=str(inbound)))
    replaced = middleware(factory.get("/", HTTP_X_CORRELATION_ID="req_legacy-not-a-uuid"))

    assert reused[CORRELATION_HEADER] == str(inbound)
    assert uuid.UUID(replaced[CORRELATION_HEADER])
    assert replaced[CORRELATION_HEADER] != "req_legacy-not-a-uuid"


def test_correlation_middleware_cleans_context_when_downstream_raises() -> None:
    def fail(request: HttpRequest) -> HttpResponse:
        del request
        assert get_correlation_context() is not None
        raise RuntimeError("downstream failed")

    with pytest.raises(RuntimeError, match="downstream failed"):
        CorrelationMiddleware(fail)(RequestFactory().get("/"))

    assert get_correlation_context() is None
    assert get_correlation_id() == ""


def test_post_auth_middleware_enriches_context_for_view_and_restores_it() -> None:
    tenant_id = uuid.uuid4()
    observed: dict[str, object] = {}

    def view(request: HttpRequest) -> HttpResponse:
        del request
        observed["context"] = get_correlation_context()
        return HttpResponse(status=200)

    identity_middleware = ObservabilityIdentityMiddleware(view)

    def authentication_layer(request: HttpRequest) -> HttpResponse:
        request.user = SimpleNamespace(  # type: ignore[attr-defined]
            id=42,
            is_authenticated=True,
            profile=SimpleNamespace(tenant_id=tenant_id),
        )
        return identity_middleware(request)

    response = CorrelationMiddleware(authentication_layer)(RequestFactory().get("/"))
    context = observed["context"]

    assert isinstance(context, CorrelationContext)
    assert context.tenant_id == tenant_id
    assert context.actor_id == "42"
    assert response.status_code == 200
    assert get_correlation_context() is None


def test_task_context_round_trip_through_publish_prerun_and_postrun() -> None:
    correlation_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    parent = TaskContext(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        actor_id="actor-7",
        causation_id="root-request",
        job_id="parent-job",
    )
    headers: dict[str, object] = {"id": "child-job", "existing": "preserved"}

    with bind_task_context(parent):
        inject_task_context(headers=headers)

    assert get_task_context() is None
    assert headers["existing"] == "preserved"
    assert headers[TASK_CORRELATION_HEADER] == str(correlation_id)
    assert headers[TASK_TENANT_HEADER] == str(tenant_id)
    assert headers[TASK_ACTOR_HEADER] == "actor-7"
    assert headers[TASK_CAUSATION_HEADER] == "parent-job"
    assert headers[TASK_JOB_HEADER] == "child-job"

    task = SimpleNamespace(request=SimpleNamespace(headers=headers))
    restore_task_context(task=task, task_id="child-job")
    restored = get_task_context()
    try:
        assert restored is not None
        assert restored.correlation_id == correlation_id
        assert restored.tenant_id == tenant_id
        assert restored.actor_id == "actor-7"
        assert restored.causation_id == "parent-job"
        assert get_correlation_id() == str(correlation_id)
    finally:
        clear_task_context(task=task)

    assert get_task_context() is None
    assert get_correlation_id() == ""


def test_http_context_is_serialized_at_publish_boundary() -> None:
    correlation_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    http_context = CorrelationContext(
        correlation_id=correlation_id,
        request_id="request-hop",
        tenant_id=tenant_id,
        actor_id="actor-http",
    )
    headers: dict[str, object] = {"id": "new-job"}

    with bind_correlation_context(http_context):
        inject_task_context(headers=headers)

    assert headers[TASK_CORRELATION_HEADER] == str(correlation_id)
    assert headers[TASK_TENANT_HEADER] == str(tenant_id)
    assert headers[TASK_ACTOR_HEADER] == "actor-http"
    assert headers[TASK_CAUSATION_HEADER] == "request-hop"


def test_prerun_uses_sender_and_invalid_headers_do_not_retain_prior_context() -> None:
    prior = TaskContext(correlation_id=uuid.uuid4(), job_id="prior-job")
    sender = SimpleNamespace(request=SimpleNamespace(headers={TASK_CORRELATION_HEADER: "invalid"}))

    with bind_task_context(prior):
        restore_task_context(sender=sender, task_id="replacement-job")
        restored = get_task_context()
        try:
            assert restored is not None
            assert restored.correlation_id != prior.correlation_id
            assert restored.job_id == "replacement-job"
        finally:
            clear_task_context(sender=sender)

        assert get_task_context() == prior
