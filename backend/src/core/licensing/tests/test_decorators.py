"""
License Decorator Tests for SARAISE.

Phase 7.5: Licensing Subsystem
Tests for license decorators.
"""

import json
import pytest
from django.test import RequestFactory
from django.http import JsonResponse
from unittest.mock import patch
from django.utils import timezone
from datetime import timedelta

from ..models import License, LicenseStatus, Organization
from ..decorators import requires_license, requires_module, requires_write_access
from ..services import ModuleAccessService

# Enable database access for all tests in this module
pytestmark = pytest.mark.django_db


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
    )


@pytest.fixture
def expired_license(organization):
    """Create an expired license."""
    return License.objects.create(
        organization=organization,
        status=LicenseStatus.EXPIRED,
        core_tier='free',
        max_companies=1,
        license_expires_at=timezone.now() - timedelta(days=1),
    )


def test_view(request):
    """Test view function."""
    return JsonResponse({'status': 'ok'})


class TestRequiresLicenseDecorator:
    """Test @requires_license decorator."""
    
    def test_allows_in_development_mode(self):
        """Test that decorator allows in development mode."""
        decorated = requires_license(test_view)
        request = RequestFactory().get('/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'development'):
            response = decorated(request)
            assert response.status_code == 200
    
    def test_allows_in_saas_mode(self):
        """Test that decorator allows in SaaS mode."""
        decorated = requires_license(test_view)
        request = RequestFactory().get('/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'saas'):
            response = decorated(request)
            assert response.status_code == 200
    
    def test_blocks_without_license(self):
        """Test that decorator blocks without license."""
        decorated = requires_license(test_view)
        request = RequestFactory().get('/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = decorated(request)
            assert response.status_code == 403
            assert isinstance(response, JsonResponse)
            data = json.loads(response.content)
            assert data['error'] == 'license_required'
    
    def test_allows_with_valid_license(self, active_license):
        """Test that decorator allows with valid license."""
        decorated = requires_license(test_view)
        request = RequestFactory().get('/test/')
        request.license = active_license
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = decorated(request)
            assert response.status_code == 200
    
    def test_blocks_with_invalid_license(self, expired_license):
        """Test that decorator blocks with invalid license."""
        decorated = requires_license(test_view)
        request = RequestFactory().get('/test/')
        request.license = expired_license
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = decorated(request)
            assert response.status_code == 403


class TestRequiresModuleDecorator:
    """Test @requires_module decorator."""
    
    def test_allows_in_development_mode(self):
        """Test that decorator allows in development mode."""
        decorated = requires_module('crm')(test_view)
        request = RequestFactory().get('/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'development'):
            response = decorated(request)
            assert response.status_code == 200
    
    def test_blocks_without_license(self):
        """Test that decorator blocks without license."""
        decorated = requires_module('crm')(test_view)
        request = RequestFactory().get('/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = decorated(request)
            assert response.status_code == 403
            assert isinstance(response, JsonResponse)
            data = json.loads(response.content)
            assert data['error'] == 'no_license'
    
    def test_allows_licensed_module(self, active_license):
        """Test that decorator allows licensed module."""
        decorated = requires_module('crm')(test_view)
        request = RequestFactory().get('/test/')
        request.license = active_license
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            with patch.object(ModuleAccessService, 'can_access_module', return_value=(True, 'Allowed')):
                response = decorated(request)
                assert response.status_code == 200
    
    def test_blocks_unlicensed_module(self, active_license):
        """Test that decorator blocks unlicensed module."""
        decorated = requires_module('manufacturing')(test_view)
        request = RequestFactory().get('/test/')
        request.license = active_license
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            with patch.object(ModuleAccessService, 'can_access_module', return_value=(False, 'Not licensed')):
                response = decorated(request)
                assert response.status_code == 403
                assert isinstance(response, JsonResponse)
                data = json.loads(response.content)
                assert data['error'] == 'module_not_licensed'


class TestRequiresWriteAccessDecorator:
    """Test @requires_write_access decorator."""
    
    def test_allows_in_development_mode(self):
        """Test that decorator allows in development mode."""
        decorated = requires_write_access('crm')(test_view)
        request = RequestFactory().get('/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'development'):
            response = decorated(request)
            assert response.status_code == 200
    
    def test_blocks_without_license(self):
        """Test that decorator blocks without license."""
        decorated = requires_write_access('crm')(test_view)
        request = RequestFactory().get('/test/')
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            response = decorated(request)
            assert response.status_code == 403
    
    def test_allows_write_with_valid_license(self, active_license):
        """Test that decorator allows write with valid license."""
        decorated = requires_write_access('crm')(test_view)
        request = RequestFactory().get('/test/')
        request.license = active_license
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            with patch.object(ModuleAccessService, 'can_write_module', return_value=True):
                response = decorated(request)
                assert response.status_code == 200
    
    def test_blocks_write_with_expired_license(self, expired_license):
        """Test that decorator blocks write with expired license."""
        decorated = requires_write_access('crm')(test_view)
        request = RequestFactory().get('/test/')
        request.license = expired_license
        
        with patch('django.conf.settings.SARAISE_MODE', 'self-hosted'):
            with patch.object(ModuleAccessService, 'can_write_module', return_value=False):
                response = decorated(request)
                assert response.status_code == 403
                assert isinstance(response, JsonResponse)
                data = json.loads(response.content)
                assert data['error'] == 'read_only_mode'

