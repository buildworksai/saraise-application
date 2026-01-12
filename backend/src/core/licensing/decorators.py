"""
License enforcement decorators for SARAISE.

Provides decorators for:
- API endpoint license checks
- Module-level gating
- Feature flag enforcement

Phase 7.5: Licensing Subsystem
Reference: saraise-documentation/planning/phases/phase-7.5-licensing.md
"""

import functools
import logging
from typing import Callable, Optional

from django.conf import settings
from django.http import JsonResponse
from rest_framework import status
from rest_framework.request import Request

from .services import ModuleAccessService
from .validator import get_license_validator

logger = logging.getLogger("saraise.licensing")


def require_license(func: Callable) -> Callable:
    """
    Decorator to require a valid license for an API endpoint.

    Returns 402 Payment Required if license is invalid.

    Usage:
        @require_license
        def my_view(request):
            ...
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        validator = get_license_validator()

        # Skip in development mode
        if validator.is_development_mode:
            return func(*args, **kwargs)

        # Check license validity
        license_info = validator.get_license()
        if not license_info or not license_info.is_valid:
            logger.warning("License invalid - blocking request")
            return JsonResponse(
                {
                    "error": "license_required",
                    "message": "A valid license is required to access this feature.",
                    "status": license_info.status.value if license_info else "not_found",
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        return func(*args, **kwargs)

    return wrapper


def require_module(module_id: str, write: bool = False) -> Callable:
    """
    Decorator to require a specific module license.

    Args:
        module_id: The module identifier (e.g., "industry.manufacturing")
        write: Whether this is a write operation (enforces soft-lock)

    Returns 402 if module is not licensed, 403 if soft-locked.

    Usage:
        @require_module("industry.manufacturing")
        def manufacturing_api(request):
            ...

        @require_module("core.hr", write=True)
        def update_employee(request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            validator = get_license_validator()

            # Skip in development mode
            if validator.is_development_mode:
                return func(*args, **kwargs)

            # Check module access
            if not validator.check_module_access(module_id, write_operation=write):
                license_info = validator.get_license()

                # Determine error type
                if license_info and license_info.is_expired and write:
                    # Soft-lock - read-only mode
                    logger.warning(f"Soft-lock: denying write to {module_id}")
                    return JsonResponse(
                        {
                            "error": "soft_locked",
                            "message": (
                                "Your license has expired. "
                                "The system is in read-only mode. "
                                "Please renew your subscription to enable write operations."
                            ),
                            "module": module_id,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
                else:
                    # Module not licensed
                    logger.warning(f"Module not licensed: {module_id}")
                    return JsonResponse(
                        {
                            "error": "module_not_licensed",
                            "message": f"The '{module_id}' module is not included in your license.",
                            "module": module_id,
                            "upgrade_url": "https://subscribe.saraise.com",
                        },
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )

            return func(*args, **kwargs)

        return wrapper

    return decorator


class LicenseRequiredMixin:
    """
    Mixin for DRF ViewSets to require a valid license.

    Usage:
        class MyViewSet(LicenseRequiredMixin, viewsets.ModelViewSet):
            ...
    """

    def check_license(self, request: Request, write: bool = False) -> Optional[JsonResponse]:
        """
        Check license and return error response if invalid.

        Returns None if license is valid, JsonResponse if invalid.
        """
        validator = get_license_validator()

        if validator.is_development_mode:
            return None

        license_info = validator.get_license()

        if not license_info or not license_info.is_valid:
            return JsonResponse(
                {
                    "error": "license_required",
                    "message": "A valid license is required.",
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        if write and validator.is_soft_locked():
            return JsonResponse(
                {
                    "error": "soft_locked",
                    "message": "System is in read-only mode due to expired license.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return None

    def initial(self, request: Request, *args, **kwargs):
        """Override to add license check."""
        super().initial(request, *args, **kwargs)

        # Determine if this is a write operation
        write = request.method in ("POST", "PUT", "PATCH", "DELETE")

        error_response = self.check_license(request, write=write)
        if error_response:
            raise LicenseException(error_response)


class ModuleRequiredMixin:
    """
    Mixin for DRF ViewSets to require a specific module license.

    Usage:
        class ManufacturingViewSet(ModuleRequiredMixin, viewsets.ModelViewSet):
            required_module = "industry.manufacturing"
    """

    required_module: str = ""

    def check_module_license(self, request: Request) -> Optional[JsonResponse]:
        """Check module license."""
        if not self.required_module:
            return None

        validator = get_license_validator()

        if validator.is_development_mode:
            return None

        write = request.method in ("POST", "PUT", "PATCH", "DELETE")

        if not validator.check_module_access(self.required_module, write_operation=write):
            if validator.is_soft_locked() and write:
                return JsonResponse(
                    {
                        "error": "soft_locked",
                        "message": "System is in read-only mode.",
                        "module": self.required_module,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            return JsonResponse(
                {
                    "error": "module_not_licensed",
                    "message": f"Module '{self.required_module}' is not licensed.",
                    "upgrade_url": "https://subscribe.saraise.com",
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        return None

    def initial(self, request: Request, *args, **kwargs):
        """Override to add module license check."""
        super().initial(request, *args, **kwargs)

        error_response = self.check_module_license(request)
        if error_response:
            raise LicenseException(error_response)


class LicenseException(Exception):
    """Exception for license validation failures in ViewSets."""

    def __init__(self, response: JsonResponse):
        self.response = response
        super().__init__("License validation failed")


# ============================================================================
# Phase 7.5: Additional decorators using services directly
# ============================================================================


def requires_license(func: Callable) -> Callable:
    """
    Decorator to require valid license for a view.

    Phase 7.5: Uses LicenseService directly.

    Usage:
        @requires_license
        def my_view(request):
            ...
    """

    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        # Skip in development mode
        if getattr(settings, "SARAISE_MODE", "development") == "development":
            return func(request, *args, **kwargs)

        # Skip in SaaS mode
        if getattr(settings, "SARAISE_MODE", "development") == "saas":
            return func(request, *args, **kwargs)

        license = getattr(request, "license", None)
        if not license or not license.is_license_valid():
            return JsonResponse(
                {
                    "error": "license_required",
                    "message": "Valid license required for this operation.",
                },
                status=403,
            )
        return func(request, *args, **kwargs)

    return wrapper


def requires_module(module_name: str):
    """
    Decorator to require specific module access.

    Phase 7.5: Uses ModuleAccessService directly.

    Usage:
        @requires_module("manufacturing")
        def manufacturing_api(request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            # Skip in development mode
            if getattr(settings, "SARAISE_MODE", "development") == "development":
                return func(request, *args, **kwargs)

            # Skip in SaaS mode
            if getattr(settings, "SARAISE_MODE", "development") == "saas":
                return func(request, *args, **kwargs)

            license = getattr(request, "license", None)
            if not license:
                return JsonResponse(
                    {
                        "error": "no_license",
                        "message": "License required.",
                    },
                    status=403,
                )

            can_access, reason = ModuleAccessService.can_access_module(license, module_name)
            if not can_access:
                return JsonResponse(
                    {
                        "error": "module_not_licensed",
                        "message": reason,
                        "module": module_name,
                    },
                    status=403,
                )

            return func(request, *args, **kwargs)

        return wrapper

    return decorator


def requires_write_access(module_name: str):
    """
    Decorator to require write access (not in soft lock).

    Phase 7.5: Uses ModuleAccessService to check write permissions.

    Usage:
        @requires_write_access("crm")
        def update_customer(request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            # Skip in development mode
            if getattr(settings, "SARAISE_MODE", "development") == "development":
                return func(request, *args, **kwargs)

            # Skip in SaaS mode
            if getattr(settings, "SARAISE_MODE", "development") == "saas":
                return func(request, *args, **kwargs)

            license = getattr(request, "license", None)
            if not license:
                return JsonResponse(
                    {
                        "error": "no_license",
                        "message": "License required.",
                    },
                    status=403,
                )

            if not ModuleAccessService.can_write_module(license, module_name):
                return JsonResponse(
                    {
                        "error": "read_only_mode",
                        "message": ("License expired. Read-only mode active. " "Please renew to enable writes."),
                        "module": module_name,
                    },
                    status=403,
                )

            return func(request, *args, **kwargs)

        return wrapper

    return decorator
