"""Validation helpers for contextual security policy structures."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError

_MFA_METHODS = frozenset({"totp", "webauthn", "push", "sms", "email", "recovery_code"})
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "credential",
        "password",
        "secret",
        "session",
        "session_id",
        "token",
        "api_key",
        "private_key",
    }
)
_SENSITIVE_CONTENT_KEYS = frozenset(
    {
        "mask_input",
        "mask_inputs",
        "policy_payload",
        "raw_policy_payload",
        "raw_row_attributes",
        "row_attributes",
    }
)
_PII_KEYS = frozenset(
    {
        "address",
        "date_of_birth",
        "email",
        "first_name",
        "full_name",
        "last_name",
        "national_id",
        "passport_number",
        "phone",
        "phone_number",
        "ssn",
        "tax_id",
    }
)
MAX_AUDIT_BYTES = 16 * 1024


def _string_array(value: object, field: str, *, maximum: int = 100) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) > maximum:
        raise ValidationError({field: f"Must be an array containing at most {maximum} strings."})
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError({field: "Every item must be a nonblank string."})
    return list(value)


def validate_security_profile(profile: object) -> None:
    """Validate network, geography, time, and authentication policy structures."""

    networks: dict[str, set[ipaddress.IPv4Network | ipaddress.IPv6Network]] = {}
    for field in ("ip_whitelist", "ip_blacklist"):
        raw = _string_array(getattr(profile, field), field)
        try:
            networks[field] = {ipaddress.ip_network(item, strict=False) for item in raw}
        except ValueError as exc:
            raise ValidationError({field: "Contains an invalid CIDR network."}) from exc
    if networks["ip_whitelist"] & networks["ip_blacklist"]:
        raise ValidationError("The IP allowlist and blocklist cannot contain the same network.")

    countries: dict[str, set[str]] = {}
    for field in ("allowed_countries", "blocked_countries"):
        raw = _string_array(getattr(profile, field), field)
        normalized = {item.upper() for item in raw}
        if any(len(item) != 2 or not item.isalpha() for item in normalized):
            raise ValidationError({field: "Country codes must be ISO 3166-1 alpha-2 values."})
        countries[field] = normalized
    if countries["allowed_countries"] & countries["blocked_countries"]:
        raise ValidationError("Allowed and blocked countries cannot overlap.")

    methods = _string_array(getattr(profile, "allowed_mfa_methods"), "allowed_mfa_methods", maximum=20)
    if not set(methods).issubset(_MFA_METHODS):
        raise ValidationError({"allowed_mfa_methods": "Contains an unregistered MFA method."})
    password_policy = getattr(profile, "password_policy")
    if not isinstance(password_policy, Mapping):
        raise ValidationError({"password_policy": "Must be an object."})

    restrictions = getattr(profile, "time_restrictions")
    if not isinstance(restrictions, Mapping):
        raise ValidationError({"time_restrictions": "Must be an object."})
    if restrictions:
        if set(restrictions) - {"timezone", "weekdays", "windows"}:
            raise ValidationError({"time_restrictions": "Contains unsupported keys."})
        timezone_name = restrictions.get("timezone")
        try:
            ZoneInfo(str(timezone_name))
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError({"time_restrictions": "Timezone must be a valid IANA identifier."}) from exc
        weekdays = restrictions.get("weekdays", [])
        if not isinstance(weekdays, Sequence) or any(
            not isinstance(day, int) or day < 1 or day > 7 for day in weekdays
        ):
            raise ValidationError({"time_restrictions": "Weekdays must contain integers from 1 to 7."})
        windows = restrictions.get("windows", [])
        if not isinstance(windows, Sequence):
            raise ValidationError({"time_restrictions": "Windows must be an array."})
        for window in windows:
            if not isinstance(window, Mapping) or set(window) != {"start", "end"}:
                raise ValidationError({"time_restrictions": "Each window requires start and end."})
            try:
                start = time.fromisoformat(str(window["start"]))
                end = time.fromisoformat(str(window["end"]))
            except ValueError as exc:
                raise ValidationError({"time_restrictions": "Window times must be ISO local times."}) from exc
            if start >= end:
                raise ValidationError({"time_restrictions": "Window end must be later than start."})

    ranges = {
        "session_timeout_minutes": (5, 1440),
        "absolute_session_timeout_hours": (1, 168),
        "max_concurrent_sessions": (1, 100),
    }
    for field, (minimum, maximum) in ranges.items():
        value = getattr(profile, field)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValidationError({field: f"Must be between {minimum} and {maximum}."})


def _is_sensitive_evidence_key(key: object) -> bool:
    """Identify secrets, raw policy inputs, and subject PII in durable evidence."""

    normalized = str(key).strip().lower().replace("-", "_")
    if normalized in _SENSITIVE_KEYS | _SENSITIVE_CONTENT_KEYS | _PII_KEYS:
        return True
    for identity_prefix in ("actor_", "subject_", "user_"):
        if normalized.startswith(identity_prefix) and normalized.removeprefix(identity_prefix) in _PII_KEYS:
            return True
    return False


def redact_sensitive(value: object, *, depth: int = 0) -> object:
    """Recursively redact secrets and bound collection sizes for permanent evidence."""

    if depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in list(value.items())[:100]:
            result[str(key)[:100]] = (
                "[REDACTED]" if _is_sensitive_evidence_key(key) else redact_sensitive(item, depth=depth + 1)
            )
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_sensitive(item, depth=depth + 1) for item in list(value)[:100]]
    if isinstance(value, str):
        return value[:2000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2000]


__all__ = ["MAX_AUDIT_BYTES", "redact_sensitive", "validate_security_profile"]
