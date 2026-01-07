"""
SARAISE Licensing Subsystem

Provides license validation, module gating, and trial management
for self-hosted installations.

Reference: saraise-documentation/licensing/licensing-architecture.md
"""

from .client import LicenseClient
from .validator import LicenseValidator
from .models import LicenseInfo, ModuleLicense
from .decorators import require_license, require_module

__all__ = [
    'LicenseClient',
    'LicenseValidator',
    'LicenseInfo',
    'ModuleLicense',
    'require_license',
    'require_module',
]

