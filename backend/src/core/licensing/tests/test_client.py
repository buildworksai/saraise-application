"""
License Client Tests for SARAISE.

Phase 7.5: Licensing Subsystem
Tests for LicenseClient.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import override_settings

from src.core.licensing.client import LicenseClient, LicenseValidationError, _CircuitBreaker
from src.core.licensing.models import LicenseInfo, LicenseTier, LicenseValidationStatus

# Note: These tests don't require database access - they test LicenseClient
# which doesn't interact with Django models directly


class TestLicenseClient:
    """Test LicenseClient."""

    def test_init_with_default_url(self):
        """Test client initialization with default URL."""
        with patch("src.core.licensing.client.settings", object()):
            client = LicenseClient()
            assert client.base_url == "https://license.saraise.com"
            assert client._cached_license is None
            assert client._cache_timestamp is None

    def test_init_with_custom_url(self):
        """Test client initialization with custom URL."""
        client = LicenseClient(base_url="https://custom-license.example.com////")
        assert client.base_url == "https://custom-license.example.com"

    def test_init_preserves_non_separator_suffix_when_trimming_url(self):
        """URL normalization trims only slash separators."""
        client = LicenseClient(base_url="https://license.test/X/")

        assert client.base_url == "https://license.test/X"

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

    def test_validate_connected_mode_success(self):
        """Test validate in connected mode with successful server response."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_MODE", "connected"):
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "valid": True,
                    "license": {"tier": "professional", "expires_at": "2027-01-07T00:00:00Z"},
                    "core": {"tier": "free", "limits": {"max_companies": 1}},
                    "modules": {"allowed": ["manufacturing"], "denied": []},
                    "features": [],
                    "next_check": "2026-01-08T00:00:00Z",
                }
                with patch("requests.post", return_value=mock_response):
                    client = LicenseClient(base_url="https://license.test.com")
                    result = client.validate("sk_live_xxx", "org-123")
                    assert isinstance(result, LicenseInfo)
                    assert result.organization_id == "org-123"
                    assert result.status == LicenseValidationStatus.VALID
                    assert result.tier == LicenseTier.PROFESSIONAL
                    assert result.expires_at == datetime(2027, 1, 7, tzinfo=timezone.utc)
                    assert [module.module_id for module in result.licensed_modules] == ["manufacturing"]

    def test_parse_success_response_falls_back_for_malformed_objects(self):
        """Malformed optional objects are rejected and use safe defaults."""
        client = LicenseClient()

        result = client._parse_success_response(
            {
                "valid": True,
                "license": "not-an-object",
                "modules": {"allowed": ["crm", 7, None]},
            },
            "org-123",
        )

        assert result.tier == LicenseTier.FREE
        assert [module.module_id for module in result.licensed_modules] == ["crm"]
        assert result.licensed_modules[0].module_name == "Crm"

    def test_parse_success_response_handles_non_string_expiry_as_default(self):
        """A non-string expiry is treated as missing and falls back safely."""
        client = LicenseClient()
        before = datetime.utcnow()

        result = client._parse_success_response(
            {
                "valid": True,
                "license": {"tier": "professional", "expires_at": 123},
                "modules": {"allowed": ["crm"]},
            },
            "org-123",
        )

        after = datetime.utcnow()
        assert result.tier == LicenseTier.PROFESSIONAL
        assert before + timedelta(days=364, hours=23, minutes=59) < result.expires_at
        assert result.expires_at < after + timedelta(days=365, minutes=1)

    def test_parse_success_response_accepts_zulu_expiry_exactly(self):
        """Zulu UTC expiration is normalized to an aware datetime."""
        client = LicenseClient()

        result = client._parse_success_response(
            {
                "valid": True,
                "license": {"tier": "starter", "expires_at": "2027-01-07T00:00:00Z"},
                "modules": {"allowed": ["crm"]},
            },
            "org-123",
        )

        assert result.expires_at == datetime(2027, 1, 7, tzinfo=timezone.utc)

    def test_parse_success_response_uses_core_default_when_allowed_modules_missing(self):
        """Missing allowed modules grants the documented core fallback only."""
        client = LicenseClient()

        result = client._parse_success_response(
            {
                "valid": True,
                "license": {"tier": "starter", "expires_at": "not-a-date"},
                "modules": {"allowed": "crm"},
            },
            "org-123",
        )

        assert result.tier == LicenseTier.STARTER
        assert len(result.licensed_modules) == 1
        assert result.licensed_modules[0].module_id == "core.*"
        assert result.licensed_modules[0].tier_required == LicenseTier.FREE

    def test_validate_connected_mode_server_unreachable(self):
        """Test validate in connected mode when server is unreachable."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_MODE", "connected"):
                client = LicenseClient()
                with patch("requests.post", side_effect=requests.RequestException("Connection refused")):
                    with pytest.raises(LicenseValidationError) as exc_info:
                        client.validate("test-key", "org-123")
                    assert exc_info.value.status == LicenseValidationStatus.INVALID

    def test_validate_connected_mode_rejects_non_object_response(self):
        """Online validation must reject non-object JSON response bodies."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_MODE", "connected"):
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = ["valid"]

                client = LicenseClient(base_url="https://license.test.com")
                with patch("requests.post", return_value=mock_response):
                    with pytest.raises(
                        LicenseValidationError,
                        match="^License server returned invalid response$",
                    ) as exc_info:
                        client.validate("sk_live_xxx", "org-123")

                assert exc_info.value.status == LicenseValidationStatus.INVALID

    def test_validate_connected_mode_preserves_expired_status(self):
        """The platform license_expired error maps to EXPIRED, not INVALID."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_MODE", "connected"):
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "valid": False,
                    "error": "license_expired",
                    "message": "License expired",
                }

                client = LicenseClient(base_url="https://license.test.com")
                with patch("requests.post", return_value=mock_response):
                    with pytest.raises(LicenseValidationError, match="^License expired$") as exc_info:
                        client.validate("sk_live_xxx", "org-123")

                assert exc_info.value.status == LicenseValidationStatus.EXPIRED

    def test_validate_connected_mode_uses_invalid_default_error(self):
        """Invalid online responses without message use the documented default."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_MODE", "connected"):
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"valid": False, "error": "unknown"}

                client = LicenseClient(base_url="https://license.test.com")
                with patch("requests.post", return_value=mock_response):
                    with pytest.raises(LicenseValidationError, match="^License invalid$") as exc_info:
                        client.validate("sk_live_xxx", "org-123")

                assert exc_info.value.status == LicenseValidationStatus.INVALID

    def test_validate_isolated_mode_invalid_key(self):
        """Test validate in isolated mode with invalid key."""
        with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
            with patch("django.conf.settings.SARAISE_LICENSE_MODE", "isolated"):
                client = LicenseClient()
                with pytest.raises(LicenseValidationError) as exc_info:
                    client.validate("invalid-key-format", "org-123")
                assert exc_info.value.status == LicenseValidationStatus.INVALID

    def test_validate_offline_requires_expiration_field(self):
        """Offline keys fail closed when expiration is absent or malformed."""
        client = LicenseClient()
        payload = {"organization": {"id": "org-123"}, "modules": {"included": ["core.*"]}}

        with patch("src.core.licensing.services.LicenseService._decode_license_key", return_value=(payload, b"sig")):
            with patch("src.core.licensing.services.LicenseService._verify_signature", return_value=True):
                with pytest.raises(LicenseValidationError, match="^License key missing expiration$") as exc_info:
                    client._validate_offline("offline-key", "org-123")

        assert exc_info.value.status == LicenseValidationStatus.INVALID

    def test_validate_offline_rejects_non_string_expiration_field(self):
        """Offline expiration must be a string timestamp."""
        client = LicenseClient()
        payload = {
            "organization": {"id": "org-123"},
            "validity": {"expires_at": 123},
            "modules": {"included": ["core.*"]},
        }

        with patch("src.core.licensing.services.LicenseService._decode_license_key", return_value=(payload, b"sig")):
            with patch("src.core.licensing.services.LicenseService._verify_signature", return_value=True):
                with pytest.raises(LicenseValidationError, match="^License key missing expiration$") as exc_info:
                    client._validate_offline("offline-key", "org-123")

        assert exc_info.value.status == LicenseValidationStatus.INVALID

    def test_validate_offline_uses_validity_expiration_and_included_modules(self):
        """Offline validation honors validity.expires_at and module inclusion."""
        client = LicenseClient()
        expires_at = datetime.utcnow() + timedelta(days=30)
        payload = {
            "organization": {"id": "org-123", "name": "Acme"},
            "core": {"tier": "enterprise"},
            "modules": {"included": ["core.crm", 12]},
            "validity": {"expires_at": expires_at.isoformat()},
        }

        with patch("src.core.licensing.services.LicenseService._decode_license_key", return_value=(payload, b"sig")):
            with patch("src.core.licensing.services.LicenseService._verify_signature", return_value=True):
                result = client._validate_offline("offline-key", "org-123")

        assert result.organization_name == "Acme"
        assert result.tier == LicenseTier.ENTERPRISE
        assert result.expires_at == expires_at
        assert [module.module_id for module in result.licensed_modules] == ["core.crm"]
        assert result.licensed_modules[0].tier_required == LicenseTier.ENTERPRISE

    def test_validate_offline_uses_top_level_expiration_fallback(self):
        """Offline keys may carry expires_at at the top level for compatibility."""
        client = LicenseClient()
        expires_at = datetime.utcnow() + timedelta(days=30)
        payload = {
            "organization_id": "org-123",
            "core": {"tier": "starter"},
            "modules": {"included": []},
            "expires_at": expires_at.isoformat(),
        }

        with patch("src.core.licensing.services.LicenseService._decode_license_key", return_value=(payload, b"sig")):
            with patch("src.core.licensing.services.LicenseService._verify_signature", return_value=True):
                result = client._validate_offline("offline-key", "org-123")

        assert result.tier == LicenseTier.STARTER
        assert result.expires_at == expires_at
        assert [module.module_id for module in result.licensed_modules] == ["core.*"]

    def test_validate_offline_accepts_zulu_expiration(self):
        """Offline Zulu UTC expiration is normalized to an aware datetime."""
        client = LicenseClient()
        payload = {
            "organization": {"id": "org-123"},
            "modules": {"included": ["core.*"]},
            "validity": {"expires_at": "2027-01-07T00:00:00Z"},
        }

        with patch("src.core.licensing.services.LicenseService._decode_license_key", return_value=(payload, b"sig")):
            with patch("src.core.licensing.services.LicenseService._verify_signature", return_value=True):
                result = client._validate_offline("offline-key", "org-123")

        assert result.expires_at == datetime(2027, 1, 7, tzinfo=timezone.utc)

    def test_circuit_breaker_opens_after_configured_failure_threshold(self):
        """The breaker blocks calls after exactly the configured failure count."""
        breaker = _CircuitBreaker(failure_threshold=2, reset_timeout_seconds=60)
        failing_call = MagicMock(side_effect=requests.RequestException("down"))

        for _ in range(2):
            with pytest.raises(requests.RequestException):
                breaker.call(failing_call)

        blocked_call = MagicMock()
        with pytest.raises(
            LicenseValidationError,
            match="^License server circuit breaker open$",
        ) as exc_info:
            breaker.call(blocked_call)

        assert exc_info.value.status == LicenseValidationStatus.INVALID
        blocked_call.assert_not_called()

    def test_circuit_breaker_default_contract(self):
        """Documented breaker defaults are part of the licensing contract."""
        breaker = _CircuitBreaker()

        assert breaker.failure_threshold == 5
        assert breaker.reset_timeout == 60.0

    def test_circuit_breaker_resets_after_timeout(self):
        """After reset timeout expires, the breaker allows a trial call again."""
        breaker = _CircuitBreaker(failure_threshold=1, reset_timeout_seconds=10)
        failing_call = MagicMock(side_effect=requests.RequestException("down"))
        successful_call = MagicMock(return_value="ok")

        with patch("src.core.licensing.client.time.monotonic", return_value=100.0):
            with pytest.raises(requests.RequestException):
                breaker.call(failing_call)

        with patch("src.core.licensing.client.time.monotonic", return_value=111.0):
            assert breaker.call(successful_call) == "ok"

        assert breaker._failures == 0

    @override_settings(SARAISE_LICENSE_SERVER_URL="https://settings-url.com/")
    def test_init_with_settings_url_trims_trailing_slashes(self):
        """Configured license URL is normalized like explicit URLs."""
        client = LicenseClient()

        assert client.base_url == "https://settings-url.com"

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
