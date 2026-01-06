"""Tests for Module Registry Service.

Task: 501.2 - Module Registry & Compatibility Validation
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from ..module_registry_service import (
    ModuleRegistryService,
    RegistryError,
    DependencyResolutionError,
    module_registry_service,
)
from ..module_registry_models import ModuleRegistryEntry, TenantModuleInstallation
from ..module_manifest_schema import ModuleType, ModuleLifecycle


@pytest.mark.django_db
class TestModuleRegistryService:
    """Test ModuleRegistryService."""

    def test_register_module(self) -> None:
        """Test registering a module."""
        service = ModuleRegistryService()

        manifest_yaml = """
name: test-module
version: 1.0.0
description: Test module
type: domain
lifecycle: managed
"""

        entry = service.register_module(manifest_yaml, verify_signature=False)

        assert entry.name == "test-module"
        assert entry.version == "1.0.0"
        assert entry.module_type == "domain"
        assert entry.is_active is True

    def test_register_module_duplicate(self) -> None:
        """Test registering duplicate module fails."""
        service = ModuleRegistryService()

        manifest_yaml = """
name: test-module
version: 1.0.0
description: Test module
type: domain
lifecycle: managed
"""

        service.register_module(manifest_yaml, verify_signature=False)

        # Try to register again
        with pytest.raises(RegistryError, match="already registered"):
            service.register_module(manifest_yaml, verify_signature=False)

    def test_get_module(self) -> None:
        """Test getting module from registry."""
        service = ModuleRegistryService()

        manifest_yaml = """
name: test-module
version: 1.0.0
description: Test module
type: domain
lifecycle: managed
"""

        service.register_module(manifest_yaml, verify_signature=False)

        # Get by name and version
        entry = service.get_module("test-module", "1.0.0")
        assert entry is not None
        assert entry.name == "test-module"

        # Get latest version
        entry = service.get_module("test-module")
        assert entry is not None
        assert entry.version == "1.0.0"

    def test_get_module_not_found(self) -> None:
        """Test getting non-existent module returns None."""
        service = ModuleRegistryService()

        entry = service.get_module("non-existent", "1.0.0")
        assert entry is None

    def test_list_modules(self) -> None:
        """Test listing modules."""
        service = ModuleRegistryService()

        manifest_yaml1 = """
name: module1
version: 1.0.0
description: Module 1
type: domain
lifecycle: managed
"""

        manifest_yaml2 = """
name: module2
version: 1.0.0
description: Module 2
type: core
lifecycle: core
"""

        service.register_module(manifest_yaml1, verify_signature=False)
        service.register_module(manifest_yaml2, verify_signature=False)

        # List all modules
        modules = service.list_modules()
        assert len(modules) >= 2

        # Filter by type
        domain_modules = service.list_modules(module_type="domain")
        assert len(domain_modules) >= 1
        assert all(m.module_type == "domain" for m in domain_modules)

    def test_resolve_dependencies_simple(self) -> None:
        """Test resolving simple dependencies."""
        service = ModuleRegistryService()

        # Register dependency
        dep_yaml = """
name: core-identity
version: 1.0.0
description: Core identity module
type: core
lifecycle: core
"""

        service.register_module(dep_yaml, verify_signature=False)

        # Register module with dependency
        module_yaml = """
name: test-module
version: 1.0.0
description: Test module
type: domain
lifecycle: managed
dependencies:
  - core-identity >=1.0.0
"""

        service.register_module(module_yaml, verify_signature=False)

        # Resolve dependencies
        resolved = service.resolve_dependencies("test-module", "1.0.0")

        assert len(resolved) >= 1
        module_names = {m.name for m in resolved}
        assert "test-module" in module_names
        assert "core-identity" in module_names

    def test_resolve_dependencies_missing(self) -> None:
        """Test resolving dependencies fails when dependency missing."""
        service = ModuleRegistryService()

        module_yaml = """
name: test-module
version: 1.0.0
description: Test module
type: domain
lifecycle: managed
dependencies:
  - missing-module >=1.0.0
"""

        service.register_module(module_yaml, verify_signature=False)

        with pytest.raises(DependencyResolutionError):
            service.resolve_dependencies("test-module", "1.0.0")

    def test_check_compatibility(self) -> None:
        """Test checking module compatibility."""
        service = ModuleRegistryService()

        manifest_yaml = """
name: test-module
version: 1.0.0
description: Test module
type: domain
lifecycle: managed
"""

        service.register_module(manifest_yaml, verify_signature=False)

        is_compatible, errors = service.check_compatibility(
            "test-module", "1.0.0", "tenant-1"
        )

        assert is_compatible is True
        assert len(errors) == 0

    def test_check_compatibility_not_found(self) -> None:
        """Test checking compatibility fails when module not found."""
        service = ModuleRegistryService()

        is_compatible, errors = service.check_compatibility(
            "non-existent", "1.0.0", "tenant-1"
        )

        assert is_compatible is False
        assert len(errors) > 0

    def test_search_modules(self) -> None:
        """Test searching modules."""
        service = ModuleRegistryService()

        manifest_yaml = """
name: test-module
version: 1.0.0
description: Test module for search
type: domain
lifecycle: managed
"""

        service.register_module(manifest_yaml, verify_signature=False)

        # Search by name
        results = service.search_modules(query="test-module")
        assert len(results) >= 1
        assert any(r.name == "test-module" for r in results)

        # Search by description
        results = service.search_modules(query="search")
        assert len(results) >= 1

    def test_get_installed_modules(self) -> None:
        """Test getting installed modules for tenant."""
        service = ModuleRegistryService()

        tenant_id = "tenant-1"

        # Create installation
        entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        TenantModuleInstallation.objects.create(
            tenant_id=tenant_id,
            module_name="test-module",
            module_version="1.0.0",
            registry_entry=entry,
            status="installed",
        )

        installed = service.get_installed_modules(tenant_id)

        assert len(installed) >= 1
        assert any(m.module_name == "test-module" for m in installed)

