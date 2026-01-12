"""
SARAISE Core Application

This app contains core infrastructure including:
- Authentication and authorization
- Module management
- Licensing subsystem
- Compliance models
- Module registry models
- Entitlement models
- Module guardrail models
"""

# Import licensing models so Django can discover them
# Models imported lazily to avoid Django app registry issues
# from .licensing.models import Organization, License, LicenseValidationLog

# Note: Other models (compliance, module_registry, etc.) are in separate files
# and will be discovered by Django when imported. They should be imported
# in models.py or through app config if needed.

__all__ = [
    "Organization",
    "License",
    "LicenseValidationLog",
]
