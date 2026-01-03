---
description: UI terminology, branding, visual identity, and frontend access control for SARAISE
globs: frontend/**/*.{ts,tsx,css,scss}
alwaysApply: true
---

# 🎨 SARAISE Frontend Standards (Branding & Access Control)

**Rule IDs**: SARAISE-11000 to SARAISE-11011
**Consolidates**: `13-branding-visual.md`, `16-frontend-access-control.md`

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Module Framework: `docs/architecture/module-framework.md`

---

## Branding & Visual Identity

### SARAISE-11000 Central Branding Registry (SINGLE SOURCE OF TRUTH)

**⚠️ CRITICAL**: All branding elements are defined here. Other files MUST reference these variables, not hardcode branding values.

**Environment Variables for Branding:**
```bash
# Company & Product Names
COMPANY_NAME="SARAISE"
PRODUCT_NAME="SARAISE"
FULL_PRODUCT_NAME="SARAISE - Secure and Reliable AI Symphony ERP"

# Repository Information
REPO_OWNER="buildworksai"
REPO_NAME="saraise"
REPO_URL="https://github.com/buildworksai/saraise.git"

# Domain Configuration
PROD_DOMAIN="saraise.com"
STAGING_DOMAIN="staging.saraise.com"
API_DOMAIN="api.saraise.com"
```

**Python Helper Functions:**
```python
def get_company_name() -> str:
    return os.getenv('COMPANY_NAME', 'SARAISE')

def get_product_name() -> str:
    return os.getenv('PRODUCT_NAME', 'SARAISE')

def get_full_product_name() -> str:
    return os.getenv('FULL_PRODUCT_NAME', 'SARAISE - Secure and Reliable AI Symphony ERP')
```

**TypeScript Helper Functions:**
```typescript
export const getBranding = () => ({
  companyName: import.meta.env.VITE_COMPANY_NAME || 'SARAISE',
  productName: import.meta.env.VITE_PRODUCT_NAME || 'SARAISE',
  fullProductName: import.meta.env.VITE_FULL_PRODUCT_NAME || 'SARAISE - Secure and Reliable AI Symphony ERP'
});

export const getFooterText = () => {
  const branding = getBranding();
  return `${branding.fullProductName}`;
};
```

### SARAISE-11001 Platform Naming
- Must be referred to as "SARAISE" or "SARAISE - Secure and Reliable AI Symphony ERP" in code comments, UI, docs, logs.
- Use `get_full_product_name()` helper function for consistency.

### SARAISE-11002 UI Terminology Standards
- **No internal jargon** in user-facing text
- **Consistency**: use the same term for the same concept
- **Clarity**: short, unambiguous labels
- **Accessibility**: ARIA labels describe purpose, not appearance

Examples: Use "Sign in" or "Log in" consistently, Use "Workspace" vs "Project" per product naming decisions, Use "Tenant" vs "Organization" consistently

### SARAISE-11003 Semantic Color Palette
- Deep Blue: `#1565C0` (primary.main), `#0D47A1` (primary.dark)
- Gold: `#FF8F00` (warning.main), `#F57C00` (warning.dark)
- Teal/Electric Blue: `#00ACC1` (info.main), `#0097A7` (info.dark)
- Green: `#388E3C` (success.main), `#2E7D32` (success.dark)

### SARAISE-11004 Component Color Enforcement
```tsx
<AppBar sx={{ bgcolor: 'primary.main' }} />
<Chip label="Enterprise" color="warning" />
<Button variant="contained" color="info" />
<Alert severity="success" />
```
No hardcoded hex in components; use theme tokens.

### SARAISE-11005 Toast Notifications
- Include timeout indicator (progress bar)
- Durations: 6s info, 8s warnings/errors
- Dismissible with proper ARIA

---

## Frontend Access Control

### SARAISE-11006 Auth Context Implementation

See [Auth Context Implementation](docs/architecture/examples/frontend/components/auth-context.tsx).

**Key Features:**
- `AuthProvider` component with session-based authentication
- `useAuth()` hook for accessing auth state
- Automatic session check on mount
- Role checking methods: `hasRole()`, `hasTenantRole()`

### SARAISE-11007 Role Helper Hook

See [Role Helper Hook](docs/architecture/examples/frontend/hooks/use-roles.ts).

**Key Features:**
- Platform role checks: `isPlatformOwner`, `isPlatformOperator`, `isPlatformAuditor`, `isPlatformBillingManager`
- Tenant role checks: `isTenantAdmin`, `isTenantDeveloper`, `isTenantOperator`, etc.
- Combined checks: `canManageBilling`, `canViewAuditLogs`, `canDeploy`, `canManageUsers`

### SARAISE-11008 Page Protection

See [Protected Page Component](docs/architecture/examples/frontend/components/protected-page.tsx).

**Key Features:**
- Redirect to login if not authenticated
- Check role requirements (`requireRole`, `requireTenantRole`)
- Custom fallback for access denied

### SARAISE-11009 Component-Level Gating

See [Component-Level Gating](docs/architecture/examples/frontend/components/component-level-gating.tsx).

**Key Patterns:**
- Hide components completely if user lacks permissions
- Disable buttons/actions based on role checks
- Use `useRoles()` hook for convenience checks

### SARAISE-11010 Role-to-Feature Mapping

**Authoritative mapping:**
- **Billing** → `platform_billing_manager` OR `tenant_billing_manager`
- **Audit Logs** → `platform_auditor` OR `tenant_auditor`
- **Deploy/Execute** → `tenant_operator` OR `tenant_developer`
- **Admin Console** → `platform_owner` OR `tenant_admin`
- **User Management** → `platform_owner` OR `tenant_admin`
- **System Settings** → `platform_owner`

### SARAISE-11011 Security Requirements

- ✅ **Session-based**: Roles from session cookies only
- ✅ **Deny-by-default**: Hide unauthorized UI elements
- ✅ **No client-side role storage**: Never store roles in localStorage
- ✅ **Consistent checks**: Use `useAuth()` hook everywhere
- ✅ **Backend validation**: Frontend checks are UX only, backend enforces security

---

**Audit**: Version 7.0.0; Consolidated 2025-12-23
