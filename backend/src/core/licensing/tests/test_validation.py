"""
License Validation Tests for SARAISE.

Phase 7.5: Licensing Subsystem
Tests for license validation, trial period, grace period, and module access.

Reference: saraise-documentation/planning/phases/phase-7.5-licensing.md
"""

import base64
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.utils import timezone

from ..models import License, LicenseStatus, LicenseValidationLog, Organization
from ..services import LicenseService, ModuleAccessService

# Enable database access for all tests in this module
pytestmark = pytest.mark.django_db


@pytest.fixture
def organization():
    """Create a test organization."""
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def trial_license(organization):
    """Create a trial license."""
    return LicenseService.initialize_trial(organization)


@pytest.fixture
def active_license(organization):
    """Create an active license."""
    return License.objects.create(
        organization=organization,
        status=LicenseStatus.ACTIVE,
        core_tier="free",
        max_companies=1,
        license_expires_at=timezone.now() + timedelta(days=365),
    )


@pytest.fixture
def expired_license(organization):
    """Create an expired license."""
    return License.objects.create(
        organization=organization,
        status=LicenseStatus.EXPIRED,
        core_tier="free",
        max_companies=1,
        license_expires_at=timezone.now() - timedelta(days=1),
    )


@pytest.fixture
def grace_license(organization):
    """Create a license in grace period."""
    return License.objects.create(
        organization=organization,
        status=LicenseStatus.GRACE,
        core_tier="free",
        max_companies=1,
        grace_ends_at=timezone.now() + timedelta(days=10),
        license_expires_at=timezone.now() - timedelta(days=1),
    )


class TestTrialPeriod:
    """Test trial period functionality."""

    def test_trial_initialized_with_14_days(self, trial_license):
        """Test that trial is initialized with 14 days."""
        assert trial_license.status == LicenseStatus.TRIAL
        assert trial_license.trial_ends_at is not None
        days_remaining = (trial_license.trial_ends_at - timezone.now()).days
        assert 13 <= days_remaining <= 14

    def test_trial_is_valid_during_period(self, trial_license):
        """Test that trial is valid during the trial period."""
        assert trial_license.is_trial_active()
        assert trial_license.is_license_valid()
        assert trial_license.can_write()

    def test_trial_expires_after_14_days(self, trial_license):
        """Test that trial expires after 14 days."""
        # Simulate expired trial
        trial_license.trial_ends_at = timezone.now() - timedelta(days=1)
        trial_license.save()

        assert not trial_license.is_trial_active()
        assert not trial_license.is_license_valid()

    def test_trial_organization_created(self, organization):
        """Test that trial creates license for organization."""
        license = LicenseService.initialize_trial(organization)
        assert license.organization == organization
        assert license.status == LicenseStatus.TRIAL


class TestLicenseValidation:
    """Test license validation."""

    def test_active_license_is_valid(self, active_license):
        """Test that active license is valid."""
        assert active_license.is_license_valid()
        assert active_license.can_write()

    def test_expired_license_is_invalid(self, expired_license):
        """Test that expired license is invalid."""
        assert not expired_license.is_license_valid()
        assert not expired_license.can_write()

    @patch("src.core.licensing.services.requests.post")
    def test_connected_validation_success(self, mock_post, active_license):
        """Test successful connected validation."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "valid": True,
                "license": {"tier": "free"},
                "core": {"limits": {"max_companies": 1}},
                "modules": {"allowed": []},
            },
        )

        with patch.object(LicenseService, "_get_instance_id", return_value="test"):
            is_valid, message = LicenseService._validate_connected(active_license)

        assert is_valid
        assert "valid" in message.lower()
        active_license.refresh_from_db()
        assert active_license.status == LicenseStatus.ACTIVE

    @patch("src.core.licensing.services.requests.post")
    def test_connected_validation_failure(self, mock_post, active_license):
        """Test failed connected validation."""
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"valid": False, "error": "license_expired", "message": "License expired"}
        )

        with patch.object(LicenseService, "_get_instance_id", return_value="test"):
            is_valid, message = LicenseService._validate_connected(active_license)

        assert not is_valid
        assert "expired" in message.lower()
        active_license.refresh_from_db()
        assert active_license.status == LicenseStatus.EXPIRED

    @patch("src.core.licensing.services.requests.post")
    def test_connected_validation_server_error(self, mock_post, active_license):
        """Test server error handling (grace period)."""
        mock_post.side_effect = requests.RequestException("Connection error")

        is_valid, message = LicenseService._validate_connected(active_license)

        # Should enter grace period
        assert is_valid  # Grace period allows access
        assert "grace" in message.lower() or "unreachable" in message.lower()
        active_license.refresh_from_db()
        assert active_license.status == LicenseStatus.GRACE

    def test_isolated_validation_no_key(self, active_license):
        """Test isolated validation with no key."""
        active_license.license_key = ""
        active_license.save()

        is_valid, message = LicenseService._validate_isolated(active_license)

        assert not is_valid
        assert "no license key" in message.lower()

    def test_validate_license_development_mode(self, active_license):
        """Test validation in development mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            is_valid, message = LicenseService.validate_license(active_license)
            assert is_valid
            assert "development" in message.lower()

    def test_validate_license_saas_mode(self, active_license):
        """Test validation in SaaS mode."""
        with patch("django.conf.settings.SARAISE_MODE", "saas"):
            is_valid, message = LicenseService.validate_license(active_license)
            assert is_valid
            assert "saas" in message.lower()


