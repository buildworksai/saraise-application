"""
License Service for SARAISE.

Business logic for license validation and management.

Phase 7.5: Licensing Subsystem
Reference: saraise-documentation/planning/phases/phase-7.5-licensing.md
"""

import base64
import hashlib
import json
import logging
import socket
from datetime import datetime, timedelta
from typing import Any, Mapping, Tuple

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from django.conf import settings
from django.utils import timezone

from .models import License, LicenseStatus, LicenseValidationLog, Organization

logger = logging.getLogger("saraise.licensing")


class LicenseService:
    """Service for license validation and management."""

    TRIAL_DURATION_DAYS = 14
    GRACE_PERIOD_DAYS = 30
    LICENSE_SERVER_URL = "https://license.saraise.com"
    SERVER_UNREACHABLE_MESSAGE = "License server unreachable."
    # fmt: off
    RESTORE_CONNECTIVITY_MESSAGE = (
        "Please restore connectivity to license server."
    )
    PUBLIC_KEY_MISSING_MESSAGE = (
        "License public key not configured - "
        "signature verification skipped"
    )
    # fmt: on

    @staticmethod
    def _mapping_value(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        """Return nested JSON data only when it is an object."""
        value = data.get(key)
        if isinstance(value, Mapping):
            return value
        return {}

    @classmethod
    def initialize_trial(cls, organization: Organization) -> License:
        """Initialize 14-day trial for new organization."""
        now = timezone.now()
        trial_ends = now + timedelta(days=cls.TRIAL_DURATION_DAYS)

        license = License.objects.create(
            organization=organization,
            status=LicenseStatus.TRIAL,
            core_tier="free",
            max_companies=1,
            max_users=-1,
            trial_started_at=now,
            trial_ends_at=trial_ends,
        )

        cls._log_validation(license, "trial_start", True)
        return license

    @classmethod
    def validate_license(cls, license: License) -> Tuple[bool, str]:
        """
        Validate license based on mode.

        Returns:
            Tuple of (is_valid, message)
        """
        mode = getattr(settings, "SARAISE_MODE", "development")
        license_mode = getattr(settings, "SARAISE_LICENSE_MODE", "connected")

        # Development mode - skip validation
        if mode == "development":
            return True, "Development mode - validation skipped"

        # SaaS mode - skip (handled by platform billing)
        if mode == "saas":
            return True, "SaaS mode - handled by platform billing"

        # Self-hosted mode
        if mode == "self-hosted":
            if license_mode == "connected":
                return cls._validate_connected(license)
            else:
                return cls._validate_isolated(license)

        return False, f"Unknown mode: {mode}"

    @classmethod
    def _validate_connected(cls, license: License) -> Tuple[bool, str]:
        """Validate license via license server."""
        version = getattr(settings, "SARAISE_VERSION", "1.0.0")
        license_server_url = getattr(
            settings,
            "SARAISE_LICENSE_SERVER_URL",
            cls.LICENSE_SERVER_URL,
        )
        try:
            response = requests.post(
                f"{license_server_url}/api/v1/validate/",
                json={
                    "organization_id": str(license.organization_id),
                    "license_key": license.license_key,
                    "instance_id": cls._get_instance_id(),
                    "version": version,
                    "modules_requested": [],
                },
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, Mapping):
                    cls._handle_invalid(license, "invalid_server_response")
                    cls._log_validation(
                        license,
                        "connected",
                        False,
                        "Invalid server response",
                    )
                    return False, "License server returned invalid response"
                if data.get("valid"):
                    cls._update_from_server(license, data)
                    cls._log_validation(
                        license,
                        "connected",
                        True,
                        server_response=data,
                    )
                    return True, "License valid"
                else:
                    cls._handle_invalid(license, data.get("error", "unknown"))
                    message = str(data.get("message", "License invalid"))
                    cls._log_validation(
                        license,
                        "connected",
                        False,
                        message,
                        data,
                    )
                    return False, message
            else:
                # Server error - enter grace period if not already
                return cls._handle_server_unreachable(license)

        except requests.RequestException as e:
            logger.warning(f"License server request failed: {e}")
            return cls._handle_server_unreachable(license)

    @classmethod
    def _validate_isolated(cls, license: License) -> Tuple[bool, str]:
        """Validate offline license key."""
        if not license.license_key:
            return False, "No license key configured"

        try:
            # Decode and verify key (platform format)
            data, signature = cls._decode_license_key(license.license_key)

            # Verify signature
            if not cls._verify_signature(data, signature):
                cls._log_validation(
                    license,
                    "isolated",
                    False,
                    "Invalid signature",
                )
                return False, "Invalid license key signature"

            # Extract org ID (platform uses organization.id)
            org_data = cls._mapping_value(data, "organization")
            org_id = org_data.get("id") or data.get("organization_id")
            if org_id != str(license.organization_id):
                cls._log_validation(
                    license,
                    "isolated",
                    False,
                    "Organization mismatch",
                )
                return False, "License key does not match organization"

            # Check expiry (platform uses validity.expires_at)
            validity = cls._mapping_value(data, "validity")
            expires_at_str = validity.get("expires_at")
            if not expires_at_str:
                expires_at_str = data.get("expires_at", "")
            if isinstance(expires_at_str, str) and expires_at_str:
                normalized_expiry = expires_at_str.replace("Z", "+00:00")
                expires_at = datetime.fromisoformat(normalized_expiry)
                if timezone.is_naive(expires_at):
                    expires_at = timezone.make_aware(expires_at)
                if timezone.now() > expires_at:
                    cls._handle_expired(license)
                    cls._log_validation(
                        license,
                        "isolated",
                        False,
                        "License expired",
                    )
                    return False, "License has expired"
                license.license_expires_at = expires_at

            # Update license from key data (platform nested structure)
            core = cls._mapping_value(data, "core")
            core_limits = core.get("limits")
            if not isinstance(core_limits, Mapping):
                core_limits = cls._mapping_value(data, "core_limits")
            modules = cls._mapping_value(data, "modules")
            core_tier = core.get("tier", data.get("core_tier", "free"))
            max_companies = core_limits.get("max_companies", 1)
            industry_modules = modules.get(
                "included",
                data.get("industry_modules", []),
            )
            license.core_tier = str(core_tier)
            license.max_companies = int(max_companies)
            if isinstance(industry_modules, list):
                license.industry_modules = industry_modules
            else:
                license.industry_modules = []
            license.status = LicenseStatus.ACTIVE
            license.last_validated_at = timezone.now()
            license.save()

            cls._log_validation(license, "isolated", True)
            return True, "License valid"

        except ValueError as e:
            logger.error(f"License key decode error: {e}")
            cls._log_validation(license, "isolated", False, str(e))
            return False, str(e)
        except Exception as e:
            logger.error(f"License validation error: {e}", exc_info=True)
            cls._log_validation(license, "isolated", False, str(e))
            return False, f"License validation error: {e}"

    @classmethod
    def _handle_server_unreachable(cls, license: License) -> Tuple[bool, str]:
        """Handle case when license server is unreachable."""
        license.validation_failures += 1

        if license.status == LicenseStatus.TRIAL:
            # For trial licenses, allow if trial period hasn't expired
            if license.is_trial_active():
                license.save()
                if license.trial_ends_at:
                    days_left = (license.trial_ends_at - timezone.now()).days
                else:
                    days_left = 0
                cls._log_validation(
                    license,
                    "connected",
                    False,
                    "Server unreachable - trial still active",
                )
                # fmt: off
                message = (
                    f"{cls.SERVER_UNREACHABLE_MESSAGE} "
                    f"Trial period active. {days_left} days remaining."
                )
                # fmt: on
                return True, message
            else:
                # Trial expired - lock the license
                license.status = LicenseStatus.LOCKED
                license.save()
                cls._log_validation(
                    license,
                    "connected",
                    False,
                    "Trial period expired",
                )
                return (
                    False,
                    "Trial period has expired. Please activate a license.",
                )

        elif license.status == LicenseStatus.ACTIVE:
            # Enter grace period
            license.status = LicenseStatus.GRACE
            # fmt: off
            license.grace_ends_at = timezone.now() + timedelta(
                days=cls.GRACE_PERIOD_DAYS
            )
            # fmt: on
            license.save()
            cls._log_validation(
                license,
                "connected",
                False,
                "Server unreachable - entering grace period",
            )
            grace_end = license.grace_ends_at.date()
            # fmt: off
            message = (
                f"{cls.SERVER_UNREACHABLE_MESSAGE} "
                f"Grace period active until {grace_end}"
            )
            # fmt: on
            return True, message

        elif license.status == LicenseStatus.GRACE:
            # fmt: off
            grace_expired = (
                license.grace_ends_at
                and timezone.now() > license.grace_ends_at
            )
            # fmt: on
            if grace_expired:
                # Grace period expired
                license.status = LicenseStatus.LOCKED
                license.save()
                cls._log_validation(
                    license,
                    "connected",
                    False,
                    "Grace period expired",
                )
                # fmt: off
                return (
                    False,
                    "Grace period expired. "
                    f"{cls.RESTORE_CONNECTIVITY_MESSAGE}",
                )
                # fmt: on
            elif license.grace_ends_at is None:
                license.status = LicenseStatus.LOCKED
                license.save()
                cls._log_validation(
                    license,
                    "connected",
                    False,
                    "Grace period missing end date",
                )
                # fmt: off
                return (
                    False,
                    "Grace period is invalid. "
                    f"{cls.RESTORE_CONNECTIVITY_MESSAGE}",
                )
                # fmt: on
            else:
                days_left = (license.grace_ends_at - timezone.now()).days
                license.save()
                return (
                    True,
                    f"Grace period active. {days_left} days remaining.",
                )

        license.save()
        return False, "License validation failed"

    @classmethod
    def _handle_invalid(cls, license: License, error: str) -> None:
        """Handle invalid license response."""
        if error == "license_expired":
            cls._handle_expired(license)
        else:
            license.status = LicenseStatus.LOCKED
            license.save()

    @classmethod
    def _handle_expired(cls, license: License) -> None:
        """Handle expired license - soft lock."""
        license.status = LicenseStatus.EXPIRED
        license.save()

    @classmethod
    def _update_from_server(
        cls,
        license: License,
        data: Mapping[str, Any],
    ) -> None:
        """Update license from server response."""
        license_data = cls._mapping_value(data, "license")
        core_data = cls._mapping_value(data, "core")
        limits_data = cls._mapping_value(core_data, "limits")
        modules_data = cls._mapping_value(data, "modules")
        max_companies = limits_data.get("max_companies", 1)
        allowed_modules = modules_data.get("allowed", [])
        license.status = LicenseStatus.ACTIVE
        license.core_tier = str(license_data.get("tier", "free"))
        license.max_companies = int(max_companies)
        if isinstance(allowed_modules, list):
            license.industry_modules = allowed_modules
        else:
            license.industry_modules = []
        license.last_validated_at = timezone.now()
        license.validation_failures = 0
        license.save()

    @classmethod
    def _decode_license_key(cls, key: str) -> Tuple[dict[str, Any], str]:
        """
        Decode license key into payload dict and signature.

        Platform format: base64(JSON{...payload, "signature": "base64_sig"})
        Matches license-server KeyGeneratorService.format_license_key().
        """
        try:
            decoded = base64.b64decode(key)
            key_data = json.loads(decoded.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid license key format: {e}") from e
        if not isinstance(key_data, dict):
            raise ValueError("License key payload must be a JSON object")

        signature = key_data.get("signature")
        if not isinstance(signature, str) or not signature:
            raise ValueError("License key missing signature")

        return key_data, signature

    @classmethod
    def _verify_signature(
        cls,
        payload_dict: Mapping[str, Any],
        signature_b64: str,
    ) -> bool:
        """
        Verify RSA signature.

        Serialization must match platform CryptoService.serialize_payload()
        for deterministic verification.
        """
        try:
            public_key_pem = getattr(
                settings,
                "SARAISE_LICENSE_PUBLIC_KEY",
                None,
            )

            if not public_key_pem:
                logger.warning(cls.PUBLIC_KEY_MISSING_MESSAGE)
                current_mode = getattr(settings, "SARAISE_MODE", "development")
                if current_mode == "development":
                    return True
                return False

            # Serialize payload without signature (matches platform crypto.py)
            # fmt: off
            payload_clean = {
                k: v for k, v in payload_dict.items() if k != "signature"
            }
            # fmt: on
            payload_bytes = json.dumps(
                payload_clean,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            signature_bytes = base64.b64decode(signature_b64)

            public_key_pem_bytes = public_key_pem.encode()
            # fmt: off
            public_key = serialization.load_pem_public_key(
                public_key_pem_bytes
            )
            # fmt: on
            if not isinstance(public_key, RSAPublicKey):
                logger.error("License public key must be an RSA public key")
                return False
            # PSS padding must match platform crypto.py (RSA-PSS with SHA256)
            public_key.verify(
                signature_bytes,
                payload_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    @classmethod
    def _get_instance_id(cls) -> str:
        """Generate unique instance ID."""
        import uuid as uuid_mod

        data = f"{socket.gethostname()}-{uuid_mod.getnode()}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    @classmethod
    def _log_validation(
        cls,
        license: License,
        validation_type: str,
        success: bool,
        error_message: str = "",
        server_response: Mapping[str, Any] | None = None,
    ) -> None:
        """Log validation attempt."""
        try:
            LicenseValidationLog.objects.create(
                license=license,
                validation_type=validation_type,
                success=success,
                error_message=error_message,
                server_response=server_response,
            )
        except Exception as e:
            # Logging failure must not break license validation.
            logger.warning(f"Failed to log validation: {e}")


class ModuleAccessService:
    """Service for checking module access based on license."""

    FOUNDATION_MODULES = [
        # Mode-aware: full CRUD in self-hosted, read-only in SaaS.
        "platform_management",
        "tenant_management",
        "security_access_control",
        "ai_agent_management",
        "workflow_automation",
        "metadata_modeling",
        # Document Management System uses module name "dms".
        "dms",
        "integration_platform",
        "ai_provider_configuration",
        "localization",
        "billing_subscriptions",
        "data_migration",
    ]

    CORE_MODULES = [
        "crm",
        "accounting_finance",
        "sales_management",
        "purchase_management",
        "inventory_management",
        "human_resources",
        "project_management",
        "business_intelligence",
        "communication_hub",
        "bank_reconciliation",
        "budget_management",
        "asset_management",
        "fixed_assets",
        "sales_operations",
        "purchase_operations",
        "compliance_risk_management",
        "master_data_management",
        "multi_company",
        "compliance_management",
        "email_marketing",
        "dms_business",
    ]

    @classmethod
    def can_access_module(
        cls,
        license: License,
        module_name: str,
    ) -> Tuple[bool, str]:
        """
        Check if license allows access to a module.

        Returns:
            Tuple of (can_access, reason)
        """
        # Foundation modules - always free
        if module_name in cls.FOUNDATION_MODULES:
            return True, "Foundation module - always available"

        # Core modules - free for single company
        if module_name in cls.CORE_MODULES:
            if license.status in [LicenseStatus.TRIAL, LicenseStatus.ACTIVE]:
                return True, "Core module - available"
            elif license.status in [
                LicenseStatus.EXPIRED,
                LicenseStatus.GRACE,
            ]:
                # Soft lock - read only
                return True, "Core module - read-only mode"
            else:
                return False, "License required for Core modules"

        # Industry modules - require purchase
        if license.has_module(module_name):
            return True, "Industry module - licensed"

        return False, f"Industry module '{module_name}' not in license"

    @classmethod
    def can_write_module(cls, license: License, module_name: str) -> bool:
        """Check if writes are allowed for a module."""
        # Foundation - always writable
        if module_name in cls.FOUNDATION_MODULES:
            return True

        # Check license status for write permission
        return license.can_write()
