"""Safe JSON logging for SARAISE application and extension modules."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from django.conf import settings

from src.core.observability.correlation import get_correlation_context, get_task_context

REDACTED = "***REDACTED***"
MAX_LOG_DEPTH = 8
MAX_LOG_ITEMS = 100
MAX_LOG_STRING_LENGTH = 8192

_SECURITY_KEY_PATTERN = re.compile(
    r"password|passphrase|passwd|pwd|secret|token|credential|authorization|cookie|session|csrf|signature|"
    r"api[_-]?key|private[_-]?key|access[_-]?key|connection[_-]?string|dsn",
    re.IGNORECASE,
)
_CONTENT_KEY_PATTERN = re.compile(
    r"^(?:content|body|payload|prompt|completion|embeddings?|raw[_-]?model[_-]?output|ocr[_-]?text|"
    r"extracted[_-]?text|page[_-]?content|document[_-]?(?:bytes|content|body|text)|"
    r"provider[_-]?(?:body|request|response)(?:[_-].*)?|request[_-]?body|response[_-]?body|"
    r"webhook[_-]?payload|(?:email|sms)[_-]?body|(?:file|upload)[_-]?(?:body|content))$",
    re.IGNORECASE,
)
_KEY_VALUE_PATTERN = re.compile(
    r"(?P<key>password|passphrase|passwd|pwd|secret|token|credential|authorization|proxy-authorization|"
    r"api[_-]?key|private[_-]?key|client[_-]?secret|access[_-]?key|session[_-]?id|cookie|set-cookie|"
    r"csrf|signature|webhook[_-]?secret|connection[_-]?string|dsn|provider[_-]?(?:body|request|response)|"
    r"document[_-]?(?:content|body|text)|ocr[_-]?text|extracted[_-]?text|page[_-]?content|"
    r"request[_-]?body|response[_-]?body|webhook[_-]?payload|(?:email|sms)[_-]?body|prompt|completion)"
    r"(?P<separator>[\"']?\s*[:=]\s*[\"']?)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIAL_PATTERN = re.compile(r"(?P<scheme>https?://)[^\s/@:]+:[^\s/@]+@", re.IGNORECASE)
_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_SENSITIVE_MESSAGE_PAYLOAD_PATTERN = re.compile(
    r"(?P<label>(?:provider[ _-]?(?:request|response)(?:[ _-]?body)?|"
    r"(?:http[ _-]?)?(?:request|response)[ _-]?body|document[ _-]?(?:bytes|content|body|text)|"
    r"(?:ocr|extracted)[ _-]?text|page[ _-]?content|webhook[ _-]?payload|(?:email|sms)[ _-]?body|"
    r"(?:file|upload)[ _-]?(?:body|content)|prompt|completion|embeddings?|raw[ _-]?model[ _-]?output)"
    r"\s*[:=]\s*).*$",
    re.IGNORECASE,
)
_PROVIDER_ERROR_BODY_PATTERN = re.compile(
    r"(?P<label>(?:OpenAI|Anthropic|Google Gemini|Groq|HuggingFace) API "
    r"(?:error:\s*\d{3}\s*-|request failed:)\s*).*$",
    re.IGNORECASE,
)

_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {
    "asctime",
    "message",
    "taskName",
}
_REQUIRED_FIELDS = {
    "timestamp",
    "level",
    "logger",
    "message",
    "service",
    "environment",
    "correlation_id",
    "tenant_id",
    "actor_id",
    "user_id",
    "request_id",
    "job_id",
    "task_id",
    "causation_id",
    "error",
}


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().replace("-", "_")
    return bool(_SECURITY_KEY_PATTERN.search(normalized) or _CONTENT_KEY_PATTERN.fullmatch(normalized))


def redact_text(value: str) -> str:
    """Remove common credential forms from unstructured text."""

    def replace_key_value(match: re.Match[str]) -> str:
        return f"{match.group('key')}{match.group('separator')}{REDACTED}"

    value = _KEY_VALUE_PATTERN.sub(replace_key_value, value)
    value = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)} {REDACTED}", value)
    value = _URL_CREDENTIAL_PATTERN.sub(lambda match: f"{match.group('scheme')}{REDACTED}@", value)
    value = _SENSITIVE_MESSAGE_PAYLOAD_PATTERN.sub(lambda match: f"{match.group('label')}{REDACTED}", value)
    value = _PROVIDER_ERROR_BODY_PATTERN.sub(lambda match: f"{match.group('label')}{REDACTED}", value)

    def mask_card(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return f"****{digits[-4:]}"

    redacted = _CARD_PATTERN.sub(mask_card, value)
    if len(redacted) > MAX_LOG_STRING_LENGTH:
        return f"{redacted[:MAX_LOG_STRING_LENGTH]}...[TRUNCATED]"
    return redacted


def redact_value(value: object, *, _seen: set[int] | None = None, _depth: int = 0) -> object:
    """Recursively sanitize values while preserving JSON-useful structure."""
    if _depth >= MAX_LOG_DEPTH:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (UUID, Decimal, date, datetime)):
        return str(value)
    if isinstance(value, bytes):
        return redact_text(value.decode("utf-8", errors="replace"))

    seen = _seen if _seen is not None else set()
    value_id = id(value)
    if value_id in seen:
        return "<recursive>"

    if isinstance(value, Mapping):
        seen.add(value_id)
        try:
            sanitized: dict[str, object] = {}
            for index, (raw_key, nested_value) in enumerate(value.items()):
                if index >= MAX_LOG_ITEMS:
                    sanitized["_truncated_items"] = len(value) - MAX_LOG_ITEMS
                    break
                key = str(raw_key)
                sanitized[key] = (
                    REDACTED if _is_sensitive_key(key) else redact_value(nested_value, _seen=seen, _depth=_depth + 1)
                )
            return sanitized
        finally:
            seen.remove(value_id)

    if isinstance(value, Sequence):
        seen.add(value_id)
        try:
            return [redact_value(item, _seen=seen, _depth=_depth + 1) for item in value[:MAX_LOG_ITEMS]]
        finally:
            seen.remove(value_id)

    return redact_text(str(value))


def _sensitive_literals(
    value: object,
    *,
    sensitive_parent: bool = False,
    seen: set[int] | None = None,
    depth: int = 0,
) -> set[str]:
    """Collect labelled secret values so repeats in the message are removed."""
    if depth >= MAX_LOG_DEPTH:
        return set()
    if isinstance(value, (str, bytes)):
        literal = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        return {literal} if sensitive_parent and len(literal) >= 4 else set()

    visited = seen if seen is not None else set()
    value_id = id(value)
    if value_id in visited:
        return set()
    if isinstance(value, Mapping):
        visited.add(value_id)
        try:
            literals: set[str] = set()
            for index, (key, nested) in enumerate(value.items()):
                if index >= MAX_LOG_ITEMS:
                    break
                literals.update(
                    _sensitive_literals(
                        nested,
                        sensitive_parent=sensitive_parent or _is_sensitive_key(key),
                        seen=visited,
                        depth=depth + 1,
                    )
                )
            return literals
        finally:
            visited.remove(value_id)
    if isinstance(value, Sequence):
        visited.add(value_id)
        try:
            literals = set()
            for item in value[:MAX_LOG_ITEMS]:
                literals.update(
                    _sensitive_literals(
                        item,
                        sensitive_parent=sensitive_parent,
                        seen=visited,
                        depth=depth + 1,
                    )
                )
            return literals
        finally:
            visited.remove(value_id)
    return set()


def current_log_context() -> dict[str, str | None]:
    """Build the common identity fields for formatters and logging filters."""
    active_task = get_task_context()
    active_request = get_correlation_context()
    if active_task is not None:
        return {
            "correlation_id": str(active_task.correlation_id),
            "tenant_id": str(active_task.tenant_id) if active_task.tenant_id else None,
            "actor_id": active_task.actor_id,
            "request_id": None,
            "job_id": active_task.job_id,
            "task_id": active_task.job_id,
            "causation_id": active_task.causation_id,
        }
    if active_request is not None:
        return {
            "correlation_id": str(active_request.correlation_id),
            "tenant_id": str(active_request.tenant_id) if active_request.tenant_id else None,
            "actor_id": active_request.actor_id,
            "request_id": active_request.request_id,
            "job_id": None,
            "task_id": None,
            "causation_id": None,
        }
    return {
        "correlation_id": None,
        "tenant_id": None,
        "actor_id": None,
        "request_id": None,
        "job_id": None,
        "task_id": None,
        "causation_id": None,
    }


class ObservabilityContextFilter(logging.Filter):
    """Attach active request/task identity without replacing explicit fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in current_log_context().items():
            if getattr(record, key, None) is None:
                setattr(record, key, value)
        if getattr(record, "user_id", None) is None:
            record.user_id = getattr(record, "actor_id", None)
        return True


