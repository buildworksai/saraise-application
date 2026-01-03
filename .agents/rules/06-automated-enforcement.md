---
description: Automated local enforcement via pre-commit hooks; DRY references to quality gates
globs: **/*
alwaysApply: true
---

# 🤖 SARAISE Automated Enforcement — Local (Pre-Commit) & Automated Enforcement — CI/CD

**⚠️ TECH STACK CONFIGURATION**: All technology versions are defined in `03-tech-stack.md`.
This file references tech versions with fallback defaults.
To change tech versions, update the environment variables in `03-tech-stack.md`.

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Engineering Governance: `docs/architecture/engineering-governance-and-pr-controls.md`

## SARAISE-04001 Pre-Commit Hook Mandatory
- Run `tsc --noEmit` (SARAISE-04002: Zero TS errors) across **all** `frontend/src/**/*.{ts,tsx}` (no partial scopes, no exclusions for “legacy” domains).
- Run `eslint` with `--max-warnings 0` using rules that treat unused imports/variables and `any`-heavy patterns as **errors**, not warnings.
- Optional: run unit tests for changed packages
- Reference quality checks only in CI; do not expose secrets locally

## SARAISE-04002 Zero TypeScript Errors
- Commit is blocked on **any** TypeScript error from `tsc --noEmit`, regardless of directory:
  - No “temporary” ignores of `frontend/src/pages/**`.
  - No “only check changed files” loopholes for TypeScript.

## SARAISE-04003 Security Secrets Detection
- No hardcoded secrets committed; rely on scanner rules in CI.

## SARAISE-04004 DRY Cross-References
- Thresholds and metrics are defined in `02-quality-enforcement.md`.

## SARAISE-04005 Quality Gate Workflow (reference)

See [Quality Gate Workflow](docs/architecture/examples/infrastructure/ci-cd/quality-gate-workflow.yml).

**Key Steps:**
- TypeScript check (`tsc --noEmit`) - SARAISE-04002
- Test coverage ≥ 90%
- Frontend build when frontend/ changed
- Security audit

## SARAISE-04006 Deployment Gates
- Pre: quality gate passed, security scan clean
- Post: health checks + smoke tests

## SARAISE-04007 Branch Protection
- Require checks: TypeScript, ESLint, Tests, SonarQube

## SARAISE-04008 Environment-Aware Security Testing Pipeline
- **Development Environment:** Basic security checks for rapid development
- **Staging Environment:** Standard security testing for validation
- **Production Environment:** Comprehensive security testing for deployment

### Environment-Specific Security Testing

See [Environment-Aware Security Testing Pipeline](docs/architecture/examples/infrastructure/ci-cd/environment-aware-security-pipeline.yml).

**Key Features:**
- Development: Basic security checks
- Staging: Standard security testing (SAST, dependency scan)
- Production: Comprehensive security testing (SAST, DAST, container scan)

### Environment-Specific Security Scripts

See [Security Scripts](docs/architecture/examples/infrastructure/package-security-scripts.json).

**Key Scripts:**
- `lint:security:*` - Environment-aware linting
- `test:security:*` - Environment-aware security testing
- `sast:scan` - Static Application Security Testing
- `dast:scan` - Dynamic Application Security Testing
- `dependency:scan` - Dependency vulnerability scanning
- `container:security:scan` - Container image scanning

## SARAISE-04009 Environment-Aware Pre-Commit Hooks
- **Development Environment:** Basic pre-commit checks for productivity
- **Staging Environment:** Standard pre-commit checks for quality
- **Production Environment:** Comprehensive pre-commit checks for security

### Environment-Specific Pre-Commit Configuration

See [Pre-Commit Configuration](docs/architecture/examples/infrastructure/pre-commit-config.yaml).

**Key Features:**
- TypeScript check for all environments
- ESLint check with zero warnings
- Environment-specific security checks
- SAST scan for production

## SARAISE-04010 Environment-Aware CI/CD Security Gates
- **Development Environment:** Basic quality gates for rapid iteration
- **Staging Environment:** Standard quality gates for validation
- **Production Environment:** Maximum quality gates for deployment

### Environment-Specific Quality Gates

See [Environment-Aware Quality Gates](docs/architecture/examples/infrastructure/ci-cd/environment-aware-quality-gates.yml).

**Key Features:**
- Development: Coverage ≥ 70%, basic security audit
- Staging: Coverage ≥ 80%, standard security scans
- Production: Coverage ≥ 90%, comprehensive security scans, frontend build enforcement

## SARAISE-04011 Security Monitoring & Alerting
- **Development Environment:** Basic logging for debugging
- **Staging Environment:** Standard monitoring for testing
- **Production Environment:** Comprehensive monitoring for security

### Environment-Specific Security Monitoring

See [Security Monitoring & Alerting](docs/architecture/examples/backend/services/security-monitoring.py).

**Key Features:**
- Development: Basic logging (INFO level)
- Staging: Standard logging with alerts (WARNING level)
- Production: Comprehensive logging with SIEM integration (ERROR level)
- Monitor authentication and authorization events

## SARAISE-04012 Complete Testing Implementation

### Backend Testing Examples

See [Backend Testing Examples](docs/architecture/examples/backend/tests/test_auth.py).

**Key Features:**
- Test database setup with fixtures
- Authentication tests (user creation, login, protected endpoints)
- AI agent management tests
- Multi-tenant isolation tests

### Frontend Testing Examples

See [Frontend Testing Examples](docs/architecture/examples/frontend/__tests__/auth.test.tsx).

**Key Features:**
- Auth context testing
- Login/logout flow tests
- Role checking tests
- Session cookie handling tests

### Integration Testing Examples

See [Integration Testing Examples](docs/architecture/examples/backend/tests/test_integration.py).

**Key Features:**
- Agent lifecycle tests (create, get, update, delete)
- Workflow creation and execution tests
- End-to-end integration scenarios
