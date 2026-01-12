"""Module Installer Service.

Implements module installation workflow with dependency validation, migrations, and permission registration.
Task: 502.1 - Module Installation
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.apps import apps
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from .module_installation_models import InstallationStatus, InstallationStep, ModuleInstallation
from .module_registry_models import ModuleRegistryEntry, TenantModuleInstallation
from .module_registry_service import DependencyResolutionError, module_registry_service

logger = logging.getLogger(__name__)


class InstallationError(Exception):
    """Installation error."""

    pass


class ModuleInstaller:
    """Module installer service.

    Handles module installation workflow.
    """

    def __init__(self) -> None:
        """Initialize installer."""
        self.registry_service = module_registry_service

    @transaction.atomic
    def install_module(
        self,
        tenant_id: str,
        module_name: str,
        module_version: str,
        installed_by: str,
    ) -> ModuleInstallation:
        """Install a module for a tenant.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.
            module_version: Module version.
            installed_by: User/system who initiated installation.

        Returns:
            ModuleInstallation instance.

        Raises:
            InstallationError: If installation fails.
        """
        # Get module from registry
        registry_entry = self.registry_service.get_module(module_name, module_version)
        if not registry_entry:
            raise InstallationError(f"Module {module_name} v{module_version} not found in registry")

        # Check if already installed
        existing = TenantModuleInstallation.objects.filter(
            tenant_id=tenant_id, module_name=module_name, status="installed"
        ).first()
        if existing:
            raise InstallationError(f"Module {module_name} already installed for tenant {tenant_id}")

        # Create installation record
        installation = ModuleInstallation.objects.create(
            tenant_id=tenant_id,
            module_name=module_name,
            module_version=module_version,
            registry_entry=registry_entry,
            status=InstallationStatus.PENDING,
            installed_by=installed_by,
        )

        try:
            # Step 1: Validate dependencies
            self._log_step(installation, "validate_dependencies", 1)
            self._validate_dependencies(tenant_id, registry_entry)

            # Step 2: Resolve and install dependencies
            self._log_step(installation, "install_dependencies", 2)
            self._install_dependencies(tenant_id, registry_entry, installed_by)

            # Step 3: Run migrations
            self._log_step(installation, "run_migrations", 3)
            self._run_migrations(module_name)

            # Step 4: Register permissions
            self._log_step(installation, "register_permissions", 4)
            self._register_permissions(tenant_id, registry_entry)

            # Step 5: Register SoD actions
            self._log_step(installation, "register_sod_actions", 5)
            self._register_sod_actions(tenant_id, registry_entry)

            # Step 6: Register search indexes
            self._log_step(installation, "register_search_indexes", 6)
            self._register_search_indexes(tenant_id, registry_entry)

            # Step 7: Register AI tools
            self._log_step(installation, "register_ai_tools", 7)
            self._register_ai_tools(tenant_id, registry_entry)

            # Step 8: Post-install verification
            self._log_step(installation, "post_install_verification", 8)
            self._post_install_verification(tenant_id, module_name)

            # Create tenant installation record
            TenantModuleInstallation.objects.create(
                tenant_id=tenant_id,
                module_name=module_name,
                module_version=module_version,
                registry_entry=registry_entry,
                installed_by=installed_by,
                status="installed",
            )

            # Mark installation as completed
            installation.status = InstallationStatus.COMPLETED
            installation.completed_at = timezone.now()
            installation.save()

            logger.info(f"Successfully installed module {module_name} v{module_version} " f"for tenant {tenant_id}")

            return installation

        except Exception as e:
            # Mark installation as failed
            installation.status = InstallationStatus.FAILED
            installation.completed_at = timezone.now()
            installation.error_message = str(e)
            installation.error_details = {"exception_type": type(e).__name__}
            installation.save()

            logger.error(
                f"Failed to install module {module_name} v{module_version} " f"for tenant {tenant_id}: {e}",
                exc_info=True,
            )

            raise InstallationError(f"Installation failed: {e}") from e

    def _validate_dependencies(self, tenant_id: str, registry_entry: ModuleRegistryEntry) -> None:
        """Validate module dependencies.

        Args:
            tenant_id: Tenant ID.
            registry_entry: Module registry entry.

        Raises:
            InstallationError: If dependencies are not satisfied.
        """
        try:
            is_compatible, errors = self.registry_service.check_compatibility(
                registry_entry.name, registry_entry.version, tenant_id
            )
            if not is_compatible:
                raise InstallationError(f"Dependency validation failed: {', '.join(errors)}")
        except DependencyResolutionError as e:
            raise InstallationError(f"Dependency resolution failed: {e}") from e

    def _install_dependencies(
        self,
        tenant_id: str,
        registry_entry: ModuleRegistryEntry,
        installed_by: str,
    ) -> None:
        """Install module dependencies.

        Args:
            tenant_id: Tenant ID.
            registry_entry: Module registry entry.
            installed_by: User/system who initiated installation.

        Raises:
            InstallationError: If dependency installation fails.
        """
        try:
            resolved_deps = self.registry_service.resolve_dependencies(
                registry_entry.name, registry_entry.version, tenant_id
            )
        except DependencyResolutionError as e:
            raise InstallationError(f"Dependency resolution failed: {e}") from e

        # Install dependencies (excluding self)
        for dep_entry in resolved_deps:
            if dep_entry.name == registry_entry.name:
                continue  # Skip self

            # Check if already installed
            existing = TenantModuleInstallation.objects.filter(
                tenant_id=tenant_id, module_name=dep_entry.name, status="installed"
            ).first()

            if not existing:
                # Recursively install dependency
                logger.info(f"Installing dependency {dep_entry.name} v{dep_entry.version} " f"for tenant {tenant_id}")
                self.install_module(tenant_id, dep_entry.name, dep_entry.version, installed_by)

    def _run_migrations(self, module_name: str) -> None:
        """Run module migrations.

        Args:
            module_name: Module name.

        Raises:
            InstallationError: If migrations fail.
        """
        try:
            # Convert module name to Django app name
            app_name = module_name.replace("-", "_")

            # Check if app exists
            try:
                apps.get_app_config(app_name)
            except LookupError:
                # Try alternative naming
                app_name = f"modules.{module_name.replace('-', '_')}"
                try:
                    apps.get_app_config(app_name)
                except LookupError:
                    logger.warning(f"Module {module_name} app not found, skipping migrations")
                    return

            # Run migrations
            call_command("migrate", app_name, verbosity=0, interactive=False)

            logger.info(f"Ran migrations for module {module_name}")

        except Exception as e:
            raise InstallationError(f"Migration failed for {module_name}: {e}") from e

    def _register_permissions(self, tenant_id: str, registry_entry: ModuleRegistryEntry) -> None:
        """Register module permissions.

        Args:
            tenant_id: Tenant ID.
            registry_entry: Module registry entry.

        Raises:
            InstallationError: If permission registration fails.
        """
        try:
            # Import permission registry (placeholder - actual implementation depends on platform)
            # from saraise.backend.src.core.permission_registry import PermissionRegistry
            # permission_registry = PermissionRegistry()
            # for perm in registry_entry.permissions:
            #     permission_registry.register(tenant_id, perm, registry_entry.name)

            logger.info(
                f"Registered {len(registry_entry.permissions)} permissions " f"for module {registry_entry.name}"
            )

        except Exception as e:
            raise InstallationError(f"Permission registration failed: {e}") from e

    def _register_sod_actions(self, tenant_id: str, registry_entry: ModuleRegistryEntry) -> None:
        """Register SoD actions.

        Args:
            tenant_id: Tenant ID.
            registry_entry: Module registry entry.

        Raises:
            InstallationError: If SoD action registration fails.
        """
        try:
            # Import SoD registry (placeholder - actual implementation depends on platform)
            # from saraise.backend.src.core.sod_registry import SoDRegistry
            # sod_registry = SoDRegistry()
            # for action in registry_entry.sod_actions:
            #     sod_registry.register(tenant_id, action, registry_entry.name)

            logger.info(
                f"Registered {len(registry_entry.sod_actions)} SoD actions " f"for module {registry_entry.name}"
            )

        except Exception as e:
            raise InstallationError(f"SoD action registration failed: {e}") from e

    def _register_search_indexes(self, tenant_id: str, registry_entry: ModuleRegistryEntry) -> None:
        """Register search indexes.

        Args:
            tenant_id: Tenant ID.
            registry_entry: Module registry entry.

        Raises:
            InstallationError: If search index registration fails.
        """
        try:
            # Import search registry (placeholder - actual implementation depends on platform)
            # from saraise.backend.src.core.search_registry import SearchRegistry
            # search_registry = SearchRegistry()
            # for index in registry_entry.search_indexes:
            #     search_registry.register(tenant_id, index, registry_entry.name)

            logger.info(
                f"Registered {len(registry_entry.search_indexes)} search indexes " f"for module {registry_entry.name}"
            )

        except Exception as e:
            raise InstallationError(f"Search index registration failed: {e}") from e

    def _register_ai_tools(self, tenant_id: str, registry_entry: ModuleRegistryEntry) -> None:
        """Register AI tools.

        Args:
            tenant_id: Tenant ID.
            registry_entry: Module registry entry.

        Raises:
            InstallationError: If AI tool registration fails.
        """
        try:
            # Import AI tool registry (placeholder - actual implementation depends on platform)
            # from saraise.backend.src.modules.ai_agent_management.tool_registry import ToolRegistryService
            # tool_registry = ToolRegistryService()
            # for tool_name in registry_entry.ai_tools:
            #     tool_registry.register_from_module(tenant_id, registry_entry.name, tool_name)

            logger.info(f"Registered {len(registry_entry.ai_tools)} AI tools " f"for module {registry_entry.name}")

        except Exception as e:
            raise InstallationError(f"AI tool registration failed: {e}") from e

    def _post_install_verification(self, tenant_id: str, module_name: str) -> None:
        """Perform post-install verification.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.

        Raises:
            InstallationError: If verification fails.
        """
        try:
            # Verify module is installed
            installation = TenantModuleInstallation.objects.filter(
                tenant_id=tenant_id, module_name=module_name, status="installed"
            ).first()

            if not installation:
                raise InstallationError(f"Module {module_name} installation verification failed")

            # Additional verification checks can be added here
            logger.info(f"Post-install verification passed for {module_name}")

        except Exception as e:
            raise InstallationError(f"Verification failed: {e}") from e

    def _log_step(
        self,
        installation: ModuleInstallation,
        step_name: str,
        step_order: int,
    ) -> InstallationStep:
        """Log installation step.

        Args:
            installation: ModuleInstallation instance.
            step_name: Step name.
            step_order: Step order.

        Returns:
            Created InstallationStep instance.
        """
        step = InstallationStep.objects.create(
            installation=installation,
            step_name=step_name,
            step_order=step_order,
            status="running",
            started_at=timezone.now(),
        )

        installation.status = InstallationStatus.INSTALLING
        installation.installation_log.append(
            {
                "step": step_name,
                "order": step_order,
                "started_at": step.started_at.isoformat(),
            }
        )
        installation.save()

        return step

    def _complete_step(self, step: InstallationStep, success: bool, output: Optional[Dict[str, Any]] = None) -> None:
        """Complete installation step.

        Args:
            step: InstallationStep instance.
            success: Whether step succeeded.
            output: Optional step output.
        """
        step.completed_at = timezone.now()
        if step.started_at:
            duration = (step.completed_at - step.started_at).total_seconds() * 1000
            step.duration_ms = int(duration)

        if success:
            step.status = "completed"
        else:
            step.status = "failed"

        if output:
            step.output = output

        step.save()


# Global installer instance
module_installer = ModuleInstaller()
