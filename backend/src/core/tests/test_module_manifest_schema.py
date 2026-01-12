"""Tests for Module Manifest Schema.

Task: 501.1 - Module Manifest Schema & Signing
"""

from __future__ import annotations

import pytest
import yaml

from ..module_manifest_schema import (
    ManifestValidationError,
    ManifestValidator,
    ModuleLifecycle,
    ModuleManifest,
    ModuleType,
    manifest_validator,
)


class TestModuleManifest:
    """Test ModuleManifest dataclass."""

    def test_create_manifest(self) -> None:
        """Test creating a manifest."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        assert manifest.name == "test-module"
        assert manifest.version == "1.0.0"
        assert manifest.type == ModuleType.DOMAIN
        assert manifest.lifecycle == ModuleLifecycle.MANAGED

    def test_to_dict(self) -> None:
        """Test converting manifest to dictionary."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
            dependencies=[{"name": "core-identity", "version": ">=1.0.0"}],
            permissions=["test.resource:view"],
        )

        manifest_dict = manifest.to_dict()

        assert manifest_dict["name"] == "test-module"
        assert manifest_dict["version"] == "1.0.0"
        assert manifest_dict["type"] == "domain"
        assert manifest_dict["lifecycle"] == "managed"
        assert len(manifest_dict["dependencies"]) == 1
        assert len(manifest_dict["permissions"]) == 1

    def test_to_yaml(self) -> None:
        """Test converting manifest to YAML."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        yaml_str = manifest.to_yaml()
        parsed = yaml.safe_load(yaml_str)

        assert parsed["name"] == "test-module"
        assert parsed["version"] == "1.0.0"

    def test_get_content_hash(self) -> None:
        """Test getting content hash."""
        manifest1 = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        manifest2 = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        # Same content should produce same hash
        assert manifest1.get_content_hash() == manifest2.get_content_hash()

        # Different content should produce different hash
        manifest3 = ModuleManifest(
            name="test-module",
            version="1.0.1",  # Different version
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        assert manifest1.get_content_hash() != manifest3.get_content_hash()


class TestManifestValidator:
    """Test ManifestValidator."""

    def test_validate_valid_manifest(self) -> None:
        """Test validating a valid manifest."""
        manifest_data = {
            "name": "test-module",
            "version": "1.0.0",
            "description": "Test module",
            "type": "domain",
            "lifecycle": "managed",
        }

        validator = ManifestValidator()
        manifest = validator.validate(manifest_data)

        assert manifest.name == "test-module"
        assert manifest.version == "1.0.0"
        assert manifest.type == ModuleType.DOMAIN

    def test_validate_missing_required_field(self) -> None:
        """Test validation fails with missing required field."""
        manifest_data = {
            "name": "test-module",
            # Missing version
            "description": "Test module",
            "type": "domain",
            "lifecycle": "managed",
        }

        validator = ManifestValidator()
        with pytest.raises(ManifestValidationError):
            validator.validate(manifest_data)

    def test_validate_invalid_name(self) -> None:
        """Test validation fails with invalid name."""
        manifest_data = {
            "name": "Test-Module",  # Invalid: uppercase
            "version": "1.0.0",
            "description": "Test module",
            "type": "domain",
            "lifecycle": "managed",
        }

        validator = ManifestValidator()
        with pytest.raises(ManifestValidationError):
            validator.validate(manifest_data)

    def test_validate_invalid_version(self) -> None:
        """Test validation fails with invalid version."""
        manifest_data = {
            "name": "test-module",
            "version": "1.0",  # Invalid: missing patch
            "description": "Test module",
            "type": "domain",
            "lifecycle": "managed",
        }

        validator = ManifestValidator()
        with pytest.raises(ManifestValidationError):
            validator.validate(manifest_data)

    def test_validate_invalid_type(self) -> None:
        """Test validation fails with invalid type."""
        manifest_data = {
            "name": "test-module",
            "version": "1.0.0",
            "description": "Test module",
            "type": "invalid-type",
            "lifecycle": "managed",
        }

        validator = ManifestValidator()
        with pytest.raises(ManifestValidationError):
            validator.validate(manifest_data)

    def test_validate_dependencies(self) -> None:
        """Test validating dependencies."""
        manifest_data = {
            "name": "test-module",
            "version": "1.0.0",
            "description": "Test module",
            "type": "domain",
            "lifecycle": "managed",
            "dependencies": ["core-identity >=1.0.0"],
        }

        validator = ManifestValidator()
        manifest = validator.validate(manifest_data)

        assert len(manifest.dependencies) == 1

    def test_validate_permissions(self) -> None:
        """Test validating permissions."""
        manifest_data = {
            "name": "test-module",
            "version": "1.0.0",
            "description": "Test module",
            "type": "domain",
            "lifecycle": "managed",
            "permissions": ["test.resource:view", "test.resource:create"],
        }

        validator = ManifestValidator()
        manifest = validator.validate(manifest_data)

        assert len(manifest.permissions) == 2

    def test_validate_invalid_permission_format(self) -> None:
        """Test validation fails with invalid permission format."""
        manifest_data = {
            "name": "test-module",
            "version": "1.0.0",
            "description": "Test module",
            "type": "domain",
            "lifecycle": "managed",
            "permissions": ["invalid-permission"],  # Invalid format
        }

        validator = ManifestValidator()
        with pytest.raises(ManifestValidationError):
            validator.validate(manifest_data)

    def test_validate_from_yaml(self) -> None:
        """Test validating from YAML string."""
        yaml_content = """
name: test-module
version: 1.0.0
description: Test module
type: domain
lifecycle: managed
"""

        validator = ManifestValidator()
        manifest = validator.validate_from_yaml(yaml_content)

        assert manifest.name == "test-module"
        assert manifest.version == "1.0.0"

    def test_validate_from_yaml_invalid(self) -> None:
        """Test validation fails with invalid YAML."""
        yaml_content = "invalid: yaml: content: ["

        validator = ManifestValidator()
        with pytest.raises(ManifestValidationError):
            validator.validate_from_yaml(yaml_content)
