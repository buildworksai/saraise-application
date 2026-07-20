"""Tests for safe structured logging."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import date
from decimal import Decimal

from src.core.observability.correlation import (
    CorrelationContext,
    TaskContext,
    bind_correlation_context,
    bind_task_context,
)
from src.core.observability.logging import REDACTED, JSONFormatter, ObservabilityContextFilter, redact_value


def _record(message: str = "operation completed") -> logging.LogRecord:
    return logging.LogRecord(
        name="src.core.tests",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_json_formatter_emits_required_shape_with_null_context() -> None:
    payload = json.loads(JSONFormatter().format(_record()))

    assert set(
        (
            "timestamp",
            "level",
            "logger",
            "message",
            "correlation_id",
            "tenant_id",
            "actor_id",
            "request_id",
            "job_id",
            "task_id",
        )
    ).issubset(payload)
    assert payload["timestamp"].endswith("Z")
    assert payload["level"] == "INFO"
    assert payload["logger"] == "src.core.tests"
    assert payload["correlation_id"] is None
    assert payload["request_id"] is None
    assert payload["job_id"] is None


def test_json_formatter_uses_http_context_and_explicit_fields_take_precedence() -> None:
    correlation_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    context = CorrelationContext(
        correlation_id=correlation_id,
        request_id="request-hop",
        tenant_id=tenant_id,
        actor_id="actor-1",
    )
    record = _record()
    record.actor_id = "explicit-actor"  # type: ignore[attr-defined]

    with bind_correlation_context(context):
        ObservabilityContextFilter().filter(record)
        payload = json.loads(JSONFormatter().format(record))

    assert payload["correlation_id"] == str(correlation_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["actor_id"] == "explicit-actor"
    assert payload["request_id"] == "request-hop"
    assert payload["job_id"] is None


def test_json_formatter_uses_task_context() -> None:
    correlation_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    context = TaskContext(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        actor_id="system-worker",
        causation_id="parent-job",
        job_id="current-job",
    )

    with bind_task_context(context):
        payload = json.loads(JSONFormatter().format(_record("task completed")))

    assert payload["correlation_id"] == str(correlation_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["actor_id"] == "system-worker"
    assert payload["job_id"] == "current-job"
    assert payload["task_id"] == "current-job"
    assert payload["causation_id"] == "parent-job"


def test_json_formatter_redacts_secret_keys_values_and_never_log_content() -> None:
    canaries = {
        "password": "PASSWORD-CANARY",  # pragma: allowlist secret
        "nested_token": "TOKEN-CANARY",
        "document": "DOCUMENT-CANARY",
        "provider": "PROVIDER-CANARY",
        "connection": "DATABASE-CANARY",
        "message": "MESSAGE-CANARY",
    }
    record = _record(
        "login token=MESSAGE-CANARY; provider response body: PROVIDER-MESSAGE-CANARY; " "repeated PASSWORD-CANARY"
    )
    record.password = canaries["password"]  # type: ignore[attr-defined]
    record.details = {  # type: ignore[attr-defined]
        "credentials_blob": {"value": canaries["nested_token"]},
        "document_content": canaries["document"],
        "provider_response_body_raw": canaries["provider"],
        "connection_string": canaries["connection"],
        "safe_count": 4,
    }

    rendered = JSONFormatter().format(record)
    payload = json.loads(rendered)

    assert REDACTED in rendered
    assert payload["details"]["safe_count"] == 4
    for canary in (*canaries.values(), "PROVIDER-MESSAGE-CANARY"):
        assert canary not in rendered


def test_json_formatter_does_not_serialize_raw_exception_message() -> None:
    record = _record("provider request failed")
    try:
        raise RuntimeError("UNLABELLED-EXCEPTION-SECRET")
    except RuntimeError:
        record.exc_info = sys.exc_info()

    payload = json.loads(JSONFormatter().format(record))
    rendered = json.dumps(payload)

    assert "UNLABELLED-EXCEPTION-SECRET" not in rendered
    assert payload["error"] == {"type": "RuntimeError", "code": None, "retryable": False}


def test_json_formatter_removes_unstructured_provider_and_document_bodies() -> None:
    provider_log = JSONFormatter().format(_record("OpenAI API request failed: RAW-PROVIDER-CANARY"))
    document_log = JSONFormatter().format(_record("document content: RAW-DOCUMENT-CANARY"))

    assert "RAW-PROVIDER-CANARY" not in provider_log
    assert "RAW-DOCUMENT-CANARY" not in document_log
    assert REDACTED in provider_log
    assert REDACTED in document_log


def test_redaction_is_cycle_safe_depth_limited_and_json_compatible() -> None:
    cyclic: dict[str, object] = {
        "safe_uuid": uuid.uuid4(),
        "safe_date": date(2026, 7, 20),
        "safe_decimal": Decimal("1.25"),
    }
    cyclic["self"] = cyclic
    deep: object = "leaf"
    for _ in range(12):
        deep = {"safe": deep}
    cyclic["deep"] = deep

    sanitized = redact_value(cyclic)
    rendered = json.dumps(sanitized)

    assert "<recursive>" in rendered
    assert "<max-depth>" in rendered
    assert "2026-07-20" in rendered
    assert "1.25" in rendered


def test_redaction_bounds_collections_strings_and_handles_bytes() -> None:
    sanitized = redact_value(
        {
            "safe_bytes": b"hello",
            "safe_items": list(range(150)),
            "safe_long": "x" * 9000,
        }
    )

    assert sanitized["safe_bytes"] == "hello"  # type: ignore[index]
    assert len(sanitized["safe_items"]) == 100  # type: ignore[arg-type,index]
    assert str(sanitized["safe_long"]).endswith("...[TRUNCATED]")  # type: ignore[index]


def test_formatter_accepts_allowlisted_structured_error() -> None:
    record = _record("dependency failed")
    record.error = {  # type: ignore[attr-defined]
        "type": "DependencyTimeout",
        "code": "dependency_timeout",
        "retryable": True,
        "raw_message": "MUST-NOT-APPEAR",
    }

    rendered = JSONFormatter().format(record)
    payload = json.loads(rendered)

    assert payload["error"] == {
        "type": "DependencyTimeout",
        "code": "dependency_timeout",
        "retryable": True,
    }
    assert "MUST-NOT-APPEAR" not in rendered
