## 6) Identity, Auth, DRBAC, ABAC, SoD, JIT, RLP

### 6.1 Authentication (Who You Are)

SARAISE uses **server-managed, stateful session authentication** for all interactive access.

- Web UI and ERP application access:
  - Session-based authentication only
  - Secure, HTTP-only cookies
  - Server-side session validation and invalidation

- Identity federation:
  - OIDC (primary)
  - SAML 2.0 (enterprise)

- Local authentication:
  - Allowed only for SMB tenants and break-glass access

JSON Web Tokens (JWTs) are **not** used for interactive user authentication.
JWTs are permitted **only** for:
- External API access
- Service-to-service communication
- Short-lived, scope-restricted integration tokens

### 6.2 Provisioning (Who Exists)
- **SCIM 2.0** for user/group lifecycle sync

### 6.3 Identity Model (Tenant-scoped)
- `User` (can be local or federated)
- `Group` / `SecurityGroup`
- `Role`
- `Policy`
- `Permission` (resource:action)
- `Session` (server-managed, short TTL, tenant-bound, continuously validated)

### 6.4 DRBAC (Dynamic RBAC)
DRBAC here means roles and permissions are **tenant-administered**, dynamic, and auditable.
- Role templates shipped by platform
- Tenant can clone/modify within guardrails
- Every role change is audited

### 6.5 ABAC (Attribute-Based)
Policies support conditions:
- org_unit, site, region, cost_center, project, classification, time-of-day, device posture, risk score

Enforcement points:
1. API middleware (deny early)
2. Query layer filters (row-level)
3. Command/action layer (prevent side effects)

### 6.6 SoD (Segregation of Duties)
SoD is not a checkbox. It’s enforceable constraints:
- Example: creator of a payment cannot approve it
- Conflicting roles matrix per tenant
- Workflow engine validates SoD at transition time

### 6.7 JIT (Just‑In‑Time Privilege)
- Elevated roles granted with:
  - justification
  - time-bound TTL
  - approval workflow
  - mandatory audit log

### 6.8 RLP / Row-Level Protection (Row-level access)
- Default: app-layer enforced row filtering + mandatory tenant_id scoping.
- For regulated modules: optional Postgres **Row Level Security** on highest-risk tables.

---

## 10) Security (Baseline Controls)

- **TLS everywhere**
- **KMS-managed encryption** for secrets/keys
- **Strong session security** (server-managed sessions, short TTL, rotation, CSRF protection, explicit invalidation on privilege change)
- **Rate limiting** and abuse detection per tenant
- **WAF** at edge
- **SBOM + signed images**
- **SAST/DAST** in CI
- **Least privilege** service accounts
- **Tenant isolation testing** is a release gate
