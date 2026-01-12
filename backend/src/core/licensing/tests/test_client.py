"""
License Client Tests for SARAISE.

Phase 7.5: Licensing Subsystem
Tests for LicenseClient.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from ..client import LicenseClient, LicenseValidationError
from ..models import LicenseInfo, LicenseTier, LicenseValidationStatus, ModuleLicense

# Note: These tests don't require database access - they test LicenseClient
# which doesn't interact with Django models directly


class TestLicenseClient:
    """Test LicenseClient."""

    def test_init_with_default_url(self):
        """Test client initialization with default URL."""
        with patch("django.conf.settings") as mock_settings:
            delattr(mock_settings, "SARAISE_LICENSE_SERVER_URL")
            client = LicenseClient()
            assert client.base_url == "https://license.saraise.com"
            assert client._cached_license is None
            assert client._cache_timestamp is None

    def test_init_with_custom_url(self):
        """Test client initialization with custom URL."""
        client = LicenseClient(base_url="https://custom-license.example.com")
        assert client.base_url == "https://custom-license.example.com"

    def test_init_with_settings_url(self):
        """Test client initialization with settings URL."""
        with patch("django.conf.settings.SARAISE_LICENSE_SERVER_URL", "https://settings-url.com"):
            client = LicenseClient()
            assert client.base_url == "https://settings-url.com"

    def test_validate_development_mode(self):
        """Test validate in development mode."""
        with patch("django.conf.settings.SARAISE_MODE", "development"):
            client = LicenseClient()
            result = client.validate("test-key", "org-123")

            assert isinstance(result, LicenseInfo)
            assert result.organization_id == "org-123"
            assert result.tier == LicenseTier.ENTERPRISE
            assert result.status == LicenseValidationStatus.VALID
            assert len(result.licensed_modules) == 3

    def test_validate_connected_mode_not_implemented(self):
        """Test validate in connected mode (not yet implemented)."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_MODE", "connected"):
                client = LicenseClient()
                with pytest.raises(NotImplementedError) as exc_info:
                    client.validate("test-key", "org-123")
                assert "Online license validation not yet implemented" in str(exc_info.value)

    def test_validate_isolated_mode_not_implemented(self):
        """Test validate in isolated mode (not yet implemented)."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_MODE", "isolated"):
                client = LicenseClient()
                with pytest.raises(NotImplementedError) as exc_info:
                    client.validate("test-key", "org-123")
                assert "Offline license validation not yet implemented" in str(exc_info.value)

    def test_mock_development_license(self):
        """Test _mock_development_license method."""
        client = LicenseClient()
        result = client._mock_development_license("test-org")

        assert isinstance(result, LicenseInfo)
        assert result.organization_id == "test-org"
        assert result.organization_name == "Development Organization"
        assert result.tier == LicenseTier.ENTERPRISE
        assert result.status == LicenseValidationStatus.VALID
        assert result.is_connected is False
        assert len(result.licensed_modules) == 3

        # Check module details
        foundation_module = result.licensed_modules[0]
        assert foundation_module.module_id == "foundation.*"
        assert foundation_module.is_licensed is True

        core_module = result.licensed_modules[1]
        assert core_module.module_id == "core.*"
        assert core_module.is_licensed is True

        industry_module = result.licensed_modules[2]
        assert industry_module.module_id == "industry.*"
        assert industry_module.is_licensed is True

    def test_mock_development_license_no_org_id(self):
        """Test _mock_development_license with no organization ID."""
        client = LicenseClient()
        result = client._mock_development_license(None)
        assert result.organization_id == "dev-org-001"

    def test_get_cached_license_valid(self):
        """Test get_cached_license with valid cache."""
        client = LicenseClient()
        mock_license = client._mock_development_license("test-org")
        client._cached_license = mock_license
        client._cache_timestamp = datetime.utcnow() - timedelta(minutes=30)  # 30 minutes ago

        result = client.get_cached_license()
        assert result == mock_license

    def test_get_cached_license_expired(self):
        """Test get_cached_license with expired cache."""
        client = LicenseClient()
        mock_license = client._mock_development_license("test-org")
        client._cached_license = mock_license
        client._cache_timestamp = datetime.utcnow() - timedelta(hours=2)  # 2 hours ago

        result = client.get_cached_license()
        assert result is None

    def test_get_cached_license_no_cache(self):
        """Test get_cached_license with no cache."""
        client = LicenseClient()
        result = client.get_cached_license()
        assert result is None

    def test_clear_cache(self):
        """Test clear_cache method."""
        client = LicenseClient()
        client._cached_license = client._mock_development_license("test-org")
        client._cache_timestamp = datetime.utcnow()

        client.clear_cache()

        assert client._cached_license is None
        assert client._cache_timestamp is None


class TestLicenseValidationError:
    """Test LicenseValidationError exception."""

    def test_init(self):
        """Test exception initialization."""
        error = LicenseValidationError("License expired", LicenseValidationStatus.EXPIRED)

        assert str(error) == "License expired"
        assert error.status == LicenseValidationStatus.EXPIRED
