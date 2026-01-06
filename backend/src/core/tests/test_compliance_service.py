"""Tests for Compliance Service.

Task: 503.3 - Compliance Checks
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from ..compliance_service import (
    ComplianceService,
    ComplianceError,
    compliance_service,
)
from ..compliance_models import (
    ComplianceCheck,
    ComplianceCheckType,
    ResidencyRule,
    PolicyBundleValidation,
)


@pytest.mark.django_db
class TestComplianceService:
    """Test ComplianceService."""

    def test_check_residency_compliant(self) -> None:
        """Test checking residency compliance."""
        service = ComplianceService()

        # Create residency rule
        ResidencyRule.objects.create(
            tenant_id="tenant-1",
            module_name="test-module",
            required_region="us-east-1",
            is_active=True,
        )

        is_compliant, violations = service.check_residency(
            tenant_id="tenant-1",
            module_name="test-module",
            data_region="us-east-1",
        )

        assert is_compliant is True
        assert len(violations) == 0

    def test_check_residency_violation(self) -> None:
        """Test checking residency violation."""
        service = ComplianceService()

        ResidencyRule.objects.create(
            tenant_id="tenant-1",
            module_name="test-module",
            required_region="us-east-1",
            is_active=True,
        )

        is_compliant, violations = service.check_residency(
            tenant_id="tenant-1",
            module_name="test-module",
            data_region="eu-west-1",  # Wrong region
        )

        assert is_compliant is False
        assert len(violations) > 0

    def test_check_residency_no_rules(self) -> None:
        """Test checking residency with no rules is compliant."""
        service = ComplianceService()

        is_compliant, violations = service.check_residency(
            tenant_id="tenant-1",
            module_name="test-module",
            data_region="us-east-1",
        )

        assert is_compliant is True
        assert len(violations) == 0

    def test_validate_policy_bundle_valid(self) -> None:
        """Test validating valid policy bundle."""
        service = ComplianceService()

        policy_bundle = {
            "version": "1.0.0",
            "policies": [
                {
                    "name": "allow-access",
                    "effect": "allow",
                    "conditions": {},
                },
                {
                    "name": "deny-admin",
                    "effect": "deny",
                    "conditions": {},
                },
            ],
        }

        is_valid, errors, warnings = service.validate_policy_bundle(
            tenant_id="tenant-1",
            module_name="test-module",
            policy_bundle=policy_bundle,
            policy_bundle_version="1.0.0",
        )

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_policy_bundle_invalid(self) -> None:
        """Test validating invalid policy bundle."""
        service = ComplianceService()

        # Missing required fields
        policy_bundle = {
            "version": "1.0.0",
            # Missing "policies" field
        }

        is_valid, errors, warnings = service.validate_policy_bundle(
            tenant_id="tenant-1",
            module_name="test-module",
            policy_bundle=policy_bundle,
            policy_bundle_version="1.0.0",
        )

        assert is_valid is False
        assert len(errors) > 0

    def test_validate_policy_bundle_invalid_effect(self) -> None:
        """Test validating policy bundle with invalid effect."""
        service = ComplianceService()

        policy_bundle = {
            "version": "1.0.0",
            "policies": [
                {
                    "name": "test-policy",
                    "effect": "invalid",  # Invalid effect
                },
            ],
        }

        is_valid, errors, warnings = service.validate_policy_bundle(
            tenant_id="tenant-1",
            module_name="test-module",
            policy_bundle=policy_bundle,
            policy_bundle_version="1.0.0",
        )

        assert is_valid is False
        assert len(errors) > 0

    def test_check_module_compliance_on_install(self) -> None:
        """Test checking compliance on install."""
        service = ComplianceService()

        is_compliant, violations = service.check_module_compliance_on_install(
            tenant_id="tenant-1",
            module_name="test-module",
        )

        assert isinstance(is_compliant, bool)
        assert isinstance(violations, list)

    def test_check_module_compliance_on_upgrade(self) -> None:
        """Test checking compliance on upgrade."""
        service = ComplianceService()

        is_compliant, violations = service.check_module_compliance_on_upgrade(
            tenant_id="tenant-1",
            module_name="test-module",
            from_version="1.0.0",
            to_version="1.1.0",
        )

        assert isinstance(is_compliant, bool)
        assert isinstance(violations, list)

    def test_get_compliance_report(self) -> None:
        """Test getting compliance report."""
        service = ComplianceService()

        # Create compliance checks
        ComplianceCheck.objects.create(
            tenant_id="tenant-1",
            module_name="test-module",
            check_type=ComplianceCheckType.RESIDENCY,
            status="passing",
        )

        ComplianceCheck.objects.create(
            tenant_id="tenant-1",
            module_name="test-module",
            check_type=ComplianceCheckType.POLICY_BUNDLE,
            status="failing",
        )

        report = service.get_compliance_report(tenant_id="tenant-1")

        assert report["total_checks"] >= 2
        assert report["passing"] >= 1
        assert report["failing"] >= 1
        assert "checks_by_type" in report
        assert "recent_checks" in report

    def test_create_residency_rule(self) -> None:
        """Test creating residency rule."""
        service = ComplianceService()

        rule = service.create_residency_rule(
            tenant_id="tenant-1",
            module_name="test-module",
            required_region="us-east-1",
            description="US data residency requirement",
        )

        assert rule is not None
        assert rule.tenant_id == "tenant-1"
        assert rule.module_name == "test-module"
        assert rule.required_region == "us-east-1"
        assert rule.is_active is True

    def test_create_residency_rule_global(self) -> None:
        """Test creating global residency rule."""
        service = ComplianceService()

        rule = service.create_residency_rule(
            tenant_id=None,  # Global rule
            module_name=None,  # All modules
            required_region="us-east-1",
        )

        assert rule is not None
        assert rule.tenant_id is None
        assert rule.module_name is None
        assert rule.required_region == "us-east-1"

