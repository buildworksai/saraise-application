---
description: Module Architecture & Dependencies
globs: backend/src/modules/**/*.py
alwaysApply: true
---

# 🔗 SARAISE Module Dependencies & Integration

**⚠️ CRITICAL**: All module dependencies MUST be properly declared and managed to prevent conflicts and ensure compatibility.

**Rule IDs**: SARAISE-26001 to SARAISE-26010, SARAISE-28001 to SARAISE-28010

**Related Documentation:**
- Module Framework: `docs/architecture/module-framework.md`
- Application Architecture: `docs/architecture/application-architecture.md`

## SARAISE-28001 Module Dependency Management

### Dependency Declaration

Modules declare dependencies in `manifest.yaml` per `docs/architecture/module-framework.md` (§ 3.1). Example:

```yaml
name: finance-ledger
version: 1.3.0
dependencies:
  - core-identity >=1.0
  - core-workflow >=1.0
```

## SARAISE-28002 Dependency Resolution

### Dependency Resolver

See [Module Dependency Resolver](docs/architecture/examples/backend/core/module-dependency-resolver.py).

## SARAISE-28003 Module Integration Patterns

### Service Integration

See [Module Service Integration](docs/architecture/examples/backend/services/module-service-integration.py).

## SARAISE-28004 Module Event System

### Event-Based Integration

See [Module Event System](docs/architecture/examples/backend/core/module-events.py).

## SARAISE-28005 Module API Integration

### Cross-Module API Calls

See [Module API Integration](docs/architecture/examples/backend/services/module-api-integration.py).

## SARAISE-28006 Module Data Sharing

### Shared Data Patterns

See [Module Data Sharing](docs/architecture/examples/backend/core/module-data-sharing.py).

## SARAISE-28007 Module Version Compatibility

### Version Compatibility Check

See [Module Compatibility Checker](docs/architecture/examples/backend/core/module-compatibility.py).

## SARAISE-28008 Module Dependency Injection

### Dependency Injection Patterns

See [Module Dependency Injection](docs/architecture/examples/backend/services/module-dependency-injection.py).

## SARAISE-28009 Module Conflict Resolution

### Conflict Detection and Resolution

See [Module Conflict Resolver](docs/architecture/examples/backend/core/module-conflict-resolver.py).

## SARAISE-28010 Module Dependency Testing

### Dependency Test Patterns

See [Module Dependency Testing Examples](docs/architecture/examples/backend/tests/test_module_dependencies.py) for complete test examples.

---

**Next Steps**: Use these patterns to manage module dependencies. Ensure all dependencies are properly declared and conflicts are resolved before module installation.

---

**Audit**: Version 7.0.0; Consolidated 2025-12-23
