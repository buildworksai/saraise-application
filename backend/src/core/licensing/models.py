"""
License data models for SARAISE.

This module contains:
1. Dataclasses for license information (from license server or offline keys)
2. Django models for storing license data in the database

Reference: saraise-documentation/licensing/licensing-architecture.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from django.db import models
from django.utils import timezone
import uuid


class LicenseTier(Enum):
    """License tier levels."""
    TRIAL = "trial"
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class LicenseStatus(Enum):
    """License validation status."""
    VALID = "valid"
    EXPIRED = "expired"
    GRACE_PERIOD = "grace_period"
    INVALID = "invalid"
    NOT_FOUND = "not_found"


@dataclass
class ModuleLicense:
    """License information for a specific module."""
    module_id: str
    module_name: str
    tier_required: LicenseTier
    is_licensed: bool
    expires_at: Optional[datetime] = None
    features: list[str] = field(default_factory=list)


@dataclass
class LicenseInfo:
    """
    Complete license information for an organization.
    
    Attributes:
        organization_id: Immutable organization identifier (bound to license key)
        organization_name: Display name of the organization
        tier: Current license tier
        status: Current validation status
        issued_at: When the license was issued
        expires_at: When the license expires
        grace_expires_at: When grace period ends (if in grace period)
        licensed_modules: List of licensed modules
        is_connected: Whether this is a connected or isolated license
        last_validated: Last successful validation timestamp
    """
    organization_id: str
    organization_name: str
    tier: LicenseTier
    status: LicenseStatus
    issued_at: datetime
    expires_at: datetime
    licensed_modules: list[ModuleLicense] = field(default_factory=list)
    grace_expires_at: Optional[datetime] = None
    is_connected: bool = True
    last_validated: Optional[datetime] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if license is currently valid (includes grace period)."""
        return self.status in (LicenseStatus.VALID, LicenseStatus.GRACE_PERIOD)
    
    @property
    def is_expired(self) -> bool:
        """Check if license is expired (past grace period)."""
        return self.status == LicenseStatus.EXPIRED
    
    @property
    def days_until_expiry(self) -> int:
        """Calculate days until license expires."""
        if self.expires_at:
            delta = self.expires_at - datetime.utcnow()
            return max(0, delta.days)
        return 0
    
    def has_module(self, module_id: str) -> bool:
        """Check if a specific module is licensed."""
        return any(m.module_id == module_id and m.is_licensed 
                   for m in self.licensed_modules)


@dataclass
class TrialInfo:
    """Trial period information."""
    organization_id: str
    started_at: datetime
    expires_at: datetime
    is_expired: bool
    days_remaining: int
    
    @classmethod
    def calculate(cls, organization_id: str, started_at: datetime, 
                  trial_days: int = 14) -> 'TrialInfo':
        """Calculate trial info from start date."""
        from datetime import timedelta
        expires_at = started_at + timedelta(days=trial_days)
        now = datetime.utcnow()
        is_expired = now > expires_at
        days_remaining = max(0, (expires_at - now).days) if not is_expired else 0
        
        return cls(
            organization_id=organization_id,
            started_at=started_at,
            expires_at=expires_at,
            is_expired=is_expired,
            days_remaining=days_remaining,
        )


# ============================================================================
# Django Models for License Storage
# ============================================================================

class LicenseStatus(models.TextChoices):
    """License status choices for Django model."""
    TRIAL = 'trial', 'Trial'
    ACTIVE = 'active', 'Active'
    EXPIRED = 'expired', 'Expired'
    GRACE = 'grace', 'Grace Period'
    LOCKED = 'locked', 'Locked'


class Organization(models.Model):
    """Organization bound to license key.
    
    CRITICAL: In self-hosted mode, there is only ONE organization per deployment.
    This model stores the organization information for the license.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'licensing_organization'
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'
    
    def __str__(self):
        return self.name


class License(models.Model):
    """License record for self-hosted deployments.
    
    CRITICAL: In self-hosted mode, there is only ONE license per deployment.
    This model tracks the license status, trial period, and module access.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    
    # License details
    license_key = models.TextField(blank=True)  # Encrypted JWT-like structure
    status = models.CharField(
        max_length=20, 
        choices=LicenseStatus.choices, 
        default=LicenseStatus.TRIAL
    )
    
    # Tier and limits
    core_tier = models.CharField(
        max_length=20, 
        default='free'
    )  # free, professional, enterprise
    max_companies = models.IntegerField(default=1)
    max_users = models.IntegerField(default=-1)  # -1 = unlimited
    
    # Industry modules
    industry_modules = models.JSONField(
        default=list
    )  # ["manufacturing", "retail"]
    
    # Validity
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    license_issued_at = models.DateTimeField(null=True, blank=True)
    license_expires_at = models.DateTimeField(null=True, blank=True)
    grace_ends_at = models.DateTimeField(null=True, blank=True)
    
    # Tracking
    last_validated_at = models.DateTimeField(null=True, blank=True)
    validation_failures = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'licensing_license'
        verbose_name = 'License'
        verbose_name_plural = 'Licenses'
    
    def is_trial_active(self) -> bool:
        """Check if trial period is still active."""
        if self.status != LicenseStatus.TRIAL:
            return False
        if not self.trial_ends_at:
            return False
        return timezone.now() < self.trial_ends_at
    
    def is_license_valid(self) -> bool:
        """Check if license is valid (not expired)."""
        if self.status == LicenseStatus.TRIAL:
            return self.is_trial_active()
        if self.status in [LicenseStatus.EXPIRED, LicenseStatus.LOCKED]:
            return False
        if self.status == LicenseStatus.GRACE:
            return self.grace_ends_at and timezone.now() < self.grace_ends_at
        if self.status == LicenseStatus.ACTIVE:
            return self.license_expires_at and timezone.now() < self.license_expires_at
        return False
    
    def can_write(self) -> bool:
        """Check if write operations are allowed.
        
        In soft lock, only reads are allowed.
        """
        return self.status not in [LicenseStatus.EXPIRED, LicenseStatus.LOCKED]
    
    def has_module(self, module_name: str) -> bool:
        """Check if license includes a specific industry module."""
        return module_name in self.industry_modules
    
    def __str__(self):
        return f"{self.organization.name} - {self.status}"


class LicenseValidationLog(models.Model):
    """Audit log for license validations.
    
    Tracks all license validation attempts for debugging and compliance.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    license = models.ForeignKey(License, on_delete=models.CASCADE)
    
    validation_type = models.CharField(
        max_length=20
    )  # startup, periodic, module_access
    success = models.BooleanField()
    error_message = models.TextField(blank=True)
    server_response = models.JSONField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'licensing_validation_log'
        verbose_name = 'License Validation Log'
        verbose_name_plural = 'License Validation Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['license', '-created_at']),
            models.Index(fields=['validation_type', 'success']),
        ]
    
    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"{self.license.organization.name} - {self.validation_type} - {status}"

