"""Versioned tenant runtime policy for the Integration Platform.

Defaults live in one reviewed document so runtime behaviour is never scattered
through adapters, views, workers, or frontend code. Platform ceilings remain
code-level security invariants; tenants may only select values inside them.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Final, Mapping

from django.core.exceptions import ValidationError


CONFIGURATION_SCHEMA_VERSION: Final = 1

DEFAULT_CONFIGURATION: Final[dict[str, object]] = {
    "schema_version": CONFIGURATION_SCHEMA_VERSION,
    "environment": "default",
    "adapter": {
        "spi_version": "1.0",
        "capabilities": ["test", "pull", "push", "receive", "deliver"],
        "adapter_key_max_length": 200,
        "cursor_max_length": 4096,
    },
    "transformations": {
        "operations": ["rename", "string_case", "trim", "number", "date_format", "default", "enum_map"],
        "string_case_modes": ["lower", "upper", "title", "casefold"],
        "number_modes": ["integer", "float", "decimal"],
        "default_number_mode": "decimal",
        "default_input_date_format": "%Y-%m-%dT%H:%M:%S%z",
        "allow_unmapped_enum": False,
        "max_chain_length": 20,
    },
    "validation": {
        "name_max_length": 255,
        "description_max_length": 4000,
        "credential_max_length": 65536,
        "url_max_length": 2000,
        "event_name_pattern": r"^[a-z][a-z0-9_.:-]{0,254}$",
        "event_name_max_length": 255,
        "nonce_max_length": 128,
        "signature_max_length": 128,
        "error_code_max_length": 100,
    },
    "security": {
        "connector_access_policy": "explicit_entitlement",
        "secret_field_names": ["authorization", "password", "secret", "token", "api_key"],
        "signature_window_seconds": 300,
        "payload_max_bytes": 1048576,
        "credential_hint_characters": 4,
        "signing_secret_bytes": 48,
        "outbound_nonce_bytes": 24,
        "diagnostic_fields": ["request_id", "trace_id", "error_code"],
    },
    "webhooks": {
        "timeout_seconds_default": 10,
        "timeout_seconds_min": 1,
        "timeout_seconds_max": 30,
        "max_attempts_default": 5,
        "max_attempts_min": 1,
        "max_attempts_max": 10,
        "success_status_min": 200,
        "success_status_max": 299,
        "retry_statuses": [408, 429],
        "retry_server_error_min": 500,
        "retry_delay_max_seconds": 3600,
        "connect_timeout_max_seconds": 5,
        "http_client_retries": 0,
        "inbound_rate": "60/min",
    },
    "synchronization": {
        "directions": ["pull", "push"],
        "active_statuses": ["active"],
        "pull_batch_limit": 1000,
        "quota_cost": 1,
    },
    "workflows": {
        "integration_delete_statuses": ["inactive"],
        "integration_activation_statuses": ["active"],
        "activation_requires_successful_test": True,
        "integration_transitions": {
            "inactive": ["testing"],
            "testing": ["active", "error"],
            "active": ["inactive", "error"],
            "error": ["testing", "inactive"],
        },
        "credential_transitions": {"active": ["revoked", "expired"], "revoked": [], "expired": []},
        "webhook_transitions": {"inactive": ["active"], "active": ["inactive", "error"], "error": ["active"]},
        "delivery_transitions": {
            "queued": ["delivering", "cancelled"],
            "delivering": ["delivered", "retrying", "dead_letter"],
            "retrying": ["queued", "cancelled"],
            "delivered": [],
            "dead_letter": ["queued"],
            "cancelled": [],
        },
    },
    "jobs": {
        "poll_after_ms": 1000,
        "progress_min": 0,
        "progress_max": 100,
        "terminal_progress": 100,
    },
    "list": {
        "page_size": 25,
        "connector_page_size": 100,
        "refresh_interval_ms": 10000,
        "active_delivery_poll_ms": 5000,
        "integration_poll_ms": 2500,
        "integration_ordering": "-created_at",
        "integration_ordering_fields": ["name", "created_at", "updated_at", "status"],
        "webhook_ordering": "-created_at",
        "webhook_ordering_fields": ["name", "created_at", "updated_at", "status"],
        "delivery_ordering": "-created_at,-id",
        "mapping_ordering": "position",
        "mapping_ordering_fields": ["position", "name", "created_at", "updated_at"],
    },
    "quotas": {
        "integration_write": 2,
        "integration_transition": 2,
        "integration_test": 5,
        "integration_sync": 10,
        "credential_create": 2,
        "credential_rotate": 3,
        "credential_revoke": 2,
        "webhook_write": 2,
        "webhook_transition": 2,
        "webhook_rotate_secret": 3,
        "delivery_redrive": 5,
        "mapping_write": 2,
        "mapping_validate": 2,
        "mapping_preview": 3,
    },
    "mapping": {"default_position": 0, "default_required": False, "preview_record_limit": 100},
    "health": {"probe_timeout_seconds": 2, "broker_acknowledgement_seconds": 300},
    "feature_flags": {
        "configuration_ui": {"enabled": True, "roles": ["tenant_admin"], "cohorts": ["all"]},
        "push_synchronization": {"enabled": False, "roles": [], "cohorts": []},
    },
    "navigation": {
        "base_order": 300,
        "route_order": {
            "integration-platform.integrations.list": 0,
            "integration-platform.integrations.create": 1,
            "integration-platform.integrations.detail": 2,
            "integration-platform.integrations.edit": 3,
            "integration-platform.credentials.metadata": 4,
            "integration-platform.credentials.create": 5,
            "integration-platform.credentials.rotate": 6,
            "integration-platform.connectors.list": 10,
            "integration-platform.connectors.detail": 11,
            "integration-platform.connectors.setup": 12,
            "integration-platform.webhooks.list": 20,
            "integration-platform.webhooks.create": 21,
            "integration-platform.webhooks.detail": 22,
            "integration-platform.webhooks.edit": 23,
            "integration-platform.deliveries.list": 30,
            "integration-platform.deliveries.detail": 31,
            "integration-platform.mappings.list": 40,
            "integration-platform.mappings.create": 41,
            "integration-platform.mappings.detail": 42,
            "integration-platform.mappings.edit": 43,
            "integration-platform.configuration": 50,
        },
        "status_positive": ["active", "delivered", "succeeded", "healthy"],
        "status_warning": ["testing", "retrying", "queued", "degraded"],
        "status_danger": ["error", "failed", "dead_letter", "unavailable"],
    },
}

ABSOLUTE_LIMITS: Final[dict[str, tuple[int, int]]] = {
    "adapter.adapter_key_max_length": (1, 512),
    "adapter.cursor_max_length": (1, 16384),
    "transformations.max_chain_length": (1, 100),
    "validation.name_max_length": (1, 1024),
    "validation.description_max_length": (1, 65536),
    "validation.credential_max_length": (1, 1048576),
    "validation.url_max_length": (64, 8192),
    "validation.event_name_max_length": (1, 1024),
    "validation.nonce_max_length": (32, 512),
    "validation.signature_max_length": (71, 512),
    "validation.error_code_max_length": (16, 255),
    "security.signature_window_seconds": (30, 900),
    "security.payload_max_bytes": (1024, 10485760),
    "security.credential_hint_characters": (0, 12),
    "security.signing_secret_bytes": (32, 128),
    "security.outbound_nonce_bytes": (16, 64),
    "webhooks.timeout_seconds_min": (1, 30),
    "webhooks.timeout_seconds_max": (1, 120),
    "webhooks.max_attempts_min": (1, 10),
    "webhooks.max_attempts_max": (1, 20),
    "webhooks.retry_delay_max_seconds": (1, 86400),
    "webhooks.connect_timeout_max_seconds": (1, 30),
    "webhooks.http_client_retries": (0, 5),
    "synchronization.pull_batch_limit": (1, 10000),
    "synchronization.quota_cost": (1, 100),
    "jobs.poll_after_ms": (250, 60000),
    "jobs.progress_min": (0, 100),
    "jobs.progress_max": (0, 100),
    "jobs.terminal_progress": (0, 100),
    "list.page_size": (1, 200),
    "list.connector_page_size": (1, 200),
    "list.refresh_interval_ms": (1000, 300000),
    "list.active_delivery_poll_ms": (250, 300000),
    "list.integration_poll_ms": (250, 300000),
    "mapping.default_position": (0, 1000000),
    "mapping.preview_record_limit": (1, 1000),
    "health.probe_timeout_seconds": (1, 30),
    "health.broker_acknowledgement_seconds": (30, 3600),
    "navigation.base_order": (0, 10000),
}


def default_configuration() -> dict[str, object]:
    return deepcopy(DEFAULT_CONFIGURATION)


def _path(document: Mapping[str, object], dotted: str) -> object:
    value: object = document
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise ValidationError({"document": f"Missing required setting {dotted}."})
        value = value[part]
    return value


def _validate_shape(value: object, template: object, dotted: str = "document") -> None:
    """Reject missing/unknown fields and wrong JSON types at every level."""

    if isinstance(template, Mapping):
        if not isinstance(value, Mapping):
            raise ValidationError({"document": f"{dotted} must be an object."})
        missing, unknown = set(template) - set(value), set(value) - set(template)
        if missing or unknown:
            raise ValidationError(
                {"document": f"{dotted} fields must match schema; missing={sorted(missing)}, unknown={sorted(unknown)}."}
            )
        for key, child_template in template.items():
            _validate_shape(value[key], child_template, f"{dotted}.{key}")
        return
    if isinstance(template, list):
        if not isinstance(value, list):
            raise ValidationError({"document": f"{dotted} must be an array."})
        if template:
            for index, child in enumerate(value):
                _validate_shape(child, template[0], f"{dotted}[{index}]")
        return
    expected_type = type(template)
    if expected_type is int and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValidationError({"document": f"{dotted} must be an integer."})
    if expected_type is not int and not isinstance(value, expected_type):
        raise ValidationError({"document": f"{dotted} must be {expected_type.__name__}."})


def validate_configuration(document: object) -> dict[str, object]:
    """Validate a complete portable document and enforce platform guard rails."""

    if not isinstance(document, Mapping):
        raise ValidationError({"document": "Configuration must be a JSON object."})
    _validate_shape(document, DEFAULT_CONFIGURATION)
    if document.get("schema_version") != CONFIGURATION_SCHEMA_VERSION:
        raise ValidationError({"schema_version": "Unsupported configuration schema version."})
    for dotted, (minimum, maximum) in ABSOLUTE_LIMITS.items():
        value = _path(document, dotted)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValidationError({"document": f"{dotted} must be between {minimum} and {maximum}."})
    timeout_min = _path(document, "webhooks.timeout_seconds_min")
    timeout_max = _path(document, "webhooks.timeout_seconds_max")
    attempts_min = _path(document, "webhooks.max_attempts_min")
    attempts_max = _path(document, "webhooks.max_attempts_max")
    if int(timeout_min) > int(timeout_max) or int(attempts_min) > int(attempts_max):
        raise ValidationError({"document": "Webhook minimums cannot exceed maximums."})
    if not int(timeout_min) <= int(_path(document, "webhooks.timeout_seconds_default")) <= int(timeout_max):
        raise ValidationError({"document": "Webhook timeout default must be inside its configured range."})
    if not int(attempts_min) <= int(_path(document, "webhooks.max_attempts_default")) <= int(attempts_max):
        raise ValidationError({"document": "Webhook attempt default must be inside its configured range."})
    progress_min = int(_path(document, "jobs.progress_min"))
    progress_max = int(_path(document, "jobs.progress_max"))
    terminal_progress = int(_path(document, "jobs.terminal_progress"))
    if progress_min > progress_max or not progress_min <= terminal_progress <= progress_max:
        raise ValidationError({"document": "Job progress bounds and terminal progress are inconsistent."})
    if _path(document, "security.connector_access_policy") != "explicit_entitlement":
        raise ValidationError({"document": "Connector access policy must fail closed with explicit_entitlement."})
    required_secret_fields = set(DEFAULT_CONFIGURATION["security"]["secret_field_names"])
    configured_secret_fields = set(_path(document, "security.secret_field_names"))
    if not required_secret_fields.issubset(configured_secret_fields):
        raise ValidationError({"document": "Security secret field names may be extended but cannot remove platform protections."})
    directions = _path(document, "synchronization.directions")
    if not isinstance(directions, list) or not directions or set(directions) - {"pull", "push"}:
        raise ValidationError({"document": "Synchronization directions must be a non-empty pull/push allow-list."})
    capabilities = _path(document, "adapter.capabilities")
    if not capabilities or len(capabilities) != len(set(capabilities)) or set(capabilities) - {"test", "pull", "push", "receive", "deliver"}:
        raise ValidationError({"document": "Adapter capabilities contain unsupported values."})
    if _path(document, "adapter.spi_version") not in {"1.0"}:
        raise ValidationError({"document": "Adapter SPI version is not supported by this runtime."})
    allowed_transformations = {"rename", "string_case", "trim", "number", "date_format", "default", "enum_map"}
    operations = _path(document, "transformations.operations")
    if not operations or len(operations) != len(set(operations)) or set(operations) - allowed_transformations:
        raise ValidationError({"document": "Transformation operation allow-list is invalid."})
    route_order = _path(document, "navigation.route_order")
    if not all(isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10000 for value in route_order.values()):
        raise ValidationError({"document": "Navigation route order values must be integers between 0 and 10000."})
    for quota_name, quota_cost in _path(document, "quotas").items():
        if isinstance(quota_cost, bool) or not isinstance(quota_cost, int) or not 1 <= quota_cost <= 100:
            raise ValidationError({"document": f"Quota {quota_name} must be between 1 and 100."})
    return deepcopy(dict(document))


def setting(document: Mapping[str, object], dotted: str) -> object:
    return _path(document, dotted)


__all__ = [
    "ABSOLUTE_LIMITS",
    "CONFIGURATION_SCHEMA_VERSION",
    "DEFAULT_CONFIGURATION",
    "default_configuration",
    "setting",
    "validate_configuration",
]
