# DAST Testing Guide

**SPDX-License-Identifier: Apache-2.0**  
**Purpose**: Guide for testing and validating DAST (OWASP ZAP) workflow

---

## Overview

The DAST (Dynamic Application Security Testing) workflow uses OWASP ZAP to scan the running application for security vulnerabilities.

**Location**: `.github/workflows/security.yml`  
**Trigger**: PRs to `main` or `develop` branches

---

## Prerequisites

1. Application must be running and accessible
2. Docker Compose services must be available
3. Health endpoint must be accessible at `/health/`

---

## Workflow Steps

### 1. Start Application Services

The workflow automatically starts services using:
```bash
docker-compose -f docker-compose.dev.yml up -d
```

### 2. Wait for Services

The workflow waits for services to be ready:
```bash
timeout 120 bash -c 'until curl -f http://localhost:8000/health/; do sleep 2; done'
```

### 3. ZAP Baseline Scan

OWASP ZAP performs a baseline scan:
- Target: `http://localhost:8000`
- Rules: `.zap/rules.tsv` (custom rules)
- Action: `fail_action: true` (fails on findings)

### 4. Report Generation

- HTML report: `report_html.html`
- Uploaded as artifact: `zap-report`
- Retention: 30 days

---

## Custom Rules Configuration

**File**: `.zap/rules.tsv`

### Rule Format
```
Rule ID, Action (IGNORE|WARN|FAIL), Reason
```

### Example Rules
```
10021	IGNORE	Expected authentication required for protected endpoints
10000	FAIL	SQL Injection (critical)
10011	WARN	Weak Authentication (high)
```

### Rule Actions
- **IGNORE**: Skip this rule (for false positives)
- **WARN**: Log warning but don't fail
- **FAIL**: Block merge if finding detected

---

## Testing Locally

### 1. Start Application
```bash
cd saraise-application
docker-compose -f docker-compose.dev.yml up -d
```

### 2. Run ZAP Scan
```bash
# Install ZAP (if not installed)
# macOS: brew install zaproxy
# Or use Docker:
docker run -t owasp/zap2docker-stable zap-baseline.py -t http://localhost:8000
```

### 3. Review Findings
- Check console output for findings
- Review HTML report if generated
- Update `.zap/rules.tsv` to ignore false positives

---

## Common False Positives

### Authentication Required (401/403)
- **Rule**: 10021, 10020
- **Action**: IGNORE
- **Reason**: Protected endpoints should return 401/403

### API Versioning
- **Rule**: 10054
- **Action**: IGNORE
- **Reason**: `/api/v1/` prefix is intentional

### Session Cookies
- **Rule**: 10010
- **Action**: WARN
- **Reason**: HttpOnly cookies are correct

---

## Critical Findings (Always Block)

These findings **always block merge**:
- SQL Injection (10000)
- Command Injection (10001)
- Path Traversal (10002)
- Remote Code Execution (10003)
- Cross-Site Scripting (10004, 10005)
- Cross-Site Request Forgery (10007)
- Server-Side Request Forgery (10008)
- Insecure Direct Object Reference (10009)

---

## Troubleshooting

### Services Not Starting
- Check Docker Compose configuration
- Verify port 8000 is available
- Check service logs: `docker-compose logs`

### Health Check Fails
- Verify health endpoint exists: `/health/`
- Check application logs
- Verify database connection

### ZAP Scan Fails
- Check ZAP logs in workflow output
- Verify target URL is accessible
- Review custom rules for conflicts

---

## Best Practices

1. **Run locally first** - Test DAST scan locally before pushing
2. **Review false positives** - Update rules to ignore known false positives
3. **Address critical findings immediately** - Never ignore critical security issues
4. **Document exceptions** - If a finding is acceptable, document why in rules file
5. **Regular updates** - Keep ZAP and rules updated

---

## Integration with CI/CD

The DAST workflow:
- Runs automatically on PRs to `main`/`develop`
- Blocks merge on critical findings
- Generates reports for review
- Uploads artifacts for analysis

**No manual intervention required** - fully automated security scanning.

---

## References

- [OWASP ZAP Documentation](https://www.zaproxy.org/docs/)
- [ZAP GitHub Action](https://github.com/zaproxy/action-baseline)
- [SARAISE Security Model](../saraise-documentation/architecture/existing/security-model.md)
