"""Module Manifest Schema Definition.

Defines the schema for module manifests and validation logic.
Task: 501.1 - Module Manifest Schema & Signing
"""

from __future__ import annotations

import yaml
import hashlib
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re

from django.core.exceptions import ValidationError


class ModuleType(str, Enum):
    """Module type enumeration."""

    CORE = "core"
    DOMAIN = "domain"
    INDUSTRY = "industry"
    INTEGRATION = "integration"
    FOUNDATION = "foundation"


class ModuleLifecycle(str, Enum):
    """Module lifecycle enumeration."""

    CORE = "core"  # Always present, cannot be uninstalled
    MANAGED = "managed"  # Can be installed/uninstalled
    INTEGRATION = "integration"  # External integration modules


@dataclass
class ModuleManifest:
    """Module manifest data structure.

    Represents a validated module manifest.
    """

    name: str
    version: str
    description: str
    type: ModuleType
    lifecycle: ModuleLifecycle
    dependencies: List[Dict[str, str]] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    sod_actions: List[str] = field(default_factory=list)
    search_indexes: List[str] = field(default_factory=list)
    ai_tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    signature: Optional[str] = None
    signature_algorithm: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "type": self.type.value,
            "lifecycle": self.lifecycle.value,
            "dependencies": self.dependencies,
            "permissions": self.permissions,
            "sod_actions": self.sod_actions,
            "search_indexes": self.search_indexes,
            "ai_tools": self.ai_tools,
            "metadata": self.metadata,
            "signature": self.signature,
            "signature_algorithm": self.signature_algorithm,
        }

    def to_yaml(self) -> str:
        """Convert manifest to YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False)

    def get_content_hash(self) -> str:
        """Get content hash for signing."""
        content = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "type": self.type.value,
            "lifecycle": self.lifecycle.value,
            "dependencies": self.dependencies,
            "permissions": self.permissions,
            "sod_actions": self.sod_actions,
            "search_indexes": self.search_indexes,
            "ai_tools": self.ai_tools,
            "metadata": self.metadata,
        }
        content_json = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_json.encode()).hexdigest()


class ManifestValidationError(ValidationError):
    """Manifest validation error."""

    pass


class ManifestValidator:
    """Manifest validator.

    Validates module manifests against schema.
    """

    # Version pattern: MAJOR.MINOR.PATCH (semantic versioning)
    VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$")

    # Module name pattern: lowercase, alphanumeric, hyphens, underscores
    NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")

    # Permission pattern: module.resource:action
    PERMISSION_PATTERN = re.compile(r"^[a-z0-9_-]+\.[a-z0-9_-]+:[a-z0-9_-]+$")

    # Dependency pattern: module-name >=version or module-name ==version
    DEPENDENCY_PATTERN = re.compile(
        r"^[a-z0-9_-]+\s*(>=|<=|==|>|<)\s*\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$"
    )

    REQUIRED_FIELDS = [
        "name",
        "version",
        "description",
        "type",
        "lifecycle",
    ]

    def validate(self, manifest_data: Dict[str, Any]) -> ModuleManifest:
        """Validate manifest data and return ModuleManifest.

        Args:
            manifest_data: Raw manifest dictionary.

        Returns:
            Validated ModuleManifest instance.

        Raises:
            ManifestValidationError: If validation fails.
        """
        errors: List[str] = []

        # Check required fields
        for field_name in self.REQUIRED_FIELDS:
            if field_name not in manifest_data:
                errors.append(f"Missing required field: {field_name}")

        if errors:
            raise ManifestValidationError("; ".join(errors))

        # Validate name
        name = manifest_data.get("name", "")
        if not self.NAME_PATTERN.match(name):
            errors.append(
                f"Invalid module name '{name}': must be lowercase alphanumeric with hyphens/underscores"
            )

        # Validate version
        version = manifest_data.get("version", "")
        if not self.VERSION_PATTERN.match(version):
            errors.append(
                f"Invalid version '{version}': must be semantic version (MAJOR.MINOR.PATCH)"
            )

        # Validate type
        type_str = manifest_data.get("type", "")
        try:
            module_type = ModuleType(type_str)
        except ValueError:
            errors.append(
                f"Invalid type '{type_str}': must be one of {[t.value for t in ModuleType]}"
            )

        # Validate lifecycle
        lifecycle_str = manifest_data.get("lifecycle", "")
        try:
            lifecycle = ModuleLifecycle(lifecycle_str)
        except ValueError:
            errors.append(
                f"Invalid lifecycle '{lifecycle_str}': must be one of {[l.value for l in ModuleLifecycle]}"
            )

        # Validate dependencies
        dependencies = manifest_data.get("dependencies", [])
        if not isinstance(dependencies, list):
            errors.append("Dependencies must be a list")
        else:
            for dep in dependencies:
                if isinstance(dep, str):
                    # Simple string dependency: "module-name >=1.0"
                    if not self.DEPENDENCY_PATTERN.match(dep):
                        errors.append(f"Invalid dependency format: {dep}")
                elif isinstance(dep, dict):
                    # Dict dependency: {"name": "module-name", "version": ">=1.0"}
                    if "name" not in dep:
                        errors.append("Dependency dict must have 'name' field")
                else:
                    errors.append(f"Invalid dependency type: {type(dep)}")

        # Validate permissions
        permissions = manifest_data.get("permissions", [])
        if not isinstance(permissions, list):
            errors.append("Permissions must be a list")
        else:
            for perm in permissions:
                if not isinstance(perm, str):
                    errors.append(f"Permission must be a string: {perm}")
                elif not self.PERMISSION_PATTERN.match(perm):
                    errors.append(
                        f"Invalid permission format '{perm}': must be 'module.resource:action'"
                    )

        # Validate SoD actions
        sod_actions = manifest_data.get("sod_actions", [])
        if not isinstance(sod_actions, list):
            errors.append("SoD actions must be a list")
        else:
            for action in sod_actions:
                if not isinstance(action, str):
                    errors.append(f"SoD action must be a string: {action}")
                elif not self.PERMISSION_PATTERN.match(action):
                    errors.append(
                        f"Invalid SoD action format '{action}': must be 'module.resource:action'"
                    )

        # Validate search indexes
        search_indexes = manifest_data.get("search_indexes", [])
        if not isinstance(search_indexes, list):
            errors.append("Search indexes must be a list")
        else:
            for index in search_indexes:
                if not isinstance(index, str):
                    errors.append(f"Search index must be a string: {index}")

        # Validate AI tools
        ai_tools = manifest_data.get("ai_tools", [])
        if not isinstance(ai_tools, list):
            errors.append("AI tools must be a list")
        else:
            for tool in ai_tools:
                if not isinstance(tool, str):
                    errors.append(f"AI tool must be a string: {tool}")

        if errors:
            raise ManifestValidationError("; ".join(errors))

        # Create ModuleManifest instance
        return ModuleManifest(
            name=name,
            version=version,
            description=manifest_data.get("description", ""),
            type=module_type,
            lifecycle=lifecycle,
            dependencies=dependencies,
            permissions=permissions,
            sod_actions=sod_actions,
            search_indexes=search_indexes,
            ai_tools=ai_tools,
            metadata=manifest_data.get("metadata", {}),
            signature=manifest_data.get("signature"),
            signature_algorithm=manifest_data.get("signature_algorithm"),
        )

    def validate_from_yaml(self, yaml_content: str) -> ModuleManifest:
        """Validate manifest from YAML string.

        Args:
            yaml_content: YAML content string.

        Returns:
            Validated ModuleManifest instance.

        Raises:
            ManifestValidationError: If validation fails.
        """
        try:
            manifest_data = yaml.safe_load(yaml_content)
            if not isinstance(manifest_data, dict):
                raise ManifestValidationError("Manifest must be a YAML object")
            return self.validate(manifest_data)
        except yaml.YAMLError as e:
            raise ManifestValidationError(f"Invalid YAML: {e}") from e


# Global validator instance
manifest_validator = ManifestValidator()

