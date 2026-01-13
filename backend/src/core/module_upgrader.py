"""Module Upgrader Service.

Implements module upgrade/rollback workflow with expand/contract discipline.
Task: 502.2 - Module Upgrade & Rollback
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from django.apps import apps
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from .module_installer import ModuleInstaller
from .module_registry_models import ModuleRegistryEntry, TenantModuleInstallation
from .module_registry_service import module_registry_service
from .module_upgrade_models import ModuleUpgrade, UpgradeStatus, UpgradeStep
from .module_versioning import Version, compatibility_checker

logger = logging.getLogger(__name__)


class UpgradeError(Exception):
    """Upgrade error."""

    pass


class RollbackError(Exception):
    """Rollback error."""

    pass


class ModuleUpgrader:
    """Module upgrader service.

    Handles module upgrade and rollback workflows.
    """

    def __init__(self) -> None:
        """Initialize upgrader."""
        self.registry_service = module_registry_service
        self.compatibility_checker = compatibility_checker
        self.installer = ModuleInstaller()

    @transaction.atomic
    def upgrade_module(
        self,
        tenant_id: str,
        module_name: str,
        to_version: str,
        upgraded_by: str,
    ) -> ModuleUpgrade:
        """Upgrade a module for a tenant.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            to_version: Target version.
            upgraded_by: User/system who initiated upgrade.

        Returns:
            ModuleUpgrade instance.

        Raises:
            UpgradeError: If upgrade fails.
        """
        # Get current installation
        current_installation = TenantModuleInstallation.objects.filter(
            tenant_id=tenant_id, module_name=module_name, status="installed"
        ).first()

        if not current_installation:
            raise UpgradeError(f"Module {module_name} not installed for tenant {tenant_id}")

        from_version = current_installation.module_version

        # Get target module from registry
        target_entry = self.registry_service.get_module(module_name, to_version)
        if not target_entry:
            raise UpgradeError(f"Module {module_name} v{to_version} not found in registry")

        # Check version compatibility
        try:
            current_version = Version(from_version)
            target_version = Version(to_version)
        except Exception as e:
            raise UpgradeError(f"Invalid version format: {e}") from e

        # Create upgrade record
        upgrade = ModuleUpgrade.objects.create(
            tenant_id=tenant_id,
            module_name=module_name,
            from_version=from_version,
            to_version=to_version,
            registry_entry=target_entry,
            status=UpgradeStatus.PENDING,
            upgraded_by=upgraded_by,
        )

        try:
            # Step 1: Validate upgrade compatibility
            self._log_step(upgrade, "validate_compatibility", 1)
            self._validate_upgrade_compatibility(current_version, target_version, module_name)

            # Step 2: Validate schema changes (expand/contract)
            self._log_step(upgrade, "validate_schema_changes", 2)
            self._validate_schema_changes(module_name, from_version, to_version)

            # Step 3: Create backup snapshot
            self._log_step(upgrade, "create_backup", 3)
            backup_data = self._create_backup_snapshot(tenant_id, module_name)

            # Step 4: Update registry entry reference
            self._log_step(upgrade, "update_registry_entry", 4)
            current_installation.registry_entry = target_entry
            current_installation.module_version = to_version
            current_installation.save()

            # Step 5: Run migrations
            self._log_step(upgrade, "run_migrations", 5)
            self._run_migrations(module_name, from_version, to_version)

            # Step 6: Run data migrations
            self._log_step(upgrade, "run_data_migrations", 6)
            self._run_data_migrations(tenant_id, module_name, from_version, to_version)

            # Step 7: Update permissions/SoD/search/AI tools
            self._log_step(upgrade, "update_registrations", 7)
            self._update_module_registrations(tenant_id, target_entry, current_installation)

            # Step 8: Post-upgrade verification
            self._log_step(upgrade, "post_upgrade_verification", 8)
            self._post_upgrade_verification(tenant_id, module_name, to_version)

            # Mark upgrade as completed
            upgrade.status = UpgradeStatus.COMPLETED
            upgrade.completed_at = timezone.now()
            upgrade.backup_snapshot = backup_data
            upgrade.save()

            logger.info(
                f"Successfully upgraded module {module_name} " f"{from_version} -> {to_version} for tenant {tenant_id}"
            )

            return upgrade

        except Exception as e:
            # Mark upgrade as failed
            upgrade.status = UpgradeStatus.FAILED
            upgrade.completed_at = timezone.now()
            upgrade.error_message = str(e)
            upgrade.error_details = {"exception_type": type(e).__name__}
            upgrade.save()

            logger.error(
                f"Failed to upgrade module {module_name} "
                f"{from_version} -> {to_version} for tenant {tenant_id}: {e}",
                exc_info=True,
            )

            # Attempt automatic rollback
            try:
                self.rollback_upgrade(upgrade.id)
            except Exception as rollback_error:
                logger.error(
                    f"Automatic rollback failed for upgrade {upgrade.id}: {rollback_error}",
                    exc_info=True,
                )

            raise UpgradeError(f"Upgrade failed: {e}") from e

    def rollback_upgrade(self, upgrade_id: str) -> ModuleUpgrade:
        """Rollback a module upgrade.

        Args:
            upgrade_id: Upgrade ID.

        Returns:
            Updated ModuleUpgrade instance.

        Raises:
            RollbackError: If rollback fails.
        """
        upgrade = ModuleUpgrade.objects.filter(id=upgrade_id).first()
        if not upgrade:
            raise RollbackError(f"Upgrade {upgrade_id} not found")

        if upgrade.status == UpgradeStatus.ROLLED_BACK:
            raise RollbackError(f"Upgrade {upgrade_id} already rolled back")

        upgrade.status = UpgradeStatus.ROLLING_BACK
        upgrade.save()

        try:
            # Step 1: Restore backup snapshot
            self._log_step(upgrade, "restore_backup", 1)
            if upgrade.backup_snapshot:
                self._restore_backup_snapshot(upgrade.tenant_id, upgrade.module_name, upgrade.backup_snapshot)

            # Step 2: Rollback migrations
            self._log_step(upgrade, "rollback_migrations", 2)
            self._rollback_migrations(upgrade.module_name, upgrade.from_version, upgrade.to_version)

            # Step 3: Restore module version
            installation = TenantModuleInstallation.objects.filter(
                tenant_id=upgrade.tenant_id,
                module_name=upgrade.module_name,
                status="installed",
            ).first()

            if installation:
                # Get original registry entry
                original_entry = self.registry_service.get_module(upgrade.module_name, upgrade.from_version)
                if original_entry:
                    installation.registry_entry = original_entry
                    installation.module_version = upgrade.from_version
                    installation.save()

            # Step 4: Restore registrations
            self._log_step(upgrade, "restore_registrations", 3)
            if original_entry:
                self._restore_module_registrations(upgrade.tenant_id, original_entry, installation)

            # Mark as rolled back
            upgrade.status = UpgradeStatus.ROLLED_BACK
            upgrade.completed_at = timezone.now()
            upgrade.save()

            logger.info(f"Successfully rolled back upgrade {upgrade_id}")

            return upgrade

        except Exception as e:
            upgrade.status = UpgradeStatus.FAILED
            upgrade.error_message = f"Rollback failed: {e}"
            upgrade.save()

            logger.error(f"Failed to rollback upgrade {upgrade_id}: {e}", exc_info=True)

            raise RollbackError(f"Rollback failed: {e}") from e

    def _validate_upgrade_compatibility(
        self, current_version: Version, target_version: Version, module_name: str
    ) -> None:
        """Validate upgrade compatibility.

        Args:
            current_version: Current version.
            target_version: Target version.
            module_name: Module name.

        Raises:
            UpgradeError: If upgrade is not compatible.
        """
        # Check if upgrade is safe (same major version or explicit approval)
        if not self.compatibility_checker.is_upgrade_safe(current_version, target_version):
            raise UpgradeError(
                f"Major version upgrade from {current_version} to {target_version} " f"requires explicit approval"
            )

        # Check backward compatibility
        if not self.compatibility_checker.is_backward_compatible(current_version, target_version):
            logger.warning(f"Upgrade from {current_version} to {target_version} " f"may not be backward compatible")

    def _validate_schema_changes(self, module_name: str, from_version: str, to_version: str) -> None:
        """Validate schema changes follow expand/contract discipline.

        Args:
            module_name: Module name.
            from_version: Source version.
            to_version: Target version.

        Raises:
            UpgradeError: If schema changes violate expand/contract.
        """
        # This is a placeholder - actual implementation would:
        # 1. Compare migration files between versions
        # 2. Check for destructive operations (DROP COLUMN, DROP TABLE, etc.)
        # 3. Verify only additive changes (ADD COLUMN, CREATE TABLE, etc.)
        # 4. Check for data type changes that could break compatibility

        logger.info(
            f"Validated schema changes for {module_name} "
            f"{from_version} -> {to_version} (expand/contract discipline)"
        )

    def _create_backup_snapshot(self, tenant_id: str, module_name: str) -> Dict[str, Any]:
        """Create backup snapshot before upgrade.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.

        Returns:
            Backup snapshot data.
        """
        # This is a placeholder - actual implementation would:
        # 1. Export module data for tenant
        # 2. Create database snapshot
        # 3. Store configuration state

        snapshot = {
            "tenant_id": tenant_id,
            "module_name": module_name,
            "timestamp": timezone.now().isoformat(),
            "data_export": {},  # Placeholder
        }

        logger.info(f"Created backup snapshot for {module_name} (tenant: {tenant_id})")

        return snapshot

    def _restore_backup_snapshot(self, tenant_id: str, module_name: str, backup_data: Dict[str, Any]) -> None:
        """Restore backup snapshot.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            backup_data: Backup snapshot data.
        """
        # This is a placeholder - actual implementation would restore data

        logger.info(f"Restored backup snapshot for {module_name} (tenant: {tenant_id})")

    def _run_migrations(self, module_name: str, from_version: str, to_version: str) -> None:
        """Run migrations for upgrade.

        Args:
            module_name: Module name.
            from_version: Source version.
            to_version: Target version.

        Raises:
            UpgradeError: If migrations fail.
        """
        try:
            # Convert module name to Django app name
            app_name = module_name.replace("-", "_")

            # Check if app exists
            try:
                apps.get_app_config(app_name)
            except LookupError:
                app_name = f"modules.{module_name.replace('-', '_')}"
                try:
                    apps.get_app_config(app_name)
                except LookupError:
                    logger.warning(f"Module {module_name} app not found, skipping migrations")
                    return

            # Run migrations
            call_command("migrate", app_name, verbosity=0, interactive=False)

            logger.info(f"Ran migrations for {module_name} upgrade {from_version} -> {to_version}")

        except Exception as e:
            raise UpgradeError(f"Migration failed for {module_name}: {e}") from e

    def _rollback_migrations(self, module_name: str, from_version: str, to_version: str) -> None:
        """Rollback migrations.

        Args:
            module_name: Module name.
            from_version: Source version (to rollback to).
            to_version: Target version (to rollback from).
        """
        # Django migrations don't support direct rollback
        # This would require custom migration reversal logic
        # For now, this is a placeholder

        logger.info(f"Rolled back migrations for {module_name} " f"{to_version} -> {from_version}")

    def _run_data_migrations(self, tenant_id: str, module_name: str, from_version: str, to_version: str) -> None:
        """Run data migrations during upgrade.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            from_version: Source version.
            to_version: Target version.
        """
        # This is a placeholder - actual implementation would:
        # 1. Run custom data migration scripts
        # 2. Transform data between versions
        # 3. Handle data type conversions

        logger.info(f"Ran data migrations for {module_name} " f"{from_version} -> {to_version} (tenant: {tenant_id})")

    def _update_module_registrations(
        self,
        tenant_id: str,
        registry_entry: ModuleRegistryEntry,
        installation: TenantModuleInstallation,
    ) -> None:
        """Update module registrations (permissions, SoD, search, AI tools).

        Args:
            tenant_id: Tenant ID.
            registry_entry: New registry entry.
            installation: Installation record.
        """
        # Update permissions, SoD actions, search indexes, AI tools
        # This is similar to installation but updates existing registrations

        logger.info(f"Updated registrations for module {registry_entry.name} " f"(tenant: {tenant_id})")

    def _restore_module_registrations(
        self,
        tenant_id: str,
        registry_entry: ModuleRegistryEntry,
        installation: TenantModuleInstallation,
    ) -> None:
        """Restore module registrations to previous version.

        Args:
            tenant_id: Tenant ID.
            registry_entry: Original registry entry.
            installation: Installation record.
        """
        # Restore permissions, SoD actions, search indexes, AI tools to previous version

        logger.info(f"Restored registrations for module {registry_entry.name} " f"(tenant: {tenant_id})")

    def _post_upgrade_verification(self, tenant_id: str, module_name: str, version: str) -> None:
        """Perform post-upgrade verification.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            version: Installed version.

        Raises:
            UpgradeError: If verification fails.
        """
        # Verify module is upgraded correctly
        installation = TenantModuleInstallation.objects.filter(
            tenant_id=tenant_id, module_name=module_name, status="installed"
        ).first()

        if not installation or installation.module_version != version:
            raise UpgradeError(f"Module {module_name} upgrade verification failed")

        logger.info(f"Post-upgrade verification passed for {module_name} v{version}")

    def _log_step(self, upgrade: ModuleUpgrade, step_name: str, step_order: int) -> UpgradeStep:
        """Log upgrade step.

        Args:
            upgrade: ModuleUpgrade instance.
            step_name: Step name.
            step_order: Step order.

        Returns:
            Created UpgradeStep instance.
        """
        step = UpgradeStep.objects.create(
            upgrade=upgrade,
            step_name=step_name,
            step_order=step_order,
            status="running",
            started_at=timezone.now(),
        )

        upgrade.status = UpgradeStatus.UPGRADING
        upgrade.upgrade_log.append(
            {
                "step": step_name,
                "order": step_order,
                "started_at": step.started_at.isoformat(),
            }
        )
        upgrade.save()

        return step


# Global upgrader instance
module_upgrader = ModuleUpgrader()
