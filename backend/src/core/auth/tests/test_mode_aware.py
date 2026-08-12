"""
Tests for mode-aware authentication.

Tests mode detection, routing, and session validation.
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIClient

from src.core.auth.mode import get_saraise_mode, is_development, is_saas, is_self_hosted
from src.core.auth_api import current_user_view, login_view, logout_view, update_profile_view
from src.core.authentication import CsrfExemptSessionAuthentication, RelaxedCsrfSessionAuthentication
from src.core.licensing.models import License, Organization
from src.core.user_models import UserProfile

User = get_user_model()


def _record_set_cookie_calls():
    calls = []
    original_set_cookie = Response.set_cookie

    def record_set_cookie(self, *args, **kwargs):
        key = args[0] if args else kwargs.get("key")
        value = args[1] if len(args) > 1 else kwargs.get("value", "")
        calls.append({"key": key, "value": value, "path": kwargs.get("path")})
        return original_set_cookie(self, *args, **kwargs)

    return calls, record_set_cookie


def _assert_session_cookie_calls_use_path(calls, *, cookie_name, session_id, expected_path):
    session_calls = [call for call in calls if call["key"] == cookie_name and call["value"] == session_id]
    assert session_calls
    assert {call["path"] for call in session_calls} == {expected_path}


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
        assert session_cookie["path"] == settings.SESSION_COOKIE_PATH
        assert session_cookie["httponly"] is True
        assert session_cookie["samesite"] == settings.SESSION_COOKIE_SAMESITE
        assert settings.CSRF_COOKIE_NAME in response.cookies

    def test_login_endpoint_contract_allows_pre_session_csrf_bootstrap(self):
        """Login must keep explicit auth, permission, and CSRF bootstrap decorators."""
        wrapped_view = login_view.cls

        assert wrapped_view.authentication_classes == [CsrfExemptSessionAuthentication]
        assert wrapped_view.permission_classes == [AllowAny]
        assert login_view.csrf_exempt is True
        assert "post" in wrapped_view.http_method_names

    @override_settings(SARAISE_MODE="self-hosted")
    def test_login_creates_missing_profile_for_legacy_user(self):
        """Legacy users without UserProfile rows must be repaired during login."""
        self.user.profile.delete()
        assert not UserProfile.objects.filter(user=self.user).exists()

        response = self.client.post(
            "/api/v1/auth/login/", {"email": "test@example.com", "password": "testpass123"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert UserProfile.objects.filter(user=self.user).exists()
        assert response.data["user"]["tenant_id"] is None

    @override_settings(
        SARAISE_MODE="self-hosted",
        SESSION_COOKIE_NAME="custom_session",
        SESSION_COOKIE_PATH="/custom-auth/",
    )
    def test_login_session_cookie_uses_configured_name_and_path(self):
        """Login must mirror configured Django session cookie attributes exactly."""
        set_cookie_calls, record_set_cookie = _record_set_cookie_calls()
        with patch.object(Response, "set_cookie", record_set_cookie):
            response = self.client.post(
                "/api/v1/auth/login/", {"email": "test@example.com", "password": "testpass123"}, format="json"
            )

        session_cookie = response.cookies["custom_session"]
        assert response.status_code == status.HTTP_200_OK
        assert session_cookie.value == response.data["session_id"]
        assert session_cookie["path"] == "/custom-auth/"
        _assert_session_cookie_calls_use_path(
            set_cookie_calls,
            cookie_name="custom_session",
            session_id=response.data["session_id"],
            expected_path="/custom-auth/",
        )

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
        assert response.data == {"error": "Invalid credentials"}

    @override_settings(SARAISE_MODE="self-hosted")
    def test_login_self_hosted_unknown_email_fails_closed(self):
        """Unknown email identities must use the same invalid-credential envelope."""
        response = self.client.post(
            "/api/v1/auth/login/", {"email": "missing@example.com", "password": "testpass123"}, format="json"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data == {"error": "Invalid credentials"}

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


class TestAuthenticatedSessionEndpoints(TestCase):
    """Endpoint-level session contracts for auth_api.py."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="session-user",
            email="session@example.com",
            password="testpass123",
            is_staff=True,
        )

    def test_endpoint_decorators_preserve_session_auth_contracts(self):
        """Authenticated endpoints must keep explicit session auth classes and methods."""
        assert logout_view.cls.authentication_classes == [SessionAuthentication]
        assert current_user_view.cls.authentication_classes == [RelaxedCsrfSessionAuthentication]
        assert update_profile_view.cls.authentication_classes == [SessionAuthentication]
        assert "post" in logout_view.cls.http_method_names
        assert "get" in current_user_view.cls.http_method_names
        assert "patch" in update_profile_view.cls.http_method_names
        assert "put" in update_profile_view.cls.http_method_names

    def test_session_endpoints_require_authentication(self):
        """Session-owned endpoints must not allow anonymous access."""
        assert self.client.get("/api/v1/auth/me/").status_code == status.HTTP_403_FORBIDDEN
        assert self.client.post("/api/v1/auth/logout/").status_code == status.HTTP_403_FORBIDDEN
        assert self.client.post("/api/v1/auth/refresh/").status_code == status.HTTP_403_FORBIDDEN
        assert self.client.patch("/api/v1/auth/profile/", {"username": "blocked"}, format="json").status_code == (
            status.HTTP_403_FORBIDDEN
        )

    @override_settings(SARAISE_MODE="development")
    def test_current_user_returns_complete_profile_payload_and_csrf_cookie(self):
        """Authenticated identity lookup must expose the same stable user shape as login."""
        self.client.force_login(self.user)

        response = self.client.get("/api/v1/auth/me/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "user": {
                "id": str(self.user.id),
                "email": "session@example.com",
                "username": "session-user",
                "is_staff": True,
                "is_superuser": False,
                "tenant_id": None,
                "platform_role": None,
                "tenant_role": None,
            }
        }
        assert settings.CSRF_COOKIE_NAME in response.cookies

    @override_settings(SARAISE_MODE="development")
    def test_current_user_creates_missing_profile_for_legacy_user(self):
        """Current-user lookup must repair authenticated legacy users missing profiles."""
        self.user.profile.delete()
        assert not UserProfile.objects.filter(user=self.user).exists()
        self.client.force_login(self.user)

        response = self.client.get("/api/v1/auth/me/")

        assert response.status_code == status.HTTP_200_OK
        assert UserProfile.objects.filter(user=self.user).exists()
        assert response.data["user"]["tenant_id"] is None

    @override_settings(SARAISE_MODE="development")
    def test_current_user_misconfigured_profile_logs_out_and_fails_closed(self):
        """Current-user endpoint must not leak identities with invalid profile state."""
        profile = self.user.profile
        profile.platform_role = "platform_owner"
        profile.tenant_role = "tenant_admin"
        profile.save_base(update_fields=["platform_role", "tenant_role"])
        self.client.force_login(self.user)

        response = self.client.get("/api/v1/auth/me/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"] == "User profile is misconfigured"
        assert response.data["details"]["tenant_role"] == ["Tenant role is not allowed for platform-scoped users."]
        assert response.data["details"]["platform_role"] == ["Platform role is not allowed for tenant-scoped users."]
        assert self.client.session.get("_auth_user_id") is None

    def test_logout_clears_session_and_returns_contract_message(self):
        """Logout must invalidate the active Django session."""
        self.client.force_login(self.user)

        response = self.client.post("/api/v1/auth/logout/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"message": "Logged out successfully"}
        assert self.client.session.get("_auth_user_id") is None

    def test_refresh_session_returns_contract_message(self):
        """Refresh endpoint validates the existing session without mutating the response shape."""
        self.client.force_login(self.user)

        response = self.client.post("/api/v1/auth/refresh/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"message": "Session refreshed"}

    def test_update_profile_changes_username_and_email_when_unique(self):
        """Profile updates must persist unique identity fields and return the refreshed user."""
        self.client.force_login(self.user)

        response = self.client.patch(
            "/api/v1/auth/profile/",
            {"username": "updated-session-user", "email": "updated-session@example.com"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["username"] == "updated-session-user"
        assert response.data["user"]["email"] == "updated-session@example.com"
        self.user.refresh_from_db()
        assert self.user.username == "updated-session-user"
        assert self.user.email == "updated-session@example.com"

    def test_update_profile_put_method_is_supported(self):
        """The profile endpoint contract supports full-update PUT as well as PATCH."""
        self.client.force_login(self.user)

        response = self.client.put("/api/v1/auth/profile/", {"username": "put-session-user"}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["username"] == "put-session-user"

    def test_update_profile_ignores_blank_username(self):
        """Blank username input is a no-op, not a destructive identity update."""
        self.client.force_login(self.user)

        response = self.client.patch("/api/v1/auth/profile/", {"username": ""}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["username"] == "session-user"
        self.user.refresh_from_db()
        assert self.user.username == "session-user"

    def test_update_profile_creates_missing_profile_for_legacy_user(self):
        """Profile updates must repair authenticated legacy users missing profiles."""
        self.user.profile.delete()
        assert not UserProfile.objects.filter(user=self.user).exists()
        self.client.force_login(self.user)

        response = self.client.patch("/api/v1/auth/profile/", {"email": "legacy-update@example.com"}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["email"] == "legacy-update@example.com"
        assert UserProfile.objects.filter(user=self.user).exists()

    def test_update_profile_rejects_duplicate_username_and_email(self):
        """Identity update checks must fail closed on both unique fields."""
        User.objects.create_user(username="taken", email="taken@example.com", password="testpass123")
        self.client.force_login(self.user)

        username_response = self.client.patch("/api/v1/auth/profile/", {"username": "taken"}, format="json")
        email_response = self.client.patch("/api/v1/auth/profile/", {"email": "taken@example.com"}, format="json")

        assert username_response.status_code == status.HTTP_400_BAD_REQUEST
        assert username_response.data == {"error": "Username already taken"}
        assert email_response.status_code == status.HTTP_400_BAD_REQUEST
        assert email_response.data == {"error": "Email already taken"}

    def test_update_profile_password_change_requires_current_password(self):
        """Password updates must require the caller to prove knowledge of the current password."""
        self.client.force_login(self.user)

        response = self.client.patch("/api/v1/auth/profile/", {"password": "newpass123"}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"error": "Current password is required to change password"}
        self.user.refresh_from_db()
        assert self.user.check_password("testpass123") is True

    def test_update_profile_password_change_rejects_wrong_current_password(self):
        """Wrong current password must leave the stored credential unchanged."""
        self.client.force_login(self.user)

        response = self.client.patch(
            "/api/v1/auth/profile/",
            {"password": "newpass123", "current_password": "wrongpass"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"error": "Current password is incorrect"}
        self.user.refresh_from_db()
        assert self.user.check_password("testpass123") is True

    def test_update_profile_password_change_rejects_short_password(self):
        """Local auth must enforce the minimum password length before saving."""
        self.client.force_login(self.user)

        response = self.client.patch(
            "/api/v1/auth/profile/",
            {"password": "short", "current_password": "testpass123"},  # pragma: allowlist secret
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"error": "Password must be at least 8 characters long"}
        self.user.refresh_from_db()
        assert self.user.check_password("testpass123") is True

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
        ]
    )
    def test_update_profile_password_change_rejects_validator_failures(self):
        """Django password validators must remain part of the update contract."""
        self.client.force_login(self.user)

        response = self.client.patch(
            "/api/v1/auth/profile/",
            {"password": "password", "current_password": "testpass123"},  # pragma: allowlist secret
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"error": ["This password is too common."]}
        self.user.refresh_from_db()
        assert self.user.check_password("testpass123") is True

    def test_update_profile_password_change_saves_valid_password(self):
        """A valid password change must update only after all guards pass."""
        self.client.force_login(self.user)

        response = self.client.patch(
            "/api/v1/auth/profile/",
            {"password": "StrongerPass123!", "current_password": "testpass123"},  # pragma: allowlist secret
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        self.user.refresh_from_db()
        assert self.user.check_password("StrongerPass123!") is True


class TestRegistrationEndpoint(TestCase):
    """Registration contracts owned by auth_api.py."""

    def setUp(self):
        self.client = APIClient()

    @override_settings(SARAISE_MODE="development")
    def test_register_requires_email_and_password(self):
        response = self.client.post("/api/v1/auth/register/", {"email": "new@example.com"}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"error": "Email and password are required"}

    @override_settings(SARAISE_MODE="development")
    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(username="existing", email="new@example.com", password="testpass123")

        response = self.client.post(
            "/api/v1/auth/register/",
            {"email": "new@example.com", "password": "testpass123", "company_name": "Acme"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"error": "User with this email already exists"}

    @override_settings(SARAISE_MODE="development")
    def test_register_first_development_user_creates_org_profile_session_and_cookie(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {"email": "new@example.com", "password": "testpass123", "company_name": "Acme"},
            format="json",
        )

        user = User.objects.get(email="new@example.com")
        organization = Organization.objects.get(name="Acme")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Registration successful"
        assert response.data["session_id"]
        assert response.data["user"]["id"] == str(user.id)
        assert response.data["user"]["tenant_id"] == str(organization.id)
        assert response.data["user"]["tenant_role"] == "tenant_admin"
        session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        assert session_cookie.value == response.data["session_id"]
        assert session_cookie["path"] == settings.SESSION_COOKIE_PATH

    @override_settings(
        SARAISE_MODE="development",
        SESSION_COOKIE_NAME="custom_registration_session",
        SESSION_COOKIE_PATH="/custom-registration/",
    )
    def test_register_session_cookie_uses_configured_name_and_path(self):
        set_cookie_calls, record_set_cookie = _record_set_cookie_calls()
        with patch.object(Response, "set_cookie", record_set_cookie):
            response = self.client.post(
                "/api/v1/auth/register/",
                {"email": "new@example.com", "password": "testpass123", "company_name": "Acme"},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        session_cookie = response.cookies["custom_registration_session"]
        assert session_cookie.value == response.data["session_id"]
        assert session_cookie["path"] == "/custom-registration/"
        _assert_session_cookie_calls_use_path(
            set_cookie_calls,
            cookie_name="custom_registration_session",
            session_id=response.data["session_id"],
            expected_path="/custom-registration/",
        )

    @override_settings(SARAISE_MODE="development")
    def test_register_subsequent_development_user_uses_existing_license_organization(self):
        organization = Organization.objects.create(name="Existing", domain="existing.example")
        License.objects.create(organization=organization)

        response = self.client.post(
            "/api/v1/auth/register/",
            {"email": "member@example.com", "password": "testpass123", "company_name": "Ignored"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["user"]["tenant_id"] == str(organization.id)
        assert response.data["user"]["tenant_role"] == "tenant_user"
        assert Organization.objects.count() == 1


class TestSaaSLogin(TestCase):
    """Test SaaS mode login delegation."""

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18001")
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

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18001")
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
