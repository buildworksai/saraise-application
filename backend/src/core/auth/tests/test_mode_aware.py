"""
Tests for mode-aware authentication.

Tests mode detection, routing, and session validation.
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth.mode import get_saraise_mode, is_development, is_saas, is_self_hosted

User = get_user_model()


class TestModeDetection(TestCase):
    """Test mode detection utilities."""

    @override_settings(SARAISE_MODE="development")
    def test_get_saraise_mode_development(self):
        """Test mode detection in development mode."""
        assert get_saraise_mode() == "development"
        assert is_development() is True
        assert is_self_hosted() is False
        assert is_saas() is False

    @override_settings(SARAISE_MODE="self-hosted")
    def test_get_saraise_mode_self_hosted(self):
        """Test mode detection in self-hosted mode."""
        assert get_saraise_mode() == "self-hosted"
        assert is_self_hosted() is True
        assert is_development() is False
        assert is_saas() is False

    @override_settings(SARAISE_MODE="saas")
    def test_get_saraise_mode_saas(self):
        """Test mode detection in SaaS mode."""
        assert get_saraise_mode() == "saas"
        assert is_saas() is True
        assert is_self_hosted() is False
        assert is_development() is False

    def test_get_saraise_mode_default(self):
        """Test default mode handling."""
        # When SARAISE_MODE is explicitly None, getattr returns None
        # The actual default is set in settings.py, not in mode.py
        # This test verifies the behavior when mode is not set
        with override_settings(SARAISE_MODE=None):
            mode = get_saraise_mode()
            # getattr returns None when attribute is explicitly None
            # In production, settings.py sets default to 'self-hosted'
            # This test verifies the fallback behavior
            assert mode is None or mode in ("development", "self-hosted")


class TestSelfHostedLogin(TestCase):
    """Test self-hosted mode login flow."""

    def setUp(self):
        """Set up test user."""
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @override_settings(SARAISE_MODE="self-hosted")
    def test_login_self_hosted_success(self):
        """Test successful login in self-hosted mode."""
        response = self.client.post(
            "/api/v1/auth/login/", {"email": "test@example.com", "password": "testpass123"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert "user" in response.data
        assert "session_id" in response.data
        assert response.data["user"]["email"] == "test@example.com"
        assert response.data["user"]["id"] == str(self.user.id)
        assert response.data["user"]["username"] == "testuser"
        assert response.data["user"]["is_staff"] is False
        assert response.data["user"]["is_superuser"] is False
        assert response.data["user"]["tenant_id"] is None
        assert response.data["user"]["platform_role"] is None
        assert response.data["user"]["tenant_role"] is None

        session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        assert session_cookie.value == response.data["session_id"]
        assert session_cookie["httponly"] is True
        assert session_cookie["samesite"] == settings.SESSION_COOKIE_SAMESITE

    @override_settings(SARAISE_MODE="self-hosted")
    def test_login_requires_email_and_password(self):
        """Missing credentials must fail before identity lookup."""
        response = self.client.post("/api/v1/auth/login/", {"email": "test@example.com"}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"error": "Email and password are required"}

    @override_settings(SARAISE_MODE="self-hosted")
    def test_login_self_hosted_invalid_credentials(self):
        """Test login with invalid credentials in self-hosted mode."""
        response = self.client.post(
            "/api/v1/auth/login/", {"email": "test@example.com", "password": "wrongpass"}, format="json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "error" in response.data

    @override_settings(SARAISE_MODE="self-hosted")
    def test_login_mfa_token_is_rejected_before_password_validation(self):
        """The local login endpoint must reject unsupported MFA payloads explicitly."""
        response = self.client.post(
            "/api/v1/auth/login/",
            {"email": "test@example.com", "password": "testpass123", "mfa_token": "000000"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"error": "MFA is not supported by this endpoint"}

    @override_settings(SARAISE_MODE="self-hosted")
    def test_login_duplicate_email_fails_closed(self):
        """Duplicate email identities must not produce a 500 or select an arbitrary account."""
        User.objects.create_user(username="duplicate", email="test@example.com", password="testpass123")

        with self.assertLogs("saraise.auth", level="ERROR") as logs:
            response = self.client.post(
                "/api/v1/auth/login/", {"email": "test@example.com", "password": "testpass123"}, format="json"
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data == {"error": "Invalid credentials"}
        assert logs.output == ["ERROR:saraise.auth:auth.login.duplicate_email_identity"]

    @override_settings(SARAISE_MODE="self-hosted")
    def test_login_misconfigured_profile_logs_out_and_fails_closed(self):
        """A profile that fails validation must not leave an authenticated session behind."""
        profile = self.user.profile
        profile.platform_role = "platform_owner"
        profile.tenant_role = "tenant_admin"
        profile.save_base(update_fields=["platform_role", "tenant_role"])

        response = self.client.post(
            "/api/v1/auth/login/", {"email": "test@example.com", "password": "testpass123"}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"] == "User profile is misconfigured"
        assert response.data["details"]["tenant_role"] == ["Tenant role is not allowed for platform-scoped users."]
        assert response.data["details"]["platform_role"] == ["Platform role is not allowed for tenant-scoped users."]
        assert "tenant_id" in response.data["details"]
        assert self.client.session.get("_auth_user_id") is None

    @override_settings(SARAISE_MODE="development")
    def test_login_development_mode(self):
        """Test login in development mode (same as self-hosted)."""
        response = self.client.post(
            "/api/v1/auth/login/", {"email": "test@example.com", "password": "testpass123"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert "user" in response.data


class TestSaaSLogin(TestCase):
    """Test SaaS mode login delegation."""

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    @patch("src.core.auth_api.delegate_login")
    def test_login_saas_success(self, mock_delegate):
        """Test successful login delegation in SaaS mode."""
        # Mock platform response
        mock_delegate.return_value = {
            "user": {
                "id": "user-123",
                "email": "test@example.com",
                "username": "testuser",
            },
            "session_id": "session-123",
        }

        response = self.client.post(
            "/api/v1/auth/login/", {"email": "test@example.com", "password": "testpass123"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "user" in response.data
        assert "session_id" in response.data
        assert response.data["user"] == mock_delegate.return_value["user"]
        assert response.data["session_id"] == "session-123"
        assert response.data["message"] == "Login successful (SaaS mode)"
        mock_delegate.assert_called_once_with("test@example.com", "testpass123")

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    @patch("src.core.auth_api.delegate_login")
    def test_login_saas_failure(self, mock_delegate):
        """Test failed login delegation in SaaS mode."""
        # Mock platform failure
        mock_delegate.return_value = None

        response = self.client.post(
            "/api/v1/auth/login/", {"email": "test@example.com", "password": "wrongpass"}, format="json"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data == {"error": "Invalid credentials"}
        mock_delegate.assert_called_once_with("test@example.com", "wrongpass")


class TestModeSwitching(TestCase):
    """Test behavior when switching between modes."""

    def setUp(self):
        """Set up test user."""
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @override_settings(SARAISE_MODE="self-hosted")
    def test_registration_blocked_in_saas_mode(self):
        """Test that registration is blocked in SaaS mode."""
        # Temporarily switch to SaaS mode
        with override_settings(SARAISE_MODE="saas"):
            response = self.client.post(
                "/api/v1/auth/register/",
                {"email": "newuser@example.com", "password": "newpass123", "company_name": "Test Company"},
                format="json",
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "platform" in response.data["error"].lower()
