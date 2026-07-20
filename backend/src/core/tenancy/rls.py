"""Typed PostgreSQL row-level-security tenant context.

PostgreSQL's ``SET LOCAL`` lifetime is a transaction, not a request or a
Python call frame.  This module makes that constraint explicit: both web
middleware and background workers enter :func:`tenant_context`, which owns an
atomic transaction and installs a validated UUID in ``app.tenant_id``.

Worker tasks should wrap their callable with :func:`tenant_context_worker` and
must receive ``tenant_id`` as a keyword argument.  Missing or malformed tenant
identity fails closed before business logic executes.
"""

from __future__ import annotations

import contextvars
import functools
from collections.abc import Callable, Generator
from contextlib import contextmanager, nullcontext
from typing import ParamSpec, TypeVar, cast
from uuid import UUID

from django.db import DEFAULT_DB_ALIAS, connections, transaction

TENANT_SETTING = "app.tenant_id"

_tenant_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "saraise_tenant_id",
    default=None,
)

P = ParamSpec("P")
R = TypeVar("R")


class InvalidTenantContext(ValueError):
    """Raised when a tenant identifier is not a valid UUID."""


class MissingTenantContext(PermissionError):
    """Raised when tenant-scoped worker code receives no tenant identifier."""


def _as_uuid(tenant_id: UUID | str) -> UUID:
    """Return a canonical UUID or fail before any database statement runs."""
    if isinstance(tenant_id, UUID):
        return tenant_id
    try:
        return UUID(str(tenant_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidTenantContext("tenant_id must be a valid UUID") from exc


def get_current_tenant_id() -> UUID | None:
    """Return the tenant bound to the current Python execution context."""
    return _tenant_id.get()


def _set_database_context(tenant_id: UUID, *, using: str) -> None:
    """Install the transaction-local PostgreSQL setting.

    ``set_config(..., true)`` is the parameter-safe equivalent of ``SET
    LOCAL``.  Refusing to run without an active transaction prevents the
    setting from disappearing immediately under Django autocommit.
    """
    connection = connections[using]
    if connection.vendor != "postgresql":
        return
    if not connection.in_atomic_block:
        raise RuntimeError("PostgreSQL tenant context requires an active transaction")

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, true)",
            [TENANT_SETTING, str(tenant_id)],
        )


@contextmanager
def tenant_context(
    tenant_id: UUID | str,
    *,
    using: str = DEFAULT_DB_ALIAS,
) -> Generator[UUID, None, None]:
    """Bind a typed tenant to Python and the database for one transaction."""
    canonical_tenant_id = _as_uuid(tenant_id)
    token = _tenant_id.set(canonical_tenant_id)
    try:
        connection = connections[using]
        transaction_scope = transaction.atomic(using=using) if connection.vendor == "postgresql" else nullcontext()
        with transaction_scope:
            _set_database_context(canonical_tenant_id, using=using)
            yield canonical_tenant_id
    finally:
        _tenant_id.reset(token)


def tenant_context_worker(
    function: Callable[P, R],
) -> Callable[P, R]:
    """Make a worker callable require and install its ``tenant_id`` keyword.

    The decorated function keeps ``tenant_id`` in its public signature and
    receives the canonical UUID value.  This works with Celery, RQ, Django-Q,
    or an in-process executor without coupling isolation to one queue vendor.
    """

    @functools.wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        tenant_value = kwargs.get("tenant_id")
        if tenant_value is None:
            raise MissingTenantContext(f"worker {function.__module__}.{function.__qualname__} requires tenant_id")
        tenant_id = cast(UUID | str, tenant_value)
        with tenant_context(tenant_id) as canonical_tenant_id:
            kwargs["tenant_id"] = canonical_tenant_id
            return function(*args, **kwargs)

    wrapped.isolation_contract = "tenant_context"  # type: ignore[attr-defined]
    return wrapped
