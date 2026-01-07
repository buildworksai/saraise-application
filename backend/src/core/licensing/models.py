"""
License data models for SARAISE.

These are NOT Django models - they are dataclasses for license information
that may come from the license server or offline key files.

Reference: saraise-documentation/licensing/licensing-architecture.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


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

