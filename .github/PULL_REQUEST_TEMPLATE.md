# Pull Request

## Description

<!-- Provide a clear and concise description of what this PR does -->

## Type of Change

<!-- Mark the relevant option with an 'x' -->

- [ ] 🐛 Bug fix (non-breaking change which fixes an issue)
- [ ] ✨ New feature (non-breaking change which adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] 📚 Documentation update
- [ ] 🧪 Test addition/update
- [ ] 🔧 Refactoring (no functional changes)
- [ ] ⚡ Performance improvement
- [ ] 🔒 Security fix
- [ ] 📦 Module addition/update
- [ ] 🎨 UI/UX improvement

## Related Issues

<!-- Link related issues using keywords (e.g., Closes #123, Fixes #456, Related to #789) -->

Closes #
Related to #

## Changes Made

<!-- Provide a detailed list of changes -->

- [Change 1]
- [Change 2]
- [Change 3]

## Testing

### Test Coverage

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] E2E tests added/updated (if applicable)
- [ ] Tenant isolation tests added (for new models)
- [ ] Manual testing completed

### Test Results

```bash
# Backend tests
cd backend && pytest tests/ --cov=src --cov-report=term
# Results: [Pass/Fail with details]

# Frontend tests
cd frontend && npm test
# Results: [Pass/Fail with details]
```

### Coverage

- **Current Coverage**: [XX%]
- **Target Coverage**: 90%+
- **Coverage Report**: [Link if available]

## Architecture Compliance (FROZEN ARCHITECTURE)

<!-- These are non-negotiable. Verify ALL applicable items. -->

### Multi-Tenancy (REQUIRED)

- [ ] All tenant-scoped models have `tenant_id` column
- [ ] All queries filter by `tenant_id`
- [ ] Tenant isolation tests included for new models
- [ ] No cross-tenant data access possible

### Authentication (FROZEN)

- [ ] Uses session-based authentication (NO JWT for interactive users)
- [ ] No auth implementation in modules (platform-level only)
- [ ] Sessions contain identity snapshot only

### Authorization (FROZEN)

- [ ] Uses Policy Engine for authorization (deny-by-default)
- [ ] RBAC properly enforced
- [ ] No permissions cached in sessions

### Module Standards (REQUIRED for module changes)

- [ ] `manifest.yaml` present and valid
- [ ] Full stack implementation (backend + frontend + tests)
- [ ] No backend-only stubs

**Reference Architecture Documents:**
- `docs/architecture/authentication-and-session-management-spec.md`
- `docs/architecture/policy-engine-spec.md`
- `docs/architecture/module-framework.md`
- `docs/architecture/security-model.md`

## Security Considerations

<!-- Mark all that apply -->

- [ ] Authentication/authorization reviewed
- [ ] Input validation added
- [ ] SQL injection prevention verified
- [ ] XSS prevention verified
- [ ] CSRF protection verified
- [ ] Audit logging added (if applicable)
- [ ] Tenant isolation verified (if applicable)
- [ ] Security rules followed (see `.agents/rules/`)

### Security Checklist

- [ ] No hardcoded secrets or credentials
- [ ] Environment variables used for configuration
- [ ] Sensitive data properly encrypted
- [ ] Rate limiting considered (if applicable)
- [ ] Error messages don't expose sensitive information

**Reference**: `.agents/rules/07-rbac-security.md`, `.agents/rules/08-secrets-management.md`

## Code Quality

### Backend (Python)

- [ ] Type hints added to all functions
- [ ] Follows PEP 8 style guidelines
- [ ] Code formatted with Black
- [ ] Linting passes (Flake8)
- [ ] No `# type: ignore` without justification
- [ ] Business logic in services (not route handlers)

### Frontend (TypeScript/React)

- [ ] TypeScript strict mode compliant
- [ ] No `any` types (use `unknown` or generics)
- [ ] React hooks called before early returns
- [ ] Component props properly typed
- [ ] ESLint passes with zero warnings
- [ ] No console.log statements in production code

**Reference**: `.agents/rules/04-backend-standards.md`, `.agents/rules/05-frontend-standards.md`

## Performance

<!-- Verify compliance with performance SLAs -->

- [ ] API latency within targets (p99 ≤200ms for writes, ≤50ms for reads)
- [ ] Database queries optimized
- [ ] N+1 queries avoided
- [ ] Indexes added for `tenant_id` and frequently queried fields
- [ ] Caching considered (if applicable)
- [ ] Frontend bundle size checked

**Reference**: `docs/architecture/performance-slas.md`

## Documentation

- [ ] Code comments added for complex logic
- [ ] Docstrings added to public functions/classes
- [ ] README updated (if new folder created)
- [ ] API documentation updated (if applicable)
- [ ] Architecture docs updated (if applicable)
- [ ] Changelog updated (if applicable)

## Pre-Commit Checks

```bash
# Run pre-commit hooks
pre-commit run --all-files

# Backend quality checks
cd backend && black src tests && flake8 src tests && mypy src

# Frontend quality checks
cd frontend && npx tsc --noEmit && npx eslint src --ext .ts,.tsx --max-warnings 0
```

- [ ] All pre-commit hooks pass
- [ ] No quality gate bypasses

## Breaking Changes

<!-- If this is a breaking change, describe the impact and migration path -->

**Breaking Changes**: [Yes/No]

**Migration Guide**: [If applicable, describe how users should migrate]

**Deprecation Notice**: [If applicable, describe deprecated features]

## Screenshots

<!-- If applicable, add screenshots to help explain your changes -->

## Checklist

<!-- Mark all that apply -->

- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published
- [ ] I have updated the CHANGELOG.md (if applicable)

## Additional Notes

<!-- Add any additional context, questions, or notes for reviewers -->

---

**Reviewer Guidelines**:

1. Verify all checklist items are completed
2. Check architecture compliance (multi-tenancy, session auth, policy engine)
3. Verify tenant isolation tests for new models
4. Ensure tests are comprehensive (≥90% coverage)
5. Confirm security considerations are addressed
6. Verify performance SLAs are met
7. Confirm documentation is updated

**Key Architecture Documents to Reference:**
- `docs/architecture/application-architecture.md`
- `docs/architecture/security-model.md`
- `docs/architecture/performance-slas.md`
- `docs/architecture/test-architecture.md`

---

Thank you for contributing to SARAISE! 🎉