class JSONFormatter(logging.Formatter):
    """Emit redacted, machine-readable logs with stable required fields."""

    def format(self, record: logging.LogRecord) -> str:
        context = current_log_context()
        actor_id = getattr(record, "actor_id", None) or getattr(record, "user_id", None) or context["actor_id"]
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds")
        message = redact_text(record.getMessage())
        for literal in _sensitive_literals(record.__dict__):
            message = message.replace(literal, REDACTED)
        entry: dict[str, object] = {
            "timestamp": timestamp.replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "service": getattr(settings, "SERVICE_NAME", "saraise-application"),
            "environment": getattr(settings, "SARAISE_MODE", "development"),
            "correlation_id": getattr(record, "correlation_id", None) or context["correlation_id"],
            "tenant_id": getattr(record, "tenant_id", None) or context["tenant_id"],
            "actor_id": actor_id,
            "user_id": getattr(record, "user_id", None) or actor_id,
            "request_id": getattr(record, "request_id", None) or context["request_id"],
            "job_id": getattr(record, "job_id", None) or context["job_id"],
            "task_id": getattr(record, "task_id", None) or context["task_id"],
            "causation_id": getattr(record, "causation_id", None) or context["causation_id"],
            "error": self._structured_error(record),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_FIELDS or key in _REQUIRED_FIELDS:
                continue
            entry[key] = REDACTED if _is_sensitive_key(key) else redact_value(value)

        # Extra fields (line above) and message are already redacted; required identifier
        # fields (correlation_id, tenant_id, ...) must NOT be re-redacted (the card/secret
        # patterns would corrupt UUID identifiers). Do not double-redact the whole entry.
        return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _structured_error(record: logging.LogRecord) -> dict[str, object] | None:
        """Keep actionable exception identity without serializing exception text."""
        if record.exc_info and record.exc_info[0] is not None:
            error_type = record.exc_info[0]
            error_value = record.exc_info[1]
            return {
                "type": error_type.__name__,
                "code": getattr(error_value, "code", None),
                "retryable": bool(getattr(error_value, "retryable", False)),
            }
        structured = getattr(record, "error", None)
        if not isinstance(structured, Mapping):
            return None
        return {
            "type": redact_text(str(structured.get("type"))) if structured.get("type") else None,
            "code": redact_text(str(structured.get("code"))) if structured.get("code") else None,
            "retryable": bool(structured.get("retryable", False)),
        }


# Explicit alias for integrations that prefer the longer name.
JSONLogFormatter = JSONFormatter
