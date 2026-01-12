"""
Tests for SaaS authentication delegation.

Tests delegation to saraise-auth service.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from src.core.auth.saas import delegate_login, get_platform_url, validate_session


class TestSaaSDelegation(TestCase):
    """Test SaaS authentication delegation."""

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    def test_get_platform_url(self):
        """Test platform URL retrieval."""
        url = get_platform_url()
        assert url == "http://localhost:18000"

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    @patch("src.core.auth.saas.requests.post")
    def test_validate_session_success(self, mock_post):
        """Test successful session validation."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "valid": True,
            "user": {"id": "user-123", "email": "test@example.com"},
        }
        mock_post.return_value = mock_response

        result = validate_session("session-123")
        assert result is not None
        assert result["valid"] is True
        mock_post.assert_called_once()

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    @patch("src.core.auth.saas.requests.post")
    def test_validate_session_failure(self, mock_post):
        """Test failed session validation."""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        result = validate_session("invalid-session")
        assert result is None
        mock_post.assert_called_once()

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    @patch("src.core.auth.saas.requests.post")
    def test_validate_session_network_error(self, mock_post):
        """Test session validation with network error."""
        # Mock network error
        from requests.exceptions import RequestException

        mock_post.side_effect = RequestException("Network error")

        result = validate_session("session-123")
        assert result is None

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    @patch("src.core.auth.saas.requests.post")
    def test_delegate_login_success(self, mock_post):
        """Test successful login delegation."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user": {"id": "user-123", "email": "test@example.com"},
            "session_id": "session-123",
        }
        mock_post.return_value = mock_response

        result = delegate_login("test@example.com", "password123")
        assert result is not None
        assert "user" in result
        assert "session_id" in result
        mock_post.assert_called_once()

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    @patch("src.core.auth.saas.requests.post")
    def test_delegate_login_failure(self, mock_post):
        """Test failed login delegation."""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        result = delegate_login("test@example.com", "wrongpass")
        assert result is None
        mock_post.assert_called_once()

    @override_settings(SARAISE_MODE="saas", SARAISE_PLATFORM_URL="http://localhost:18000")
    @patch("src.core.auth.saas.requests.post")
    def test_delegate_login_network_error(self, mock_post):
        """Test login delegation with network error."""
        # Mock network error
        from requests.exceptions import RequestException

        mock_post.side_effect = RequestException("Network error")

        result = delegate_login("test@example.com", "password123")
        assert result is None

    @override_settings(SARAISE_MODE="self-hosted")
    def test_validate_session_not_saas(self):
        """Test that validate_session returns None when not in SaaS mode."""
        result = validate_session("session-123")
        assert result is None

    @override_settings(SARAISE_MODE="self-hosted")
    def test_delegate_login_not_saas(self):
        """Test that delegate_login returns None when not in SaaS mode."""
        result = delegate_login("test@example.com", "password123")
        assert result is None
