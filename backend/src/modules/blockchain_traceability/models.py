"""Tenant-owned persistence for product traceability and proof evidence."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Return a string UUID for immutable migration ``0001_initial``."""

    return str(uuid.uuid4())


LOWER_SHA256_RE = r"^[0-9a-f]{64}$"
lower_sha256_validator = RegexValidator(LOWER_SHA256_RE, "Enter a lowercase SHA-256 hexadecimal digest.")


class ImmutableEvidenceError(ValidationError):
    """Raised when append-only or finalized evidence is mutated."""


class LedgerNetworkStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    DEGRADED = "degraded", "Degraded"
    DISABLED = "disabled", "Disabled"


class TraceabilityAssetStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RECALLED = "recalled", "Recalled"
    RETIRED = "retired", "Retired"


class LedgerAnchorStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SUBMITTING = "submitting", "Submitting"
    SUBMITTED = "submitted", "Submitted"
    CONFIRMED = "confirmed", "Confirmed"
    FAILED = "failed", "Failed"


class AuthenticityCredentialStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


class ComplianceEvidenceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    FINALIZED = "finalized", "Finalized"
    SUPERSEDED = "superseded", "Superseded"


class ComplianceResult(models.TextChoices):
    PASS = "pass", "Pass"
    FAIL = "fail", "Fail"
    WARNING = "warning", "Warning"
    NOT_APPLICABLE = "not_applicable", "Not applicable"


class VerificationType(models.TextChoices):
    CHAIN = "chain", "Hash chain"
    ANCHOR = "anchor", "Ledger anchor"
    AUTHENTICITY = "authenticity", "Authenticity"
    COMPLIANCE = "compliance", "Compliance evidence"


class VerificationOutcome(models.TextChoices):
    VERIFIED = "verified", "Verified"
    INVALID = "invalid", "Invalid"
    NOT_AUTHENTIC = "not_authentic", "Not authentic"
    INCONCLUSIVE = "inconclusive", "Inconclusive"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable", "Dependency unavailable"


