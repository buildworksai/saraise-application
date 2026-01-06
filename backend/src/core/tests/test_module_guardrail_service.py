"""Tests for Module Guardrail Service.

Task: 503.2 - Module Guardrails
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from django.utils import timezone

from ..module_guardrail_service import (
    ModuleGuardrailService,
    GuardrailError,
    module_guardrail_service,
)
from ..module_guardrail_models import (
    GuardrailViolation,
    GuardrailRule,
    GuardrailViolationType,
)


@pytest.mark.django_db
class TestModuleGuardrailService:
    """Test ModuleGuardrailService."""

    def test_scan_module_no_violations(self) -> None:
        """Test scanning module with no violations."""
        service = ModuleGuardrailService()

        # Create temporary module directory with clean code
        with tempfile.TemporaryDirectory() as tmpdir:
            module_dir = Path(tmpdir) / "test-module"
            module_dir.mkdir()

            # Create clean Python file
            clean_file = module_dir / "models.py"
            clean_file.write_text(
                """
def create_customer(name: str) -> dict:
    return {"name": name}
"""
            )

            violations = service.scan_module("test-module", str(module_dir))
            assert len(violations) == 0

    def test_scan_module_auth_drift(self) -> None:
        """Test scanning module with auth drift violations."""
        service = ModuleGuardrailService()

        with tempfile.TemporaryDirectory() as tmpdir:
            module_dir = Path(tmpdir) / "test-module"
            module_dir.mkdir()

            # Create file with auth drift
            bad_file = module_dir / "auth.py"
            bad_file.write_text(
                """
def login(username: str, password: str) -> dict:
    return {"token": "jwt-token"}
"""
            )

            violations = service.scan_module("test-module", str(module_dir))
            assert len(violations) > 0
            assert any(
                v.violation_type == GuardrailViolationType.AUTH_DRIFT for v in violations
            )

    def test_scan_module_policy_drift(self) -> None:
        """Test scanning module with policy drift violations."""
        service = ModuleGuardrailService()

        with tempfile.TemporaryDirectory() as tmpdir:
            module_dir = Path(tmpdir) / "test-module"
            module_dir.mkdir()

            # Create file with policy drift
            bad_file = module_dir / "permissions.py"
            bad_file.write_text(
                """
def check_permission(user: str) -> bool:
    return True  # Bypass permission check
"""
            )

            violations = service.scan_module("test-module", str(module_dir))
            assert len(violations) > 0
            assert any(
                v.violation_type == GuardrailViolationType.POLICY_DRIFT for v in violations
            )

    def test_record_violation(self) -> None:
        """Test recording a violation."""
        service = ModuleGuardrailService()

        violation = service.record_violation(
            tenant_id="tenant-1",
            module_name="test-module",
            violation_type=GuardrailViolationType.AUTH_DRIFT,
            violation_details={"pattern": "def login", "line": 10},
            code_location="test-module/auth.py:10",
            severity="critical",
        )

        assert violation is not None
        assert violation.tenant_id == "tenant-1"
        assert violation.module_name == "test-module"
        assert violation.status == "detected"

    def test_check_module_compliance(self) -> None:
        """Test checking module compliance."""
        service = ModuleGuardrailService()

        with tempfile.TemporaryDirectory() as tmpdir:
            module_dir = Path(tmpdir) / "test-module"
            module_dir.mkdir()

            clean_file = module_dir / "models.py"
            clean_file.write_text("def create_item(): pass\n")

            is_compliant, violations = service.check_module_compliance(
                "test-module", str(module_dir)
            )

            assert is_compliant is True
            assert len(violations) == 0

    def test_check_module_compliance_with_violations(self) -> None:
        """Test checking module compliance with violations."""
        service = ModuleGuardrailService()

        with tempfile.TemporaryDirectory() as tmpdir:
            module_dir = Path(tmpdir) / "test-module"
            module_dir.mkdir()

            bad_file = module_dir / "auth.py"
            bad_file.write_text("def login(): pass\n")

            is_compliant, violations = service.check_module_compliance(
                "test-module", str(module_dir)
            )

            assert is_compliant is False
            assert len(violations) > 0

    def test_get_violations(self) -> None:
        """Test getting violations."""
        service = ModuleGuardrailService()

        # Create violations
        GuardrailViolation.objects.create(
            tenant_id="tenant-1",
            module_name="module1",
            violation_type=GuardrailViolationType.AUTH_DRIFT,
            severity="critical",
            status="detected",
        )

        GuardrailViolation.objects.create(
            tenant_id="tenant-1",
            module_name="module2",
            violation_type=GuardrailViolationType.POLICY_DRIFT,
            severity="high",
            status="detected",
        )

        # Get all violations
        violations = service.get_violations()
        assert len(violations) >= 2

        # Filter by tenant
        tenant_violations = service.get_violations(tenant_id="tenant-1")
        assert len(tenant_violations) >= 2

        # Filter by module
        module_violations = service.get_violations(module_name="module1")
        assert len(module_violations) >= 1

        # Filter by type
        auth_violations = service.get_violations(
            violation_type=GuardrailViolationType.AUTH_DRIFT
        )
        assert len(auth_violations) >= 1

    def test_resolve_violation(self) -> None:
        """Test resolving a violation."""
        service = ModuleGuardrailService()

        violation = GuardrailViolation.objects.create(
            tenant_id="tenant-1",
            module_name="test-module",
            violation_type=GuardrailViolationType.AUTH_DRIFT,
            severity="critical",
            status="detected",
        )

        resolved = service.resolve_violation(
            violation_id=violation.id,
            resolved_by="user-1",
            resolution_notes="False positive",
            is_false_positive=True,
        )

        assert resolved.status == "false_positive"
        assert resolved.resolved_by == "user-1"
        assert resolved.resolved_at is not None

    def test_resolve_violation_not_found(self) -> None:
        """Test resolving non-existent violation fails."""
        service = ModuleGuardrailService()

        with pytest.raises(GuardrailError, match="not found"):
            service.resolve_violation(
                violation_id="non-existent",
                resolved_by="user-1",
                resolution_notes="Test",
            )

    def test_block_module_on_violation(self) -> None:
        """Test blocking module on violations."""
        service = ModuleGuardrailService()

        # Create critical violation
        GuardrailViolation.objects.create(
            tenant_id="tenant-1",
            module_name="test-module",
            violation_type=GuardrailViolationType.AUTH_DRIFT,
            severity="critical",
            status="detected",
        )

        should_block = service.block_module_on_violation("test-module", "tenant-1")
        assert should_block is True

    def test_block_module_no_violations(self) -> None:
        """Test module not blocked when no violations."""
        service = ModuleGuardrailService()

        should_block = service.block_module_on_violation("clean-module", "tenant-1")
        assert should_block is False

    def test_block_module_multiple_high_severity(self) -> None:
        """Test module blocked with multiple high-severity violations."""
        service = ModuleGuardrailService()

        # Create 3 high-severity violations
        for i in range(3):
            GuardrailViolation.objects.create(
                tenant_id="tenant-1",
                module_name="test-module",
                violation_type=GuardrailViolationType.POLICY_DRIFT,
                severity="high",
                status="detected",
            )

        should_block = service.block_module_on_violation("test-module", "tenant-1")
        assert should_block is True

