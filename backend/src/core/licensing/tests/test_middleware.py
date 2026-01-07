"""
License Middleware Tests for SARAISE.

Phase 7.5: Licensing Subsystem
Tests for LicenseValidationMiddleware.
"""

import pytest
from django.test import RequestFactory
from django.http import JsonResponse
from unittest.mock import patch, MagicMock
from django.utils import timezone
from datetime import timedelta

from ..models import License, LicenseStatus, Organization
from ..middleware import LicenseValidationMiddleware
from ..services import LicenseService


@pytest.fixture
def organization():
    """Create a test organization."""
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def active_license(organization):
    """Create an active license."""
    return License.objects.create(
        organization=organization,
        status=LicenseStatus.ACTIVE,
        core_tier='free',
        max_companies=1,
        license_expires_at=timezone.now() + timedelta(days=365),
        last_validated_at=timezone.now(),
    )


@pytest.fixture
def locked_license(organization):
    """Create a locked license."""
    return License.objects.create(
        organization=organization,
        status=LicenseStatus.LOCKED,
        core_tier='free',
        max_companies=1,
    )


@pytest.fixture
def get_response():
    """Mock get_response function."""
    def response(request):
        return JsonResponse({'status': 'ok'})
    return response


class TestLicenseValidationMiddleware:
    """Test license validation middleware."""
    
    def test_skips_development_mode(self, get_response):
        """Test that middleware skips in development mode."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'development'):
            response = middleware(request)
            assert response.status_code == 200
    
    def test_skips_saas_mode(self, get_response):
        """Test that middleware skips in SaaS mode."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'saas'):
            response = middleware(request)
            assert response.status_code == 200
    
    def test_skips_health_endpoint(self, get_response):
        """Test that middleware skips health endpoints."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/health/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = middleware(request)
            assert response.status_code == 200
    
    def test_skips_auth_endpoints(self, get_response):
        """Test that middleware skips auth endpoints."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/auth/login/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = middleware(request)
            assert response.status_code == 200
    
    def test_skips_static_files(self, get_response):
        """Test that middleware skips static files."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/static/css/style.css')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = middleware(request)
            assert response.status_code == 200
    
    def test_blocks_when_no_license(self, get_response):
        """Test that middleware blocks when no license exists."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = middleware(request)
            assert response.status_code == 403
            data = response.json()
            assert data['error'] == 'no_license'
    
    def test_allows_with_valid_license(self, get_response, active_license):
        """Test that middleware allows requests with valid license."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = middleware(request)
            assert response.status_code == 200
            assert hasattr(request, 'license')
            assert request.license == active_license
    
    def test_blocks_locked_license(self, get_response, locked_license):
        """Test that middleware blocks locked license."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            with patch.object(LicenseService, 'validate_license', return_value=(False, 'License locked')):
                response = middleware(request)
                assert response.status_code == 403
                data = response.json()
                assert data['error'] == 'license_invalid'
    
    def test_validates_periodically(self, get_response, active_license):
        """Test that middleware validates license periodically."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/test/')
        
        # Set last_validated_at to 25 hours ago (should trigger validation)
        active_license.last_validated_at = timezone.now() - timedelta(hours=25)
        active_license.save()
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            with patch.object(LicenseService, 'validate_license', return_value=(True, 'Valid')) as mock_validate:
                response = middleware(request)
                assert response.status_code == 200
                mock_validate.assert_called_once()
    
    def test_skips_validation_if_recent(self, get_response, active_license):
        """Test that middleware skips validation if recently validated."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/test/')
        
        # Set last_validated_at to 1 hour ago (should not trigger validation)
        active_license.last_validated_at = timezone.now() - timedelta(hours=1)
        active_license.save()
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            with patch.object(LicenseService, 'validate_license') as mock_validate:
                response = middleware(request)
                assert response.status_code == 200
                mock_validate.assert_not_called()
    
    def test_validates_if_no_last_validation(self, get_response, active_license):
        """Test that middleware validates if never validated."""
        middleware = LicenseValidationMiddleware(get_response)
        request = RequestFactory().get('/api/v1/test/')
        
        active_license.last_validated_at = None
        active_license.save()
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            with patch.object(LicenseService, 'validate_license', return_value=(True, 'Valid')) as mock_validate:
                response = middleware(request)
                assert response.status_code == 200
                mock_validate.assert_called_once()