class TestModuleAccess:
    """Test module access control."""

    def test_foundation_modules_always_accessible(self, expired_license):
        """Test that foundation modules are always accessible."""
        can_access, reason = ModuleAccessService.can_access_module(expired_license, "ai_agent_management")
        assert can_access
        assert "foundation" in reason.lower()

    def test_core_modules_accessible_in_trial(self, trial_license):
        """Test that core modules are accessible during trial."""
        can_access, reason = ModuleAccessService.can_access_module(trial_license, "crm")
        assert can_access
        assert "core" in reason.lower()

    def test_core_modules_read_only_in_grace(self, grace_license):
        """Test that core modules are read-only in grace period."""
        can_access, reason = ModuleAccessService.can_access_module(grace_license, "crm")
        assert can_access  # Read access allowed
        assert "read-only" in reason.lower()

    def test_industry_modules_require_license(self, trial_license):
        """Test that industry modules require license."""
        can_access, reason = ModuleAccessService.can_access_module(trial_license, "manufacturing")
        assert not can_access
        assert "not in license" in reason.lower()

    def test_industry_modules_accessible_when_licensed(self, active_license):
        """Test that industry modules are accessible when licensed."""
        active_license.industry_modules = ["manufacturing"]
        active_license.save()

        can_access, reason = ModuleAccessService.can_access_module(active_license, "manufacturing")
        assert can_access
        assert "licensed" in reason.lower()

    def test_module_access_unknown_module(self, active_license):
        """Test access to unknown module."""
        can_access, reason = ModuleAccessService.can_access_module(active_license, "unknown_module")
        assert not can_access


class TestSoftLock:
    """Test soft lock (read-only) behavior."""

    def test_expired_license_prevents_writes(self, expired_license):
        """Test that expired license prevents writes."""
        assert not expired_license.can_write()
        assert not ModuleAccessService.can_write_module(expired_license, "crm")

    def test_foundation_modules_writable_even_when_expired(self, expired_license):
        """Test that foundation modules are writable even when expired."""
        # Foundation modules are always writable
        assert ModuleAccessService.can_write_module(expired_license, "ai_agent_management")

    def test_grace_period_allows_reads(self, grace_license):
        """Test that grace period allows reads but not writes."""
        # Reads allowed
        can_access, _ = ModuleAccessService.can_access_module(grace_license, "crm")
        assert can_access
        # Writes blocked
        assert not ModuleAccessService.can_write_module(grace_license, "crm")

    def test_locked_license_prevents_writes(self, organization):
        """Test that locked license prevents writes."""
        locked_license = License.objects.create(
            organization=organization,
            status=LicenseStatus.LOCKED,
            core_tier="free",
        )
        assert not locked_license.can_write()
        assert not ModuleAccessService.can_write_module(locked_license, "crm")


class TestGracePeriod:
    """Test grace period handling."""

    def test_grace_period_entered_on_server_unreachable(self, active_license):
        """Test that grace period is entered when server is unreachable."""
        with patch("src.core.licensing.services.requests.post") as mock_post:
            mock_post.side_effect = requests.RequestException("Connection error")

            is_valid, message = LicenseService._handle_server_unreachable(active_license)

            assert is_valid  # Grace period allows access
            active_license.refresh_from_db()
            assert active_license.status == LicenseStatus.GRACE
            assert active_license.grace_ends_at is not None

    def test_grace_period_expires(self, grace_license):
        """Test that grace period expires correctly."""
        # Simulate expired grace period
        grace_license.grace_ends_at = timezone.now() - timedelta(days=1)
        grace_license.save()

        is_valid, message = LicenseService._handle_server_unreachable(grace_license)

        assert not is_valid
        grace_license.refresh_from_db()
        assert grace_license.status == LicenseStatus.LOCKED


