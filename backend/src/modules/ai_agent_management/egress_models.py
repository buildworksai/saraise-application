"""Egress policy, decision evidence, and envelope-encrypted secret metadata."""

from __future__ import annotations

import ipaddress
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope

from .models import AITenantModel, AppendOnlyTenantModel, validate_same_tenant


def generate_uuid() -> str:
    """Preserve the callable referenced by migration 0001."""

    return str(uuid.uuid4())


class EgressDestinationType(models.TextChoices):
    DOMAIN = "domain", "Domain"
    IP = "ip", "IP address"
    CIDR = "cidr", "CIDR"
    URL_PATTERN = "url_pattern", "URL pattern"


class EgressProtocol(models.TextChoices):
    HTTP = "http", "HTTP"
    HTTPS = "https", "HTTPS"
    TCP = "tcp", "TCP"
    UDP = "udp", "UDP"


class SecretType(models.TextChoices):
    API_KEY = "api_key", "API key"
    PASSWORD = "password", "Password"
    TOKEN = "token", "Token"
    CERTIFICATE = "certificate", "Certificate"
    OTHER = "other", "Other"


@tenancy_scope(TENANT_SCOPED)
class EgressRule(AITenantModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    destination_type = models.CharField(max_length=20, choices=EgressDestinationType.choices)
    destination = models.CharField(max_length=500)
    port = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=(MinValueValidator(1), MaxValueValidator(65535)),
    )
    protocol = models.CharField(max_length=10, choices=EgressProtocol.choices, default=EgressProtocol.HTTPS)
    is_active = models.BooleanField(default=True)
    created_by = models.UUIDField()

    class Meta:
        db_table = "ai_egress_rules"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "destination_type", "destination", "port", "protocol"),
                name="ai_egress_t_target_uniq",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(port__isnull=True) | Q(port__gte=1, port__lte=65535),
                name="ai_egress_port_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active", "destination_type"), name="ai_egress_t_active_idx"),
            models.Index(fields=("tenant_id", "destination"), name="ai_egress_t_dest_idx"),
        ]
        ordering = ("name", "id")

    def clean(self) -> None:
        destination = self.destination.strip().lower().rstrip(".")
        if not destination or "*" in destination:
            raise ValidationError({"destination": "Wildcards and blank destinations are forbidden."})
        if self.destination_type in (EgressDestinationType.IP, EgressDestinationType.CIDR):
            try:
                address = (
                    ipaddress.ip_address(destination)
                    if self.destination_type == EgressDestinationType.IP
                    else ipaddress.ip_network(destination, strict=True)
                )
            except ValueError as exc:
                raise ValidationError({"destination": "Enter a canonical IP address or CIDR."}) from exc
            if not address.is_global:
                raise ValidationError({"destination": "Internal, reserved, and metadata destinations are forbidden."})
            destination = str(address)
        elif self.destination_type == EgressDestinationType.DOMAIN:
            if "://" in destination or "/" in destination or destination == "localhost" or "." not in destination:
                raise ValidationError({"destination": "Enter a canonical public DNS name."})
        elif self.destination_type == EgressDestinationType.URL_PATTERN:
            if not destination.startswith(("https://", "http://")) or any(
                token in destination for token in ("*", "[", "]", "(")
            ):
                raise ValidationError(
                    {"destination": "URL patterns must be exact public HTTP(S) prefixes without wildcards."}
                )
        self.destination = destination

    def __str__(self) -> str:
        return f"Egress Rule: {self.destination} ({self.destination_type})"


