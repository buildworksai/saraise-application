---
description: Environment variables and secrets management standards for SARAISE multi-tenant application
globs: **/*
alwaysApply: true
---

# 🔐 SARAISE Environment Variables & Secrets Management

**⚠️ PORT CONFIGURATION**: All port numbers are defined in `09-infrastructure-config.md`.
This file references port variables with fallback defaults.
To change ports, update the environment variables in `09-infrastructure-config.md`.

## SARAISE-08001 Environment Variable Standards
- **REQUIRED:** Centralized environment variable management
- **FORBIDDEN:** Hardcoded secrets, scattered configuration files
- **PURPOSE:** Secure, consistent configuration across environments

## SARAISE-08002 Environment File Structure

See [Environment File Structure](docs/architecture/examples/config/env-file-structure.sh) for complete file structure.

**Required Files:**
- Root: `.env`, `.env.example`, `.env.production`, `.env.development`, `.env.test`
- Frontend: `.env.local`, `.env.local.example`

**Forbidden Files:**
- All `.env.backup` files and variants

## SARAISE-08002 Central Timeout & Duration Registry (SINGLE SOURCE OF TRUTH)

**⚠️ CRITICAL**: All timeout and duration values are defined here. Other files MUST reference these variables, not hardcode timeout values.

See [Timeout Environment Variables](docs/architecture/examples/config/env-timeouts.sh), [Python Timeout Helpers](docs/architecture/examples/helper-functions/python-timeout-helpers.py), and [TypeScript Timeout Helpers](docs/architecture/examples/helper-functions/typescript-timeout-helpers.ts).

## SARAISE-08003 Central Logging & Monitoring Registry (SINGLE SOURCE OF TRUTH)

**⚠️ CRITICAL**: All logging levels, monitoring settings, and observability configurations are defined here. Other files MUST reference these variables, not hardcode logging values.

See [Logging Environment Variables](docs/architecture/examples/config/env-logging.sh), [Python Logging Helpers](docs/architecture/examples/helper-functions/python-logging-helpers.py), and [TypeScript Logging Helpers](docs/architecture/examples/helper-functions/typescript-logging-helpers.ts).

## SARAISE-08004 Central File Path & Directory Registry (SINGLE SOURCE OF TRUTH)

**⚠️ CRITICAL**: All file paths, directory structures, and volume mounts are defined here. Other files MUST reference these variables, not hardcode paths.

See [File Path Environment Variables](docs/architecture/examples/config/env-paths.sh), [Python Path Helpers](docs/architecture/examples/helper-functions/python-path-helpers.py), and [TypeScript Path Helpers](docs/architecture/examples/helper-functions/typescript-path-helpers.ts).

## SARAISE-08005 Central Naming Conventions Registry (SINGLE SOURCE OF TRUTH)

**⚠️ CRITICAL**: All naming conventions, standards, and terminology are defined here. Other files MUST follow these standards consistently.

See [Naming Standards Environment Variables](docs/architecture/examples/config/env-naming.sh), [Python Naming Standards](docs/architecture/examples/backend/core/naming-standards.py), and [TypeScript Naming Standards](docs/architecture/examples/frontend/lib/naming-standards.ts).

## SARAISE-08006 Environment Variable Standards

See [Required Environment Variables](docs/architecture/examples/config/env-required.sh) for complete list of required variables.

## SARAISE-08007 Environment-Specific Configuration

See [Development Environment Configuration](docs/architecture/examples/config/env-development.sh) and [Production Environment Configuration](docs/architecture/examples/config/env-production.sh) for complete configurations.

## SARAISE-08008 Frontend Environment Variables

See [Frontend Environment Configuration](docs/architecture/examples/frontend/lib/config.ts). **Required:** `.env.local.example` with `VITE_API_URL=http://localhost:30000`

## SARAISE-08009 Backend Environment Configuration

See [Settings Configuration](docs/architecture/examples/backend/config/settings.py) and [Environment Variable Validation](docs/architecture/examples/backend/config/validation.py).

## SARAISE-08010 Environment Setup Process

See [Environment Setup Process](docs/architecture/examples/config/env-setup.sh) for complete setup steps.

## SARAISE-08011 Security Best Practices

### Environment Variable Security
- **Never commit secrets**: All `.env` files must be in `.gitignore`
- **Use example files**: Always provide `.env.example` with placeholder values
- **Validate at startup**: Check for required environment variables on application start
- **Rotate secrets regularly**: Change passwords and API keys periodically

### Environment Separation
- **Development**: `.env.development` with local database and development session keys
- **Staging**: `.env.staging` with staging database and staging session keys
- **Production**: `.env.production` with production database and secure session keys from vault
- **Testing**: `.env.test` with test database and test session keys

### Multi-tenant Security
- **Tenant isolation**: Use Row-Level Multitenancy (shared schema with explicit tenant_id filtering)
- **Environment validation**: Ensure tenant context is properly validated
- **Secret per tenant**: Consider tenant-specific configuration where needed

## SARAISE-08012 Troubleshooting

See [Debugging Commands](docs/architecture/examples/config/env-debugging.sh) for troubleshooting commands and common issues.

## SARAISE-08013 Environment-Specific Secrets Security

**Development**: Plain `.env` files allowed (must be in `.gitignore`). **Staging**: Environment variables with validation. **Production**: Encrypted secrets management (AWS KMS, Azure Key Vault, etc.) with rotation every 90 days.

See [Secrets Manager](docs/architecture/examples/backend/config/secrets-manager.py).

## SARAISE-08014 Secret Rotation Policies

**Development**: Manual rotation. **Staging**: Automated every 30 days. **Production**: Automated every 90 days with immediate alerts.

See [Secret Rotation Manager](docs/architecture/examples/backend/config/secret-rotation.py).

## SARAISE-08015 Secure Secret Injection

**Development**: Direct `.env` access. **Staging**: Environment variables with validation. **Production**: Encrypted secrets via secure APIs (AWS KMS, Azure Key Vault, etc.).

See [Secure Secret Injector](docs/architecture/examples/backend/config/secret-injection.py).

---

**Note**: This rule provides a tiered, environment-appropriate approach to secrets management for the SARAISE multi-tenant application. Development uses simple environment variables for productivity, while production uses enterprise-grade encrypted secrets management.
