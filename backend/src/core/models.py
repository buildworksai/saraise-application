"""
SARAISE Core Models

This file imports all core models so Django can discover them.
Models are organized in separate files for clarity, but must be
imported here for Django's app registry.
"""

# Import all core models so Django can discover them
from .compliance_models import ComplianceCheck, ResidencyRule
from .entitlement_models import (
    EntitlementCheck,
    PlanEntitlement,
    SubscriptionPlan,
    TenantSubscription,
)
from .module_guardrail_models import GuardrailRule, GuardrailViolation
from .module_installation_models import InstallationStep, ModuleInstallation
from .module_registry_models import (
    ModuleRegistryEntry,
    TenantModuleInstallation,
)
from .module_upgrade_models import ModuleUpgrade, UpgradeStep

__all__ = [
    "ComplianceCheck",
    "ResidencyRule",
    "ModuleRegistryEntry",
    "TenantModuleInstallation",
    "SubscriptionPlan",
    "PlanEntitlement",
    "TenantSubscription",
    "EntitlementCheck",
    "GuardrailViolation",
    "GuardrailRule",
    "ModuleUpgrade",
    "UpgradeStep",
    "ModuleInstallation",
    "InstallationStep",
]
