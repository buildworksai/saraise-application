"""
SARAISE Licensing Subsystem

Provides license validation, module gating, and trial management
for self-hosted installations.

Phase 7.5: Licensing Subsystem
Reference: saraise-documentation/planning/phases/phase-7.5-licensing.md
"""

from .client import LicenseClient
from .decorators import require_license, require_module, requires_license, requires_module, requires_write_access
from .middleware import LicenseValidationMiddleware
from .models import LicenseStatus  # Django TextChoices for models
from .models import LicenseValidationStatus  # Enum for dataclasses
from .models import License, LicenseInfo, LicenseValidationLog, ModuleLicense, Organization
from .services import LicenseService, ModuleAccessService
from .validator import LicenseValidator

__all__ = [
    # Clients and validators
    "LicenseClient",
    "LicenseValidator",
    # Dataclasses
    "LicenseInfo",
    "ModuleLicense",
    "LicenseValidationStatus",  # Enum for dataclasses
    # Django models
    "Organization",
    "License",
    "LicenseStatus",  # Django TextChoices for models
    "LicenseValidationLog",
    # Services
    "LicenseService",
    "ModuleAccessService",
    # Decorators (legacy)
    "require_license",
    "require_module",
    # Decorators (Phase 7.5)
    "requires_license",
    "requires_module",
    "requires_write_access",
    # Middleware
    "LicenseValidationMiddleware",
]
