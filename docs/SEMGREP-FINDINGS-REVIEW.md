# Semgrep Findings Review

**SPDX-License-Identifier: Apache-2.0**  
**Date**: January 12, 2026  
**Baseline**: semgrep-baseline.json  
**Total Findings**: 19

---

## Findings Summary

| Severity | Count | Action Required |
|----------|-------|----------------|
| ERROR | 9 | Fix immediately or document exception |
| WARNING | 9 | Review and prioritize |
| INFO | 1 | Review (low priority) |

---

## ERROR Findings (Critical - 9)

### 1. GitHub Actions Shell Injection (3 findings)

**Files**:
- `.github/workflows/acp-check.yml:48`
- `.github/workflows/sync-release.yml:103`
- `.github/workflows/tier0-check.yml:57`

**Issue**: Potential shell injection in GitHub Actions `run:` steps

**Status**: ⚠️ **REVIEW REQUIRED**

**Action**:
- Review each workflow step
- Ensure inputs are sanitized
- Use `${{ }}` syntax properly
- Consider using `env:` for sensitive values

**Priority**: HIGH (Security concern)

---

### 2. Dockerfile Missing User (1 finding)

**File**: `backend/Dockerfile:47`

**Issue**: Dockerfile runs as root user

**Status**: ⚠️ **FIX REQUIRED**

**Action**:
```dockerfile
# Add non-root user
RUN useradd -m -u 1000 appuser
USER appuser
```

**Priority**: MEDIUM (Security best practice)

---

### 3. Additional ERROR Findings (5)

**Review Required**: Check `semgrep-baseline.json` for details:
```bash
jq '.results[] | select(.extra.severity == "ERROR") | {rule: .check_id, file: .path, line: .start.line, message: .message}' semgrep-baseline.json
```

---

## WARNING Findings (High - 9)

### 1. Django REST Framework Missing Throttle Config

**File**: `backend/saraise_backend/settings.py:236`

**Issue**: DRF throttling not configured

**Status**: ⚠️ **REVIEW REQUIRED**

**Action**: Add throttling configuration to DRF settings

**Priority**: MEDIUM (Performance/DoS protection)

---

### 2. Unvalidated Password (2 findings)

**Files**:
- `backend/src/core/auth_api.py:284`
- `backend/src/core/management/commands/seed_default_users.py:237`

**Issue**: Password validation may be missing

**Status**: ⚠️ **REVIEW REQUIRED**

**Action**: Verify password validation is in place

**Priority**: HIGH (Security)

---

### 3. CSRF Exempt (1 finding)

**File**: `backend/src/core/metrics.py:8`

**Issue**: CSRF protection disabled

**Status**: ⚠️ **REVIEW REQUIRED**

**Action**: Verify if CSRF exemption is intentional and documented

**Priority**: MEDIUM (Security)

---

### 4. Non-Literal Import (2 findings)

**Files**:
- `backend/src/modules/data_migration/services.py:648`
- `backend/src/modules/data_migration/services.py:762`

**Issue**: Dynamic imports may be unsafe

**Status**: ⚠️ **REVIEW REQUIRED**

**Action**: Review dynamic import usage, ensure inputs are validated

**Priority**: MEDIUM (Security)

---

### 5. Additional WARNING Findings (3)

**Review Required**: Check `semgrep-baseline.json` for details

---

## INFO Findings (Low - 1)

### 1. Informational Finding

**Review**: Check baseline file for details

**Priority**: LOW

---

## Action Plan

### Immediate (This Week)

1. **Fix Dockerfile User** (1 finding)
   - Add non-root user to Dockerfile
   - Test container build

2. **Review GitHub Actions Shell Injection** (3 findings)
   - Audit each workflow step
   - Sanitize inputs
   - Document if intentional

3. **Review Password Validation** (2 findings)
   - Verify password validation
   - Add validation if missing

### Short-term (Next Sprint)

1. **Address Remaining ERROR Findings** (5 findings)
   - Review each finding
   - Fix or document exception

2. **Address WARNING Findings** (9 findings)
   - Prioritize security-related warnings
   - Plan fixes for next sprint

3. **Update Custom Rules**
   - Add exclusions for false positives
   - Document justifications

---

## False Positive Handling

If a finding is a false positive:

1. **Document Justification**
   - Why is it a false positive?
   - What mitigations are in place?

2. **Update Custom Rules**
   - Add exclusion to `.semgrep/custom-rules.yaml`
   - Include justification in rule comment

3. **Example Exclusion**:
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
        - "**/specific_file.py"
```

---

## Review Process

1. **Categorize Each Finding**
   - Critical: Fix immediately
   - High: Fix in next sprint
   - Medium: Plan for future
   - Low: Review and document
   - False Positive: Update rules

2. **Create Tickets**
   - One ticket per finding (or group related findings)
   - Assign priority based on severity
   - Link to baseline file

3. **Track Progress**
   - Update baseline after fixes
   - Re-run scan to verify
   - Document improvements

---

## Baseline Update

After addressing findings:

```bash
# Re-run baseline
./scripts/semgrep-baseline.sh

# Compare results
diff semgrep-baseline.json semgrep-baseline-new.json

# Update baseline
mv semgrep-baseline-new.json semgrep-baseline.json
```

---

**Last Updated**: January 12, 2026  
**Next Review**: After fixes applied
