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

from .models import License, LicenseStatus
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
        
        # Get license (with error handling for database not ready)
        try:
            license = self._get_license()
        except Exception as e:
            # Database might not be ready yet (during migrations)
            logger.debug(f"License check failed (database may not be ready): {e}")
            return self.get_response(request)
        
        if not license:
            # Allow auth endpoints even without license (for registration)
            # CRITICAL: /api/v1/auth/me/ must always be allowed, as it's used
            # by the frontend to verify authentication status
            if request.path.startswith('/api/v1/auth/'):
                return self.get_response(request)
            return JsonResponse({
                'error': 'no_license',
                'message': 'No license configured. Please register to start trial.',
            }, status=403)
        
        # Store license in request for later use
        request.license = license
        
        # Periodic validation (every 24 hours)
        try:
            if self._should_validate(license):
                is_valid, message = LicenseService.validate_license(license)
                if not is_valid:
                    # Only block if license is locked (not grace period)
                    if license.status == LicenseStatus.LOCKED:
                        return JsonResponse({
                            'error': 'license_invalid',
                            'message': message,
                        }, status=403)
                    # For grace period, allow but log warning
                    logger.warning(f"License validation issue: {message}")
        except Exception as e:
            # Don't block requests if validation fails
            logger.warning(f"License validation error: {e}")
        
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
        try:
            return License.objects.first()
        except Exception as e:
            # Database might not be ready yet (migrations not run)
            logger.debug(f"Could not get license (database may not be ready): {e}")
            return None
    
    def _should_validate(self, license: License) -> bool:
        """Check if we should re-validate license."""
        if not license.last_validated_at:
            return True
        
        # Re-validate every 24 hours
        return timezone.now() > license.last_validated_at + timedelta(hours=24)

