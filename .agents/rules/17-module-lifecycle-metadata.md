---
description: Module Lifecycle, Metadata Modeling & Customization
globs: backend/src/modules/**/*.py
alwaysApply: true
---

# Module Lifecycle, Metadata Modeling & Customization

**Rule IDs**: SARAISE-29001 to SARAISE-29010, SARAISE-30001 to SARAISE-30010, SARAISE-31001 to SARAISE-31010
**Consolidates**: `19-module-lifecycle.md`, `17-module-lifecycle-metadata.md`, `17-module-lifecycle-metadata.md`

---
# 🔄 SARAISE Module Lifecycle Management

**⚠️ CRITICAL**: All modules MUST follow a clear lifecycle: development → testing → staging → production.

**Related Documentation:**
- Module Framework: `docs/architecture/module-framework.md`
- Application Architecture: `docs/architecture/application-architecture.md`

## SARAISE-29001 Module Lifecycle Stages

### Lifecycle Stages
1. **Development**: Module under active development
2. **Testing**: Module in testing phase
3. **Staging**: Module ready for staging deployment
4. **Production**: Module in production use
5. **Deprecated**: Module marked for removal
6. **Archived**: Module removed from active use

## SARAISE-29002 Module Installation

### Installation Process

See [Module Installer](docs/architecture/examples/backend/core/module-installer.py).

**Key Methods:**
- `install_module()` - Install module with full lifecycle (validate, check dependencies, run migrations, register routes)
- `_validate_module()` - Validate module before installation
- `_check_dependencies()` - Check module dependencies
- `_run_migrations()` - Run module migrations

## SARAISE-29003 Module Upgrade

### Upgrade Process

See [Module Upgrader](docs/architecture/examples/backend/core/module-upgrader.py).

**Key Methods:**
- `upgrade_module()` - Upgrade module from one version to another (backup, run migrations, migrate data)
- `_backup_module_data()` - Backup module data before upgrade
- `_run_upgrade_migrations()` - Run upgrade migrations

## SARAISE-29004 Module Uninstallation

### Uninstallation Process

See [Module Uninstaller](docs/architecture/examples/backend/core/module-uninstaller.py).

**Key Methods:**
- `uninstall_module()` - Uninstall module with optional data retention
- `_get_dependent_modules()` - Get modules that depend on this module

## SARAISE-29005 Module Versioning

### Version Management

See [Module Version Manager](docs/architecture/examples/backend/core/module-version-manager.py).

**Key Methods:**
- `get_module_version()` - Get installed module version
- `get_module_version_history()` - Get module version history
- `check_for_updates()` - Check for module updates

## SARAISE-29006 Module State Management

### Module State Tracking

See [Module State Model](docs/architecture/examples/backend/models/module-state-model.py).

**Key Models:**
- `ModuleState` - Enum for module states (INSTALLED, ACTIVE, INACTIVE, UPGRADING, UNINSTALLING, ERROR)
- `InstalledModule` - Model for tracking installed modules

## SARAISE-29007 Module Health Checks

### Module Health Monitoring

See [Module Health Checker](docs/architecture/examples/backend/core/module-health-checker.py).

**Key Methods:**
- `check_module_health()` - Check module health status (installed, routes registered, database tables exist)

## SARAISE-29008 Module Rollback

### Rollback Process

See [Module Rollback](docs/architecture/examples/backend/core/module-rollback.py).

**Key Methods:**
- `rollback_module()` - Rollback module to previous version (backup, run rollback migrations, restore data)

## SARAISE-29009 Module Deprecation

### Deprecation Process

See [Module Deprecation](docs/architecture/examples/backend/core/module-deprecation.py).

**Key Methods:**
- `deprecate_module()` - Deprecate module with timeline (mark deprecated, notify dependents, disable installations, schedule removal)

## SARAISE-29010 Module Lifecycle Testing

### Lifecycle Test Patterns

