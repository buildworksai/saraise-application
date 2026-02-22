"""
License Server Client for SARAISE.

Handles communication with license.saraise.com for:
- License validation
- Usage reporting
- Feature flag retrieval

Reference: saraise-documentation/licensing/licensing-architecture.md
"""

import logging
import time
from datetime import datetime
from typing import Optional

import requests
from django.conf import settings

from .models import LicenseInfo, LicenseTier, LicenseValidationStatus, ModuleLicense

logger = logging.getLogger("saraise.licensing")


def _tier_from_string(s: str) -> LicenseTier:
    """Map platform tier string to LicenseTier enum."""
    mapping = {
        "trial": LicenseTier.TRIAL,
        "free": LicenseTier.FREE,
        "starter": LicenseTier.STARTER,
        "professional": LicenseTier.PROFESSIONAL,
        "enterprise": LicenseTier.ENTERPRISE,
    }
    return mapping.get((s or "free").lower(), LicenseTier.FREE)


class _CircuitBreaker:
    """
    Simple circuit breaker for license server calls (Jidoka requirement).

    Opens after failure_threshold consecutive failures.
    Stays open for reset_timeout_seconds before allowing retry.
    """

    def __init__(self, failure_threshold: int = 5, reset_timeout_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout_seconds
        self._failures = 0
        self._last_failure_time: Optional[float] = None

    def call(self, fn, *args, **kwargs):
        """Execute fn if circuit is closed; raise if open."""
        now = time.monotonic()
        if self._failures >= self.failure_threshold and self._last_failure_time:
            if now - self._last_failure_time < self.reset_timeout:
                raise LicenseValidationError(
                    "License server circuit breaker open",
                    LicenseValidationStatus.INVALID,
                )
            self._failures = 0

        try:
            result = fn(*args, **kwargs)
            self._failures = 0
            return result
        except Exception as e:
            self._failures += 1
            self._last_failure_time = now
            raise


class LicenseClient:
    """
    Client for communicating with the SARAISE license server.

    Supports both connected mode (online validation) and isolated mode
    (offline key validation).
    """

    TIMEOUT = 10
    _circuit_breaker = _CircuitBreaker()

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the license client.

        Args:
            base_url: License server URL. Defaults to SARAISE_LICENSE_SERVER_URL.
        """
        self.base_url = (
            base_url
            or getattr(settings, "SARAISE_LICENSE_SERVER_URL", "https://license.saraise.com")
        ).rstrip("/")
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
        mode = getattr(settings, "SARAISE_MODE", "development")

        # In development mode, return a mock valid license
        if mode == "development":
            logger.debug("Development mode - returning mock license")
            return self._mock_development_license(organization_id)

        license_mode = getattr(settings, "SARAISE_LICENSE_MODE", "connected")

        if license_mode == "isolated":
            return self._validate_offline(license_key, organization_id)
        else:
            return self._validate_online(license_key, organization_id)

    def _validate_online(self, license_key: str, organization_id: str) -> LicenseInfo:
        """Validate license against the license server (connected mode)."""
        logger.info("Validating license online for org: %s", organization_id)

        version = getattr(settings, "SARAISE_VERSION", "1.0.0")

        def _do_request():
            return requests.post(
                f"{self.base_url}/api/v1/validate/",
                json={
                    "organization_id": organization_id,
                    "license_key": license_key,
                    "instance_id": self._get_instance_id(),
                    "version": version,
                    "modules_requested": [],
                },
                timeout=self.TIMEOUT,
            )

        try:
            response = self._circuit_breaker.call(_do_request)
        except requests.RequestException as e:
            logger.warning("License server request failed: %s", e)
            raise LicenseValidationError(
                f"License server unreachable: {e}",
                LicenseValidationStatus.INVALID,
            ) from e

        if response.status_code == 200:
            data = response.json()
            if data.get("valid"):
                return self._parse_success_response(data, organization_id)
            error = data.get("error", "unknown")
            message = data.get("message", "License invalid")
            status = (
                LicenseValidationStatus.EXPIRED
                if error == "license_expired"
                else LicenseValidationStatus.INVALID
            )
            raise LicenseValidationError(message, status)

        raise LicenseValidationError(
            f"License server returned {response.status_code}",
            LicenseValidationStatus.INVALID,
        )

    def _parse_success_response(self, data: dict, organization_id: str) -> LicenseInfo:
        """Parse platform validation success response into LicenseInfo."""
        from datetime import timedelta

        now = datetime.utcnow()
        license_data = data.get("license", {})
        expires_at_str = license_data.get("expires_at", "")
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            expires_at = now + timedelta(days=365)

        modules_data = data.get("modules", {})
        allowed = modules_data.get("allowed", [])
        licensed_modules = [
            ModuleLicense(
                module_id=m,
                module_name=m.replace(".", " ").replace("_", " ").title(),
                tier_required=LicenseTier.FREE,
                is_licensed=True,
                expires_at=expires_at,
            )
            for m in allowed
        ]
        if not licensed_modules:
            licensed_modules = [
                ModuleLicense(
                    module_id="core.*",
                    module_name="Core Modules",
                    tier_required=LicenseTier.FREE,
                    is_licensed=True,
                    expires_at=expires_at,
                ),
            ]

        tier_str = license_data.get("tier", "free")
        return LicenseInfo(
            organization_id=organization_id,
            organization_name="Licensed Organization",
            tier=_tier_from_string(tier_str),
            status=LicenseValidationStatus.VALID,
            issued_at=now,
            expires_at=expires_at,
            licensed_modules=licensed_modules,
            is_connected=True,
            last_validated=now,
        )

    def _validate_offline(self, license_key: str, organization_id: str) -> LicenseInfo:
        """Validate an offline license key (platform format: base64(JSON+signature))."""
        from .services import LicenseService

        logger.info("Validating offline license for org: %s", organization_id)

        try:
            data, signature = LicenseService._decode_license_key(license_key)
        except ValueError as e:
            raise LicenseValidationError(str(e), LicenseValidationStatus.INVALID) from e

        if not LicenseService._verify_signature(data, signature):
            raise LicenseValidationError(
                "Invalid license key signature",
                LicenseValidationStatus.INVALID,
            )

        org_data = data.get("organization", {})
        org_id = org_data.get("id") or data.get("organization_id")
        if org_id != organization_id:
            raise LicenseValidationError(
                "License key does not match organization",
                LicenseValidationStatus.INVALID,
            )

        validity = data.get("validity", {})
        expires_at_str = validity.get("expires_at") or data.get("expires_at", "")
        if not expires_at_str:
            raise LicenseValidationError(
                "License key missing expiration",
                LicenseValidationStatus.INVALID,
            )

        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError) as e:
            raise LicenseValidationError(
                f"Invalid expiration format: {e}",
                LicenseValidationStatus.INVALID,
            ) from e

        if datetime.utcnow().replace(tzinfo=expires_at.tzinfo) > expires_at:
            raise LicenseValidationError(
                "License has expired",
                LicenseValidationStatus.EXPIRED,
            )

        core = data.get("core", {})
        modules = data.get("modules", {})
        license_info = data.get("license", {})
        tier_str = license_info.get("tier", core.get("tier", "free"))
        included = modules.get("included", [])

        licensed_modules = [
            ModuleLicense(
                module_id=m,
                module_name=m.replace(".", " ").replace("_", " ").title(),
                tier_required=_tier_from_string(tier_str),
                is_licensed=True,
                expires_at=expires_at,
            )
            for m in included
        ]
        if not licensed_modules:
            licensed_modules = [
                ModuleLicense(
                    module_id="core.*",
                    module_name="Core Modules",
                    tier_required=_tier_from_string(tier_str),
                    is_licensed=True,
                    expires_at=expires_at,
                ),
            ]

        return LicenseInfo(
            organization_id=organization_id,
            organization_name=org_data.get("name", "Licensed Organization"),
            tier=_tier_from_string(tier_str),
            status=LicenseValidationStatus.VALID,
            issued_at=datetime.utcnow(),
            expires_at=expires_at,
            licensed_modules=licensed_modules,
            is_connected=False,
            last_validated=datetime.utcnow(),
        )

    def _get_instance_id(self) -> str:
        """Generate unique instance ID (matches LicenseService)."""
        import hashlib
        import socket
        import uuid as uuid_mod

        data = f"{socket.gethostname()}-{uuid_mod.getnode()}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

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
            status=LicenseValidationStatus.VALID,
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

    def __init__(self, message: str, status: LicenseValidationStatus):
        super().__init__(message)
        self.status = status
