# SARAISE Architecture Examples

**Status:** Aligned with Approved Architecture (Updated 2026-01-03)

This directory contains code examples that demonstrate approved architectural patterns from `docs/architecture/*.md` specifications.

## Important Notes

- **All examples align with frozen architecture specifications**
- **Sessions establish identity only** - no authorization cache
- **Policy Engine evaluates all authorization** at request time
- **Modules use manifest.yaml** format (not MODULE_MANIFEST dicts)
- **Customization patterns** - use approved tenant customization framework

## Architecture References

Core specifications (authoritative):
- `docs/architecture/authentication-and-session-management-spec.md` - Session authentication
- `docs/architecture/policy-engine-spec.md` - Authorization decisions
- `docs/architecture/security-model.md` - Security architecture
- `docs/architecture/module-framework.md` - Module patterns
- `docs/architecture/abac-attributes-architecture.md` - ABAC implementation

## Directory Structure

- `backend/` - Python/Django examples
  - `services/` - Service implementations
  - `tests/` - Test examples
  - `middleware/` - Middleware implementations
- `frontend/` - TypeScript/React examples
  - `components/` - React component examples
  - `hooks/` - Custom React hooks
  - `services/` - Frontend service implementations
- `infrastructure/` - DevOps examples
  - `docker/` - Docker configurations
  - `ci-cd/` - CI/CD pipeline examples
  - `configs/` - Configuration files
- `helper-functions/` - Helper function libraries

## Usage

Examples are referenced from `.agents/rules/` files using:
```markdown
See [Example Name](docs/architecture/examples/path/to/example.py)
```

## Key Patterns Demonstrated

1. **Session Authentication** - Identity only, no authorization cache
2. **Policy Engine Integration** - Runtime authorization evaluation
3. **Module Structure** - manifest.yaml, proper boundaries
4. **Tenant Isolation** - Row-level multitenancy patterns
5. **ABAC Implementation** - Attribute-based access control

