"""Correlation contracts for HTTP requests and Celery task boundaries.

``ContextVar`` state is process-local. Celery therefore receives a serialized
``TaskContext`` in message headers and restores it in the worker before task
execution. The signal handlers in this module are registered on import.
"""

from __future__ import annotations

import contextvars
import logging
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterator, Mapping, MutableMapping

from celery.signals import before_task_publish, task_postrun, task_prerun
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("saraise.observability.correlation")

CORRELATION_HEADER = "X-Correlation-ID"
REQUEST_HEADER = "X-Request-ID"
TASK_CORRELATION_HEADER = "saraise-correlation-id"
TASK_TENANT_HEADER = "saraise-tenant-id"
TASK_ACTOR_HEADER = "saraise-actor-id"
TASK_CAUSATION_HEADER = "saraise-causation-id"
TASK_JOB_HEADER = "saraise-job-id"

_HEADER_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _as_uuid(value: object, field_name: str) -> uuid.UUID:
    """Return a UUID value or reject malformed context at the boundary."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def _optional_uuid(value: object | None, field_name: str) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    return _as_uuid(value, field_name)


def _optional_identifier(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    identifier = str(value)
    if not _HEADER_VALUE_PATTERN.fullmatch(identifier):
        raise ValueError("context identifiers may only contain safe header characters")
    return identifier


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    """Request-scoped identity available to synchronous and async HTTP code."""

    correlation_id: uuid.UUID
    request_id: str
    tenant_id: uuid.UUID | None = None
    actor_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "correlation_id", _as_uuid(self.correlation_id, "correlation_id"))
        request_id = _optional_identifier(self.request_id)
        if request_id is None:
            raise ValueError("request_id is required")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "tenant_id", _optional_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "actor_id", _optional_identifier(self.actor_id))


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Serializable identity propagated from a publisher into a Celery worker."""

    correlation_id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    actor_id: str | None = None
    causation_id: str | None = None
    job_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "correlation_id", _as_uuid(self.correlation_id, "correlation_id"))
        object.__setattr__(self, "tenant_id", _optional_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "actor_id", _optional_identifier(self.actor_id))
        object.__setattr__(self, "causation_id", _optional_identifier(self.causation_id))
        object.__setattr__(self, "job_id", _optional_identifier(self.job_id))

    @classmethod
    def from_http(
        cls,
        context: CorrelationContext,
        *,
        job_id: object | None = None,
    ) -> TaskContext:
        """Create task identity from the active request context."""
        return cls(
            correlation_id=context.correlation_id,
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            causation_id=context.request_id,
            job_id=_optional_identifier(job_id),
        )

    @classmethod
    def from_headers(cls, headers: Mapping[str, object]) -> TaskContext:
        """Validate and deserialize context from a Celery message header."""
        return cls(
            correlation_id=_as_uuid(headers[TASK_CORRELATION_HEADER], "correlation_id"),
            tenant_id=_optional_uuid(headers.get(TASK_TENANT_HEADER), "tenant_id"),
            actor_id=_optional_identifier(headers.get(TASK_ACTOR_HEADER)),
            causation_id=_optional_identifier(headers.get(TASK_CAUSATION_HEADER)),
            job_id=_optional_identifier(headers.get(TASK_JOB_HEADER)),
        )

    def to_headers(self) -> dict[str, str]:
        """Serialize only the allowlisted context contract."""
        headers = {TASK_CORRELATION_HEADER: str(self.correlation_id)}
        optional_headers = {
            TASK_TENANT_HEADER: self.tenant_id,
            TASK_ACTOR_HEADER: self.actor_id,
            TASK_CAUSATION_HEADER: self.causation_id,
            TASK_JOB_HEADER: self.job_id,
        }
        for key, value in optional_headers.items():
            if value is not None:
                headers[key] = str(value)
        return headers

    def for_child(self, job_id: object | None) -> TaskContext:
        """Carry identity to a child job and record the current job as cause."""
        return replace(
            self,
            causation_id=self.job_id or self.causation_id,
            job_id=_optional_identifier(job_id),
        )


correlation_context: contextvars.ContextVar[CorrelationContext | None] = contextvars.ContextVar(
    "correlation_context",
    default=None,
)
task_context: contextvars.ContextVar[TaskContext | None] = contextvars.ContextVar("task_context", default=None)
_task_signal_tokens: contextvars.ContextVar[tuple[object, object] | None] = contextvars.ContextVar(
    "task_signal_tokens",
    default=None,
)

# Compatibility for integrations that previously bound a string ContextVar.
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def get_correlation_context() -> CorrelationContext | None:
    """Return the active HTTP context, if execution is inside a request."""
    return correlation_context.get()


def get_task_context() -> TaskContext | None:
    """Return the active worker/publisher context, if one has been bound."""
    return task_context.get()


def get_correlation_id() -> str:
    """Return the active correlation UUID as a string, or an empty string."""
    active_task = get_task_context()
    if active_task is not None:
        return str(active_task.correlation_id)
    active_request = get_correlation_context()
    if active_request is not None:
        return str(active_request.correlation_id)
    return correlation_id_var.get()


@contextmanager
def bind_correlation_context(context: CorrelationContext) -> Iterator[CorrelationContext]:
    """Bind HTTP context for a bounded block and always restore prior state."""
    context_token = correlation_context.set(context)
    legacy_token = correlation_id_var.set(str(context.correlation_id))
    try:
        yield context
    finally:
        correlation_id_var.reset(legacy_token)
        correlation_context.reset(context_token)


