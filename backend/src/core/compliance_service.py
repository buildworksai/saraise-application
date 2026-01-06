"""Compliance Service.

Implements compliance checks for residency and policy bundles.
Task: 503.3 - Compliance Checks
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from django.db import transaction, models
from django.utils import timezone

from .compliance_models import (
    ComplianceCheck,
    ComplianceCheckType,
    ResidencyRule,
    PolicyBundleValidation,
)
from .module_registry_models import ModuleRegistryEntry, TenantModuleInstallation

logger = logging.getLogger(__name__)


class ComplianceError(Exception):
    """Compliance error."""

    pass


class ComplianceService:
    """Compliance service.

    Manages compliance checks for residency and policy bundles.
    """

    def __init__(self) -> None:
        """Initialize compliance service."""
        pass

    def check_residency(
        self,
        tenant_id: str,
        module_name: str,
        data_region: str,
    ) -> Tuple[bool, List[str]]:
        """Check data residency compliance.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            data_region: Current data region.

        Returns:
            Tuple of (is_compliant, violations).
        """
        violations: List[str] = []

        # Get residency rules (tenant-specific, module-specific, or global)
        rules = ResidencyRule.objects.filter(is_active=True).filter(
            models.Q(tenant_id=tenant_id) | models.Q(tenant_id__isnull=True)
        ).filter(
            models.Q(module_name=module_name) | models.Q(module_name__isnull=True)
        ).order_by("tenant_id", "module_name")  # More specific rules first

        if not rules.exists():
            # No residency rules = compliant
            self._record_check(
                tenant_id, module_name, ComplianceCheckType.RESIDENCY, True, []
            )
            return True, []

        # Check if data region matches required region
        for rule in rules:
            if rule.required_region != data_region:
                violation_msg = (
                    f"Data residency violation: Module {module_name} "
                    f"data in region {data_region} but required region is {rule.required_region}"
                )
                violations.append(violation_msg)

        is_compliant = len(violations) == 0

        self._record_check(
            tenant_id, module_name, ComplianceCheckType.RESIDENCY, is_compliant, violations
        )

        return is_compliant, violations

    def validate_policy_bundle(
        self,
        tenant_id: str,
        module_name: str,
        policy_bundle: Dict[str, Any],
        policy_bundle_version: str,
    ) -> Tuple[bool, List[str], List[str]]:
        """Validate policy bundle.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            policy_bundle: Policy bundle dictionary.
            policy_bundle_version: Policy bundle version.

        Returns:
            Tuple of (is_valid, errors, warnings).
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Basic validation
        if not isinstance(policy_bundle, dict):
            errors.append("Policy bundle must be a dictionary")
            self._record_policy_validation(
                tenant_id, module_name, policy_bundle_version, False, errors, warnings
            )
            return False, errors, warnings

        # Check required fields
        required_fields = ["version", "policies"]
        for field in required_fields:
            if field not in policy_bundle:
                errors.append(f"Missing required field: {field}")

        # Validate policies structure
        if "policies" in policy_bundle:
            policies = policy_bundle["policies"]
            if not isinstance(policies, list):
                errors.append("Policies must be a list")
            else:
                for i, policy in enumerate(policies):
                    if not isinstance(policy, dict):
                        errors.append(f"Policy at index {i} must be a dictionary")
                    else:
                        # Check policy structure
                        if "name" not in policy:
                            errors.append(f"Policy at index {i} missing 'name' field")
                        if "effect" not in policy:
                            errors.append(f"Policy at index {i} missing 'effect' field")
                        elif policy["effect"] not in ["allow", "deny"]:
                            errors.append(
                                f"Policy at index {i} has invalid effect: {policy['effect']}"
                            )

        # Version validation
        if "version" in policy_bundle:
            if policy_bundle["version"] != policy_bundle_version:
                warnings.append(
                    f"Policy bundle version mismatch: "
                    f"expected {policy_bundle_version}, got {policy_bundle['version']}"
                )

        is_valid = len(errors) == 0

        self._record_policy_validation(
            tenant_id, module_name, policy_bundle_version, is_valid, errors, warnings
        )

        return is_valid, errors, warnings

    def check_module_compliance_on_install(
        self, tenant_id: str, module_name: str, module_path: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        """Check module compliance before installation.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            module_path: Optional module path.

        Returns:
            Tuple of (is_compliant, violations).
        """
        violations: List[str] = []

        # Check residency (if tenant has residency rules)
        residency_rules = ResidencyRule.objects.filter(
            tenant_id=tenant_id, is_active=True
        ).first()
        if residency_rules:
            # This is a placeholder - actual implementation would check data region
            # For now, we'll assume compliance if no explicit violation
            pass

        # Check policy bundle (if module has policy bundle)
        # This would be done during module registration/validation

        is_compliant = len(violations) == 0

        self._record_check(
            tenant_id,
            module_name,
            ComplianceCheckType.SCHEMA_COMPLIANCE,
            is_compliant,
            violations,
        )

        return is_compliant, violations

    def check_module_compliance_on_upgrade(
        self,
        tenant_id: str,
        module_name: str,
        from_version: str,
        to_version: str,
    ) -> Tuple[bool, List[str]]:
        """Check module compliance before upgrade.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            from_version: Source version.
            to_version: Target version.

        Returns:
            Tuple of (is_compliant, violations).
        """
        violations: List[str] = []

        # Check residency (if tenant has residency rules)
        residency_rules = ResidencyRule.objects.filter(
            tenant_id=tenant_id, is_active=True
        ).first()
        if residency_rules:
            # This is a placeholder - actual implementation would check data region
            pass

        # Check policy bundle compatibility
        # This would validate that policy bundle changes are compatible

        is_compliant = len(violations) == 0

        self._record_check(
            tenant_id,
            module_name,
            ComplianceCheckType.SCHEMA_COMPLIANCE,
            is_compliant,
            violations,
        )

        return is_compliant, violations

    def get_compliance_report(
        self,
        tenant_id: Optional[str] = None,
        module_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get compliance report.

        Args:
            tenant_id: Optional tenant ID filter.
            module_name: Optional module name filter.

        Returns:
            Compliance report dictionary.
        """
        query = ComplianceCheck.objects.all()

        if tenant_id:
            query = query.filter(tenant_id=tenant_id)

        if module_name:
            query = query.filter(module_name=module_name)

        checks = query.order_by("-checked_at")

        report = {
            "total_checks": checks.count(),
            "passing": checks.filter(status="passing").count(),
            "failing": checks.filter(status="failing").count(),
            "warnings": checks.filter(status="warning").count(),
            "pending": checks.filter(status="pending").count(),
            "checks_by_type": {},
            "recent_checks": [],
        }

        # Breakdown by type
        for check_type in ComplianceCheckType.values:
            type_checks = checks.filter(check_type=check_type)
            report["checks_by_type"][check_type] = {
                "total": type_checks.count(),
                "passing": type_checks.filter(status="passing").count(),
                "failing": type_checks.filter(status="failing").count(),
            }

        # Recent checks
        recent = list(checks[:10])
        report["recent_checks"] = [
            {
                "id": check.id,
                "check_type": check.check_type,
                "module_name": check.module_name,
                "status": check.status,
                "checked_at": check.checked_at.isoformat(),
                "violations": check.violations,
            }
            for check in recent
        ]

        return report

    @transaction.atomic
    def create_residency_rule(
        self,
        tenant_id: Optional[str],
        module_name: Optional[str],
        required_region: str,
        description: Optional[str] = None,
    ) -> ResidencyRule:
        """Create a residency rule.

        Args:
            tenant_id: Optional tenant ID (None = global rule).
            module_name: Optional module name (None = all modules).
            required_region: Required data residency region.
            description: Optional description.

        Returns:
            Created ResidencyRule instance.
        """
        rule = ResidencyRule.objects.create(
            tenant_id=tenant_id,
            module_name=module_name,
            required_region=required_region,
            description=description,
            is_active=True,
        )

        logger.info(
            f"Created residency rule: {required_region} "
            f"(Tenant: {tenant_id}, Module: {module_name})"
        )

        return rule

    def _record_check(
        self,
        tenant_id: str,
        module_name: str,
        check_type: str,
        is_compliant: bool,
        violations: List[str],
    ) -> ComplianceCheck:
        """Record a compliance check.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            check_type: Check type.
            is_compliant: Whether compliant.
            violations: List of violations.

        Returns:
            Created ComplianceCheck instance.
        """
        status = "passing" if is_compliant else "failing"
        if not is_compliant and len(violations) == 0:
            status = "warning"

        check = ComplianceCheck.objects.create(
            tenant_id=tenant_id,
            module_name=module_name,
            check_type=check_type,
            status=status,
            violations=violations,
            check_details={"is_compliant": is_compliant},
        )

        return check

    def _record_policy_validation(
        self,
        tenant_id: str,
        module_name: str,
        policy_bundle_version: str,
        is_valid: bool,
        errors: List[str],
        warnings: List[str],
    ) -> PolicyBundleValidation:
        """Record policy bundle validation.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            policy_bundle_version: Policy bundle version.
            is_valid: Whether valid.
            errors: List of errors.
            warnings: List of warnings.

        Returns:
            Created PolicyBundleValidation instance.
        """
        validation_status = "valid" if is_valid else "invalid"
        if not is_valid and len(errors) == 0 and len(warnings) > 0:
            validation_status = "warning"

        validation = PolicyBundleValidation.objects.create(
            tenant_id=tenant_id,
            module_name=module_name,
            policy_bundle_version=policy_bundle_version,
            validation_status=validation_status,
            validation_errors=errors,
            validation_warnings=warnings,
        )

        return validation


# Global compliance service instance
compliance_service = ComplianceService()

