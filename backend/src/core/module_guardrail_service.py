"""Module Guardrail Service.

Implements guardrails preventing module-level auth/policy drift.
Task: 503.2 - Module Guardrails
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from .module_guardrail_models import GuardrailViolation, GuardrailViolationType

logger = logging.getLogger(__name__)


class GuardrailError(Exception):
    """Guardrail error."""

    pass


class ModuleGuardrailService:
    """Module guardrail service.

    Detects and prevents module-level auth/policy drift.
    """

    # Forbidden patterns for auth drift detection
    AUTH_FORBIDDEN_PATTERNS = [
        (r"def\s+login\s*\(", "login function"),
        (r"def\s+logout\s*\(", "logout function"),
        (r"def\s+authenticate\s*\(", "authenticate function"),
        (r"JWT|jwt|JsonWebToken", "JWT token usage"),
        (r"session\.create|session\.new", "session creation"),
        (r"credential|password|secret.*=.*input", "credential handling"),
        (r"oauth|OAuth|saml|SAML|federation", "identity federation"),
        (r"@.*auth|@.*login|@.*authenticate", "auth decorator"),
    ]

    # Forbidden patterns for policy drift detection
    POLICY_FORBIDDEN_PATTERNS = [
        (r"def\s+check_permission\s*\(", "permission check bypass"),
        (r"def\s+check_policy\s*\(", "policy check bypass"),
        (r"bypass.*permission|bypass.*policy", "permission/policy bypass"),
        (r"skip.*auth|skip.*permission", "auth/permission skip"),
    ]

    def __init__(self) -> None:
        """Initialize guardrail service."""
        self.auth_patterns = [
            (re.compile(pattern, re.IGNORECASE), description) for pattern, description in self.AUTH_FORBIDDEN_PATTERNS
        ]
        self.policy_patterns = [
            (re.compile(pattern, re.IGNORECASE), description) for pattern, description in self.POLICY_FORBIDDEN_PATTERNS
        ]

    def scan_module(self, module_name: str, module_path: Optional[str] = None) -> List[GuardrailViolation]:
        """Scan module for guardrail violations.

        Args:
            module_name: Module name.
            module_path: Optional module path (if None, uses default path).

        Returns:
            List of detected GuardrailViolation instances.
        """
        violations: List[GuardrailViolation] = []

        if not module_path:
            # Default module path
            module_path = f"backend/src/modules/{module_name}"

        module_dir = Path(module_path)
        if not module_dir.exists():
            logger.warning(f"Module path {module_path} does not exist")
            return violations

        # Scan Python files
        python_files = list(module_dir.rglob("*.py"))
        for py_file in python_files:
            # Skip test files and migrations
            if "test" in str(py_file) or "migration" in str(py_file):
                continue

            try:
                file_violations = self._scan_file(py_file, module_name)
                violations.extend(file_violations)
            except Exception as e:
                logger.error(f"Error scanning file {py_file}: {e}", exc_info=True)

        return violations

    def _scan_file(self, file_path: Path, module_name: str) -> List[GuardrailViolation]:
        """Scan a single file for violations.

        Args:
            file_path: File path.
            module_name: Module name.

        Returns:
            List of GuardrailViolation instances.
        """
        violations: List[GuardrailViolation] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return violations

        # Check for auth drift
        auth_violations = self._detect_auth_drift(content, lines, file_path, module_name)
        violations.extend(auth_violations)

        # Check for policy drift
        policy_violations = self._detect_policy_drift(content, lines, file_path, module_name)
        violations.extend(policy_violations)

        return violations

    def _detect_auth_drift(
        self, content: str, lines: List[str], file_path: Path, module_name: str
    ) -> List[GuardrailViolation]:
        """Detect auth drift violations.

        Args:
            content: File content.
            lines: File lines.
            file_path: File path.
            module_name: Module name.

        Returns:
            List of GuardrailViolation instances.
        """
        violations: List[GuardrailViolation] = []

        for pattern, description in self.auth_patterns:
            matches = pattern.finditer(content)
            for match in matches:
                # Find line number
                line_num = content[: match.start()].count("\n") + 1
                line_content = lines[line_num - 1] if line_num <= len(lines) else ""

                violation = GuardrailViolation(
                    tenant_id="platform",  # Platform-level scan
                    module_name=module_name,
                    violation_type=GuardrailViolationType.AUTH_DRIFT,
                    severity="critical",
                    detected_by="guardrail_scanner",
                    violation_details={
                        "pattern": pattern.pattern,
                        "description": description,
                        "match": match.group(),
                        "line_content": line_content.strip(),
                    },
                    code_location=f"{file_path}:{line_num}",
                    status="detected",
                )
                violations.append(violation)

        return violations

    def _detect_policy_drift(
        self, content: str, lines: List[str], file_path: Path, module_name: str
    ) -> List[GuardrailViolation]:
        """Detect policy drift violations.

        Args:
            content: File content.
            lines: File lines.
            file_path: File path.
            module_name: Module name.

        Returns:
            List of GuardrailViolation instances.
        """
        violations: List[GuardrailViolation] = []

        for pattern, description in self.policy_patterns:
            matches = pattern.finditer(content)
            for match in matches:
                # Find line number
                line_num = content[: match.start()].count("\n") + 1
                line_content = lines[line_num - 1] if line_num <= len(lines) else ""

                violation = GuardrailViolation(
                    tenant_id="platform",  # Platform-level scan
                    module_name=module_name,
                    violation_type=GuardrailViolationType.POLICY_DRIFT,
                    severity="high",
                    detected_by="guardrail_scanner",
                    violation_details={
                        "pattern": pattern.pattern,
                        "description": description,
                        "match": match.group(),
                        "line_content": line_content.strip(),
                    },
                    code_location=f"{file_path}:{line_num}",
                    status="detected",
                )
                violations.append(violation)

        return violations

    @transaction.atomic
    def record_violation(
        self,
        tenant_id: str,
        module_name: str,
        violation_type: str,
        violation_details: Dict[str, Any],
        code_location: Optional[str] = None,
        severity: str = "high",
    ) -> GuardrailViolation:
        """Record a guardrail violation.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            violation_type: Violation type.
            violation_details: Violation details.
            code_location: Optional code location.
            severity: Violation severity.

        Returns:
            Created GuardrailViolation instance.
        """
        violation = GuardrailViolation.objects.create(
            tenant_id=tenant_id,
            module_name=module_name,
            violation_type=violation_type,
            severity=severity,
            violation_details=violation_details,
            code_location=code_location,
            status="detected",
        )

        logger.warning(f"Guardrail violation detected: {violation_type} in {module_name} " f"(Tenant: {tenant_id})")

        return violation

    def check_module_compliance(
        self, module_name: str, module_path: Optional[str] = None
    ) -> Tuple[bool, List[GuardrailViolation]]:
        """Check module compliance with guardrails.

        Args:
            module_name: Module name.
            module_path: Optional module path.

        Returns:
            Tuple of (is_compliant, violations).
        """
        violations = self.scan_module(module_name, module_path)

        # Record violations
        for violation in violations:
            violation.save()

        is_compliant = len(violations) == 0

        return is_compliant, violations

    def get_violations(
        self,
        tenant_id: Optional[str] = None,
        module_name: Optional[str] = None,
        violation_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[GuardrailViolation]:
        """Get guardrail violations.

        Args:
            tenant_id: Optional tenant ID filter.
            module_name: Optional module name filter.
            violation_type: Optional violation type filter.
            status: Optional status filter.

        Returns:
            List of GuardrailViolation instances.
        """
        query = GuardrailViolation.objects.all()

        if tenant_id:
            query = query.filter(tenant_id=tenant_id)

        if module_name:
            query = query.filter(module_name=module_name)

        if violation_type:
            query = query.filter(violation_type=violation_type)

        if status:
            query = query.filter(status=status)

        return list(query.order_by("-detected_at"))

    @transaction.atomic
    def resolve_violation(
        self,
        violation_id: str,
        resolved_by: str,
        resolution_notes: str,
        is_false_positive: bool = False,
    ) -> GuardrailViolation:
        """Resolve a guardrail violation.

        Args:
            violation_id: Violation ID.
            resolved_by: User who resolved.
            resolution_notes: Resolution notes.
            is_false_positive: Whether this is a false positive.

        Returns:
            Updated GuardrailViolation instance.

        Raises:
            GuardrailError: If violation not found.
        """
        violation = GuardrailViolation.objects.filter(id=violation_id).first()
        if not violation:
            raise GuardrailError(f"Violation {violation_id} not found")

        violation.status = "false_positive" if is_false_positive else "resolved"
        violation.resolved_by = resolved_by
        violation.resolution_notes = resolution_notes
        violation.resolved_at = timezone.now()
        violation.save()

        logger.info(f"Resolved guardrail violation {violation_id}")

        return violation

    def block_module_on_violation(self, module_name: str, tenant_id: Optional[str] = None) -> bool:
        """Block module access due to violations.

        Args:
            module_name: Module name.
            tenant_id: Optional tenant ID (None = all tenants).

        Returns:
            True if module should be blocked.
        """
        query = GuardrailViolation.objects.filter(
            module_name=module_name,
            status__in=["detected", "blocked"],
            severity__in=["critical", "high"],
        )

        if tenant_id:
            query = query.filter(tenant_id=tenant_id)

        critical_violations = query.filter(severity="critical").count()
        high_violations = query.filter(severity="high").count()

        # Block if critical violations exist
        if critical_violations > 0:
            return True

        # Block if multiple high-severity violations
        if high_violations >= 3:
            return True

        return False


# Global guardrail service instance
module_guardrail_service = ModuleGuardrailService()
