"""
License Validator for SARAISE.

Provides centralized license validation logic including:
- Module access checks
- Grace period handling
- Soft-lock enforcement (read-only mode)

Reference: saraise-documentation/licensing/licensing-architecture.md
"""

import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

from django.conf import settings

from .client import LicenseClient
from .models import LicenseInfo, LicenseValidationStatus, LicenseTier

logger = logging.getLogger('saraise.licensing')


class LicenseValidator:
    """
    Central license validator for SARAISE self-hosted installations.
    
    Responsibilities:
    - Validate license on startup
    - Check module access
    - Enforce grace periods
    - Apply soft-lock (read-only) for expired modules
    """
    
    _instance: Optional['LicenseValidator'] = None
    
    def __new__(cls):
        """Singleton pattern for license validator."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the license validator."""
        if self._initialized:
            return
            
        self._client = LicenseClient()
        self._license_info: Optional[LicenseInfo] = None
        self._last_check: Optional[datetime] = None
        self._initialized = True
    
    @property
    def is_development_mode(self) -> bool:
        """Check if running in development mode."""
        return getattr(settings, 'SARAISE_MODE', 'development') == 'development'
    
    @property
    def is_self_hosted(self) -> bool:
        """Check if running in self-hosted mode."""
        return getattr(settings, 'SARAISE_MODE', 'development') == 'self-hosted'
    
    @property
    def is_saas_mode(self) -> bool:
        """Check if running in SaaS mode."""
        return getattr(settings, 'SARAISE_MODE', 'development') == 'saas'
    
    def get_license(self) -> Optional[LicenseInfo]:
        """Get current license information."""
        if self.is_development_mode:
            return self._client._mock_development_license("dev-org")
        return self._license_info
    
    def validate_startup(self, license_key: str, organization_id: str) -> LicenseInfo:
        """
        Validate license on application startup.
        
        Called during Django startup to verify license status.
        
        Args:
            license_key: The license key
            organization_id: The organization ID
            
        Returns:
            LicenseInfo with current status
        """
        if self.is_development_mode:
            logger.info("Development mode - skipping license validation")
            self._license_info = self._client._mock_development_license(organization_id)
            return self._license_info
        
        if self.is_saas_mode:
            logger.info("SaaS mode - license managed by platform")
            # In SaaS mode, platform handles licensing
            return self._client._mock_development_license(organization_id)
        
        # Self-hosted mode - actual validation
        logger.info(f"Validating license for organization: {organization_id}")
        self._license_info = self._client.validate(license_key, organization_id)
        self._last_check = datetime.utcnow()
        
        if self._license_info.status == LicenseValidationStatus.GRACE_PERIOD:
            days_left = self._license_info.days_until_expiry
            logger.warning(
                f"License in grace period! {days_left} days remaining. "
                "Please renew to avoid service interruption."
            )
        elif self._license_info.status == LicenseValidationStatus.EXPIRED:
            logger.error(
                "License has expired! Application will operate in read-only mode. "
                "Please renew your subscription."
            )
        
        return self._license_info
    
    def check_module_access(self, module_id: str, write_operation: bool = False) -> bool:
        """
        Check if a module is accessible.
        
        Args:
            module_id: The module to check (e.g., "foundation.user_management")
            write_operation: Whether this is a write operation
            
        Returns:
            True if access is allowed, False otherwise
        """
        if self.is_development_mode:
            return True
        
        if self.is_saas_mode:
            # SaaS mode - module access controlled by platform
            return True
        
        license_info = self.get_license()
        if not license_info:
            logger.warning(f"No license info - denying access to {module_id}")
            return False
        
        # Check if license is valid
        if not license_info.is_valid:
            if write_operation:
                # Soft-lock: deny write operations for expired licenses
                logger.warning(
                    f"License expired - denying write access to {module_id}"
                )
                return False
            # Allow read operations even with expired license
            return True
        
        # Check module-specific licensing
        if license_info.has_module(module_id):
            return True
        
        # Check wildcard patterns (e.g., "foundation.*")
        module_parts = module_id.split('.')
        if len(module_parts) >= 1:
            wildcard = f"{module_parts[0]}.*"
            if license_info.has_module(wildcard):
                return True
        
        logger.debug(f"Module {module_id} not in licensed modules")
        return False
    
    def is_trial_active(self) -> bool:
        """Check if trial period is active."""
        license_info = self.get_license()
        if license_info:
            return license_info.tier == LicenseTier.TRIAL and license_info.is_valid
        return False
    
    def get_trial_days_remaining(self) -> int:
        """Get remaining trial days."""
        license_info = self.get_license()
        if license_info and license_info.tier == LicenseTier.TRIAL:
            return license_info.days_until_expiry
        return 0
    
    def is_soft_locked(self) -> bool:
        """Check if application is in soft-lock (read-only) mode."""
        if self.is_development_mode or self.is_saas_mode:
            return False
        
        license_info = self.get_license()
        if license_info:
            return license_info.status == LicenseValidationStatus.EXPIRED
        return True  # No license = soft-locked
    
    def needs_renewal_warning(self) -> tuple[bool, int]:
        """
        Check if renewal warning should be shown.
        
        Returns:
            Tuple of (show_warning, days_remaining)
        """
        license_info = self.get_license()
        if not license_info:
            return False, 0
        
        days = license_info.days_until_expiry
        # Show warning when less than 30 days remaining
        return days <= 30 and days > 0, days


# Singleton accessor
def get_license_validator() -> LicenseValidator:
    """Get the singleton license validator instance."""
    return LicenseValidator()

