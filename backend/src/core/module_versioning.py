"""Module Versioning & Compatibility.

Implements version comparison and compatibility checking for modules.
Task: 501.1 - Module Manifest Schema & Signing
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from enum import Enum


class VersionComparison(str, Enum):
    """Version comparison operators."""

    EQUAL = "=="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="


class VersionError(Exception):
    """Version error."""

    pass


class Version:
    """Semantic version representation.

    Supports MAJOR.MINOR.PATCH[-PRERELEASE] format.
    """

    VERSION_PATTERN = re.compile(
        r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9]+))?$"
    )

    def __init__(self, version_str: str) -> None:
        """Initialize version from string.

        Args:
            version_str: Version string (e.g., "1.2.3" or "1.2.3-alpha").

        Raises:
            VersionError: If version string is invalid.
        """
        match = self.VERSION_PATTERN.match(version_str)
        if not match:
            raise VersionError(f"Invalid version format: {version_str}")

        self.major = int(match.group(1))
        self.minor = int(match.group(2))
        self.patch = int(match.group(3))
        self.prerelease = match.group(4) if match.group(4) else None
        self.version_str = version_str

    def __str__(self) -> str:
        """Return version string."""
        return self.version_str

    def __repr__(self) -> str:
        """Return version representation."""
        return f"Version('{self.version_str}')"

    def __eq__(self, other: object) -> bool:
        """Check equality."""
        if not isinstance(other, Version):
            return False
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __lt__(self, other: Version) -> bool:
        """Check less than."""
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch
        # Prerelease versions are less than release versions
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        if self.prerelease and other.prerelease:
            return self.prerelease < other.prerelease
        return False

    def __le__(self, other: Version) -> bool:
        """Check less than or equal."""
        return self == other or self < other

    def __gt__(self, other: Version) -> bool:
        """Check greater than."""
        return not self <= other

    def __ge__(self, other: Version) -> bool:
        """Check greater than or equal."""
        return not self < other

    def compare(self, other: Version) -> int:
        """Compare versions.

        Returns:
            -1 if self < other, 0 if self == other, 1 if self > other.
        """
        if self < other:
            return -1
        if self > other:
            return 1
        return 0

    def satisfies(self, constraint: str) -> bool:
        """Check if version satisfies constraint.

        Args:
            constraint: Version constraint (e.g., ">=1.0.0", "==1.2.3", "<2.0.0").

        Returns:
            True if version satisfies constraint.

        Raises:
            VersionError: If constraint format is invalid.
        """
        constraint = constraint.strip()

        # Parse constraint
        if constraint.startswith(">="):
            operator = VersionComparison.GREATER_EQUAL
            version_str = constraint[2:].strip()
        elif constraint.startswith("<="):
            operator = VersionComparison.LESS_EQUAL
            version_str = constraint[2:].strip()
        elif constraint.startswith(">"):
            operator = VersionComparison.GREATER_THAN
            version_str = constraint[1:].strip()
        elif constraint.startswith("<"):
            operator = VersionComparison.LESS_THAN
            version_str = constraint[1:].strip()
        elif constraint.startswith("=="):
            operator = VersionComparison.EQUAL
            version_str = constraint[2:].strip()
        else:
            # Default to >= if no operator
            operator = VersionComparison.GREATER_EQUAL
            version_str = constraint

        try:
            required_version = Version(version_str)
        except VersionError as e:
            raise VersionError(f"Invalid version in constraint: {e}") from e

        if operator == VersionComparison.EQUAL:
            return self == required_version
        elif operator == VersionComparison.GREATER_THAN:
            return self > required_version
        elif operator == VersionComparison.LESS_THAN:
            return self < required_version
        elif operator == VersionComparison.GREATER_EQUAL:
            return self >= required_version
        elif operator == VersionComparison.LESS_EQUAL:
            return self <= required_version
        else:
            raise VersionError(f"Unsupported operator: {operator}")

    @staticmethod
    def parse_constraint(constraint: str) -> Tuple[str, Version]:
        """Parse version constraint.

        Args:
            constraint: Version constraint string.

        Returns:
            Tuple of (operator, version).

        Raises:
            VersionError: If constraint format is invalid.
        """
        constraint = constraint.strip()

        if constraint.startswith(">="):
            return (VersionComparison.GREATER_EQUAL, Version(constraint[2:].strip()))
        elif constraint.startswith("<="):
            return (VersionComparison.LESS_EQUAL, Version(constraint[2:].strip()))
        elif constraint.startswith(">"):
            return (VersionComparison.GREATER_THAN, Version(constraint[1:].strip()))
        elif constraint.startswith("<"):
            return (VersionComparison.LESS_THAN, Version(constraint[1:].strip()))
        elif constraint.startswith("=="):
            return (VersionComparison.EQUAL, Version(constraint[2:].strip()))
        else:
            # Default to >= if no operator
            return (VersionComparison.GREATER_EQUAL, Version(constraint))


class CompatibilityChecker:
    """Module compatibility checker.

    Checks version compatibility between modules.
    """

    def check_dependency(
        self, module_version: Version, dependency_constraint: str
    ) -> bool:
        """Check if module version satisfies dependency constraint.

        Args:
            module_version: Installed module version.
            dependency_constraint: Dependency version constraint.

        Returns:
            True if compatible.
        """
        return module_version.satisfies(dependency_constraint)

    def check_compatibility(
        self, installed_version: Version, required_constraint: str
    ) -> Tuple[bool, Optional[str]]:
        """Check compatibility between installed and required versions.

        Args:
            installed_version: Installed module version.
            required_constraint: Required version constraint.

        Returns:
            Tuple of (is_compatible, error_message).
        """
        try:
            is_compatible = installed_version.satisfies(required_constraint)
            if not is_compatible:
                return (
                    False,
                    f"Version {installed_version} does not satisfy constraint {required_constraint}",
                )
            return True, None
        except VersionError as e:
            return False, str(e)

    def is_backward_compatible(
        self, old_version: Version, new_version: Version
    ) -> bool:
        """Check if new version is backward compatible with old version.

        Args:
            old_version: Old version.
            new_version: New version.

        Returns:
            True if backward compatible (same major version).
        """
        return old_version.major == new_version.major

    def is_upgrade_safe(
        self, current_version: Version, target_version: Version
    ) -> bool:
        """Check if upgrade is safe.

        Args:
            current_version: Current installed version.
            target_version: Target version to upgrade to.

        Returns:
            True if upgrade is safe (backward compatible or patch/minor upgrade).
        """
        # Same major version is safe
        if current_version.major == target_version.major:
            return True

        # Major version upgrade requires explicit approval
        return False


# Global compatibility checker instance
compatibility_checker = CompatibilityChecker()
