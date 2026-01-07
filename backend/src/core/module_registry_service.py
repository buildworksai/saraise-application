"""Module Registry Service.

Implements module registry with dependency resolution and compatibility validation.
Task: 501.2 - Module Registry & Compatibility Validation
"""

from __future__ import annotations

import logging
import hashlib
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict, deque

from django.db import transaction, models

from .module_registry_models import (
    ModuleRegistryEntry,
    TenantModuleInstallation,
)
from .module_manifest_schema import (
    ModuleManifest,
    manifest_validator,
)
from .module_versioning import Version, compatibility_checker
from .module_signing import ManifestSigner, VerificationError

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Registry error."""

    pass


class DependencyResolutionError(RegistryError):
    """Dependency resolution error."""

    pass


class ModuleRegistryService:
    """Module registry service.

    Manages module registration, dependency resolution, and compatibility validation.
    """

    def __init__(self) -> None:
        """Initialize registry service."""
        self.validator = manifest_validator
        self.compatibility_checker = compatibility_checker
        self.signer = ManifestSigner()  # Should be configured with keys

    @transaction.atomic
    def register_module(
        self,
        manifest_yaml: str,
        signature: Optional[str] = None,
        signature_algorithm: Optional[str] = None,
        verify_signature: bool = True,
    ) -> ModuleRegistryEntry:
        """Register a module in the registry.

        Args:
            manifest_yaml: Manifest YAML content.
            signature: Optional manifest signature.
            signature_algorithm: Optional signature algorithm.
            verify_signature: Whether to verify signature.

        Returns:
            Created ModuleRegistryEntry instance.

        Raises:
            RegistryError: If registration fails.
        """
        # Validate manifest
        try:
            manifest = self.validator.validate_from_yaml(manifest_yaml)
        except Exception as e:
            raise RegistryError(f"Manifest validation failed: {e}") from e

        # Verify signature if provided
        if verify_signature and signature and signature_algorithm:
            try:
                # Remove signature from manifest for verification
                manifest_without_sig = ModuleManifest(
                    name=manifest.name,
                    version=manifest.version,
                    description=manifest.description,
                    type=manifest.type,
                    lifecycle=manifest.lifecycle,
                    dependencies=manifest.dependencies,
                    permissions=manifest.permissions,
                    sod_actions=manifest.sod_actions,
                    search_indexes=manifest.search_indexes,
                    ai_tools=manifest.ai_tools,
                    metadata=manifest.metadata,
                )
                if not self.signer.verify(
                    manifest_without_sig, signature, signature_algorithm
                ):
                    raise RegistryError("Manifest signature verification failed")
            except VerificationError as e:
                raise RegistryError(f"Signature verification failed: {e}") from e

        # Check if module already exists
        existing = ModuleRegistryEntry.objects.filter(
            name=manifest.name, version=manifest.version
        ).first()
        if existing:
            raise RegistryError(
                f"Module {manifest.name} v{manifest.version} already registered"
            )

        # Calculate manifest hash
        manifest_hash = hashlib.sha256(manifest_yaml.encode()).hexdigest()

        # Create registry entry
        entry = ModuleRegistryEntry.objects.create(
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            module_type=manifest.type.value,
            lifecycle=manifest.lifecycle.value,
            manifest_content=manifest_yaml,
            manifest_hash=manifest_hash,
            signature=signature,
            signature_algorithm=signature_algorithm,
            dependencies=manifest.dependencies,
            permissions=manifest.permissions,
            sod_actions=manifest.sod_actions,
            search_indexes=manifest.search_indexes,
            ai_tools=manifest.ai_tools,
            metadata=manifest.metadata,
            is_active=True,
        )

        logger.info(f"Registered module {manifest.name} v{manifest.version}")
        return entry

    def get_module(
        self, name: str, version: Optional[str] = None
    ) -> Optional[ModuleRegistryEntry]:
        """Get module from registry.

        Args:
            name: Module name.
            version: Optional version (latest if not specified).

        Returns:
            ModuleRegistryEntry or None if not found.
        """
        query = ModuleRegistryEntry.objects.filter(name=name, is_active=True)
        if version:
            query = query.filter(version=version)
        else:
            # Get latest version
            entries = list(query.order_by("-version"))
            if entries:
                return entries[0]
            return None
        return query.first()

    def list_modules(
        self,
        module_type: Optional[str] = None,
        lifecycle: Optional[str] = None,
        is_active: bool = True,
    ) -> List[ModuleRegistryEntry]:
        """List modules in registry.

        Args:
            module_type: Optional module type filter.
            lifecycle: Optional lifecycle filter.
            is_active: Filter by active status.

        Returns:
            List of ModuleRegistryEntry instances.
        """
        query = ModuleRegistryEntry.objects.filter(is_active=is_active)
        if module_type:
            query = query.filter(module_type=module_type)
        if lifecycle:
            query = query.filter(lifecycle=lifecycle)
        return list(query.order_by("name", "-version"))

    def resolve_dependencies(
        self, module_name: str, version: str, tenant_id: Optional[str] = None
    ) -> List[ModuleRegistryEntry]:
        """Resolve module dependencies.

        Args:
            module_name: Module name.
            version: Module version.
            tenant_id: Optional tenant ID for checking installed modules.

        Returns:
            List of ModuleRegistryEntry instances (dependency DAG in topological order).

        Raises:
            DependencyResolutionError: If dependencies cannot be resolved.
        """
        # Get module
        module = self.get_module(module_name, version)
        if not module:
            raise DependencyResolutionError(
                f"Module {module_name} v{version} not found"
            )

        # Build dependency graph
        resolved: Dict[str, ModuleRegistryEntry] = {}
        to_resolve: deque = deque([(module_name, version)])
        visited: Set[str] = set()

        while to_resolve:
            dep_name, dep_version_constraint = to_resolve.popleft()
            dep_key = f"{dep_name}@{dep_version_constraint}"

            if dep_key in visited:
                continue
            visited.add(dep_key)

            # Parse version constraint
            if ">=" in dep_version_constraint:
                constraint = dep_version_constraint
            elif "==" in dep_version_constraint:
                constraint = dep_version_constraint
            else:
                # Default to >=
                constraint = f">={dep_version_constraint}"

            # Find matching version
            candidates = ModuleRegistryEntry.objects.filter(
                name=dep_name, is_active=True
            ).order_by("-version")

            matched = None
            for candidate in candidates:
                try:
                    candidate_version = Version(candidate.version)
                    if candidate_version.satisfies(constraint):
                        matched = candidate
                        break
                except Exception:
                    continue

            if not matched:
                raise DependencyResolutionError(
                    f"Dependency {dep_name} {constraint} not found"
                )

            resolved[dep_name] = matched

            # Add dependencies of this module
            for dep in matched.dependencies:
                if isinstance(dep, str):
                    # Parse "module-name >=version"
                    parts = dep.split(" ", 1)
                    if len(parts) == 2:
                        dep_name_new, dep_version_new = parts
                    else:
                        dep_name_new = parts[0]
                        dep_version_new = ">=0.0.0"
                    to_resolve.append((dep_name_new, dep_version_new))
                elif isinstance(dep, dict):
                    dep_name_new = dep.get("name", "")
                    dep_version_new = dep.get("version", ">=0.0.0")
                    if dep_name_new:
                        to_resolve.append((dep_name_new, dep_version_new))

        # Topological sort (simple - dependencies first)
        sorted_modules: List[ModuleRegistryEntry] = []
        added: Set[str] = set()

        def add_with_deps(module_entry: ModuleRegistryEntry) -> None:
            """Add module and its dependencies."""
            if module_entry.name in added:
                return

            # Add dependencies first
            for dep in module_entry.dependencies:
                if isinstance(dep, str):
                    dep_name = dep.split(" ", 1)[0]
                elif isinstance(dep, dict):
                    dep_name = dep.get("name", "")
                else:
                    continue

                if dep_name in resolved and dep_name not in added:
                    add_with_deps(resolved[dep_name])

            sorted_modules.append(module_entry)
            added.add(module_entry.name)

        add_with_deps(module)

        return sorted_modules

    def check_compatibility(
        self,
        module_name: str,
        version: str,
        tenant_id: str,
    ) -> Tuple[bool, List[str]]:
        """Check module compatibility with tenant's installed modules.

        Args:
            module_name: Module name.
            version: Module version.
            tenant_id: Tenant ID.

        Returns:
            Tuple of (is_compatible, error_messages).
        """
        errors: List[str] = []

        # Get module
        module = self.get_module(module_name, version)
        if not module:
            return False, [f"Module {module_name} v{version} not found"]

        # Get installed modules for tenant
        installed = TenantModuleInstallation.objects.filter(
            tenant_id=tenant_id, status="installed"
        )

        # Check dependencies
        try:
            resolved_deps = self.resolve_dependencies(module_name, version, tenant_id)
        except DependencyResolutionError as e:
            errors.append(str(e))
            return False, errors

        # Check version conflicts
        installed_by_name: Dict[str, TenantModuleInstallation] = {}
        for inst in installed:
            installed_by_name[inst.module_name] = inst

        for dep_entry in resolved_deps:
            if dep_entry.name == module_name:
                continue  # Skip self

            if dep_entry.name in installed_by_name:
                installed_version_str = installed_by_name[dep_entry.name].module_version
                try:
                    installed_version = Version(installed_version_str)
                    # Check if installed version satisfies dependency
                    # This is simplified - real check would parse dependency constraints
                    if installed_version != Version(dep_entry.version):
                        # Check if versions are compatible
                        if not self.compatibility_checker.is_backward_compatible(
                            installed_version, Version(dep_entry.version)
                        ):
                            errors.append(
                                f"Version conflict: {dep_entry.name} "
                                f"(installed: {installed_version_str}, "
                                f"required: {dep_entry.version})"
                            )
                except Exception as e:
                    errors.append(f"Version check failed for {dep_entry.name}: {e}")

        return len(errors) == 0, errors

    def search_modules(
        self,
        query: Optional[str] = None,
        module_type: Optional[str] = None,
        lifecycle: Optional[str] = None,
    ) -> List[ModuleRegistryEntry]:
        """Search modules in registry.

        Args:
            query: Optional search query (searches name, description).
            module_type: Optional module type filter.
            lifecycle: Optional lifecycle filter.

        Returns:
            List of matching ModuleRegistryEntry instances.
        """
        modules = ModuleRegistryEntry.objects.filter(is_active=True)

        if module_type:
            modules = modules.filter(module_type=module_type)

        if lifecycle:
            modules = modules.filter(lifecycle=lifecycle)

        if query:
            modules = modules.filter(
                models.Q(name__icontains=query)
                | models.Q(description__icontains=query)
            )

        return list(modules.order_by("name", "-version"))

    def get_installed_modules(self, tenant_id: str) -> List[TenantModuleInstallation]:
        """Get installed modules for tenant.

        Args:
            tenant_id: Tenant ID.

        Returns:
            List of TenantModuleInstallation instances.
        """
        return list(
            TenantModuleInstallation.objects.filter(
                tenant_id=tenant_id, status="installed"
            ).order_by("module_name")
        )


# Global registry service instance
module_registry_service = ModuleRegistryService()
