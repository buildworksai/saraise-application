<!-- SPDX-License-Identifier: Apache-2.0 -->
# SARAISE Module Documentation

**Welcome to the SARAISE Module Architecture Documentation**

This directory contains comprehensive documentation for **108+ modules** that comprise the SARAISE ERP platform—the world's most advanced, AI-first, multi-tenant Enterprise Resource Planning system.

---

## 📚 Quick Navigation

### Start Here
1. **[Module Index](./00-MODULE-INDEX.md)** - Authoritative catalog of all 108+ modules organized into 3 categories
2. **[Module Framework](../architecture/module-framework.md)** - Technical specification for module architecture
3. **[Application Architecture](../architecture/application-architecture.md)** - Overall system design and patterns

---

## Module Categories (3-Tier Architecture)

SARAISE modules are organized into **three architectural categories** based on their purpose and installation model:

### 📦 [01. Foundation Modules](./01-foundation/) (22 modules)
**Platform Infrastructure Capabilities**

Core platform capabilities that enable multi-tenancy, customization, AI, workflow, security, and platform operations.

**Installation Model**: Platform-level, always available (not tenant-configurable)

**Key Modules**:
- Platform Management - System admin, health monitoring, configuration
- Tenant Management - Multi-tenant lifecycle, quotas, isolation
- Billing & Subscriptions - SaaS monetization, payment processing
- AI Provider Configuration - Unified LLM interface (OpenAI, Anthropic, Google, etc.)
- AI Agent Management - Deploy & monitor autonomous AI agents
- Workflow Automation - Visual workflow builder with AI optimization
- API Management - GraphQL & REST gateway, rate limiting
- Security & Access Control - RBAC, ABAC, MFA, SSO
- Performance Monitoring - APM, distributed tracing, alerting

[**View All Foundation Modules →**](./01-foundation/)

---

### 🏢 [02. Core Modules](./02-core/) (21 modules)
**Universal Business Operations**

Essential business functions required by virtually all businesses regardless of industry vertical.

**Installation Model**: Auto-installed for all new tenants (default, cannot be uninstalled)

**Key Modules**:
- **Customer & Revenue**: CRM, Sales Management, Communication Hub
- **Finance & Accounting**: Accounting & Finance, Bank Reconciliation, Budget Management
- **Supply Chain & Operations**: Inventory Management, Purchase Management, Project Management
- **Human Capital**: Human Resources (HRMS, Payroll, Recruitment)
- **Governance & Data**: Master Data Management, Business Intelligence, Compliance Management

[**View All Core Modules →**](./02-core/)

---

### 🎯 [03. Industry-Specific Modules](./03-industry-specific/) (65+ modules)
**Vertical-Specific & Specialized Capabilities**

Specialized modules for specific industry verticals, niche use cases, or optional business capabilities.

**Installation Model**: Optional, tenant-selectable based on subscription plan

**Categories**:
- **Manufacturing & Production**: Manufacturing, APS, Supply Chain, PLM, QMS, IoT/Industry 4.0
- **Finance & Treasury**: Treasury Management, Revenue Management (ASC 606)
- **Trade & Logistics**: Global Trade, Fleet Management, EDI
- **AI & Analytics**: AI Service Desk, Demand Forecasting, Knowledge Base
- **Marketing & Communication**: Marketing Automation, Campaign Management, Social Media, SMS, Live Chat
- **Messaging & Collaboration**: WhatsApp Business, Telegram, Slack, MS Teams
- **Data & Infrastructure**: Data Warehouse & ETL, Mobile Apps, Offline Mode
- **Industry Verticals**: Healthcare, Financial Services, Hospitality, Retail, Professional Services, Automotive, Energy, Pharma, and more

[**View All Industry-Specific Modules →**](./03-industry-specific/)

---

## 🎯 Key Features

### Multi-Tenant SaaS Architecture
- **Row-Level Multitenancy**: Shared schema with `tenant_id` isolation (Django ORM)
- **108+ Business Modules**: Foundation (22), Core (21), and Industry-Specific (65+)
- **Per-Tenant Module Installation**: Subscribe only to modules you need
- **Module Access Control**: `ModuleAccessMiddleware` enforces tenant permissions
- **Django ORM**: All models use Django ORM with proper `tenant_id` filtering
- **Django Migrations**: All database changes via `manage.py makemigrations/migrate`

### AI-First Platform
- **30+ LLM Providers**: OpenAI, Anthropic, Google, Groq, Mistral, Cohere, and more
- **Autonomous AI Agents**: Deploy & monitor AI agents with governance guardrails
- **Workflow Automation**: Visual builder with AI optimization
- **Document Intelligence**: AI-powered OCR, extraction, classification

### Enterprise Security
- **Session Authentication**: Server-managed stateful sessions (no JWT for interactive users)
- **RBAC/ABAC**: Dynamic role-based + attribute-based access control
- **SoD (Segregation of Duties)**: Enforceable constraints per tenant
- **Policy Engine**: Runtime authorization evaluation (never cached)
- **Audit Trails**: Immutable audit logs for compliance

### Communication Excellence
- **20+ Channels**: WhatsApp, Telegram, Slack, Teams, Email, SMS, Social Media
- **Unified Communication Hub**: Omnichannel inbox for all customer interactions
- **Marketing Automation**: Campaigns, segmentation, A/B testing, analytics

---

## 📋 Module Implementation Standards

### Architectural Principles

1. **Row-Level Multitenancy**: All tenant-scoped tables MUST have `tenant_id` column
2. **Session Authentication**: Server-managed sessions only (no JWT for interactive users)
3. **Manifest-Driven**: Every module MUST have `manifest.yaml` declaring permissions, dependencies, SoD actions
4. **No Auth in Modules**: Modules MUST NOT implement authentication, login, logout, session management
5. **Testing Required**: ≥90% code coverage enforced by CI
6. **Permission Model**: Modules declare permissions, Policy Engine evaluates authorization

