"""Tests for Module Upgrader.

Task: 502.2 - Module Upgrade & Rollback
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from ..module_registry_models import ModuleRegistryEntry, TenantModuleInstallation
from ..module_upgrade_models import ModuleUpgrade, UpgradeStatus
from ..module_upgrader import ModuleUpgrader, RollbackError, UpgradeError, module_upgrader
from ..module_versioning import Version


@pytest.mark.django_db
class TestModuleUpgrader:
    """Test ModuleUpgrader."""

    def test_upgrade_module(self) -> None:
        """Test upgrading a module."""
        upgrader = ModuleUpgrader()

        # Create current installation
        current_entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        tenant_id = "tenant-1"
        TenantModuleInstallation.objects.create(
            tenant_id=tenant_id,
            module_name="test-module",
            module_version="1.0.0",
            registry_entry=current_entry,
            status="installed",
        )

        # Create target entry (use get_or_create to avoid unique constraint violation)
        target_entry, _ = ModuleRegistryEntry.objects.get_or_create(
            name="test-module",
            version="1.1.0",
            defaults={
                "description": "Test module",
                "module_type": "domain",
                "lifecycle": "managed",
                "is_active": True,
            },
        )

        with patch.object(upgrader.registry_service, "get_module", return_value=target_entry):
            with patch.object(upgrader, "_validate_upgrade_compatibility"):
                with patch.object(upgrader, "_validate_schema_changes"):
                    with patch.object(upgrader, "_create_backup_snapshot", return_value={}):
                        with patch.object(upgrader, "_run_migrations"):
                            with patch.object(upgrader, "_run_data_migrations"):
                                with patch.object(upgrader, "_update_module_registrations"):
                                    with patch.object(upgrader, "_post_upgrade_verification"):
                                        upgrade = upgrader.upgrade_module(
                                            tenant_id=tenant_id,
                                            module_name="test-module",
                                            to_version="1.1.0",
                                            upgraded_by="user-1",
                                        )

        assert upgrade is not None
        assert upgrade.status == UpgradeStatus.COMPLETED
        assert upgrade.from_version == "1.0.0"
        assert upgrade.to_version == "1.1.0"

        # Verify installation updated
        installation = TenantModuleInstallation.objects.filter(
            tenant_id=tenant_id, module_name="test-module", status="installed"
        ).first()
        assert installation is not None
        assert installation.module_version == "1.1.0"

    def test_upgrade_module_not_installed(self) -> None:
        """Test upgrading non-installed module fails."""
        upgrader = ModuleUpgrader()

        with pytest.raises(UpgradeError, match="not installed"):
            upgrader.upgrade_module(
                tenant_id="tenant-1",
                module_name="non-existent",
                to_version="1.0.0",
                upgraded_by="user-1",
            )

    def test_upgrade_module_not_in_registry(self) -> None:
        """Test upgrading to version not in registry fails."""
        upgrader = ModuleUpgrader()

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

        with patch.object(upgrader.registry_service, "get_module", return_value=None):
            with pytest.raises(UpgradeError, match="not found in registry"):
                upgrader.upgrade_module(
                    tenant_id="tenant-1",
                    module_name="test-module",
                    to_version="2.0.0",
                    upgraded_by="user-1",
                )

    def test_upgrade_module_incompatible(self) -> None:
        """Test upgrading to incompatible version fails."""
        upgrader = ModuleUpgrader()

        current_entry = ModuleRegistryEntry.objects.create(
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
            registry_entry=current_entry,
            status="installed",
        )

        target_entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="2.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        with patch.object(upgrader.registry_service, "get_module", return_value=target_entry):
            with patch.object(
                upgrader,
                "_validate_upgrade_compatibility",
                side_effect=UpgradeError("Major version upgrade requires approval"),
            ):
                with pytest.raises(UpgradeError, match="Major version upgrade"):
                    upgrader.upgrade_module(
                        tenant_id="tenant-1",
                        module_name="test-module",
                        to_version="2.0.0",
                        upgraded_by="user-1",
                    )

    def test_rollback_upgrade(self) -> None:
        """Test rolling back an upgrade."""
        upgrader = ModuleUpgrader()

        # Create upgrade record
        current_entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.0.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        target_entry = ModuleRegistryEntry.objects.create(
            name="test-module",
            version="1.1.0",
            description="Test module",
            module_type="domain",
            lifecycle="managed",
            is_active=True,
        )

        tenant_id = "tenant-1"
        installation = TenantModuleInstallation.objects.create(
            tenant_id=tenant_id,
            module_name="test-module",
            module_version="1.1.0",
            registry_entry=target_entry,
            status="installed",
        )

        upgrade = ModuleUpgrade.objects.create(
            tenant_id=tenant_id,
            module_name="test-module",
            from_version="1.0.0",
            to_version="1.1.0",
            registry_entry=target_entry,
            status=UpgradeStatus.COMPLETED,
            backup_snapshot={"data": "backup"},
        )

        with patch.object(upgrader.registry_service, "get_module", return_value=current_entry):
            with patch.object(upgrader, "_restore_backup_snapshot"):
                with patch.object(upgrader, "_rollback_migrations"):
                    with patch.object(upgrader, "_restore_module_registrations"):
                        rolled_back = upgrader.rollback_upgrade(upgrade.id)

        assert rolled_back.status == UpgradeStatus.ROLLED_BACK

        # Verify installation restored
        installation.refresh_from_db()
        assert installation.module_version == "1.0.0"

    def test_rollback_upgrade_not_found(self) -> None:
        """Test rolling back non-existent upgrade fails."""
        upgrader = ModuleUpgrader()

        with pytest.raises(RollbackError, match="not found"):
            upgrader.rollback_upgrade("non-existent-id")

    def test_rollback_upgrade_already_rolled_back(self) -> None:
        """Test rolling back already rolled back upgrade fails."""
        upgrader = ModuleUpgrader()

        # Create registry entry first
        registry_entry, _ = ModuleRegistryEntry.objects.get_or_create(
            name="test-module",
            version="1.1.0",
            defaults={
                "description": "Test module",
                "module_type": "domain",
                "lifecycle": "managed",
                "is_active": True,
            },
        )

        upgrade = ModuleUpgrade.objects.create(
            tenant_id="tenant-1",
            module_name="test-module",
            from_version="1.0.0",
            to_version="1.1.0",
            registry_entry=registry_entry,
            status=UpgradeStatus.ROLLED_BACK,
        )

        with pytest.raises(RollbackError, match="already rolled back"):
            upgrader.rollback_upgrade(upgrade.id)

    def test_validate_upgrade_compatibility(self) -> None:
        """Test validating upgrade compatibility."""
        upgrader = ModuleUpgrader()

        current = Version("1.0.0")
        target = Version("1.1.0")

        with patch.object(upgrader.compatibility_checker, "is_upgrade_safe", return_value=True):
            upgrader._validate_upgrade_compatibility(current, target, "test-module")
            # Should not raise

    def test_validate_upgrade_compatibility_unsafe(self) -> None:
        """Test validation fails for unsafe upgrade."""
        upgrader = ModuleUpgrader()

        current = Version("1.0.0")
        target = Version("2.0.0")

        with patch.object(upgrader.compatibility_checker, "is_upgrade_safe", return_value=False):
            with pytest.raises(UpgradeError, match="requires explicit approval"):
                upgrader._validate_upgrade_compatibility(current, target, "test-module")