@contextmanager
def bind_task_context(context: TaskContext) -> Iterator[TaskContext]:
    """Bind task context for publishers and direct/eager task execution."""
    context_token = task_context.set(context)
    legacy_token = correlation_id_var.set(str(context.correlation_id))
    try:
        yield context
    finally:
        correlation_id_var.reset(legacy_token)
        task_context.reset(context_token)


def _valid_incoming_uuid(value: object | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        parsed = _as_uuid(str(value), "correlation_id")
    except ValueError:
        return None
    return parsed


def _request_id(request: HttpRequest, correlation_id: uuid.UUID) -> str:
    del request, correlation_id
    return str(uuid.uuid4())


def _request_identity(request: HttpRequest) -> tuple[uuid.UUID | None, str | None]:
    """Read already-authenticated identity without trusting arbitrary headers."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None, None

    actor_id = _optional_identifier(getattr(user, "id", None))
    tenant_value = getattr(request, "tenant_id", None) or getattr(user, "tenant_id", None)
    if tenant_value is None:
        profile = getattr(user, "profile", None)
        tenant_value = getattr(profile, "tenant_id", None)
    try:
        tenant_id = _optional_uuid(tenant_value, "tenant_id")
    except ValueError:
        tenant_id = None
    return tenant_id, actor_id


class CorrelationMiddleware:
    """Validate/generate a UUID correlation ID and echo it on every response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        correlation_id = _valid_incoming_uuid(request.headers.get(CORRELATION_HEADER)) or uuid.uuid4()
        request_id = _request_id(request, correlation_id)
        tenant_id, actor_id = _request_identity(request)
        context = CorrelationContext(
            correlation_id=correlation_id,
            request_id=request_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )

        request.correlation_id = str(correlation_id)  # type: ignore[attr-defined]
        request.request_id = request_id  # type: ignore[attr-defined]

        with bind_correlation_context(context):
            response = self.get_response(request)

        response[CORRELATION_HEADER] = str(correlation_id)
        response[REQUEST_HEADER] = request_id
        return response


# Historical class name remains supported for installed deployments.
CorrelationIdMiddleware = CorrelationMiddleware


class ObservabilityIdentityMiddleware:
    """Enrich the early HTTP context after Django authentication has run."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        active = get_correlation_context()
        if active is None:
            return self.get_response(request)
        tenant_id, actor_id = _request_identity(request)
        if tenant_id is None and actor_id is None:
            return self.get_response(request)
        with bind_correlation_context(replace(active, tenant_id=tenant_id, actor_id=actor_id)):
            return self.get_response(request)


def _published_job_id(headers: Mapping[str, object] | None) -> object | None:
    return headers.get("id") if headers is not None else None


@before_task_publish.connect(  # type: ignore[untyped-decorator]
    dispatch_uid="saraise.observability.before_task_publish", weak=False
)
def inject_task_context(
    sender: str | None = None,
    headers: MutableMapping[str, object] | None = None,
    body: object | None = None,
    **kwargs: Any,
) -> None:
    """Add the allowlisted context contract to outgoing Celery headers."""
    del sender, body, kwargs
    if headers is None:
        return

    job_id = _published_job_id(headers)
    active_task = get_task_context()
    active_request = get_correlation_context()
    if active_task is not None:
        outgoing = active_task.for_child(job_id)
    elif active_request is not None:
        outgoing = TaskContext.from_http(active_request, job_id=job_id)
    else:
        outgoing = TaskContext(correlation_id=uuid.uuid4(), job_id=_optional_identifier(job_id))
    headers.update(outgoing.to_headers())


def _task_headers(task: object | None) -> Mapping[str, object]:
    request = getattr(task, "request", None)
    headers = getattr(request, "headers", None)
    return headers if isinstance(headers, Mapping) else {}


@task_prerun.connect(dispatch_uid="saraise.observability.task_prerun", weak=False)  # type: ignore[untyped-decorator]
def restore_task_context(
    sender: object | None = None,
    task_id: str | None = None,
    task: object | None = None,
    args: object | None = None,
    kwargs: object | None = None,
    **extras: Any,
) -> None:
    """Restore publisher identity in the worker before task code executes."""
    del args, kwargs, extras
    active_task = task or sender
    headers = _task_headers(active_task)
    try:
        restored = TaskContext.from_headers(headers)
        if restored.job_id is None and task_id is not None:
            restored = replace(restored, job_id=_optional_identifier(task_id))
    except (KeyError, TypeError, ValueError):
        logger.warning("Celery task arrived without valid observability context")
        restored = TaskContext(correlation_id=uuid.uuid4(), job_id=_optional_identifier(task_id))

    context_token = task_context.set(restored)
    legacy_token = correlation_id_var.set(str(restored.correlation_id))
    _task_signal_tokens.set((context_token, legacy_token))


@task_postrun.connect(dispatch_uid="saraise.observability.task_postrun", weak=False)  # type: ignore[untyped-decorator]
def clear_task_context(
    sender: object | None = None,
    task_id: str | None = None,
    task: object | None = None,
    args: object | None = None,
    kwargs: object | None = None,
    retval: object | None = None,
    state: str | None = None,
    **extras: Any,
) -> None:
    """Prevent one worker job's identity from leaking into the next job."""
    del sender, task_id, args, kwargs, retval, state, extras
    tokens = _task_signal_tokens.get()
    if not tokens:
        return
    context_token, legacy_token = tokens
    correlation_id_var.reset(legacy_token)  # type: ignore[arg-type]
    task_context.reset(context_token)  # type: ignore[arg-type]
    _task_signal_tokens.set(None)
