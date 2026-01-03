---
description: Core architectural principles for SARAISE application
globs: **/*
alwaysApply: true
---

# SARAISE Core Architectural Principles

**⚠️ CRITICAL**: These principles form the foundation of the SARAISE application. All development must align with these principles.

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Module Framework: `docs/architecture/module-framework.md`
- Authentication & Session Management: `docs/architecture/authentication-and-session-management-spec.md`
- Policy Engine: `docs/architecture/policy-engine-spec.md`

## SARAISE-00001 Modular Architecture

SARAISE follows a **modular architecture** with metadata modeling capabilities:

- **Self-Contained Modules**: Each module is independent and can be developed, tested, and deployed separately
- **Module Dependencies**: Modules can depend on other modules, but circular dependencies are forbidden
- **Module Lifecycle**: Modules follow a clear lifecycle: development → testing → staging → production
- **Module Versioning**: Each module has its own version number and release cycle

**Implementation**: See `15-module-architecture.md` for modular architecture patterns and `17-module-lifecycle-metadata.md` for metadata modeling patterns.

## SARAISE-00002 Multi-Tenant Architecture

SARAISE is a **multi-tenant SaaS application** with **Row-Level Multitenancy (Shared Schema)**:

- **Row-Level Isolation**: All tenants share the same database schema. **ALL tenant-scoped tables MUST have a `tenant_id` column.**
- **Isolation Enforcement**: Tenant isolation is enforced by robust filtering in all queries and service layers. Row-Level Security (RLS) policies may be used for additional safety.
- **Tenant Context**: Tenant context is provided by authenticated user session and explicit filtering.
- **Platform vs Tenant Roles**: Clear separation between platform-level and tenant-level roles.

**Implementation**: See `21-platform-tenant.md` for tenant management patterns.

## SARAISE-00003 Session-Based Authentication (FROZEN ARCHITECTURE)

SARAISE uses **server-managed stateful session authentication** (no JWT for interactive users):

- **HTTP-Only Cookies**: Session tokens stored in HTTP-only cookies for security
- **Identity Snapshot**: Sessions contain identity snapshot (roles[], groups[], jit_grants[], policy_version) - NOT effective permissions
- **Policy Engine**: All authorization decisions evaluated at runtime by Policy Engine using identity snapshot
- **Policy Version Gating**: Sessions invalidated when policy_version changes (forced re-authentication)
- **Session Invalidation**: Sessions invalidated on logout, role/policy changes, privilege elevation
- **Deny-by-Default**: Every route requires explicit authorization via Policy Engine

**Implementation**: See `10-session-auth.md` for authentication patterns and `docs/architecture/authentication-and-session-management-spec.md` for authoritative specification.

## SARAISE-00004 Role-Based Access Control (RBAC)

SARAISE implements **comprehensive RBAC** with platform and tenant roles:

- **Platform Roles**: System-wide access (platform_owner, platform_operator, platform_auditor, platform_billing_manager)
- **Tenant Roles**: Tenant-scoped access (tenant_admin, tenant_developer, tenant_operator, tenant_billing_manager, tenant_auditor, tenant_user, tenant_viewer)
- **Explicit Enforcement**: Every protected route must declare required role
- **Tenant Validation**: Tenant-scoped routes must validate tenant access

**Implementation**: See `12-auth-enforcement.md` for RBAC enforcement patterns.

## SARAISE-00005 Immutable Audit Logging

SARAISE maintains **immutable audit logs** for all sensitive operations:

- **Append-Only**: Audit logs can only be created, never updated or deleted
- **Comprehensive Coverage**: All admin, billing, and data-impacting operations are audited
- **Tenant Isolation**: Audit logs are tenant-scoped where applicable
- **Compliance Ready**: Audit logs support compliance requirements (GDPR, SOC 2, etc.)

**Implementation**: See `11-audit-logging.md` for audit logging patterns.

## SARAISE-00006 Environment-Aware Configuration

SARAISE uses **environment-aware configuration** for security, performance, and features:

- **Development**: Relaxed validation and security for rapid development
- **Staging**: Production-like validation and security for testing
- **Production**: Maximum validation, security, and performance optimization

**Implementation**: See `08-secrets-management.md` for environment configuration patterns.

## SARAISE-00007 Enterprise SaaS Modules

SARAISE includes **comprehensive Enterprise SaaS modules**:

- **Platform Management**: Platform administration and configuration
- **Tenant Management**: Tenant lifecycle, user quotas, and subscription limits
- **Billing & Subscriptions**: Subscription management, invoicing, and payment processing
- **Subscription Plans**: Plan tiers, features, and pricing management
- **Discounts & Offers**: Promotional discounts and time-limited offers
- **Coupon Management**: Coupon code system for discounts
- **Partner Management**: Partner and affiliate program management
- **Rate Limiting**: Subscription-based API rate limiting
- **User Quotas**: User limits based on subscription tier

**Implementation**: See rules `32-40` for Enterprise SaaS module patterns.

## SARAISE-00008 Module Development Standards

SARAISE modules follow **strict development standards**:

- **Code Quality**: 90% test coverage, zero vulnerabilities, A-rated security
- **Type Safety**: Full TypeScript/Python type annotations
- **Documentation**: Comprehensive documentation for all modules
- **Testing**: Unit, integration, and end-to-end tests required

**Implementation**: See `20-module-development.md` for module development standards.

## SARAISE-00009 Customization Framework

SARAISE supports **tenant-level customization**:

- **Custom Fields**: Extend standard data models per tenant
- **Dynamic Forms**: Forms adapt to customizations
- **Workflow Customization**: Tenant-specific workflow configurations
- **Customization Framework**: Customize without modifying core code

**Implementation**: See `docs/architecture/module-framework.md` for customization patterns.

## SARAISE-00010 Technology Stack Authority

SARAISE uses a **strictly defined technology stack**:

- **Backend**: Python 3.10+, Django 5.0.6, Django REST Framework 3.15.1, PostgreSQL 17
- **ORM**: Django ORM (built-in) is mandatory for all backend data access. No other ORM is permitted.
- **Migrations**: Django migrations (manage.py) are required for all schema changes. No other migration tool is allowed.
- **Server**: Gunicorn (production), `python manage.py runserver` (development)
- **Frontend**: Vite 5.1.4, React 18, TypeScript 5, Tailwind CSS 3.4.17
- **AI/ML**: OpenAI SDK, CrewAI, LangGraph, LiteLLM
- **Infrastructure**: Docker, Redis, MinIO, Kong, Prometheus, Grafana

**Implementation**: See `03-tech-stack.md` for complete technology stack registry (SARAISE-12001, SARAISE-12002).

---

**Next Steps**: Read `01-getting-started.md` for setup instructions, then review module-specific rules for your development area.