### Module Structure

```
/module_name/
  __init__.py
  manifest.yaml      # Module contract (REQUIRED)
  models.py          # Django ORM models with tenant_id
  api.py             # DRF views
  permissions.py     # Permission declarations
  policies.py        # ABAC policy definitions
  workflows.py       # Workflow definitions
  search.py          # Search index configuration
  migrations/        # Django migrations (idempotent)
  tests/             # ≥90% coverage REQUIRED
```

### Manifest Example

```yaml
name: module-name
version: 1.0.0
description: Module description
type: core|domain|industry|integration
lifecycle: managed|core|integration
dependencies:
  - core-identity >=1.0
  - core-workflow >=1.0
permissions:
  - module.resource:create
  - module.resource:read
  - module.resource:update
  - module.resource:delete
sod_actions:
  - module.resource:create
  - module.resource:approve
search_indexes:
  - module_primary_entity
ai_tools:
  - module_action_tool
```

---

## 🚫 Architectural Anti-Patterns (FORBIDDEN)

The following patterns are **strictly prohibited** and will result in immediate rejection:

❌ **Modules implementing authentication, login, logout, session management, or credential handling**  
❌ **Omitted `tenant_id` columns in tenant-scoped models** (data leakage risk)  
❌ **Forgetting tenant filtering in queries** (critical security violation)  
❌ **JWT tokens for interactive users** (session-based auth only)  
❌ **Modules without `manifest.yaml` contract**  
❌ **Dynamic route registration** (static registration in `main.py` only)  
❌ **Skipping tests** (90% coverage mandatory)  
❌ **Circular module dependencies**  
❌ **Modifying audit logs** (they're immutable)  
❌ **Bypassing pre-commit hooks**  
❌ **Using `any` type in TypeScript**  
❌ **Database transactions in route handlers** (use services only)

---

## 📊 Module Statistics

| Category | Count | Purpose | Installation |
|----------|-------|---------|--------------|
| **Foundation** | 22 | Platform infrastructure | Platform-level |
| **Core** | 21 | Universal business operations | Auto-installed |
| **Industry-Specific** | 65+ | Vertical-specific modules | Optional |
| **TOTAL** | **108+** | **Complete ERP ecosystem** | **Flexible** |

---

## 🔗 Related Documentation

### Architecture References
- **[Module Framework](../architecture/module-framework.md)** - Detailed module architecture specification
- **[Application Architecture](../architecture/application-architecture.md)** - Overall system architecture
- **[Security Model](../architecture/security-model.md)** - Security, RBAC, ABAC, SoD specifications
- **[Authentication Spec](../architecture/authentication-and-session-management-spec.md)** - Session authentication details
- **[Policy Engine Spec](../architecture/policy-engine-spec.md)** - Authorization policy engine

### Implementation Guides
- **[Module Implementation Rules](./00-MODULE-INDEX.md#module-implementation-rules-non-negotiable)** - Non-negotiable implementation standards
- **[Module Installation Model](./00-MODULE-INDEX.md#module-installation-model)** - How modules are installed per tenant
- **[Tenant Isolation Patterns](../architecture/application-architecture.md#10-security-baseline-controls)** - Row-level multitenancy best practices

---

## 🚀 Getting Started

### For Module Developers

1. **Read the Module Framework**: Start with [Module Framework](../architecture/module-framework.md)
2. **Review Existing Modules**: Look at [CRM](./02-core/crm/README.md) or [Platform Management](./01-foundation/platform-management/README.md) as examples
3. **Understand Module Contract**: Every module needs `manifest.yaml` ([example](./00-MODULE-INDEX.md#1-module-manifest-required))
4. **Follow Testing Standards**: ≥90% coverage is mandatory
5. **Use Pre-Commit Hooks**: `pip install pre-commit && pre-commit install`

### For Architects

1. **Review Module Index**: [00-MODULE-INDEX.md](./00-MODULE-INDEX.md) - Complete catalog
2. **Understand Categorization**: Foundation vs Core vs Industry-Specific
3. **Review Security Model**: [Security Model](../architecture/security-model.md)
4. **Study Multi-Tenancy**: [Application Architecture](../architecture/application-architecture.md)

### For Business Stakeholders

1. **Explore Module Capabilities**: Browse module categories to understand what SARAISE offers
2. **Understand Subscription Model**: Core modules are included, Industry-Specific are optional
3. **Review Industry Solutions**: Find modules specific to your vertical in [Industry-Specific](./03-industry-specific/)

---

## 📝 Document Authority

This documentation represents the **authoritative baseline** for SARAISE module organization. All implementations MUST align with this structure and architectural rules.

**Document Version**: 2.0.0  
**Last Updated**: 2026-01-03  
**Status**: Architectural Baseline  
**Author**: SARAISE Architecture Team  
**Next Review**: Quarterly or upon major architectural change

---

## 🤝 Contributing

Module documentation follows strict architectural guidelines:

1. **Alignment Required**: All modules MUST align with [Module Framework](../architecture/module-framework.md)
2. **Manifest Required**: Every module MUST have `manifest.yaml`
3. **Testing Required**: ≥90% code coverage enforced by CI
4. **Security Required**: All tenant-scoped models MUST have `tenant_id`
5. **No Auth in Modules**: Platform handles authentication centrally

For questions or clarifications, refer to [Application Architecture](../architecture/application-architecture.md) or [AGENTS.md](../../AGENTS.md).

---

**Ruthless Technical Precision. Zero Compromises. Bulletproof Quality.**