class TestLicenseModels:
    """Test license model methods."""

    def test_license_has_module(self, active_license):
        """Test has_module method."""
        active_license.industry_modules = ["manufacturing", "retail"]
        active_license.save()

        assert active_license.has_module("manufacturing")
        assert active_license.has_module("retail")
        assert not active_license.has_module("healthcare")

    def test_license_validation_log_created(self, active_license):
        """Test that validation logs are created."""
        LicenseService._log_validation(
            active_license, "test_validation", True, error_message="", server_response={"test": "data"}
        )

        log = LicenseValidationLog.objects.filter(license=active_license, validation_type="test_validation").first()

        assert log is not None
        assert log.success is True
        assert log.server_response == {"test": "data"}


class TestLicenseServiceHelpers:
    """Test helper methods in LicenseService."""

    def test_get_instance_id(self):
        """Test instance ID generation."""
        instance_id = LicenseService._get_instance_id()
        assert len(instance_id) == 32
        assert isinstance(instance_id, str)

    def test_decode_license_key(self):
        """Test license key decoding."""
        payload = '{"org": "test"}'
        signature = b"test_signature"

        # Encode
        payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        key = f"{payload_b64}.{sig_b64}"

        # Decode
        decoded_payload, decoded_sig = LicenseService._decode_license_key(key)

        assert decoded_payload == payload
        assert decoded_sig == signature

    def test_decode_invalid_key(self):
        """Test decoding invalid key format."""
        with pytest.raises(ValueError, match="Invalid license key format"):
            LicenseService._decode_license_key("invalid_key")

    def test_verify_signature_development_mode(self):
        """Test signature verification in development mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            with patch("django.conf.settings.SARAISE_LICENSE_PUBLIC_KEY", None):
                result = LicenseService._verify_signature("payload", b"signature")
                assert result is True  # Development mode allows unsigned

    def test_verify_signature_no_public_key(self):
        """Test signature verification without public key."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_PUBLIC_KEY", None):
                result = LicenseService._verify_signature("payload", b"signature")
                assert result is False

    def test_handle_expired_license(self, active_license):
        """Test handling expired license."""
        LicenseService._handle_expired(active_license)
        active_license.refresh_from_db()
        assert active_license.status == LicenseStatus.EXPIRED

    def test_handle_invalid_license_expired(self, active_license):
        """Test handling invalid license with expired error."""
        LicenseService._handle_invalid(active_license, "license_expired")
        active_license.refresh_from_db()
        assert active_license.status == LicenseStatus.EXPIRED

    def test_handle_invalid_license_other(self, active_license):
        """Test handling invalid license with other error."""
        LicenseService._handle_invalid(active_license, "invalid_key")
        active_license.refresh_from_db()
        assert active_license.status == LicenseStatus.LOCKED

    def test_update_from_server(self, active_license):
        """Test updating license from server response."""
        data = {
            "license": {"tier": "professional"},
            "core": {"limits": {"max_companies": 5}},
            "modules": {"allowed": ["manufacturing", "retail"]},
        }
        LicenseService._update_from_server(active_license, data)
        active_license.refresh_from_db()
        assert active_license.status == LicenseStatus.ACTIVE
        assert active_license.core_tier == "professional"
        assert active_license.max_companies == 5
        assert active_license.industry_modules == ["manufacturing", "retail"]
        assert active_license.validation_failures == 0

    def test_isolated_validation_organization_mismatch(self, active_license):
        """Test isolated validation with organization mismatch."""
        active_license.license_key = "eyJvcmciOiAidGVzdCJ9.signature"
        active_license.save()

        with patch.object(
            LicenseService, "_decode_license_key", return_value=('{"organization_id": "wrong-id"}', b"sig")
        ):
            with patch.object(LicenseService, "_verify_signature", return_value=True):
                is_valid, message = LicenseService._validate_isolated(active_license)
                assert not is_valid
                assert "match" in message.lower() or "mismatch" in message.lower()

    def test_isolated_validation_expired_key(self, active_license):
        """Test isolated validation with expired key."""
        expired_date = (timezone.now() - timedelta(days=1)).isoformat()
        payload = f'{{"organization_id": "{active_license.organization_id}", "expires_at": "{expired_date}"}}'

        active_license.license_key = "key.signature"
        active_license.save()

        with patch.object(LicenseService, "_decode_license_key", return_value=(payload, b"sig")):
            with patch.object(LicenseService, "_verify_signature", return_value=True):
                is_valid, message = LicenseService._validate_isolated(active_license)
                assert not is_valid
                assert "expired" in message.lower()

    def test_connected_validation_server_error_500(self, active_license):
        """Test connected validation with server error 500."""
        with patch("src.core.licensing.services.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=500)

            is_valid, message = LicenseService._validate_connected(active_license)

            # Should enter grace period
            assert is_valid
            active_license.refresh_from_db()
            assert active_license.status == LicenseStatus.GRACE

    def test_grace_period_days_remaining(self, grace_license):
        """Test grace period days remaining calculation."""
        is_valid, message = LicenseService._handle_server_unreachable(grace_license)
        assert is_valid
        assert "days remaining" in message.lower() or "active" in message.lower()


class TestLicenseModelMethods:
    """Test license model methods comprehensively."""

    def test_is_trial_active_valid(self, trial_license):
        """Test is_trial_active when trial is valid."""
        assert trial_license.is_trial_active() is True

    def test_is_trial_active_wrong_status(self, active_license):
        """Test is_trial_active when status is not TRIAL."""
        assert active_license.is_trial_active() is False

    def test_is_trial_active_no_end_date(self, organization):
        """Test is_trial_active when no trial_ends_at."""
        license = License.objects.create(
            organization=organization,
            status=LicenseStatus.TRIAL,
            trial_ends_at=None,
        )
        assert license.is_trial_active() is False

    def test_is_license_valid_trial(self, trial_license):
        """Test is_license_valid for trial license."""
        assert trial_license.is_license_valid() is True

    def test_is_license_valid_active(self, active_license):
        """Test is_license_valid for active license."""
        assert active_license.is_license_valid() is True

    def test_is_license_valid_expired(self, expired_license):
        """Test is_license_valid for expired license."""
        assert expired_license.is_license_valid() is False

    def test_is_license_valid_grace(self, grace_license):
        """Test is_license_valid for grace period license."""
        assert grace_license.is_license_valid() is True

    def test_is_license_valid_grace_expired(self, organization):
        """Test is_license_valid for expired grace period."""
        license = License.objects.create(
            organization=organization,
            status=LicenseStatus.GRACE,
            grace_ends_at=timezone.now() - timedelta(days=1),
        )
        assert license.is_license_valid() is False

    def test_is_license_valid_active_expired(self, organization):
        """Test is_license_valid for active license that expired."""
        license = License.objects.create(
            organization=organization,
            status=LicenseStatus.ACTIVE,
            license_expires_at=timezone.now() - timedelta(days=1),
        )
        assert license.is_license_valid() is False

    def test_can_write_trial(self, trial_license):
        """Test can_write for trial license."""
        assert trial_license.can_write() is True

    def test_can_write_active(self, active_license):
        """Test can_write for active license."""
        assert active_license.can_write() is True

    def test_can_write_expired(self, expired_license):
        """Test can_write for expired license."""
        assert expired_license.can_write() is False

    def test_can_write_locked(self, organization):
        """Test can_write for locked license."""
        license = License.objects.create(
            organization=organization,
            status=LicenseStatus.LOCKED,
        )
        assert license.can_write() is False

    def test_can_write_grace(self, grace_license):
        """Test can_write for grace period license (should be read-only)."""
        assert grace_license.can_write() is False


class TestModuleAccessServiceEdgeCases:
    """Test edge cases in ModuleAccessService."""

    def test_core_module_locked_status(self, organization):
        """Test core module access with locked license."""
        locked_license = License.objects.create(
            organization=organization,
            status=LicenseStatus.LOCKED,
        )
        can_access, reason = ModuleAccessService.can_access_module(locked_license, "crm")
        assert not can_access

    def test_industry_module_not_in_list(self, active_license):
        """Test industry module not in license list."""
        active_license.industry_modules = ["manufacturing"]
        active_license.save()

        can_access, reason = ModuleAccessService.can_access_module(active_license, "healthcare")
        assert not can_access

    def test_can_write_module_foundation_expired(self, expired_license):
        """Test that foundation modules are writable even when expired."""
        assert ModuleAccessService.can_write_module(expired_license, "platform_management") is True

    def test_can_write_module_core_expired(self, expired_license):
        """Test that core modules are not writable when expired."""
        assert ModuleAccessService.can_write_module(expired_license, "crm") is False