See [Module Lifecycle Tests](docs/architecture/examples/backend/tests/test-module-lifecycle.py) for complete test examples.

**Required Tests:**
- Module installation
- Module upgrade
- Module uninstallation

---

**Next Steps**: Use these lifecycle management patterns to install, upgrade, and uninstall modules. Ensure all lifecycle operations are properly tested and documented.

---
# 🎨 SARAISE Customization Framework

**⚠️ CRITICAL**: All customizations MUST follow approved architecture patterns to ensure consistency, maintainability, and upgrade compatibility.

**Related Documentation:**
- Module Framework: `docs/architecture/module-framework.md`

## SARAISE-30001 Customization Principles

### Core Principles
- **Custom Fields**: Extend standard data models per tenant
- **Workflow Customization**: Tenant-specific workflow configurations  
- **Module Configuration**: Tenant-level module settings
- **Data Model Extensions**: Controlled schema extensions via migrations

### Customization Scope
- Customizations are tenant-scoped
- Platform configuration is controlled by platform team
- Custom fields validated against module schema rules
- No schema forks - use platform migration patterns

## SARAISE-30002 Custom Field Support

**Tenant-Level Field Extensions:**
- Tenants can add custom fields to module entities
- Custom fields stored in structured extension tables
- Validation enforced by platform
- Indexed for query performance

**Restrictions:**
- Cannot modify core fields
- Cannot break platform constraints
- Must respect tenant_id boundaries
- Subject to module upgrade compatibility

## SARAISE-30003 Workflow Customization

**Tenant Workflow Configuration:**
- Tenants customize workflow states and transitions
- Platform enforces SoD constraints
- Approval chains tenant-configurable
- Workflow definitions validated against module rules

## SARAISE-30004 Module Configuration

**Per-Tenant Module Settings:**
- Feature flags per module per tenant
- Business rules customization
- Integration settings tenant-scoped
- Configuration stored and versioned

## SARAISE-30005 Customization Testing

### Required Tests
- Test custom field addition and validation
- Test workflow customization doesn't violate SoD
- Test tenant isolation for customizations
- Test upgrade compatibility with customizations

---

**Next Steps**: Use approved customization patterns within module framework boundaries. Reference `docs/architecture/module-framework.md` for implementation guidelines.

---
# 🔧 SARAISE Tenant-Level Customization

**⚠️ CRITICAL**: All customizations are tenant-scoped and must not modify core code.

**Related Documentation:**
- Module Framework: `docs/architecture/module-framework.md`

## SARAISE-31001 Customization Overview

### Core Principles
- **No Core Code Changes**: Customizations must not modify platform code
- **Tenant-Scoped**: All customizations are tenant-specific
- **Upgrade Compatible**: Customizations must survive platform upgrades
- **Platform-Controlled**: Customization capabilities defined by platform

### Customization Types
- **Custom Fields**: Add fields to standard entities
- **Workflow Customization**: Customize approval workflows
- **Module Configuration**: Configure module behavior per tenant
- **Integration Settings**: Tenant-specific integration configs

## SARAISE-31002 Custom Fields

**Custom Field Management:**
- Stored in extension tables with tenant_id
- Validated against module field type rules
- Indexed for query performance
- Subject to platform upgrade compatibility

## SARAISE-31003 Workflow Customization

**Tenant Workflow Rules:**
- State machines customizable per tenant
- Transitions validated against SoD rules
- Approval chains tenant-defined
- Platform enforces workflow integrity

## SARAISE-31004 Module Settings

**Per-Tenant Module Configuration:**
- Feature toggles per module
- Business rule parameters
- Integration endpoints and credentials
- Stored encrypted where sensitive

## SARAISE-31005 Customization Validation

**Platform Enforcement:**
- Customizations validated at creation
- Compatibility checked on platform upgrades
- Tenant isolation enforced
- Cannot violate core platform constraints

---

**Audit**: Version 8.0.0; Updated 2026-01-03
