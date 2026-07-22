"""Operation-specific serializers for the governed traceability API.

Input serializers expose only client-owned fields.  Ownership, hashes,
sequences, lifecycle state, provider evidence and audit data are exclusively
assigned by domain services.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from django.utils import timezone
from rest_framework import serializers

from .models import (
    AuthenticityCredential,
    ComplianceEvidence,
    LedgerAnchor,
    LedgerNetwork,
    TraceabilityAsset,
    TraceabilityEvent,
    VerificationAttempt,
)
from .services import DEFAULT_CONFIGURATION

MAX_JSON_BYTES = int(DEFAULT_CONFIGURATION["validation"]["max_json_bytes"])
MAX_JSON_DEPTH = int(DEFAULT_CONFIGURATION["validation"]["max_json_depth"])
MAX_JSON_KEYS = int(DEFAULT_CONFIGURATION["validation"]["max_json_keys"])
SECRET_KEY_PATTERN = re.compile(
    r"(^|[_-])(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)([_-]|$)",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


class StrictInputMixin:
    """Reject misspelled and server-owned fields instead of discarding them."""

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"non_field_errors": ["Expected a JSON object."]})
        unknown = sorted(set(data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({name: ["Unknown or server-owned field."] for name in unknown})
        return super().to_internal_value(data)

    def runtime_document(self) -> Mapping[str, Any]:
        document = self.context.get("configuration") if hasattr(self, "context") else None
        return document if isinstance(document, Mapping) else DEFAULT_CONFIGURATION

    def validate_runtime_json(
        self, value: object, *, reject_secrets: bool = False, reject_urls: bool = False
    ) -> dict[str, object]:
        limits = cast(Mapping[str, int], self.runtime_document()["validation"])
        return validate_json_object(
            value,
            reject_secrets=reject_secrets,
            reject_urls=reject_urls,
            max_bytes=int(limits["max_json_bytes"]),
            max_depth=int(limits["max_json_depth"]),
            max_keys=int(limits["max_json_keys"]),
        )


def _walk_json(
    value: object,
    *,
    depth: int = 0,
    key_counter: list[int],
    reject_secrets: bool,
    reject_urls: bool,
    max_depth: int = MAX_JSON_DEPTH,
    max_keys: int = MAX_JSON_KEYS,
) -> None:
    if depth > max_depth:
        raise serializers.ValidationError(f"JSON nesting must not exceed {max_depth} levels.")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise serializers.ValidationError("JSON numbers must be finite.")
        return
    if isinstance(value, str):
        if reject_urls and URL_PATTERN.match(value.strip()):
            raise serializers.ValidationError("URLs are not permitted in provider options.")
        return
    if isinstance(value, Mapping):
        key_counter[0] += len(value)
        if key_counter[0] > max_keys:
            raise serializers.ValidationError(f"JSON documents may contain at most {max_keys} keys.")
        for key, child in value.items():
            if not isinstance(key, str):
                raise serializers.ValidationError("JSON object keys must be strings.")
            if reject_secrets and SECRET_KEY_PATTERN.search(key):
                raise serializers.ValidationError(
                    f"Configuration key '{key}' may contain a credential; use secret_ref instead."
                )
            _walk_json(
                child,
                depth=depth + 1,
                key_counter=key_counter,
                reject_secrets=reject_secrets,
                reject_urls=reject_urls,
                max_depth=max_depth,
                max_keys=max_keys,
            )
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            _walk_json(
                child,
                depth=depth + 1,
                key_counter=key_counter,
                reject_secrets=reject_secrets,
                reject_urls=reject_urls,
                max_depth=max_depth,
                max_keys=max_keys,
            )
        return
    raise serializers.ValidationError("JSON contains an unsupported value type.")


def validate_json_object(
    value: object,
    *,
    reject_secrets: bool = False,
    reject_urls: bool = False,
    max_bytes: int = MAX_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
    max_keys: int = MAX_JSON_KEYS,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise serializers.ValidationError("Expected a JSON object.")
    _walk_json(
        value,
        key_counter=[0],
        reject_secrets=reject_secrets,
        reject_urls=reject_urls,
        max_depth=max_depth,
        max_keys=max_keys,
    )
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError("Value must be valid JSON.") from exc
    if len(encoded) > max_bytes:
        raise serializers.ValidationError(f"JSON document must not exceed {max_bytes} bytes.")
    return value


def validate_gtin(value: str, allowed_lengths: Sequence[int] | None = None) -> str:
    """Validate a GS1 GTIN length and check digit while permitting no value."""

    normalized = value.strip()
    if not normalized:
        return ""
    lengths = tuple(allowed_lengths or cast(Sequence[int], DEFAULT_CONFIGURATION["validation"]["gtin_lengths"]))
    if not normalized.isdigit() or len(normalized) not in lengths:
        raise serializers.ValidationError(f"GTIN must contain one of the configured lengths: {lengths}.")
    digits = [int(character) for character in normalized]
    expected = (
        10 - sum(digit * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(digits[:-1]))) % 10
    ) % 10
    if digits[-1] != expected:
        raise serializers.ValidationError("GTIN check digit is invalid.")
    return normalized


class LedgerNetworkListSerializer(serializers.ModelSerializer):
    credential_configured = serializers.SerializerMethodField()

    class Meta:
        model = LedgerNetwork
        fields = (
            "id",
            "tenant_id",
            "network_key",
            "name",
            "provider_type",
            "network_namespace",
            "chain_id",
            "confirmation_depth",
            "supports_batch_anchors",
            "supports_finality",
            "status",
            "credential_configured",
            "last_health_status",
            "last_health_code",
            "last_health_checked_at",
            "last_successful_anchor_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_credential_configured(self, obj: LedgerNetwork) -> bool:
        return bool(obj.secret_ref)


class LedgerNetworkDetailSerializer(LedgerNetworkListSerializer):
    class Meta(LedgerNetworkListSerializer.Meta):
        fields = LedgerNetworkListSerializer.Meta.fields + (
            "description",
            "dependency_key",
            "provider_options",
            "created_by",
            "updated_by",
        )
        read_only_fields = fields


class LedgerNetworkCreateSerializer(StrictInputMixin, serializers.Serializer):
    network_key = serializers.SlugField(max_length=64)
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    provider_type = serializers.CharField(max_length=64, trim_whitespace=True)
    dependency_key = serializers.CharField(max_length=128, trim_whitespace=True)
    network_namespace = serializers.CharField(max_length=128, trim_whitespace=True)
    chain_id = serializers.CharField(required=False, max_length=128, allow_blank=True, default="")
    secret_ref = serializers.CharField(required=False, max_length=255, allow_blank=True, default="", write_only=True)
    confirmation_depth = serializers.IntegerField(required=False)
    supports_batch_anchors = serializers.BooleanField(required=False, default=False)
    supports_finality = serializers.BooleanField(required=False, default=True)
    provider_options = serializers.JSONField(required=False, default=dict)

    def validate_provider_options(self, value: object) -> dict[str, object]:
        return self.validate_runtime_json(value, reject_secrets=True, reject_urls=True)

    def validate_confirmation_depth(self, value: int) -> int:
        policy = cast(Mapping[str, int], self.runtime_document()["network_policy"])
        if not 1 <= value <= int(policy["max_confirmation_depth"]):
            raise serializers.ValidationError("Confirmation depth is outside the configured safe range.")
        return value


class LedgerNetworkUpdateSerializer(LedgerNetworkCreateSerializer):
    network_key = serializers.SlugField(max_length=64, required=False)
    name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    provider_type = serializers.CharField(max_length=64, trim_whitespace=True, required=False)
    dependency_key = serializers.CharField(max_length=128, trim_whitespace=True, required=False)
    network_namespace = serializers.CharField(max_length=128, trim_whitespace=True, required=False)
    confirmation_depth = serializers.IntegerField(required=False)
    supports_batch_anchors = serializers.BooleanField(required=False)
    supports_finality = serializers.BooleanField(required=False)
    provider_options = serializers.JSONField(required=False)


class TraceabilityAssetListSerializer(serializers.ModelSerializer):
    class Meta:
        model = TraceabilityAsset
        fields = (
            "id",
            "tenant_id",
            "asset_key",
            "name",
            "product_ref",
            "batch_ref",
            "serial_number",
            "gtin",
            "asset_type",
            "status",
            "head_sequence",
            "head_hash",
            "activated_at",
            "recalled_at",
            "retired_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TraceabilityAssetDetailSerializer(TraceabilityAssetListSerializer):
    class Meta(TraceabilityAssetListSerializer.Meta):
        fields = TraceabilityAssetListSerializer.Meta.fields + (
            "description",
            "attributes",
            "created_by",
            "updated_by",
        )
        read_only_fields = fields


class TraceabilityAssetCreateSerializer(StrictInputMixin, serializers.Serializer):
    asset_key = serializers.CharField(max_length=128, trim_whitespace=True)
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    product_ref = serializers.CharField(required=False, max_length=128, allow_blank=True, default="")
    batch_ref = serializers.CharField(required=False, max_length=128, allow_blank=True, default="")
    serial_number = serializers.CharField(required=False, max_length=128, allow_blank=True, default="")
    gtin = serializers.CharField(required=False, max_length=14, allow_blank=True, default="")
    asset_type = serializers.CharField(max_length=64, trim_whitespace=True)
    attributes = serializers.JSONField(required=False, default=dict)

    def validate_attributes(self, value: object) -> dict[str, object]:
        return self.validate_runtime_json(value)

    def validate_gtin(self, value: str) -> str:
        lengths = cast(Sequence[int], self.runtime_document()["validation"]["gtin_lengths"])
        return validate_gtin(value, lengths)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if not any(
            str(attrs.get(field, "")).strip() for field in ("product_ref", "batch_ref", "serial_number", "gtin")
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["At least one product, batch, serial-number, or GTIN reference is required."]}
            )
        return attrs


class TraceabilityAssetUpdateSerializer(TraceabilityAssetCreateSerializer):
    asset_key = serializers.CharField(max_length=128, trim_whitespace=True, required=False)
    name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    product_ref = serializers.CharField(required=False, max_length=128, allow_blank=True)
    batch_ref = serializers.CharField(required=False, max_length=128, allow_blank=True)
    serial_number = serializers.CharField(required=False, max_length=128, allow_blank=True)
    gtin = serializers.CharField(required=False, max_length=14, allow_blank=True)
    asset_type = serializers.CharField(max_length=64, trim_whitespace=True, required=False)
    attributes = serializers.JSONField(required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        # The service validates the merged entity so a partial update need not
        # resubmit the existing identifying reference.
        return attrs


class TraceabilityEventListSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = TraceabilityEvent
        fields = (
            "id",
            "tenant_id",
            "asset_id",
            "sequence",
            "event_type",
            "schema_version",
            "occurred_at",
            "recorded_at",
            "actor_ref",
            "previous_hash",
            "event_hash",
            "hash_algorithm",
            "correlation_id",
        )
        read_only_fields = fields


class TraceabilityEventDetailSerializer(TraceabilityEventListSerializer):
    class Meta(TraceabilityEventListSerializer.Meta):
        fields = TraceabilityEventListSerializer.Meta.fields + (
            "idempotency_key",
            "location",
            "payload",
            "created_by",
        )
        read_only_fields = fields


class TraceabilityEventCreateSerializer(StrictInputMixin, serializers.Serializer):
    asset_id = serializers.UUIDField()
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)
    event_type = serializers.CharField(max_length=64, trim_whitespace=True)
    schema_version = serializers.IntegerField(required=False)
    occurred_at = serializers.DateTimeField()
    actor_ref = serializers.CharField(max_length=255, trim_whitespace=True)
    location = serializers.JSONField(required=False, default=dict)
    payload = serializers.JSONField(required=False, default=dict)

    def validate_location(self, value: object) -> dict[str, object]:
        return self.validate_runtime_json(value)

    def validate_payload(self, value: object) -> dict[str, object]:
        return self.validate_runtime_json(value)

    def validate_schema_version(self, value: int) -> int:
        versions = cast(Sequence[int], self.runtime_document()["schema_policy"]["allowed_versions"])
        if value not in versions:
            raise serializers.ValidationError("Schema version is not in the configured allow-list.")
        return value


class LedgerAnchorListSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(read_only=True)
    network_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = LedgerAnchor
        fields = (
            "id",
            "tenant_id",
            "asset_id",
            "network_id",
            "start_sequence",
            "end_sequence",
            "root_hash",
            "hash_algorithm",
            "status",
            "async_job_id",
            "provider_transaction_id",
            "transaction_hash",
            "block_number",
            "block_hash",
            "confirmations",
            "failure_code",
            "submitted_at",
            "confirmed_at",
            "last_checked_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class LedgerAnchorDetailSerializer(LedgerAnchorListSerializer):
    class Meta(LedgerAnchorListSerializer.Meta):
        fields = LedgerAnchorListSerializer.Meta.fields + (
            "provider_receipt",
            "failure_message",
            "created_by",
        )
        read_only_fields = fields


class LedgerAnchorCreateSerializer(StrictInputMixin, serializers.Serializer):
    asset_id = serializers.UUIDField()
    network_id = serializers.UUIDField()
    start_sequence = serializers.IntegerField(min_value=1)
    end_sequence = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if int(attrs["end_sequence"]) < int(attrs["start_sequence"]):
            raise serializers.ValidationError({"end_sequence": ["Must be greater than or equal to start_sequence."]})
        return attrs


class AuthenticityCredentialListSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AuthenticityCredential
        fields = (
            "id",
            "tenant_id",
            "asset_id",
            "public_id",
            "credential_type",
            "status",
            "issued_at",
            "expires_at",
            "revoked_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AuthenticityCredentialDetailSerializer(AuthenticityCredentialListSerializer):
    class Meta(AuthenticityCredentialListSerializer.Meta):
        fields = AuthenticityCredentialListSerializer.Meta.fields + (
            "claims",
            "claims_hash",
            "signature_algorithm",
            "signature",
            "revocation_reason",
            "created_by",
        )
        read_only_fields = fields


class AuthenticityCredentialIssueSerializer(StrictInputMixin, serializers.Serializer):
    asset_id = serializers.UUIDField()
    claims = serializers.JSONField(required=False, default=dict)
    expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_claims(self, value: object) -> dict[str, object]:
        return self.validate_runtime_json(value)

    def validate_expires_at(self, value: object) -> object:
        if value is not None and cast(Any, value) <= timezone.now():
            raise serializers.ValidationError("Expiry must be in the future.")
        return value


class CredentialRevokeSerializer(StrictInputMixin, serializers.Serializer):
    reason = serializers.CharField(trim_whitespace=True)
    transition_key = serializers.CharField(max_length=128, trim_whitespace=True)

    def validate_reason(self, value: str) -> str:
        maximum = int(self.runtime_document()["validation"]["max_revocation_reason_chars"])
        if len(value) > maximum:
            raise serializers.ValidationError("Reason exceeds the configured safe limit.")
        return value


class AuthenticityVerificationSerializer(StrictInputMixin, serializers.Serializer):
    public_id = serializers.CharField(max_length=128, trim_whitespace=True)
    token = serializers.CharField(trim_whitespace=False, write_only=True)
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_token(self, value: str) -> str:
        maximum = int(self.runtime_document()["validation"]["max_authenticity_token_chars"])
        if len(value) > maximum:
            raise serializers.ValidationError("Token exceeds the configured safe limit.")
        return value


class ComplianceEvidenceListSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(read_only=True)
    event_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = ComplianceEvidence
        fields = (
            "id",
            "tenant_id",
            "asset_id",
            "event_id",
            "evidence_key",
            "evidence_type",
            "standard",
            "jurisdiction",
            "result",
            "status",
            "observed_at",
            "valid_until",
            "finalized_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ComplianceEvidenceDetailSerializer(ComplianceEvidenceListSerializer):
    supersedes_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta(ComplianceEvidenceListSerializer.Meta):
        fields = ComplianceEvidenceListSerializer.Meta.fields + (
            "details",
            "document_ref",
            "content_hash",
            "supersedes_id",
            "created_by",
            "updated_by",
        )
        read_only_fields = fields


class ComplianceEvidenceCreateSerializer(StrictInputMixin, serializers.Serializer):
    asset_id = serializers.UUIDField()
    event_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    evidence_key = serializers.CharField(max_length=128, trim_whitespace=True)
    evidence_type = serializers.CharField(max_length=64, trim_whitespace=True)
    standard = serializers.CharField(max_length=128, trim_whitespace=True)
    jurisdiction = serializers.CharField(required=False, max_length=64, allow_blank=True, default="")
    result = serializers.ChoiceField(choices=("pass", "fail", "warning", "not_applicable"))
    details = serializers.JSONField(required=False, default=dict)
    document_ref = serializers.UUIDField(required=False, allow_null=True, default=None)
    observed_at = serializers.DateTimeField()
    valid_until = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_details(self, value: object) -> dict[str, object]:
        return self.validate_runtime_json(value)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        valid_until = attrs.get("valid_until")
        if valid_until is not None and cast(Any, valid_until) <= attrs["observed_at"]:
            raise serializers.ValidationError({"valid_until": ["Must be later than observed_at."]})
        return attrs


class ComplianceEvidenceUpdateSerializer(ComplianceEvidenceCreateSerializer):
    asset_id = serializers.UUIDField(required=False)
    event_id = serializers.UUIDField(required=False, allow_null=True)
    evidence_key = serializers.CharField(max_length=128, trim_whitespace=True, required=False)
    evidence_type = serializers.CharField(max_length=64, trim_whitespace=True, required=False)
    standard = serializers.CharField(max_length=128, trim_whitespace=True, required=False)
    jurisdiction = serializers.CharField(required=False, max_length=64, allow_blank=True)
    result = serializers.ChoiceField(choices=("pass", "fail", "warning", "not_applicable"), required=False)
    details = serializers.JSONField(required=False)
    document_ref = serializers.UUIDField(required=False, allow_null=True)
    observed_at = serializers.DateTimeField(required=False)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs.get("valid_until") is not None and attrs.get("observed_at") is not None:
            if cast(Any, attrs["valid_until"]) <= attrs["observed_at"]:
                raise serializers.ValidationError({"valid_until": ["Must be later than observed_at."]})
        return attrs


class EvidenceSupersedeSerializer(ComplianceEvidenceCreateSerializer):
    transition_key = serializers.CharField(max_length=128, trim_whitespace=True)


class VerificationAttemptListSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(read_only=True, allow_null=True)
    anchor_id = serializers.UUIDField(read_only=True, allow_null=True)
    credential_id = serializers.UUIDField(read_only=True, allow_null=True)
    compliance_evidence_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = VerificationAttempt
        fields = (
            "id",
            "tenant_id",
            "verification_type",
            "asset_id",
            "anchor_id",
            "credential_id",
            "compliance_evidence_id",
            "outcome",
            "reason_code",
            "chain_head_hash",
            "correlation_id",
            "latency_ms",
            "created_at",
        )
        read_only_fields = fields


class VerificationAttemptDetailSerializer(VerificationAttemptListSerializer):
    class Meta(VerificationAttemptListSerializer.Meta):
        fields = VerificationAttemptListSerializer.Meta.fields + ("proof_evidence",)
        read_only_fields = fields


class ChainVerificationSerializer(StrictInputMixin, serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)


class TransitionSerializer(StrictInputMixin, serializers.Serializer):
    transition_key = serializers.CharField(max_length=128, trim_whitespace=True)


class RecallSerializer(TransitionSerializer):
    reason = serializers.CharField(trim_whitespace=True)

    def validate_reason(self, value: str) -> str:
        maximum = int(self.runtime_document()["validation"]["max_revocation_reason_chars"])
        if len(value) > maximum:
            raise serializers.ValidationError("Reason exceeds the configured safe limit.")
        return value


class ConfigurationUpdateSerializer(StrictInputMixin, serializers.Serializer):
    document = serializers.JSONField()
    environment = serializers.SlugField(required=False, default="default", max_length=64)


class ConfigurationPreviewSerializer(ConfigurationUpdateSerializer):
    pass


class ConfigurationRollbackSerializer(StrictInputMixin, serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    environment = serializers.SlugField(required=False, default="default", max_length=64)


class ConfigurationImportSerializer(StrictInputMixin, serializers.Serializer):
    schema = serializers.CharField(required=False)
    environment = serializers.SlugField(required=False, default="default", max_length=64)
    version = serializers.IntegerField(required=False, min_value=1)
    document = serializers.JSONField()


__all__ = [name for name in globals() if name.endswith("Serializer")]
