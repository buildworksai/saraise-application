# SARAISE Licensing Subsystem

**Phase 7.5: Licensing Subsystem - COMPLETE**

## Overview

The licensing subsystem provides license validation, trial management, and module access control for self-hosted SARAISE deployments.

## Features

- ✅ **14-day trial period** - Automatically starts on first user registration
- ✅ **License validation** - Connected mode (online) and isolated mode (offline keys)
- ✅ **Grace period** - 30-day grace period when license server is unreachable
- ✅ **Soft lock** - Read-only mode when license expires (data accessible, writes blocked)
- ✅ **Module access control** - Foundation/Core/Industry module gating
- ✅ **Audit logging** - All validation attempts logged

## Architecture

### Django Models

- `Organization` - Organization bound to license key
- `License` - License record with status, trial, expiry tracking
- `LicenseValidationLog` - Audit log for all validations

### Services

- `LicenseService` - License validation and management
- `ModuleAccessService` - Module access control

### Middleware

- `LicenseValidationMiddleware` - Request-level license validation (only active in self-hosted mode)

### Decorators

- `@requires_license` - Require valid license for endpoint
- `@requires_module(module_name)` - Require specific module access
- `@requires_write_access(module_name)` - Require write permissions (enforce soft lock)

## Usage

### Registration (Self-Hosted Mode)

When the first user registers in self-hosted mode, a 14-day trial is automatically initialized:

```python
POST /api/v1/auth/register/
{
    "email": "user@example.com",
    "password": "secure_password",
    "organization_name": "My Company"
}
```

### License Validation

License validation happens automatically:
- On application startup
- Periodically (every 24 hours) via middleware
- On module access checks

### Module Access Control

```python
from src.core.licensing.decorators import requires_module, requires_write_access

@requires_module("manufacturing")
def manufacturing_api(request):
    # Only accessible if manufacturing module is licensed
    ...

@requires_write_access("crm")
def update_customer(request):
    # Only writable if license is valid (not expired)
    ...
```

## Configuration

### Environment Variables

```bash
# Operating mode
SARAISE_MODE=self-hosted  # or 'development' or 'saas'

# License mode (only for self-hosted)
SARAISE_LICENSE_MODE=connected  # or 'isolated'

# License server URL (for connected mode)
SARAISE_LICENSE_SERVER_URL=https://license.saraise.com

# License public key (for isolated mode - PEM format)
SARAISE_LICENSE_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
```

### Settings

The middleware is automatically registered in `settings.py` but only active in self-hosted mode.

## Module Categories

### Foundation Modules (Always Free)
- Always accessible regardless of license status
- Always writable (even when license expired)

Examples: `platform_management`, `ai_agent_management`, `workflow_automation`

### Core Modules (Free for Single Company)
- Accessible during trial and with active license
- Read-only when license expired (soft lock)
- Write access requires valid license

Examples: `crm`, `accounting_finance`, `inventory_management`

### Industry Modules (Require Purchase)
- Must be explicitly included in license
- Accessible only when licensed
- Subject to soft lock when license expires

Examples: `manufacturing`, `healthcare`, `retail`

## Testing

Run tests with:

```bash
cd backend
pytest src/core/licensing/tests/ -v --cov=src/core/licensing --cov-report=html --cov-fail-under=90
```

## Migration

Apply the migration:

```bash
python manage.py migrate core
```

## Reference

- Phase Document: `saraise-documentation/planning/phases/phase-7.5-licensing.md`
- Architecture: `saraise-documentation/licensing/licensing-architecture.md`