def _require_object(value: Any, field_name: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError({field_name: "Must be a JSON object."}, code="invalid_json_object")


def _walk_json(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            nested_path = f"{path}.{key}"
            yield nested_path, nested
            yield from _walk_json(nested, nested_path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            nested_path = f"{path}[{index}]"
            yield nested_path, nested
            yield from _walk_json(nested, nested_path)


_SECRET_KEY_PARTS = frozenset(
    {
        "authorization",
        "credential",
        "credentials",
        "api_key",
        "apikey",
        "private_key",
        "password",
        "secret",
        "token",
    }
)


def _reject_secret_material(value: Any, field_name: str, *, reject_urls: bool = False) -> None:
    for path, nested in _walk_json(value):
        key = path.rsplit(".", 1)[-1].lower().replace("-", "_")
        sensitive_key = (
            key in _SECRET_KEY_PARTS
            or key.startswith(("private_key", "api_key"))
            or key.endswith(("_token", "_secret", "_password", "_credential", "_credentials"))
        )
        if sensitive_key:
            raise ValidationError({field_name: f"Sensitive configuration is forbidden at {path}."})
        if reject_urls and isinstance(nested, str) and nested.strip().lower().startswith(("http://", "https://")):
            raise ValidationError({field_name: f"URLs are forbidden at {path}; use the declared dependency."})


def _reject_raw_source_data(value: Any, field_name: str) -> None:
    forbidden_keys = {"ip", "ip_address", "source_ip", "client_ip", "remote_addr", "provider_url", "url"}
    for path, nested in _walk_json(value):
        key = path.rsplit(".", 1)[-1].lower()
        if key in forbidden_keys:
            raise ValidationError({field_name: f"Raw source or provider location is forbidden at {path}."})
        if isinstance(nested, str) and nested.strip().lower().startswith(("http://", "https://")):
            raise ValidationError({field_name: f"Raw provider URLs are forbidden at {path}."})


def _require_same_tenant(instance: TenantScopedModel, relation_name: str) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    tenant_id = getattr(instance, "tenant_id", None)
    if relation_id is None or tenant_id is None:
        return
    field = instance._meta.get_field(relation_name)
    related_model = field.remote_field.model
    if not related_model._default_manager.filter(pk=relation_id, tenant_id=tenant_id).exists():
        raise ValidationError(
            {relation_name: "The referenced record does not belong to this tenant."},
            code="cross_tenant_reference",
        )


def _changed_fields(instance: models.Model, field_names: Iterable[str]) -> set[str]:
    if instance._state.adding or instance.pk is None:
        return set()
    previous = type(instance)._base_manager.filter(pk=instance.pk).values(*field_names).first()
    if previous is None:
        return set()
    return {field for field in field_names if previous[field] != getattr(instance, field)}


class MutableTenantModel(TenantScopedModel, TimestampedModel):
    """Common UUID identity, actor audit, and soft-deletion contract."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.CharField(max_length=255)
    updated_by = models.CharField(max_length=255, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True


class AppendOnlyQuerySet(TenantQuerySet):
    """Prevent bulk mutation from bypassing evidence immutability."""

    def update(self, **kwargs: Any) -> int:
        raise ImmutableEvidenceError("Append-only evidence cannot be updated.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Append-only evidence cannot be deleted.", code="append_only")


class AppendOnlyTenantModel(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableEvidenceError("Append-only evidence cannot be updated.", code="append_only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Append-only evidence cannot be deleted.", code="append_only")


class LedgerNetwork(MutableTenantModel):
    network_key = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    provider_type = models.CharField(max_length=64)
    dependency_key = models.CharField(max_length=128)
    network_namespace = models.CharField(max_length=128)
    chain_id = models.CharField(max_length=128, blank=True)
    secret_ref = models.CharField(max_length=255, blank=True)
    confirmation_depth = models.PositiveSmallIntegerField(default=1)
    supports_batch_anchors = models.BooleanField(default=False)
    supports_finality = models.BooleanField(default=True)
    provider_options = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=LedgerNetworkStatus.choices,
        default=LedgerNetworkStatus.DRAFT,
    )
    transition_history = models.JSONField(default=list, blank=True)
    last_health_status = models.CharField(max_length=16, blank=True)
    last_health_code = models.CharField(max_length=64, blank=True)
    last_health_checked_at = models.DateTimeField(null=True, blank=True)
    last_successful_anchor_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "blockchain_traceability_ledger_networks"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "network_key"],
                condition=Q(is_deleted=False),
                name="bct_network_tenant_key_active_uniq",
            ),
            models.CheckConstraint(condition=Q(confirmation_depth__gte=1), name="bct_network_confirmation_gte_1"),
            models.CheckConstraint(condition=~Q(dependency_key=""), name="bct_network_dependency_nonblank"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "name"], name="bct_net_tenant_status_name"),
            models.Index(fields=["tenant_id", "provider_type"], name="bct_net_tenant_provider"),
            models.Index(fields=["tenant_id", "is_deleted", "created_at"], name="bct_net_tenant_del_created"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_object(self.provider_options, "provider_options")
        _reject_secret_material(self.provider_options, "provider_options", reject_urls=True)
        if not self.dependency_key.strip():
            raise ValidationError({"dependency_key": "Dependency key must not be blank."})
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Transition history must be a JSON array."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} [{self.network_key}]"


class TraceabilityAsset(MutableTenantModel):
    asset_key = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    product_ref = models.CharField(max_length=128, blank=True)
    batch_ref = models.CharField(max_length=128, blank=True)
    serial_number = models.CharField(max_length=128, blank=True)
    gtin = models.CharField(max_length=14, blank=True)
    asset_type = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=TraceabilityAssetStatus.choices,
        default=TraceabilityAssetStatus.DRAFT,
    )
    attributes = models.JSONField(default=dict, blank=True)
    head_sequence = models.PositiveBigIntegerField(default=0)
    head_hash = models.CharField(max_length=64, blank=True, validators=[lower_sha256_validator])
    transition_history = models.JSONField(default=list, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    recalled_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "blockchain_traceability_assets"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "asset_key"],
                condition=Q(is_deleted=False),
                name="bct_asset_tenant_key_active_uniq",
            ),
            models.CheckConstraint(
                condition=~(Q(product_ref="") & Q(batch_ref="") & Q(serial_number="") & Q(gtin="")),
                name="bct_asset_has_reference",
            ),
            models.CheckConstraint(
                condition=(Q(head_sequence=0, head_hash="") | Q(head_sequence__gt=0, head_hash__regex=LOWER_SHA256_RE)),
                name="bct_asset_head_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "created_at"], name="asset_tenant_status_created"),
            models.Index(fields=["tenant_id", "product_ref", "batch_ref"], name="bct_asset_tenant_product_batch"),
            models.Index(fields=["tenant_id", "serial_number"], name="bct_asset_tenant_serial"),
            models.Index(fields=["tenant_id", "gtin"], name="bct_asset_tenant_gtin"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_object(self.attributes, "attributes")
        if not any((self.product_ref, self.batch_ref, self.serial_number, self.gtin)):
            raise ValidationError("At least one product, batch, serial, or GTIN reference is required.")
        if self.gtin and (not self.gtin.isdigit() or len(self.gtin) not in {8, 12, 13, 14}):
            raise ValidationError({"gtin": "GTIN must contain 8, 12, 13, or 14 digits."})
        if self.head_sequence == 0 and self.head_hash:
            raise ValidationError({"head_hash": "An asset without events cannot have a head hash."})
        if self.head_sequence > 0:
            lower_sha256_validator(self.head_hash)
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Transition history must be a JSON array."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} [{self.asset_key}]"


class TraceabilityEvent(AppendOnlyTenantModel):
    asset = models.ForeignKey(TraceabilityAsset, models.PROTECT, related_name="events")
    sequence = models.PositiveBigIntegerField()
    idempotency_key = models.CharField(max_length=255)
    event_type = models.CharField(max_length=64)
    schema_version = models.PositiveSmallIntegerField(default=1)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    actor_ref = models.CharField(max_length=255)
    location = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True, validators=[lower_sha256_validator])
    event_hash = models.CharField(max_length=64, validators=[lower_sha256_validator])
    hash_algorithm = models.CharField(max_length=16, default="sha256")
    created_by = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=64, db_index=True)

    class Meta:
        db_table = "blockchain_traceability_events"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "asset", "sequence"], name="bct_event_asset_sequence_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "asset", "idempotency_key"], name="bct_event_asset_idempotency_uniq"
            ),
            models.UniqueConstraint(fields=["tenant_id", "event_hash"], name="bct_event_tenant_hash_uniq"),
            models.CheckConstraint(condition=Q(sequence__gte=1), name="bct_event_sequence_gte_1"),
            models.CheckConstraint(
                condition=(Q(sequence=1, previous_hash="") | Q(sequence__gt=1, previous_hash__regex=LOWER_SHA256_RE)),
                name="bct_event_previous_hash_consistent",
            ),
            models.CheckConstraint(condition=Q(event_hash__regex=LOWER_SHA256_RE), name="bct_event_hash_valid"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "asset", "sequence"], name="bct_event_tenant_asset_seq"),
            models.Index(fields=["tenant_id", "event_type", "occurred_at"], name="bct_event_tenant_type_time"),
            models.Index(fields=["tenant_id", "recorded_at"], name="bct_event_tenant_recorded"),
        ]
        ordering = ["sequence", "id"]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "asset")
        _require_object(self.location, "location")
        _require_object(self.payload, "payload")
        if self.sequence == 1 and self.previous_hash:
            raise ValidationError({"previous_hash": "The first event cannot have a previous hash."})
        if self.sequence > 1:
            lower_sha256_validator(self.previous_hash)
        lower_sha256_validator(self.event_hash)
        if self.hash_algorithm != "sha256":
            raise ValidationError({"hash_algorithm": "Only sha256 is supported."})

    def __str__(self) -> str:
        return f"{self.asset_id} event #{self.sequence} ({self.event_type})"


class TerminalEvidenceQuerySet(TenantQuerySet):
    terminal_statuses: frozenset[str] = frozenset()

    def update(self, **kwargs: Any) -> int:
        if self.filter(status__in=self.terminal_statuses).exists():
            raise ImmutableEvidenceError("Terminal evidence cannot be updated.", code="terminal_immutable")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Traceability evidence cannot be deleted.", code="evidence_retained")


class LedgerAnchorQuerySet(TerminalEvidenceQuerySet):
    terminal_statuses = frozenset({LedgerAnchorStatus.CONFIRMED})


class LedgerAnchor(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(TraceabilityAsset, models.PROTECT, related_name="anchors")
    network = models.ForeignKey(LedgerNetwork, models.PROTECT, related_name="anchors")
    start_sequence = models.PositiveBigIntegerField()
    end_sequence = models.PositiveBigIntegerField()
    root_hash = models.CharField(max_length=64, validators=[lower_sha256_validator])
    hash_algorithm = models.CharField(max_length=16, default="sha256")
    idempotency_key = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=LedgerAnchorStatus.choices, default=LedgerAnchorStatus.QUEUED)
    transition_history = models.JSONField(default=list, blank=True)
    async_job_id = models.UUIDField(null=True, blank=True, db_index=True)
    provider_transaction_id = models.CharField(max_length=255, blank=True)
    transaction_hash = models.CharField(max_length=255, blank=True)
    block_number = models.PositiveBigIntegerField(null=True, blank=True)
    block_hash = models.CharField(max_length=255, blank=True)
    confirmations = models.PositiveIntegerField(default=0)
    provider_receipt = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    failure_message = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=255)
    objects = LedgerAnchorQuerySet.as_manager()

    class Meta:
        db_table = "blockchain_traceability_ledger_anchors"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "network", "asset", "start_sequence", "end_sequence"],
                name="bct_anchor_network_asset_range_uniq",
            ),
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="bct_anchor_tenant_idem_uniq"),
            models.CheckConstraint(condition=Q(start_sequence__gte=1), name="bct_anchor_start_gte_1"),
            models.CheckConstraint(condition=Q(end_sequence__gte=F("start_sequence")), name="bct_anchor_range_valid"),
            models.CheckConstraint(condition=Q(root_hash__regex=LOWER_SHA256_RE), name="bct_anchor_root_hash_valid"),
            models.CheckConstraint(
                condition=(
                    ~Q(status=LedgerAnchorStatus.CONFIRMED)
                    | (
                        (Q(provider_transaction_id__gt="") | Q(transaction_hash__gt=""))
                        & Q(block_number__isnull=False)
                        & Q(block_hash__gt="")
                        & Q(confirmations__gte=1)
                        & Q(confirmed_at__isnull=False)
                    )
                ),
                name="bct_anchor_confirmed_has_evidence",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "created_at"], name="anchor_tenant_status_created"),
            models.Index(fields=["tenant_id", "asset", "end_sequence"], name="bct_anchor_tenant_asset_end"),
            models.Index(fields=["tenant_id", "network", "status"], name="anchor_tenant_net_status"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "asset")
        _require_same_tenant(self, "network")
        _require_object(self.provider_receipt, "provider_receipt")
        _reject_secret_material(self.provider_receipt, "provider_receipt")
        lower_sha256_validator(self.root_hash)
        if self.end_sequence < self.start_sequence:
            raise ValidationError({"end_sequence": "End sequence cannot precede start sequence."})
        if self.hash_algorithm != "sha256":
            raise ValidationError({"hash_algorithm": "Only sha256 is supported."})
        if self.status == LedgerAnchorStatus.CONFIRMED:
            if not (self.provider_transaction_id or self.transaction_hash):
                raise ValidationError("Confirmed anchors require transaction identity.")
            if self.block_number is None or not self.block_hash or self.confirmed_at is None:
                raise ValidationError("Confirmed anchors require block evidence and confirmation time.")
            if self.network_id and self.confirmations < self.network.confirmation_depth:
                raise ValidationError({"confirmations": "The configured confirmation depth has not been reached."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if _changed_fields(self, [field.name for field in self._meta.concrete_fields]) and not self._state.adding:
            previous_status = type(self)._base_manager.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous_status == LedgerAnchorStatus.CONFIRMED:
                raise ImmutableEvidenceError("Confirmed anchors are immutable.", code="confirmed_immutable")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Ledger anchors are retained evidence.", code="evidence_retained")

    def __str__(self) -> str:
        return f"Anchor {self.asset_id} #{self.start_sequence}-{self.end_sequence} [{self.status}]"


class AuthenticityCredentialQuerySet(TerminalEvidenceQuerySet):
    terminal_statuses = frozenset({AuthenticityCredentialStatus.REVOKED, AuthenticityCredentialStatus.EXPIRED})


class AuthenticityCredential(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(TraceabilityAsset, models.PROTECT, related_name="credentials")
    public_id = models.CharField(max_length=128)
    credential_type = models.CharField(max_length=64)
    token_digest = models.CharField(max_length=64, validators=[lower_sha256_validator])
    claims = models.JSONField(default=dict, blank=True)
    claims_hash = models.CharField(max_length=64, validators=[lower_sha256_validator])
    signature_algorithm = models.CharField(max_length=32)
    issuer_key_ref = models.CharField(max_length=255)
    signature = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=AuthenticityCredentialStatus.choices,
        default=AuthenticityCredentialStatus.ACTIVE,
    )
    transition_history = models.JSONField(default=list, blank=True)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)
    created_by = models.CharField(max_length=255)
    objects = AuthenticityCredentialQuerySet.as_manager()

    class Meta:
        db_table = "blockchain_traceability_authenticity_credentials"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "public_id"], name="bct_credential_public_id_uniq"),
            models.UniqueConstraint(fields=["tenant_id", "token_digest"], name="bct_credential_digest_uniq"),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True) | Q(expires_at__gt=F("issued_at")),
                name="bct_credential_expiry_after_issue",
            ),
            models.CheckConstraint(condition=Q(token_digest__regex=LOWER_SHA256_RE), name="bct_credential_digest_valid"),
            models.CheckConstraint(condition=Q(claims_hash__regex=LOWER_SHA256_RE), name="bct_credential_claims_hash_valid"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "asset", "status"], name="cred_tenant_asset_status"),
            models.Index(fields=["tenant_id", "status", "expires_at"], name="cred_tenant_status_exp"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "asset")
        _require_object(self.claims, "claims")
        lower_sha256_validator(self.token_digest)
        lower_sha256_validator(self.claims_hash)
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise ValidationError({"expires_at": "Expiry must be later than issuance."})
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Transition history must be a JSON array."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            prior = type(self)._base_manager.filter(pk=self.pk).values_list("status", flat=True).first()
            if prior in {AuthenticityCredentialStatus.REVOKED, AuthenticityCredentialStatus.EXPIRED}:
                raise ImmutableEvidenceError("Terminal credentials are immutable.", code="terminal_immutable")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Credentials are retained evidence.", code="evidence_retained")

    def __str__(self) -> str:
        return f"Credential {self.public_id} [{self.status}]"


class ComplianceEvidenceQuerySet(TenantQuerySet):
    def update(self, **kwargs: Any) -> int:
        if self.exclude(status=ComplianceEvidenceStatus.DRAFT).exists():
            raise ImmutableEvidenceError("Finalized evidence is immutable.", code="finalized_immutable")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        if self.exclude(status=ComplianceEvidenceStatus.DRAFT).exists():
            raise ImmutableEvidenceError("Finalized evidence cannot be deleted.", code="finalized_immutable")
        return super().delete()


class ComplianceEvidence(MutableTenantModel):
    asset = models.ForeignKey(TraceabilityAsset, models.PROTECT, related_name="compliance_evidence")
    event = models.ForeignKey(TraceabilityEvent, models.PROTECT, null=True, blank=True, related_name="compliance_evidence")
    evidence_key = models.CharField(max_length=128)
    evidence_type = models.CharField(max_length=64)
    standard = models.CharField(max_length=128)
    jurisdiction = models.CharField(max_length=64, blank=True)
    result = models.CharField(max_length=16, choices=ComplianceResult.choices)
    details = models.JSONField(default=dict, blank=True)
    document_ref = models.UUIDField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, validators=[lower_sha256_validator])
    observed_at = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=ComplianceEvidenceStatus.choices,
        default=ComplianceEvidenceStatus.DRAFT,
    )
    transition_history = models.JSONField(default=list, blank=True)
    supersedes = models.ForeignKey("self", models.PROTECT, null=True, blank=True, related_name="replacements")
    finalized_at = models.DateTimeField(null=True, blank=True)
    objects = ComplianceEvidenceQuerySet.as_manager()

    FINAL_CONTENT_FIELDS = (
        "tenant_id",
        "asset_id",
        "event_id",
        "evidence_key",
        "evidence_type",
        "standard",
        "jurisdiction",
        "result",
        "details",
        "document_ref",
        "content_hash",
        "observed_at",
        "valid_until",
        "supersedes_id",
        "finalized_at",
        "created_by",
    )

    class Meta:
        db_table = "blockchain_traceability_compliance_evidence"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "evidence_key"],
                condition=Q(is_deleted=False),
                name="bct_evidence_tenant_key_active_uniq",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=F("observed_at")),
                name="bct_evidence_valid_after_observed",
            ),
            models.CheckConstraint(
                condition=Q(status=ComplianceEvidenceStatus.DRAFT) | Q(content_hash__regex=LOWER_SHA256_RE),
                name="bct_evidence_finalized_hash",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "asset", "status"], name="evid_tenant_asset_status"),
            models.Index(fields=["tenant_id", "evidence_type", "result"], name="evid_tenant_type_result"),
            models.Index(fields=["tenant_id", "standard", "jurisdiction"], name="bct_evidence_tenant_std_juris"),
            models.Index(fields=["tenant_id", "observed_at"], name="bct_evidence_tenant_observed"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "asset")
        _require_same_tenant(self, "event")
        _require_same_tenant(self, "supersedes")
        _require_object(self.details, "details")
        if self.event_id and self.asset_id and self.event.asset_id != self.asset_id:
            raise ValidationError({"event": "The event must belong to the evidence asset."})
        if self.supersedes_id and self.asset_id and self.supersedes.asset_id != self.asset_id:
            raise ValidationError({"supersedes": "Replacement evidence must concern the same asset."})
        if self.valid_until is not None and self.valid_until <= self.observed_at:
            raise ValidationError({"valid_until": "Validity must end after observation."})
        if self.status != ComplianceEvidenceStatus.DRAFT:
            lower_sha256_validator(self.content_hash)
            if self.finalized_at is None:
                raise ValidationError({"finalized_at": "Finalized evidence requires a finalization time."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            prior_status = type(self)._base_manager.filter(pk=self.pk).values_list("status", flat=True).first()
            if prior_status in {ComplianceEvidenceStatus.FINALIZED, ComplianceEvidenceStatus.SUPERSEDED}:
                changed = _changed_fields(self, self.FINAL_CONTENT_FIELDS)
                if changed:
                    raise ImmutableEvidenceError(
                        f"Finalized evidence fields are immutable: {', '.join(sorted(changed))}.",
                        code="finalized_immutable",
                    )
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.status != ComplianceEvidenceStatus.DRAFT:
            raise ImmutableEvidenceError("Finalized evidence cannot be deleted.", code="finalized_immutable")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.evidence_key} ({self.standard}) [{self.status}]"


class VerificationAttempt(AppendOnlyTenantModel):
    verification_type = models.CharField(max_length=32, choices=VerificationType.choices)
    asset = models.ForeignKey(TraceabilityAsset, models.PROTECT, null=True, blank=True, related_name="verifications")
    anchor = models.ForeignKey(LedgerAnchor, models.PROTECT, null=True, blank=True, related_name="verifications")
    credential = models.ForeignKey(
        AuthenticityCredential, models.PROTECT, null=True, blank=True, related_name="verifications"
    )
    compliance_evidence = models.ForeignKey(
        ComplianceEvidence, models.PROTECT, null=True, blank=True, related_name="verifications"
    )
    idempotency_key = models.CharField(max_length=255)
    presented_token_digest = models.CharField(max_length=64, blank=True, validators=[lower_sha256_validator])
    outcome = models.CharField(max_length=32, choices=VerificationOutcome.choices)
    reason_code = models.CharField(max_length=64)
    chain_head_hash = models.CharField(max_length=64, blank=True, validators=[lower_sha256_validator])
    proof_evidence = models.JSONField(default=dict, blank=True)
    actor_id = models.CharField(max_length=255)
    source_fingerprint = models.CharField(max_length=64, blank=True, validators=[lower_sha256_validator])
    correlation_id = models.CharField(max_length=64, db_index=True)
    latency_ms = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "blockchain_traceability_verification_attempts"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "verification_type", "idempotency_key"],
                name="bct_verify_tenant_type_idem_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    (~Q(verification_type=VerificationType.CHAIN) | Q(asset__isnull=False))
                    & (~Q(verification_type=VerificationType.ANCHOR) | Q(anchor__isnull=False))
                    & (
                        ~Q(verification_type=VerificationType.AUTHENTICITY)
                        | Q(credential__isnull=False)
                        | ~Q(presented_token_digest="")
                    )
                    & (~Q(verification_type=VerificationType.COMPLIANCE) | Q(compliance_evidence__isnull=False))
                ),
                name="bct_verify_required_target",
            ),
            models.CheckConstraint(
                condition=~Q(outcome=VerificationOutcome.VERIFIED) | ~Q(proof_evidence={}),
                name="bct_verify_verified_evidence",
            ),
            models.CheckConstraint(
                condition=~Q(reason_code="SIMULATED_PROVIDER") | Q(outcome=VerificationOutcome.INCONCLUSIVE),
                name="bct_verify_simulated_inconclusive",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "verification_type", "created_at"], name="bct_verify_tenant_type_created"),
            models.Index(fields=["tenant_id", "outcome", "created_at"], name="verify_tenant_outcome_created"),
            models.Index(fields=["tenant_id", "asset", "created_at"], name="verify_tenant_asset_created"),
        ]
        ordering = ["-created_at", "id"]

    def clean(self) -> None:
        super().clean()
        for relation in ("asset", "anchor", "credential", "compliance_evidence"):
            _require_same_tenant(self, relation)
        required = {
            VerificationType.CHAIN: self.asset_id,
            VerificationType.ANCHOR: self.anchor_id,
            VerificationType.AUTHENTICITY: self.credential_id or self.presented_token_digest,
            VerificationType.COMPLIANCE: self.compliance_evidence_id,
        }
        if not required.get(self.verification_type):
            raise ValidationError("The verification target required by its type is missing.")
        _require_object(self.proof_evidence, "proof_evidence")
        _reject_secret_material(self.proof_evidence, "proof_evidence")
        _reject_raw_source_data(self.proof_evidence, "proof_evidence")
        if self.outcome == VerificationOutcome.VERIFIED and not self.proof_evidence:
            raise ValidationError({"proof_evidence": "Verified outcomes require concrete evidence."})
        if self.reason_code == "SIMULATED_PROVIDER" and self.outcome != VerificationOutcome.INCONCLUSIVE:
            raise ValidationError("Simulated provider results must be inconclusive.")
        for field_name in ("presented_token_digest", "chain_head_hash", "source_fingerprint"):
            value = getattr(self, field_name)
            if value:
                lower_sha256_validator(value)

    def __str__(self) -> str:
        return f"{self.verification_type} verification [{self.outcome}] ({self.id})"
