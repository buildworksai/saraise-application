<!-- SPDX-License-Identifier: Apache-2.0 -->
# Security Policy

## Reporting Security Vulnerabilities

The SARAISE team takes security seriously. We appreciate your efforts to responsibly disclose your findings and will make every effort to acknowledge your contributions.

### How to Report

**DO NOT** report security vulnerabilities through public GitHub issues.

Instead, please report them via one of these channels:

1. **Email**: security@saraise.com
2. **Security Advisory**: [GitHub Security Advisory](https://github.com/buildworksai/saraise/security/advisories/new)

### What to Include

Please provide as much information as possible:

- **Type of vulnerability** (e.g., SQL injection, XSS, authentication bypass, privilege escalation)
- **Full paths of affected files**
- **Location of affected source code** (tag/branch/commit or direct URL)
- **Step-by-step instructions to reproduce** the issue
- **Proof-of-concept or exploit code** (if available)
- **Impact assessment** — What can an attacker achieve?
- **Any special configuration required** to reproduce
- **Your contact information** for follow-up

### Response Timeline

- **Initial response**: Within 48 hours
- **Status update**: Within 7 days
- **Resolution target**: Based on severity (see below)

### Severity Levels

| Severity | Description | Response Time |
|----------|-------------|---------------|
| **Critical** | Complete system compromise, data breach, authentication bypass affecting all tenants | 24-48 hours |
| **High** | Privilege escalation, tenant isolation breach, data exposure | 3-7 days |
| **Medium** | Partial data exposure, denial of service, non-critical injection | 14-30 days |
| **Low** | Information disclosure, minor issues with minimal impact | 30-90 days |

---

## Security Architecture Overview

SARAISE implements defense-in-depth with multiple security layers:

### 1. Authentication

- **Session-based authentication** with server-managed state
- **HTTP-only cookies** to prevent XSS attacks
- **Secure cookie flags** (Secure, SameSite)
- **Session rotation** on privilege change
- **Identity federation** via OIDC and SAML 2.0
- **NO JWT for interactive users** (architecture-enforced)

See: [Authentication and Session Management Spec](docs/architecture/authentication-and-session-management-spec.md)

### 2. Authorization

- **Policy Engine** for centralized authorization decisions
- **RBAC + ABAC** with deny-by-default enforcement
- **Segregation of Duties (SoD)** constraints
- **Just-In-Time (JIT) privilege** elevation with audit trails
- **Row-Level Security** via tenant_id filtering

See: [Policy Engine Spec](docs/architecture/policy-engine-spec.md) and [Security Model](docs/architecture/security-model.md)

### 3. Multi-Tenancy

- **Row-level multitenancy** with shared schema
- **Mandatory tenant_id filtering** in all queries
- **Tenant isolation testing** as release gate
- **Per-tenant module installation** based on subscriptions

See: [Application Architecture](docs/architecture/application-architecture.md)

### 4. Data Protection

- **TLS everywhere** — all data in transit encrypted
- **KMS-managed encryption** for secrets and keys
- **Database encryption at rest**
- **Immutable audit logs** for compliance
- **PII/PHI protection** for regulated industries

### 5. Input Validation

- **Pydantic schemas** for request validation (backend)
- **Zod schemas** for form validation (frontend)
- **SQL injection prevention** via Django ORM
- **XSS prevention** via CSP headers and React sanitization
- **CSRF protection** via token validation

### 6. Network Security

- **WAF at edge** (Web Application Firewall)
- **Rate limiting** per tenant and per IP
- **DDoS protection**
- **API gateway** with request validation

### 7. Dependency Management

- **SBOM (Software Bill of Materials)** for all dependencies
- **Automated vulnerability scanning** (Snyk, Dependabot)
- **Signed container images**
- **Regular security updates**

---

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.x     | :white_check_mark: |

Currently in initial development. Security patches will be backported to supported versions.

---

## Security Best Practices for Contributors

### Code Review Checklist

When contributing, ensure:

- [ ] No hardcoded credentials or secrets
- [ ] Proper input validation on all endpoints
- [ ] Tenant_id filtering in all tenant-scoped queries
- [ ] Authorization checks before data access
- [ ] No sensitive data in logs
- [ ] HTTPS-only for all external connections
- [ ] Secure session handling
- [ ] Proper error handling (no stack traces to users)

### Forbidden Patterns

These patterns will be **rejected immediately**:

❌ **JWT for interactive users** — Session auth only  
❌ **Omitted tenant_id filtering** — Critical data leakage risk  
❌ **Authorization checks in route handlers** — Use Policy Engine  
❌ **Hardcoded secrets** — Use environment variables  
❌ **Dynamic SQL** — Use Django ORM only  
❌ **Storing passwords in plaintext** — Use bcrypt  
❌ **Exposing stack traces** — Log internally, return generic errors  

### Pre-Commit Security Checks

All commits are scanned for:
- Secrets and credentials (detect-secrets)
- Known vulnerable dependencies
- SQL injection patterns
- XSS vulnerabilities

---

## Vulnerability Disclosure Policy

### Public Disclosure

- **Coordinated disclosure** — We will work with you to patch before public disclosure
- **Credit** — We will credit you in security advisories (unless you prefer anonymity)
- **Embargo period** — Typically 90 days from initial report
- **Early disclosure** — If vulnerability is being actively exploited

### Security Advisories

Published vulnerabilities will be disclosed via:
- [GitHub Security Advisories](https://github.com/buildworksai/saraise/security/advisories)
- CHANGELOG.md
- Security mailing list (security-announce@saraise.com)

---

## Security Testing

### Allowed Testing

You may test security on:
- **Your own SARAISE installation**
- **Local development environments**
- **Public demo instances** (if explicitly marked as test environments)

### Prohibited Testing

**DO NOT** test on:
- Production instances not owned by you
- Customer/tenant data
- Shared infrastructure
- Via automated scanning tools without permission

### Bug Bounty Program

We currently do not have a formal bug bounty program, but we recognize and appreciate security researchers who report vulnerabilities responsibly.

---

## Incident Response

In the event of a security incident:

1. **Containment** — Immediate isolation of affected systems
2. **Assessment** — Determine scope and impact
3. **Notification** — Affected tenants notified within 72 hours (GDPR compliance)
4. **Remediation** — Patch and deploy fixes
5. **Post-mortem** — Root cause analysis and prevention measures

---

## Compliance

SARAISE is designed to support compliance with:

- **GDPR** — Data protection and privacy
- **SOC 2 Type II** — Security controls
- **HIPAA** — Healthcare data protection (with BAA)
- **PCI DSS** — Payment card data security
- **ISO 27001** — Information security management

See: [Multi-Region Data Semantics and Compliance Matrix](docs/architecture/multi-region-data-semantics-and-compliance-matrix.md)

---

## Security Updates

Subscribe to security announcements:
- Watch this repository for security advisories
- Email: security-announce@saraise.com

---

## Contact

- **Security email**: security@saraise.com
- **Security team**: Available 24/7 for critical vulnerabilities
- **PGP key**: Available at https://saraise.com/security/pgp

---

## Acknowledgments

We thank all security researchers who have responsibly disclosed vulnerabilities to us.

---

**Last Updated**: 2026-01-03

---

**SARAISE** — Secure and Reliable AI Symphony ERP  
Building secure, multi-tenant enterprise software.
