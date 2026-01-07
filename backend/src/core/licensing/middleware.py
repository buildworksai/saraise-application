"""
License Validation Middleware for SARAISE.

Validates license on each request in self-hosted mode.

Phase 7.5: Licensing Subsystem
Reference: saraise-documentation/planning/phases/phase-7.5-licensing.md
"""

import logging
from typing import Optional
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta

from .models import License
from .services import LicenseService

logger = logging.getLogger('saraise.licensing')


class LicenseValidationMiddleware:
    """Middleware to validate license on each request."""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip for development mode
        if getattr(settings, 'SARAISE_MODE', 'development') == 'development':
            return self.get_response(request)
        
        # Skip for SaaS mode (platform handles billing)
        if getattr(settings, 'SARAISE_MODE', 'development') == 'saas':
            return self.get_response(request)
        
        # Skip for certain paths (health checks, static files, auth)
        if self._should_skip(request.path):
            return self.get_response(request)
        
        # Get license
        license = self._get_license()
        if not license:
            return JsonResponse({
                'error': 'no_license',
                'message': 'No license configured. Please register to start trial.',
            }, status=403)
        
        # Store license in request for later use
        request.license = license
        
        # Periodic validation (every 24 hours)
        if self._should_validate(license):
            is_valid, message = LicenseService.validate_license(license)
            if not is_valid:
                # Only block if license is locked (not grace period)
                if license.status == License.LicenseStatus.LOCKED:
                    return JsonResponse({
                        'error': 'license_invalid',
                        'message': message,
                    }, status=403)
                # For grace period, allow but log warning
                logger.warning(f"License validation issue: {message}")
        
        return self.get_response(request)
    
    def _should_skip(self, path: str) -> bool:
        """Check if path should skip license validation."""
        skip_paths = [
            '/api/v1/health/',
            '/api/v1/auth/',  # Allow login/logout
            '/static/',
            '/admin/',
            '/api/schema/',  # OpenAPI schema
        ]
        return any(path.startswith(p) for p in skip_paths)
    
    def _get_license(self) -> Optional[License]:
        """Get the current license."""
        # In self-hosted mode, there's only one license
        return License.objects.first()
    
    def _should_validate(self, license: License) -> bool:
        """Check if we should re-validate license."""
        if not license.last_validated_at:
            return True
        
        # Re-validate every 24 hours
        return timezone.now() > license.last_validated_at + timedelta(hours=24)

