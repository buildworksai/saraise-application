"""
SARAISE Core Application

This app contains core infrastructure including:
- Authentication and authorization
- Module management
- Licensing subsystem
"""

# Import licensing models so Django can discover them
# Models imported lazily to avoid Django app registry issues
# from .licensing.models import Organization, License, LicenseValidationLog

__all__ = [
    'Organization',
    'License',
    'LicenseValidationLog',
]
