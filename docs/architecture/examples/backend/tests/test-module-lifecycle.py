# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module Lifecycle Testing
# backend/tests/core/test_module_lifecycle.py
# Reference: docs/architecture/module-framework.md § 1, § 2
# CRITICAL: SARAISE uses Django ORM exclusively

import pytest
from django.db import transaction
from src.core.module_installer import ModuleInstaller
from src.core.module_upgrader import ModuleUpgrader
from src.core.module_uninstaller import ModuleUninstaller
from src.models.module_state import InstalledModule

@pytest.mark.asyncio
def test_module_installation_for_tenant(tenant_fixture):
    """Test module installation per tenant.
    
    Modules are installed per-tenant based on subscription.
    See docs/architecture/module-framework.md § 2 (Per-Tenant Installation).
    """
    # ✅ CORRECT: Django ORM - no database session needed
    installer = ModuleInstaller()
    installer.install_module("module_name", "1.0.0")

    # Verify installation is scoped to this tenant
    # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
    installed = InstalledModule.objects.filter(
        name="module_name",
        tenant_id=tenant_fixture.id
    ).first()
    assert installed is not None
    assert installed.version == "1.0.0"
    assert installed.tenant_id == tenant_fixture.id

@pytest.mark.asyncio
def test_module_upgrade(tenant_fixture):
    """Test module upgrade per tenant.
    
    Module upgrades are tenant-scoped operations.
    """
    # Install module
    # ✅ CORRECT: Django ORM - no database session needed
    installer = ModuleInstaller()
    installer.install_module("module_name", "1.0.0")

    # Upgrade module
    upgrader = ModuleUpgrader()
    upgrader.upgrade_module("module_name", "1.0.0", "1.1.0")

    # Verify upgrade is scoped to this tenant
    # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
    installed = InstalledModule.objects.filter(
        name="module_name",
        tenant_id=tenant_fixture.id
    ).first()
    assert installed.version == "1.1.0"
    assert installed.tenant_id == tenant_fixture.id

@pytest.mark.asyncio
def test_module_uninstallation(tenant_fixture):
    """Test module uninstallation per tenant.
    
    Module uninstallation is tenant-scoped (doesn't affect other tenants).
    """
    # Install module
    # ✅ CORRECT: Django ORM - no database session needed
    installer = ModuleInstaller()
    installer.install_module("module_name", "1.0.0")

    # Uninstall module
    uninstaller = ModuleUninstaller()
    uninstaller.uninstall_module("module_name", keep_data=False)

    # Verify uninstallation is scoped to this tenant
    # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
    installed = InstalledModule.objects.filter(
        name="module_name",
        tenant_id=tenant_fixture.id
    ).first()
    assert installed is None

