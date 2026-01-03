<!-- SPDX-License-Identifier: Apache-2.0 -->
# Contributing to SARAISE

Thank you for your interest in contributing to **SARAISE** — the Secure and Reliable AI Symphony ERP platform!

We welcome contributions from the community and are grateful for your support. This guide will help you understand how to contribute effectively.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Architecture is Supreme](#architecture-is-supreme)
- [Development Workflow](#development-workflow)
- [Quality Gates](#quality-gates)
- [Contribution Types](#contribution-types)
- [Pull Request Process](#pull-request-process)
- [Testing Requirements](#testing-requirements)
- [Documentation](#documentation)
- [Contributor License Agreement](#contributor-license-agreement)
- [Getting Help](#getting-help)

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to conduct@saraise.com.

---

## Getting Started

### Prerequisites

- **Python**: 3.11+
- **Node.js**: 20.10.0+
- **PostgreSQL**: 14+
- **Redis**: 7.0+
- **Git**: 2.40+

### Setup Development Environment

1. **Clone the repository**:
   ```bash
   git clone https://github.com/buildworksai/saraise.git
   cd saraise
   ```

2. **Install pre-commit hooks** (MANDATORY):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

3. **Backend setup**:
   ```bash
   cd backend
   pip install -e .[dev]
   python manage.py migrate
   ```

4. **Frontend setup**:
   ```bash
   cd frontend
   npm ci
   ```

5. **Run tests to verify setup**:
   ```bash
   cd backend && pytest tests -v
   cd frontend && npm test
   ```

---

## Architecture is Supreme

⚠️ **CRITICAL**: The application architecture in `docs/architecture/` is **frozen and authoritative**.

### Non-Negotiable Rules

1. **Architecture freeze** is enforced — see [Architecture Freeze and Change Control](docs/architecture/architecture-freeze-and-change-control.md)
2. **Multi-tenant row-level isolation** — ALL tenant-scoped tables MUST have `tenant_id`
3. **Session-based authentication only** — NO JWT for interactive users (see [Authentication Spec](docs/architecture/authentication-and-session-management-spec.md))
4. **Modular architecture** — Modules in `backend/src/modules/` with `manifest.yaml` contracts
5. **Static route registration** — Routes registered in `backend/src/main.py` only
6. **RBAC with Policy Engine** — Authorization via Policy Engine, not in-session caching

### Before Contributing

1. Read [Application Architecture](docs/architecture/application-architecture.md)
2. Review [Module Framework](docs/architecture/module-framework.md)
3. Check [Security Model](docs/architecture/security-model.md)
4. Understand [Policy Engine Spec](docs/architecture/policy-engine-spec.md)

**If your contribution conflicts with architecture, it will be rejected.**

---

## Development Workflow

### Branch Strategy

- `main` — Production-ready, protected
- `develop` — Integration branch
- `feature/*` — New features
- `fix/*` — Bug fixes
- `docs/*` — Documentation updates

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`

**Examples**:
```bash
feat(crm): add customer credit limit validation
fix(auth): resolve session cookie expiration edge case
docs(api): update API documentation for billing module
test(hr): increase payroll calculation test coverage
```

### Pre-Commit Hooks

**ALL commits MUST pass pre-commit checks** — no exceptions.

Enforced checks:
- **TypeScript**: Zero errors (`tsc --noEmit`)
- **ESLint**: Zero warnings (`--max-warnings 0`)
- **Python**: Black formatting, isort, flake8, mypy
- **God Controller**: No `db.add()`, `db.commit()`, `db.rollback()` in route files
- **File quality**: Trailing whitespace, YAML/JSON validation, merge conflicts

Run manually:
```bash
pre-commit run --all-files
```

**Bypassing pre-commit hooks is forbidden and will result in PR rejection.**

---

## Quality Gates

### Testing Requirements

- **≥90% code coverage** (enforced by CI)
- Backend: `cd backend && pytest tests -v --cov=src --cov-report=html`
- Frontend: `cd frontend && npm test`

### Type Safety

- **Backend**: MyPy with strict mode for new files
- **Frontend**: TypeScript with zero errors (SARAISE-04002)

### Code Quality

**Backend**:
```bash
cd backend
black src tests
isort src tests
flake8 src tests --max-line-length=120
mypy src
```

**Frontend**:
```bash
cd frontend
npx tsc --noEmit
npx eslint src --ext .ts,.tsx --max-warnings 0
```

### Anti-Patterns (Will Be Rejected)

❌ Omitted `tenant_id` in tenant-scoped models  
❌ JWT tokens for interactive users  
❌ Dynamic route registration  
❌ Skipping tests  
❌ Modules without `manifest.yaml`  
❌ Database transactions in route handlers  
❌ Bypassing pre-commit hooks  
❌ Using `any` type in TypeScript  

---

## Contribution Types

### 1. Bug Fixes

- Create an issue first describing the bug
- Reference the issue in your PR
- Include tests demonstrating the fix
- Update CHANGELOG.md

### 2. New Features

**For new modules**:
1. Review [Module Framework](docs/architecture/module-framework.md)
2. Create module structure in `backend/src/modules/{module_name}/`
3. Provide `manifest.yaml` contract
4. Register routes in `backend/src/main.py`
5. Create Django migration: `python manage.py makemigrations module_name`
6. Write tests (≥90% coverage)
7. Document in `docs/modules/{module_name}.md`

**For feature enhancements**:
- Discuss in an issue first
- Ensure alignment with architecture
- Follow existing patterns

### 3. Documentation

- Technical docs in `docs/`
- API docs as OpenAPI specs
- Module docs in `docs/modules/`
- Update README.md if needed

### 4. Performance Improvements

- Include benchmarks
- Document methodology
- Ensure no regression in functionality

---

## Pull Request Process

### Before Submitting

1. ✅ All tests pass locally
2. ✅ Pre-commit hooks pass
3. ✅ Code coverage ≥90%
4. ✅ TypeScript compiles with zero errors
5. ✅ Documentation updated
6. ✅ CHANGELOG.md updated

### PR Template

When creating a PR, include:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Architecture Compliance
- [ ] No architectural changes introduced
- [ ] Changes align with frozen architecture
- [ ] Relevant architecture spec: [link]

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Coverage ≥90%

## Checklist
- [ ] Pre-commit hooks pass
- [ ] TypeScript compiles with zero errors
- [ ] CHANGELOG.md updated
- [ ] Documentation updated
- [ ] CLA signed
```

### Review Process

1. **Automated checks** — CI must pass
2. **Code review** — At least 1 approval required
3. **Architecture review** — For core/platform changes
4. **Testing verification** — Coverage and quality gates

### Merge Requirements

- All CI checks pass
- Approved by maintainers
- No merge conflicts
- Branch up to date with target

---

## Testing Requirements

### Backend Testing

```bash
cd backend
pytest tests -v --cov=src --cov-report=html
```

**Test structure**:
- Use fixtures from `backend/tests/conftest.py`
- Test files in `backend/src/modules/*/tests/`
- Cover happy paths, edge cases, and error scenarios

### Frontend Testing

```bash
cd frontend
npm test
```

**Test patterns**:
- React Testing Library for components
- TanStack Query testing utilities for data hooks
- Vitest for unit tests

---

## Documentation

### Required Documentation

1. **Architecture docs** — In `docs/architecture/` (changes require ACP)
2. **Module docs** — In `docs/modules/` for each business module
3. **API docs** — OpenAPI specifications
4. **Code comments** — For complex logic

### Documentation Standards

- Use Markdown
- Include code examples
- Update CHANGELOG.md
- Keep AGENTS.md synchronized

---

## Contributor License Agreement

By contributing, you agree to our [Contributor License Agreement](CLA.md).

**Key points**:
- Grant copyright license for your contributions
- Grant patent license
- Represent that contributions are your original work
- No obligation for us to use your contribution

Your first PR will be considered your CLA signature.

---

## Getting Help

### Resources

- **Documentation**: `docs/architecture/` and `docs/modules/`
- **Agent instructions**: `AGENTS.md`
- **Architecture rules**: `.agents/rules/`

### Communication Channels

- **Issues**: [GitHub Issues](https://github.com/buildworksai/saraise/issues)
- **Discussions**: [GitHub Discussions](https://github.com/buildworksai/saraise/discussions)
- **Email**: dev@saraise.com
- **Security**: security@saraise.com

### Reporting Issues

Use our issue templates:
- Bug report
- Feature request
- Security vulnerability (see [SECURITY.md](SECURITY.md))

---

## Recognition

Contributors are recognized in:
- CHANGELOG.md
- GitHub contributors page
- Release notes

---

## License

By contributing to SARAISE, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

---

**Thank you for contributing to SARAISE!**

We value your time and effort in making this platform better for everyone.

---

**Last Updated**: 2026-01-03
