"""Tests for Module Versioning.

Task: 501.1 - Module Manifest Schema & Signing
"""

from __future__ import annotations

import pytest

from ..module_versioning import (
    Version,
    VersionError,
    VersionComparison,
    CompatibilityChecker,
    compatibility_checker,
)


class TestVersion:
    """Test Version class."""

    def test_create_version(self) -> None:
        """Test creating a version."""
        version = Version("1.2.3")

        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease is None

    def test_create_version_with_prerelease(self) -> None:
        """Test creating version with prerelease."""
        version = Version("1.2.3-alpha")

        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease == "alpha"

    def test_create_version_invalid(self) -> None:
        """Test creating version with invalid format."""
        with pytest.raises(VersionError):
            Version("1.2")  # Missing patch

    def test_version_equality(self) -> None:
        """Test version equality."""
        v1 = Version("1.2.3")
        v2 = Version("1.2.3")
        v3 = Version("1.2.4")

        assert v1 == v2
        assert v1 != v3

    def test_version_comparison(self) -> None:
        """Test version comparison."""
        v1 = Version("1.2.3")
        v2 = Version("1.2.4")
        v3 = Version("2.0.0")

        assert v1 < v2
        assert v2 > v1
        assert v1 <= v2
        assert v2 >= v1
        assert v1 < v3

    def test_version_prerelease_comparison(self) -> None:
        """Test prerelease version comparison."""
        v1 = Version("1.2.3-alpha")
        v2 = Version("1.2.3-beta")
        v3 = Version("1.2.3")

        assert v1 < v2
        assert v1 < v3  # Prerelease < release
        assert v3 > v1

    def test_satisfies_equal(self) -> None:
        """Test version satisfies == constraint."""
        version = Version("1.2.3")

        assert version.satisfies("==1.2.3") is True
        assert version.satisfies("==1.2.4") is False

    def test_satisfies_greater_equal(self) -> None:
        """Test version satisfies >= constraint."""
        version = Version("1.2.3")

        assert version.satisfies(">=1.2.3") is True
        assert version.satisfies(">=1.2.2") is True
        assert version.satisfies(">=1.2.4") is False

    def test_satisfies_less_equal(self) -> None:
        """Test version satisfies <= constraint."""
        version = Version("1.2.3")

        assert version.satisfies("<=1.2.3") is True
        assert version.satisfies("<=1.2.4") is True
        assert version.satisfies("<=1.2.2") is False

    def test_satisfies_greater_than(self) -> None:
        """Test version satisfies > constraint."""
        version = Version("1.2.3")

        assert version.satisfies(">1.2.2") is True
        assert version.satisfies(">1.2.3") is False

    def test_satisfies_less_than(self) -> None:
        """Test version satisfies < constraint."""
        version = Version("1.2.3")

        assert version.satisfies("<1.2.4") is True
        assert version.satisfies("<1.2.3") is False

    def test_satisfies_default_operator(self) -> None:
        """Test version satisfies constraint without operator (defaults to >=)."""
        version = Version("1.2.3")

        assert version.satisfies("1.2.2") is True  # Defaults to >=
        assert version.satisfies("1.2.3") is True
        assert version.satisfies("1.2.4") is False

    def test_satisfies_invalid_constraint(self) -> None:
        """Test satisfies fails with invalid constraint."""
        version = Version("1.2.3")

        with pytest.raises(VersionError):
            version.satisfies("invalid")

    def test_compare(self) -> None:
        """Test compare method."""
        v1 = Version("1.2.3")
        v2 = Version("1.2.4")
        v3 = Version("1.2.3")

        assert v1.compare(v2) == -1
        assert v2.compare(v1) == 1
        assert v1.compare(v3) == 0

    def test_parse_constraint(self) -> None:
        """Test parsing version constraint."""
        operator, version = Version.parse_constraint(">=1.2.3")

        assert operator == VersionComparison.GREATER_EQUAL
        assert version == Version("1.2.3")

        operator, version = Version.parse_constraint("==1.0.0")
        assert operator == VersionComparison.EQUAL
        assert version == Version("1.0.0")


class TestCompatibilityChecker:
    """Test CompatibilityChecker."""

    def test_check_dependency(self) -> None:
        """Test checking dependency."""
        checker = CompatibilityChecker()
        version = Version("1.2.3")

        assert checker.check_dependency(version, ">=1.0.0") is True
        assert checker.check_dependency(version, ">=2.0.0") is False

    def test_check_compatibility(self) -> None:
        """Test checking compatibility."""
        checker = CompatibilityChecker()
        version = Version("1.2.3")

        is_compatible, error = checker.check_compatibility(version, ">=1.0.0")
        assert is_compatible is True
        assert error is None

        is_compatible, error = checker.check_compatibility(version, ">=2.0.0")
        assert is_compatible is False
        assert error is not None

    def test_is_backward_compatible(self) -> None:
        """Test checking backward compatibility."""
        checker = CompatibilityChecker()

        v1 = Version("1.2.3")
        v2 = Version("1.3.0")
        v3 = Version("2.0.0")

        assert checker.is_backward_compatible(v1, v2) is True  # Same major
        assert checker.is_backward_compatible(v1, v3) is False  # Different major

    def test_is_upgrade_safe(self) -> None:
        """Test checking upgrade safety."""
        checker = CompatibilityChecker()

        v1 = Version("1.2.3")
        v2 = Version("1.3.0")
        v3 = Version("2.0.0")

        assert checker.is_upgrade_safe(v1, v2) is True  # Same major
        assert checker.is_upgrade_safe(v1, v3) is False  # Major upgrade