@tenancy_scope(TENANT_SCOPED)
class EgressRequest(AppendOnlyTenantModel):
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.PROTECT,
        related_name="egress_requests",
    )
    destination = models.CharField(max_length=500)
    resolved_address = models.GenericIPAddressField(null=True, blank=True, unpack_ipv4=True)
    port = models.PositiveIntegerField(validators=(MinValueValidator(1), MaxValueValidator(65535)))
    protocol = models.CharField(max_length=10, choices=EgressProtocol.choices)
    allowed = models.BooleanField()
    matched_rule = models.ForeignKey(
        EgressRule,
        on_delete=models.PROTECT,
        related_name="matched_requests",
        null=True,
        blank=True,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reason_code = models.CharField(max_length=100)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_egress_requests"
        constraints = [
            models.CheckConstraint(
                condition=Q(allowed=False) | Q(matched_rule__isnull=False),
                name="ai_egress_allowed_rule_ck",
            ),
            models.CheckConstraint(condition=Q(port__gte=1, port__lte=65535), name="ai_egress_request_port_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "agent_execution", "requested_at"), name="ai_egress_req_t_exec_idx"),
            models.Index(fields=("tenant_id", "allowed", "requested_at"), name="ai_egress_req_t_allow_idx"),
        ]
        ordering = ("-requested_at", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "agent_execution", "matched_rule")
        if self.allowed and self.matched_rule_id and not self.matched_rule.is_active:
            raise ValidationError({"matched_rule": "An allowed request requires an active rule."})
        if not isinstance(self.metadata, dict):
            raise ValidationError({"metadata": "Must be a JSON object."})

    def __str__(self) -> str:
        return f"Egress Request {self.id} ({'allowed' if self.allowed else 'blocked'})"


@tenancy_scope(TENANT_SCOPED)
class Secret(AITenantModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    secret_type = models.CharField(max_length=20, choices=SecretType.choices)
    ciphertext = models.TextField(editable=False)
    wrapped_data_key = models.TextField(editable=False)
    key_id = models.CharField(max_length=255, editable=False)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_rotated_at = models.DateTimeField(default=timezone.now)
    rotation_interval_days = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.UUIDField()

    class Meta:
        db_table = "ai_secrets"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "name"), name="ai_secret_t_name_uniq"),
            models.CheckConstraint(
                condition=Q(rotation_interval_days__isnull=True) | Q(rotation_interval_days__gt=0),
                name="ai_secret_rotation_ck",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True) | Q(expires_at__gt=models.F("created_at")),
                name="ai_secret_expiry_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "name"), name="ai_secret_t_name_idx"),
            models.Index(fields=("tenant_id", "is_active", "expires_at"), name="ai_secret_t_active_idx"),
        ]
        ordering = ("name", "id")

    def __str__(self) -> str:
        return f"Secret {self.name} ({self.secret_type})"


@tenancy_scope(TENANT_SCOPED)
class SecretAccess(AppendOnlyTenantModel):
    secret = models.ForeignKey(Secret, on_delete=models.PROTECT, related_name="access_logs")
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.PROTECT,
        related_name="secret_accesses",
        null=True,
        blank=True,
    )
    accessed_by = models.UUIDField()
    accessed_at = models.DateTimeField(auto_now_add=True)
    purpose = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_secret_accesses"
        indexes = [
            models.Index(fields=("tenant_id", "secret", "accessed_at"), name="ai_secret_acc_t_secret_idx"),
            models.Index(fields=("tenant_id", "agent_execution", "accessed_at"), name="ai_secret_acc_t_exec_idx"),
        ]
        ordering = ("-accessed_at", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "secret", "agent_execution")
        if not self.purpose.strip():
            raise ValidationError({"purpose": "A nonblank access purpose is required."})
        if not isinstance(self.metadata, dict):
            raise ValidationError({"metadata": "Must be a JSON object."})

    def __str__(self) -> str:
        return f"Secret Access {self.id}"


@tenancy_scope(TENANT_SCOPED)
class SecretRotationRecord(AppendOnlyTenantModel):
    """Idempotency and compensation evidence for a completed secret rotation."""

    secret = models.ForeignKey(Secret, on_delete=models.PROTECT, related_name="rotation_records")
    idempotency_key = models.CharField(max_length=255)
    rotated_by = models.UUIDField()
    correlation_id = models.UUIDField()
    previous_ciphertext = models.TextField(editable=False)
    previous_wrapped_data_key = models.TextField(editable=False)
    previous_key_id = models.CharField(max_length=255, editable=False)
    resulting_rotated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_secret_rotation_records"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="ai_secret_rotation_t_idem_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "secret", "-created_at"),
                name="ai_secret_rotation_t_sec_idx",
            ),
            models.Index(fields=("tenant_id", "correlation_id"), name="ai_secret_rotation_corr_idx"),
        ]

    def clean(self) -> None:
        validate_same_tenant(self, "secret")
