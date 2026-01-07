"""
License Server Client for SARAISE.

Handles communication with license.saraise.com for:
- License validation
- Usage reporting
- Feature flag retrieval

Reference: saraise-documentation/licensing/licensing-architecture.md
"""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from django.conf import settings

from .models import LicenseInfo, LicenseStatus, LicenseTier, ModuleLicense

logger = logging.getLogger('saraise.licensing')


class LicenseClient:
    """
    Client for communicating with the SARAISE license server.
    
    Supports both connected mode (online validation) and isolated mode
    (offline key validation).
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the license client.
        
        Args:
            base_url: License server URL. Defaults to SARAISE_LICENSE_SERVER_URL.
        """
        self.base_url = base_url or getattr(
            settings, 'SARAISE_LICENSE_SERVER_URL', 
            'https://license.saraise.com'
        )
        self._cached_license: Optional[LicenseInfo] = None
        self._cache_timestamp: Optional[datetime] = None
    
    def validate(self, license_key: str, organization_id: str) -> LicenseInfo:
        """
        Validate a license key with the server.
        
        Args:
            license_key: The license key to validate
            organization_id: The organization ID to validate against
            
        Returns:
            LicenseInfo with validation result
            
        Raises:
            LicenseValidationError: If validation fails
        """
        mode = getattr(settings, 'SARAISE_MODE', 'development')
        
        # In development mode, return a mock valid license
        if mode == 'development':
            logger.debug("Development mode - returning mock license")
            return self._mock_development_license(organization_id)
        
        license_mode = getattr(settings, 'SARAISE_LICENSE_MODE', 'connected')
        
        if license_mode == 'isolated':
            return self._validate_offline(license_key, organization_id)
        else:
            return self._validate_online(license_key, organization_id)
    
    def _validate_online(self, license_key: str, organization_id: str) -> LicenseInfo:
        """Validate license against the license server."""
        # TODO: Implement actual HTTP call to license server
        # POST /api/v1/validate
        # Body: { "license_key": "...", "organization_id": "..." }
        logger.info(f"Validating license online for org: {organization_id}")
        
        # Placeholder - will be implemented when license server is ready
        raise NotImplementedError(
            "Online license validation not yet implemented. "
            "Use SARAISE_MODE=development for testing."
        )
    
    def _validate_offline(self, license_key: str, organization_id: str) -> LicenseInfo:
        """Validate an offline license key."""
        # TODO: Implement cryptographic validation of offline keys
        # Keys are signed JWT-like structures with:
        # - Organization ID (must match)
        # - Tier
        # - Expiry date
        # - Licensed modules
        # - Signature (RSA/Ed25519)
        logger.info(f"Validating offline license for org: {organization_id}")
        
        # Placeholder - will be implemented when key format is finalized
        raise NotImplementedError(
            "Offline license validation not yet implemented. "
            "Use SARAISE_MODE=development for testing."
        )
    
    def _mock_development_license(self, organization_id: str) -> LicenseInfo:
        """Return a mock license for development mode."""
        from datetime import timedelta
        
        now = datetime.utcnow()
        
        # All modules enabled in development
        mock_modules = [
            ModuleLicense(
                module_id="foundation.*",
                module_name="All Foundation Modules",
                tier_required=LicenseTier.FREE,
                is_licensed=True,
                expires_at=now + timedelta(days=365),
            ),
            ModuleLicense(
                module_id="core.*",
                module_name="All Core Modules",
                tier_required=LicenseTier.FREE,
                is_licensed=True,
                expires_at=now + timedelta(days=365),
            ),
            ModuleLicense(
                module_id="industry.*",
                module_name="All Industry Modules",
                tier_required=LicenseTier.ENTERPRISE,
                is_licensed=True,  # Enabled for development
                expires_at=now + timedelta(days=365),
            ),
        ]
        
        return LicenseInfo(
            organization_id=organization_id or "dev-org-001",
            organization_name="Development Organization",
            tier=LicenseTier.ENTERPRISE,
            status=LicenseStatus.VALID,
            issued_at=now,
            expires_at=now + timedelta(days=365),
            licensed_modules=mock_modules,
            is_connected=False,
            last_validated=now,
        )
    
    def get_cached_license(self) -> Optional[LicenseInfo]:
        """Get the cached license info if still valid."""
        if self._cached_license and self._cache_timestamp:
            from datetime import timedelta
            cache_age = datetime.utcnow() - self._cache_timestamp
            # Cache valid for 1 hour
            if cache_age < timedelta(hours=1):
                return self._cached_license
        return None
    
    def clear_cache(self) -> None:
        """Clear the license cache."""
        self._cached_license = None
        self._cache_timestamp = None


class LicenseValidationError(Exception):
    """Raised when license validation fails."""
    
    def __init__(self, message: str, status: LicenseStatus):
        super().__init__(message)
        self.status = status

