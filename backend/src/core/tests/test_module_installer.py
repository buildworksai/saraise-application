"""Tests for Module Installer.

Task: 502.1 - Module Installation
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from django.utils import timezone

from ..module_installation_models import InstallationStatus, ModuleInstallation
from ..module_installer import InstallationError, ModuleInstaller, module_installer
from ..module_registry_models import ModuleRegistryEntry, TenantModuleInstallation


@pytest.mark.django_db
class TestModuleInstaller:
    """Test ModuleInstaller."""

    def test_install_module(self) -> None:
        """Test installing a module."""
        installer = ModuleInstaller()

        # Create registry entry
        entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            dependencies=[],
            permissions=[],
            sod_actions=[],
            search_indexes=[],
            ai_tools=[],
            is_active=True,
        )

        tenant_id = "tenant-1"

        with patch.object(installer.registry_service, "get_module", return_value=entry):
            with patch.object(installer.registry_service, "check_compatibility", return_value=(True, [])):
                with patch.object(installer.registry_service, "resolve_dependencies", return_value=[entry]):
                    with patch.object(installer, "_run_migrations"):
                        with patch.object(installer, "_register_permissions"):
                            with patch.object(installer, "_register_sod_actions"):
                                with patch.object(installer, "_register_search_indexes"):
                                    with patch.object(installer, "_register_ai_tools"):
                                        with patch.object(installer, "_post_install_verification"):
                                            installation = installer.install_module(
                                                tenant_id=tenant_id,
                                                module_name="test-module",
                                                module_version="1.0.0",
                                                installed_by="user-1",
                                            )

        assert installation is not None
        assert installation.status == InstallationStatus.COMPLETED
        assert installation.module_name == "test-module"

        # Verify tenant installation created
        tenant_install = TenantModuleInstallation.objects.filter(
            tenant_id=tenant_id, module_name="test-module", status="installed"
        ).first()
        assert tenant_install is not None

    def test_install_module_not_in_registry(self) -> None:
        """Test installing module not in registry fails."""
        installer = ModuleInstaller()

        with patch.object(installer.registry_service, "get_module", return_value=None):
            with pytest.raises(InstallationError, match="not found in registry"):
                installer.install_module(
                    tenant_id="tenant-1",
                    module_name="non-existent",
                    module_version="1.0.0",
                    installed_by="user-1",
                )

    def test_install_module_already_installed(self) -> None:
        """Test installing already installed module fails."""
        installer = ModuleInstaller()

        entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        TenantModuleInstallation.objects.create(
            tenant_id="tenant-1",
            module_name="test-module",
            module_version="1.0.0",
            registry_entry=entry,
            status="installed",
        )

        with patch.object(installer.registry_service, "get_module", return_value=entry):
            with pytest.raises(InstallationError, match="already installed"):
                installer.install_module(
                    tenant_id="tenant-1",
                    module_name="test-module",
                    module_version="1.0.0",
                    installed_by="user-1",
                )

    def test_install_module_dependency_failure(self) -> None:
        """Test installation fails when dependency validation fails."""
        installer = ModuleInstaller()

        entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        with patch.object(installer.registry_service, "get_module", return_value=entry):
            with patch.object(
                installer.registry_service,
                "check_compatibility",
                return_value=(False, ["Dependency missing"]),
            ):
                with pytest.raises(InstallationError, match="Dependency validation failed"):
                    installer.install_module(
                        tenant_id="tenant-1",
                        module_name="test-module",
                        module_version="1.0.0",
                        installed_by="user-1",
                    )

    def test_install_module_migration_failure(self) -> None:
        """Test installation fails when migrations fail."""
        installer = ModuleInstaller()

        entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            dependencies=[],
            is_active=True,
        )

        with patch.object(installer.registry_service, "get_module", return_value=entry):
            with patch.object(installer.registry_service, "check_compatibility", return_value=(True, [])):
                with patch.object(installer.registry_service, "resolve_dependencies", return_value=[entry]):
                    with patch.object(installer, "_run_migrations", side_effect=Exception("Migration failed")):
                        with pytest.raises(InstallationError):
                            installer.install_module(
                                tenant_id="tenant-1",
                                module_name="test-module",
                                module_version="1.0.0",
                                installed_by="user-1",
                            )

        # Verify installation marked as failed
        installation = ModuleInstallation.objects.filter(tenant_id="tenant-1", module_name="test-module").first()
        assert installation is not None
        assert installation.status == InstallationStatus.FAILED

    def test_validate_dependencies(self) -> None:
        """Test validating dependencies."""
        installer = ModuleInstaller()

        entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        with patch.object(
            installer.registry_service,
            "check_compatibility",
            return_value=(True, []),
        ):
            installer._validate_dependencies("tenant-1", entry)
            # Should not raise

    def test_validate_dependencies_failure(self) -> None:
        """Test dependency validation failure."""
        installer = ModuleInstaller()

        entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        with patch.object(
            installer.registry_service,
            "check_compatibility",
            return_value=(False, ["Dependency error"]),
        ):
            with pytest.raises(InstallationError, match="Dependency validation failed"):
                installer._validate_dependencies("tenant-1", entry)
