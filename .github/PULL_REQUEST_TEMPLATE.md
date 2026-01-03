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
- [ ] Manual testing completed

### Test Results

```bash
# Backend tests
cd backend && pytest
# Results: [Pass/Fail with details]

# Frontend tests
cd frontend && npm test
# Results: [Pass/Fail with details]
```

### Coverage

- **Current Coverage**: [XX%]
- **Target Coverage**: 90%+
- **Coverage Report**: [Link if available]

## Security Considerations

<!-- Mark all that apply -->

- [ ] Authentication/authorization reviewed
- [ ] Input validation added
- [ ] SQL injection prevention verified
- [ ] XSS prevention verified
- [ ] CSRF protection verified
- [ ] Audit logging added (if applicable)
- [ ] RBAC properly enforced (if applicable)
- [ ] Tenant isolation verified (if applicable)
- [ ] Security rules followed (see `.agents/rules/`)

### Security Checklist

- [ ] No hardcoded secrets or credentials
- [ ] Environment variables used for configuration
- [ ] Sensitive data properly encrypted
- [ ] Rate limiting considered (if applicable)
- [ ] Error messages don't expose sensitive information

## Architecture Compliance

<!-- Verify compliance with SARAISE architecture principles (FROZEN ARCHITECTURE) -->

- [ ] Follows modular architecture (see `.agents/rules/15-module-architecture.md`)
- [ ] Uses session-based authentication (no JWT) - see `.agents/rules/10-session-auth.md`
- [ ] Implements RBAC with deny-by-default - see `.agents/rules/12-auth-enforcement.md`
- [ ] Maintains tenant isolation - see `.agents/rules/21-platform-tenant.md`
- [ ] Includes audit logging for sensitive operations - see `.agents/rules/11-audit-logging.md`

## Code Quality

### Backend (Python)

- [ ] Type hints added to all functions
- [ ] Follows PEP 8 style guidelines
- [ ] Code formatted with Black
- [ ] Linting passes (Flake8)
- [ ] No `# type: ignore` without justification
- [ ] Async/await used for I/O operations

### Frontend (TypeScript/React)

- [ ] TypeScript strict mode compliant
- [ ] No `any` types (use `unknown` or generics)
- [ ] React hooks called before early returns
- [ ] Component props properly typed
- [ ] ESLint passes with zero warnings
- [ ] No console.log statements in production code

## Documentation

- [ ] Code comments added for complex logic
- [ ] Docstrings added to public functions/classes
- [ ] README updated (if applicable)
- [ ] API documentation updated (if applicable)
- [ ] Architecture docs updated (if applicable)
- [ ] Changelog updated (if applicable)

## Performance

- [ ] Database queries optimized
- [ ] N+1 queries avoided
- [ ] Caching considered (if applicable)
- [ ] Frontend bundle size checked
- [ ] Performance impact assessed

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

- Verify all checklist items are completed
- Check code quality and architecture compliance
- Ensure tests are comprehensive
- Verify security considerations are addressed
- Confirm documentation is updated

---

Thank you for contributing to SARAISE! 🎉
