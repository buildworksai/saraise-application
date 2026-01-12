# Semgrep Baseline Guide

**SPDX-License-Identifier: Apache-2.0**  
**Purpose**: Guide for establishing and maintaining Semgrep baseline

---

## Overview

Semgrep is a static analysis tool (SAST) that scans code for security vulnerabilities and code quality issues.

**Configuration**: `.semgrep.yml` and `.semgrep/custom-rules.yaml`  
**Baseline Script**: `scripts/semgrep-baseline.sh`

---

## Establishing Baseline

### 1. Run Baseline Script

```bash
cd saraise-application
./scripts/semgrep-baseline.sh
```

This will:
- Install Semgrep (if not present)
- Run scan with auto-config and custom rules
- Generate `semgrep-baseline.json`
- Show summary of findings

### 2. Review Findings

```bash
# View findings by severity
jq '.results[] | select(.extra.severity == "ERROR")' semgrep-baseline.json

# Count findings
jq '[.results[] | select(.extra.severity == "ERROR")] | length' semgrep-baseline.json
```

### 3. Address Critical Findings

**Critical/High findings (ERROR severity) must be addressed:**
- Fix the vulnerability
- Or document why it's acceptable (with justification)
- Update custom rules to ignore if false positive

### 4. Update Custom Rules

Edit `.semgrep/custom-rules.yaml` to ignore false positives:

```yaml
rules:
  - id: ignore-false-positive
    pattern: |
      $PATTERN
    message: "Known false positive - documented in issue #XXX"
    languages: [python]
    severity: INFO
    paths:
      exclude:
        - "**/legacy_code.py"
```

---

## Custom Rules

### Current Custom Rules

1. **No JWT for Interactive Users** (SARAISE-07001)
   - Detects JWT usage (forbidden for interactive users)
   - Severity: ERROR

2. **Tenant ID Required in Queries** (SARAISE-08001)
   - Warns about queries that may be missing tenant_id filter
   - Severity: WARNING
   - Excludes: tests, migrations

3. **No Hardcoded Secrets** (SARAISE-10001)
   - Detects potential hardcoded secrets
   - Severity: ERROR

### Adding New Rules

Edit `.semgrep/custom-rules.yaml`:

```yaml
rules:
  - id: your-rule-id
    pattern: |
      $PATTERN
    message: "Description of issue"
    languages: [python, typescript]
    severity: ERROR | WARNING | INFO
    paths:
      include:
        - "backend/**/*.py"
      exclude:
        - "**/tests/**"
```

---

## CI/CD Integration

Semgrep runs in:
1. **Pre-commit hooks** - Local validation
2. **CI/CD pipeline** - `.github/workflows/ci-cd.yml`
3. **Quality guardrails** - `.github/workflows/quality-guardrails.yml`

### CI Behavior

- **Critical/High findings**: Block merge
- **Medium findings**: Warning (non-blocking)
- **Low findings**: Info only

### SARIF Upload

Results are uploaded to GitHub Security tab:
- Format: SARIF
- Location: GitHub Security → Code scanning alerts

---

## Maintenance

### Regular Updates

1. **Update Semgrep**: Monthly
   ```bash
   pip install --upgrade semgrep
   ```

2. **Review Baseline**: Quarterly
   - Re-run baseline script
   - Review new findings
   - Update custom rules

3. **Update Custom Rules**: As needed
   - Add rules for new patterns
   - Remove obsolete rules
   - Update false positive exclusions

### Baseline Regeneration

When to regenerate baseline:
- After major code changes
- After updating Semgrep version
- After adding new custom rules
- Quarterly review

---

## Common Patterns

### Ignoring False Positives

```yaml
rules:
  - id: rule-id
    pattern: |
      $PATTERN
    message: "Issue description"
    languages: [python]
    severity: INFO  # Downgrade to INFO to ignore
    paths:
      exclude:
        - "**/legacy/**"
        - "**/vendor/**"
```

### Path-Specific Rules

```yaml
rules:
  - id: strict-rule
    pattern: |
      $PATTERN
    message: "Strict rule for specific paths"
    languages: [python]
    severity: ERROR
    paths:
      include:
        - "backend/src/core/**"
        - "backend/src/modules/security/**"
```

---

## Troubleshooting

### Semgrep Not Found
```bash
pip install semgrep
```

### Too Many False Positives
- Review custom rules
- Add exclusions for known patterns
- Consider downgrading severity

### Missing Findings
- Check rule patterns
- Verify file paths in include/exclude
- Review Semgrep version compatibility

---

## Best Practices

1. **Start Strict** - Begin with ERROR severity, downgrade only with justification
2. **Document Exceptions** - Always document why a finding is ignored
3. **Regular Reviews** - Review baseline quarterly
4. **Fix, Don't Ignore** - Prefer fixing issues over ignoring them
5. **Team Awareness** - Share findings with team for learning

---

## References

- [Semgrep Documentation](https://semgrep.dev/docs/)
- [Semgrep Rules](https://semgrep.dev/r)
- [SARAISE Security Model](../saraise-documentation/architecture/existing/security-model.md)
