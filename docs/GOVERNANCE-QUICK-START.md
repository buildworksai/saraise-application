# Governance Quick Start Guide

**SPDX-License-Identifier: Apache-2.0**  
**Purpose**: Quick reference for governance tools and processes

---

## 🚀 Quick Commands

### Pre-Commit Hooks
```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run all hooks manually
pre-commit run --all-files
```

### Security Scanning

#### SAST (Semgrep)
```bash
# Install
pip install semgrep

# Run scan
semgrep --config=auto --config=.semgrep/custom-rules.yaml --json

# Establish baseline
./scripts/semgrep-baseline.sh
```

#### DAST (OWASP ZAP)
```bash
# Test locally (requires Docker)
docker-compose -f docker-compose.dev.yml up -d
docker run -t owasp/zap2docker-stable zap-baseline.py -t http://localhost:8000
```

### Coverage Verification
```bash
# Per-module coverage check
python3 scripts/coverage-per-module.py

# Overall coverage
cd backend && pytest tests/ --cov=src --cov-report=term
cd frontend && npm test -- --coverage
```

### Workflow Validation
```bash
# Install actionlint
brew install actionlint

# Validate workflows
./scripts/validate-workflows.sh
```

### GCR Management
```bash
# Populate entities
python3 scripts/populate-gcr-entities.py

# Initialize dimensions
python3 scripts/compliance-dimensions-init.py

# Collect compliance data
python3 scripts/gcr-collector.py
```

---

## 📋 Pre-PR Checklist

Before creating a PR:

- [ ] Pre-commit hooks pass: `pre-commit run --all-files`
- [ ] TypeScript compiles: `cd frontend && npm run typecheck`
- [ ] ESLint passes: `cd frontend && npm run lint`
- [ ] Python quality: `cd backend && black --check . && flake8 . && mypy src`
- [ ] Tests pass: `cd backend && pytest tests/`
- [ ] Coverage ≥90%: `coverage report --fail-under=90`
- [ ] No secrets: `detect-secrets scan`

---

## 🔒 Tier 0 Changes

If modifying Tier 0 paths:
- [ ] Use Tier 0 PR template
- [ ] Complete mandatory checklist
- [ ] Get 2 senior reviewers
- [ ] Link ACP if architecture change

**Tier 0 Paths**:
- `backend/src/core/auth/`
- `backend/src/core/licensing/`
- `backend/src/core/encryption/`

---

## 🛡️ Security Rules

### Always Block
- Critical SAST findings
- Critical DAST findings
- Container vulnerabilities (critical/high)
- Hardcoded secrets
- JWT for interactive users

### Review Required
- High SAST findings
- High DAST findings
- Medium security issues

---

## 📊 Compliance Dimensions

| Dimension | Threshold | Enforcement |
|-----------|-----------|-------------|
| SAST | ZERO critical/high | Blocking |
| DAST | ZERO critical | Blocking |
| Container | ZERO critical/high | Blocking |
| Coverage | ≥90% | Blocking |
| TypeScript | ZERO errors | Blocking |
| ESLint | ZERO warnings | Blocking |
| Complexity | ≤15 | Blocking |

---

## 🐛 Troubleshooting

### Pre-commit Fails
```bash
# Update hooks
pre-commit autoupdate

# Run specific hook
pre-commit run semgrep --all-files
```

### Coverage Below Threshold
```bash
# Check per-module
python3 scripts/coverage-per-module.py

# Generate detailed report
cd backend && pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

### Semgrep False Positives
1. Review finding in `semgrep-baseline.json`
2. Update `.semgrep/custom-rules.yaml`
3. Add exclusion or downgrade severity

---

## 📚 Documentation

- **DAST Testing**: `docs/DAST-TESTING.md`
- **Semgrep Baseline**: `docs/SEMGREP-BASELINE.md`
- **Governance Fix Pack**: `saraise-documentation/reports/governance-fix-pack-implementation-summary.md`

---

## 🔗 Useful Links

- [Semgrep Rules](https://semgrep.dev/r)
- [OWASP ZAP Docs](https://www.zaproxy.org/docs/)
- [GitHub Actions](https://docs.github.com/en/actions)

---

**Last Updated**: January 12, 2026
