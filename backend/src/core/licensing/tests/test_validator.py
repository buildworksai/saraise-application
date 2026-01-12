"""
License Validator Tests for SARAISE.

Phase 7.5: Licensing Subsystem
Tests for LicenseValidator.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from ..client import LicenseClient
from ..models import LicenseInfo, LicenseTier, LicenseValidationStatus, ModuleLicense
from ..validator import LicenseValidator, get_license_validator

# Enable database access for all tests in this module
pytestmark = pytest.mark.django_db


class TestLicenseValidator:
    """Test LicenseValidator."""

    def test_singleton_pattern(self):
        """Test that validator is a singleton."""
        validator1 = LicenseValidator()
        validator2 = LicenseValidator()

        assert validator1 is validator2

    def test_is_development_mode_true(self):
        """Test is_development_mode when in development."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            assert validator.is_development_mode is True

    def test_is_development_mode_false(self):
        """Test is_development_mode when not in development."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            assert validator.is_development_mode is False

    def test_is_self_hosted_true(self):
        """Test is_self_hosted when in self-hosted mode."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            assert validator.is_self_hosted is True

    def test_is_self_hosted_false(self):
        """Test is_self_hosted when not in self-hosted mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            assert validator.is_self_hosted is False

    def test_is_saas_mode_true(self):
        """Test is_saas_mode when in SaaS mode."""
        with patch("django.conf.settings.SARAISE_MODE", "saas"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            assert validator.is_saas_mode is True

    def test_is_saas_mode_false(self):
        """Test is_saas_mode when not in SaaS mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            assert validator.is_saas_mode is False

    def test_get_license_development_mode(self):
        """Test get_license in development mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            result = validator.get_license()
            assert result is not None
            assert isinstance(result, LicenseInfo)
            assert result.organization_id == "dev-org"

    def test_get_license_no_license_info(self):
        """Test get_license when no license info is set."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            validator._license_info = None

            result = validator.get_license()
            assert result is None

    def test_get_license_with_license_info(self):
        """Test get_license when license info is set."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=365),
                licensed_modules=[],
            )
            validator._license_info = mock_license

            result = validator.get_license()
            assert result == mock_license

    def test_validate_startup_development_mode(self):
        """Test validate_startup in development mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            result = validator.validate_startup("test-key", "org-123")
            assert isinstance(result, LicenseInfo)
            assert result.organization_id == "org-123"

    def test_validate_startup_saas_mode(self):
        """Test validate_startup in SaaS mode."""
        with patch("django.conf.settings.SARAISE_MODE", "saas"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            result = validator.validate_startup("test-key", "org-123")
            assert isinstance(result, LicenseInfo)
            assert result.organization_id == "org-123"

    def test_validate_startup_self_hosted_mode(self):
        """Test validate_startup in self-hosted mode."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch.object(LicenseClient, "validate") as mock_validate:
                mock_license = LicenseInfo(
                    organization_id="test-org",
                    organization_name="Test Org",
                    tier=LicenseTier.PROFESSIONAL,
                    status=LicenseValidationStatus.VALID,
                    issued_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(days=365),
                    licensed_modules=[],
                )
                mock_validate.return_value = mock_license

                validator = LicenseValidator()
                validator._initialized = False  # Reset for test
                validator.__init__()

                result = validator.validate_startup("test-key", "org-123")
                assert result == mock_license
                mock_validate.assert_called_once_with("test-key", "org-123")

    def test_validate_startup_grace_period(self):
        """Test validate_startup with grace period status."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch.object(LicenseClient, "validate") as mock_validate:
                expires_at = datetime.utcnow() + timedelta(days=10)
                grace_expires_at = datetime.utcnow() + timedelta(days=10)
                mock_license = LicenseInfo(
                    organization_id="test-org",
                    organization_name="Test Org",
                    tier=LicenseTier.PROFESSIONAL,
                    status=LicenseValidationStatus.GRACE_PERIOD,
                    issued_at=datetime.utcnow(),
                    expires_at=expires_at,
                    licensed_modules=[],
                    grace_expires_at=grace_expires_at,
                )
                mock_validate.return_value = mock_license

                validator = LicenseValidator()
                validator._initialized = False  # Reset for test
                validator.__init__()

                result = validator.validate_startup("test-key", "org-123")
                assert result == mock_license
                assert result.status == LicenseValidationStatus.GRACE_PERIOD

    def test_validate_startup_expired(self):
        """Test validate_startup with expired status."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch.object(LicenseClient, "validate") as mock_validate:
                mock_license = LicenseInfo(
                    organization_id="test-org",
                    organization_name="Test Org",
                    tier=LicenseTier.PROFESSIONAL,
                    status=LicenseValidationStatus.EXPIRED,
                    issued_at=datetime.utcnow() - timedelta(days=400),
                    expires_at=datetime.utcnow() - timedelta(days=30),
                    licensed_modules=[],
                )
                mock_validate.return_value = mock_license

                validator = LicenseValidator()
                validator._initialized = False  # Reset for test
                validator.__init__()

                result = validator.validate_startup("test-key", "org-123")
                assert result == mock_license

    def test_check_module_access_development_mode(self):
        """Test check_module_access in development mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            # Should allow all modules in development
            assert validator.check_module_access("any.module") is True
            assert validator.check_module_access("any.module", write_operation=True) is True

    def test_check_module_access_saas_mode(self):
        """Test check_module_access in SaaS mode."""
        with patch("django.conf.settings.SARAISE_MODE", "saas"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            # Should allow all modules in SaaS mode
            assert validator.check_module_access("any.module") is True
            assert validator.check_module_access("any.module", write_operation=True) is True

    def test_check_module_access_no_license(self):
        """Test check_module_access when no license info."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            validator._license_info = None

            assert validator.check_module_access("any.module") is False

    def test_check_module_access_expired_read(self):
        """Test check_module_access with expired license (read allowed)."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.EXPIRED,
                issued_at=datetime.utcnow() - timedelta(days=400),
                expires_at=datetime.utcnow() - timedelta(days=30),
                licensed_modules=[],
            )
            # LicenseInfo.is_valid is a property, not an attribute
            validator._license_info = mock_license

            # Read should be allowed (is_valid=False but read operations allowed)
            assert validator.check_module_access("any.module", write_operation=False) is True
            # Write should be blocked
            assert validator.check_module_access("any.module", write_operation=True) is False

    def test_check_module_access_valid_has_module(self):
        """Test check_module_access with valid license and module."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_module = ModuleLicense(
                module_id="test.module",
                module_name="Test Module",
                tier_required=LicenseTier.PROFESSIONAL,
                is_licensed=True,
                expires_at=datetime.utcnow() + timedelta(days=365),
            )
            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=365),
                licensed_modules=[mock_module],
            )
            # LicenseInfo.has_module is a method, not an attribute
            validator._license_info = mock_license

            assert validator.check_module_access("test.module") is True

    def test_check_module_access_valid_wildcard(self):
        """Test check_module_access with valid license and wildcard pattern."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_module = ModuleLicense(
                module_id="foundation.*",
                module_name="All Foundation Modules",
                tier_required=LicenseTier.FREE,
                is_licensed=True,
                expires_at=datetime.utcnow() + timedelta(days=365),
            )
            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=365),
                licensed_modules=[mock_module],
            )
            # LicenseInfo.has_module is a method that checks licensed_modules
            validator._license_info = mock_license

            assert validator.check_module_access("foundation.user_management") is True

    def test_check_module_access_not_licensed(self):
        """Test check_module_access when module is not licensed."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=365),
                licensed_modules=[],  # Empty list means no modules licensed
            )
            # has_module is a method that checks licensed_modules
            validator._license_info = mock_license

            assert validator.check_module_access("unlicensed.module") is False

    def test_is_trial_active_true(self):
        """Test is_trial_active when trial is active."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.TRIAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=10),
                licensed_modules=[],
            )
            # is_valid is a property, not an attribute
            validator._license_info = mock_license

            assert validator.is_trial_active() is True

    def test_is_trial_active_false(self):
        """Test is_trial_active when not a trial."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=365),
                licensed_modules=[],
            )
            # is_valid is a property, not an attribute
            validator._license_info = mock_license

            assert validator.is_trial_active() is False

    def test_is_trial_active_no_license(self):
        """Test is_trial_active when no license."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            validator._license_info = None

            assert validator.is_trial_active() is False

    def test_get_trial_days_remaining(self):
        """Test get_trial_days_remaining."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            expires_at = datetime.utcnow() + timedelta(days=10)
            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.TRIAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=expires_at,
                licensed_modules=[],
            )
            # days_until_expiry is a property that calculates from expires_at
            validator._license_info = mock_license

            days = validator.get_trial_days_remaining()
            assert days == 10 or days == 9  # Allow for timing differences

    def test_get_trial_days_remaining_not_trial(self):
        """Test get_trial_days_remaining when not a trial."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=365),
                licensed_modules=[],
            )
            validator._license_info = mock_license

            assert validator.get_trial_days_remaining() == 0

    def test_is_soft_locked_development_mode(self):
        """Test is_soft_locked in development mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            assert validator.is_soft_locked() is False

    def test_is_soft_locked_saas_mode(self):
        """Test is_soft_locked in SaaS mode."""
        with patch("django.conf.settings.SARAISE_MODE", "saas"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            assert validator.is_soft_locked() is False

    def test_is_soft_locked_expired(self):
        """Test is_soft_locked when license is expired."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.EXPIRED,
                issued_at=datetime.utcnow() - timedelta(days=400),
                expires_at=datetime.utcnow() - timedelta(days=30),
                licensed_modules=[],
            )
            validator._license_info = mock_license

            assert validator.is_soft_locked() is True

    def test_is_soft_locked_no_license(self):
        """Test is_soft_locked when no license."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            validator._license_info = None

            assert validator.is_soft_locked() is True

    def test_needs_renewal_warning_true(self):
        """Test needs_renewal_warning when warning needed."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            expires_at = datetime.utcnow() + timedelta(days=20)
            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=expires_at,
                licensed_modules=[],
            )
            # days_until_expiry is a property that calculates from expires_at
            validator._license_info = mock_license

            show_warning, days = validator.needs_renewal_warning()
            assert show_warning is True
            assert days <= 30  # Should be <= 30 days
            assert days > 0

    def test_needs_renewal_warning_false(self):
        """Test needs_renewal_warning when warning not needed."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()

            expires_at = datetime.utcnow() + timedelta(days=60)
            mock_license = LicenseInfo(
                organization_id="test-org",
                organization_name="Test Org",
                tier=LicenseTier.PROFESSIONAL,
                status=LicenseValidationStatus.VALID,
                issued_at=datetime.utcnow(),
                expires_at=expires_at,
                licensed_modules=[],
            )
            # days_until_expiry is a property that calculates from expires_at
            validator._license_info = mock_license

            show_warning, days = validator.needs_renewal_warning()
            assert show_warning is False  # More than 30 days remaining
            assert days > 30

    def test_needs_renewal_warning_no_license(self):
        """Test needs_renewal_warning when no license."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            validator = LicenseValidator()
            validator._initialized = False  # Reset for test
            validator.__init__()
            validator._license_info = None

            show_warning, days = validator.needs_renewal_warning()
            assert show_warning is False
            assert days == 0


class TestGetLicenseValidator:
    """Test get_license_validator function."""

    def test_get_license_validator_returns_singleton(self):
        """Test that get_license_validator returns singleton."""
        validator1 = get_license_validator()
        validator2 = get_license_validator()

        assert validator1 is validator2
        assert isinstance(validator1, LicenseValidator)
