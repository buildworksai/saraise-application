<!-- SPDX-License-Identifier: Apache-2.0 -->
# SARAISE Module Architecture - Authoritative Index

**Document Version:** 2.0.0  
**Last Updated:** 2026-01-03  
**Status:** Architectural Baseline  
**Authority:** Strict architectural adherence required

---

## Executive Summary

This document serves as the **authoritative master index** for all SARAISE ERP modules. SARAISE is a **multi-tenant SaaS ERP platform** with **80+ business modules** organized into **three architectural categories**: Foundation, Core, and Industry-Specific.

### Critical Architectural Principles

1. **Row-Level Multitenancy**: All tenant-scoped tables **MUST have `tenant_id` column**
2. **Module Isolation**: Modules are **NOT microservices** - one codebase, one schema, one runtime
3. **Session Authentication**: Server-managed stateful sessions only (no JWT for interactive users)
4. **RBAC/ABAC Authorization**: Policy Engine evaluates authorization at runtime
5. **Module Access Control**: Per-tenant module installation enforced by `ModuleAccessMiddleware`
6. **Manifest-Driven**: Every module MUST have `manifest.yaml` declaring permissions, dependencies, SoD actions
7. **No Auth in Modules**: Modules **MUST NOT** implement authentication, login, logout, session management, or credential handling

**ARCHITECTURAL VIOLATIONS WILL BE REJECTED IMMEDIATELY.**

---

## Module Categories (3-Tier Architecture)

### Category Definitions

| Category | Definition | Installation Model | Examples |
|----------|------------|-------------------|----------|
| **01-FOUNDATION** | Platform infrastructure capabilities (not business-specific) | Platform-level, always available | Platform Management, Tenant Management, AI Agents, Workflow Engine |
| **02-CORE** | Universal business operations required by all industries | Auto-installed for all new tenants | CRM, Accounting, Sales, Purchase, Inventory, HR |
| **03-INDUSTRY-SPECIFIC** | Vertical-specific or specialized modules | Optional, tenant-selectable based on subscription | Manufacturing, Healthcare, Retail, Marketing Automation |

---

## Implementation Phase Alignment (FROZEN ARCHITECTURE)

**CRITICAL CONTEXT**: Module categories align with SARAISE implementation sequencing as defined in `docs/architecture/implementation-sequencing-and-build-order.md`.

### Phase Status by Category

| Category | Implementation Phase | Current Status | When to Implement |
|----------|---------------------|----------------|-------------------|
| **01-FOUNDATION** | **Phase 1-5** | **ACTIVE IMPLEMENTATION** | **NOW** (Platform infrastructure, AI agents, workflow, security) |
| **02-CORE** | **Phase 8** | **SPECIFICATION ONLY** | **Phase 8** (After platform foundation complete) |
| **03-INDUSTRY-SPECIFIC** | **Phase 8+** | **SPECIFICATION ONLY** | **Phase 8+** (After core modules proven) |

### Implementation Rules (FROZEN ARCHITECTURE)

**✅ APPROVED FOR IMPLEMENTATION (Phase 1-5)**:
- Foundation modules only (Platform Management, Tenant Management, Security, AI Agents, Workflow, etc.)
- Core infrastructure capabilities that enable multi-tenancy, AI, and platform operations
- Framework readiness for module packaging, subscription, migrations

**❌ NOT FOR IMPLEMENTATION YET (Phase 8)**:
- Core business modules (CRM, Accounting, Sales, Purchase, Inventory, HR, etc.)
- Documented for specification only - DO NOT implement until Phase 8 begins
- Framework must be complete before business module rollout

**❌ NOT FOR IMPLEMENTATION YET (Phase 8+)**:
- Industry-specific modules (Manufacturing, Healthcare, Retail, Marketing, etc.)
- Documented for future reference - DO NOT implement until core modules proven
- Requires platform + core modules operational first

**ENFORCEMENT**: Any attempt to implement Phase 8+ modules before platform foundation completion will be rejected. Architecture Change Process (ACP) + Board approval required to change sequencing.

---

## [01. Foundation Modules](./01-foundation/)

**IMPLEMENTATION STATUS:** ✅ **ACTIVE IMPLEMENTATION - Phase 1-5**
**CURRENT PHASE:** Phase 1 (Platform Foundations)
**WHEN:** NOW (Platform infrastructure priority)

**Purpose**: Core platform capabilities that enable multi-tenancy, customization, AI, workflow, security, and platform operations.

**Characteristics**:
- Infrastructure, not domain logic
- Required for platform to function
- Not tenant-installable (platform-level)
- Enable other modules to operate

### Platform Infrastructure (8 modules)

- **[Platform Management](./01-foundation/platform-management/README.md)** - System administration, health monitoring, global configuration, feature flags, environment management
- **[Tenant Management](./01-foundation/tenant-management/README.md)** - Multi-tenant lifecycle, user quotas, isolation, subscription management, tenant provisioning
- **[Billing & Subscriptions](./01-foundation/billing-subscriptions/README.md)** - Complete SaaS billing, invoicing, payment processing, subscription plans, usage metering
- **[Metadata Modeling](./01-foundation/metadata-modeling/README.md)** - Dynamic Resources, custom fields, flexible data models, schema evolution
- **[Customization Framework](./01-foundation/customization-framework/README.md)** - No-code/low-code customization engine, custom scripts, client scripts, server scripts
- **[Data Migration Framework](./01-foundation/data-migration/README.md)** - Intelligent data import/migration from external systems with AI-powered field mapping, validation, rollback
- **[Document Management System (DMS)](./01-foundation/dms/README.md)** - Enterprise document storage, versioning, access control, file organization
- **[Blockchain Traceability](./01-foundation/blockchain-traceability/README.md)** - Blockchain-based product traceability and authenticity verification

### AI & Automation Platform (6 modules)

- **[AI Provider Configuration](./01-foundation/ai-provider-configuration/README.md)** - Unified interface for all LLM providers (OpenAI, Anthropic, Google, Groq, Mistral, etc.)
- **[AI Agent Management](./01-foundation/ai-agent-management/README.md)** - Create, deploy, monitor autonomous AI agents with governance and guardrails
- **[Workflow Automation](./01-foundation/workflow-automation/README.md)** - Visual workflow builder with conditional logic, approvals, state machines, AI optimization
- **[Automation Orchestration](./01-foundation/automation-orchestration/README.md)** - Advanced orchestration for multi-agent workflows and workstreams
- **[Document Intelligence](./01-foundation/document-intelligence/README.md)** - AI-powered document processing, OCR, data extraction, classification
- **[Process Mining](./01-foundation/process-mining/README.md)** - Discover and optimize business processes using AI, process analytics, bottleneck detection

### Integration & Security Infrastructure (4 modules)

- **[API Management](./01-foundation/api-management/README.md)** - GraphQL & REST API gateway, rate limiting, API versioning, developer portal
- **[Integration Platform](./01-foundation/integration-platform/README.md)** - iPaaS for third-party integrations, connectors, webhooks, event streaming
- **[Security & Access Control](./01-foundation/security-access-control/README.md)** - Advanced RBAC, ABAC, MFA, SSO, session management, security policies
- **[Backup & Disaster Recovery](./01-foundation/backup-disaster-recovery/README.md)** - Automated backups, point-in-time recovery, disaster recovery orchestration

### Platform Operations (4 modules)

- **[Performance Monitoring](./01-foundation/performance-monitoring/README.md)** - APM, distributed tracing, logging, metrics, alerting, SLA monitoring
- **[Localization](./01-foundation/localization/README.md)** - Multi-language support, regional compliance, currency, date/time formats, RTL support
- **[Regional Compliance](./01-foundation/regional/README.md)** - Country-specific regulatory compliance, tax rules, legal requirements
- **[Backup & Recovery (Additional)](./01-foundation/backup-recovery/README.md)** - Extended backup capabilities, incremental backups, retention policies

**Total Foundation Modules: 22**

---

## [02. Core Modules](./02-core/)

**IMPLEMENTATION STATUS:** ❌ **SPECIFICATION ONLY - NOT FOR IMPLEMENTATION UNTIL PHASE 8**
**CURRENT PHASE:** Phase 1 (Platform Foundations)
**WHEN:** Phase 8 (After platform foundation complete - Phases 1-7)
**DO NOT IMPLEMENT:** These modules are documented for future implementation only. Framework must be complete first.

**Purpose**: Universal business operations required by virtually all businesses regardless of industry vertical.

**Characteristics**:
- Essential for business operations
- Universal applicability across all industries
- Auto-installed for all new tenants (default)
- Foundational to business workflows

### Customer & Revenue Management (4 modules)

- **[CRM (Customer Relationship Management)](./02-core/crm/README.md)** - Comprehensive customer lifecycle management, lead management, opportunity tracking, contact/account management, sales pipeline, activity tracking
- **[Sales Management](./02-core/sales-management/README.md)** - Complete order-to-cash cycle, quotations, sales orders, delivery notes, customer invoicing
- **[Sales Operations](./02-core/sales/README.md)** - Sales forecasting, territory management, sales analytics, commission management
- **[Communication Hub](./02-core/communication-hub/README.md)** - Unified inbox for all channels (email, chat, calls), omnichannel customer engagement

### Finance & Accounting (5 modules)

- **[Accounting & Finance](./02-core/accounting-finance/README.md)** - Multi-currency, multi-entity financial management, general ledger, accounts payable/receivable, financial reporting, journal entries
- **[Bank Reconciliation](./02-core/bank-reconciliation/README.md)** - Automated bank statement import, reconciliation, payment matching
- **[Budget Management](./02-core/budget-management/README.md)** - Budget planning, tracking, variance analysis, forecast vs. actual
- **[Asset Management](./02-core/asset-management/README.md)** - Fixed asset tracking, depreciation, maintenance scheduling, asset lifecycle
- **[Fixed Assets (Additional)](./02-core/fixed-assets/README.md)** - Extended fixed asset capabilities, asset transfers, disposal

### Supply Chain & Operations (4 modules)

- **[Inventory Management](./02-core/inventory-management/README.md)** - Real-time stock tracking, warehouse management, stock transfers, batch/serial tracking, reorder levels
- **[Purchase Management](./02-core/purchase-management/README.md)** - Procure-to-pay automation, purchase requisitions, RFQs, purchase orders, supplier management
- **[Purchase Operations](./02-core/purchase/README.md)** - Supplier evaluation, purchase analytics, procurement contracts
- **[Project Management](./02-core/project-management/README.md)** - Enterprise project planning, task management, resource allocation, time tracking, Gantt charts, project costing

### Human Capital Management (1 module)

- **[Human Resources](./02-core/human-resources/README.md)** - Complete HRMS with payroll, attendance, leave management, recruitment, performance reviews, employee lifecycle

### Governance & Data Management (5 modules)

- **[Compliance & Risk Management](./02-core/compliance-risk-management/README.md)** - Regulatory compliance, risk assessment, audit trails, policy management, SOC2/GDPR/ISO compliance
- **[Master Data Management (MDM)](./02-core/master-data-management/README.md)** - Single source of truth for master data (customers, suppliers, products, locations) with AI-powered deduplication, data quality validation, governance workflows
- **[Business Intelligence & Analytics](./02-core/business-intelligence/README.md)** - Real-time dashboards, custom reports, data visualization, KPI tracking, predictive analytics
- **[Multi-Company Management](./02-core/multi-company/README.md)** - Consolidated reporting, inter-company transactions, multi-entity accounting, cross-company workflows
- **[Compliance Management](./02-core/compliance-management/README.md)** - Audit & governance, complete audit trails, compliance reporting, regulatory frameworks

### Communication & Marketing (1 module)

- **[Email Marketing](./02-core/email-marketing/README.md)** - Campaign management, automation, segmentation, analytics, A/B testing, transactional emails, deliverability tools

### Document Management (1 module)

- **[Document Management System (DMS)](./02-core/dms/README.md)** - Core business document management, workflow integration, approval routing

**Total Core Modules: 21**

---

## [03. Industry-Specific Modules](./03-industry-specific/)

**IMPLEMENTATION STATUS:** ❌ **SPECIFICATION ONLY - NOT FOR IMPLEMENTATION UNTIL PHASE 8+**
**CURRENT PHASE:** Phase 1 (Platform Foundations)
**WHEN:** Phase 8+ (After core modules proven operational)
**DO NOT IMPLEMENT:** These modules are documented for future reference only. Platform + core modules must be operational first.

**Purpose**: Specialized modules for specific industry verticals, niche use cases, or optional business capabilities.

**Characteristics**:
- Only relevant to specific industries or use cases
- Not universal - tailored to vertical needs
- Optional, tenant-selectable based on subscription
- Can depend on core modules

### Manufacturing & Production (8 modules)

- **[Manufacturing](./03-industry-specific/manufacturing/README.md)** - Production planning, BOM management, quality control, AI-powered scheduling, shop floor execution, MRP/MPS, work order management, material requirement planning
- **[Advanced Planning & Scheduling (APS)](./03-industry-specific/advanced-planning-scheduling/README.md)** - Intelligent production planning, finite capacity scheduling, multi-constraint optimization, what-if scenario analysis
- **[Supply Chain Management](./03-industry-specific/supply-chain/README.md)** - End-to-end supply chain optimization, demand planning, supplier collaboration, logistics management
- **[Product Lifecycle Management (PLM)](./03-industry-specific/product-lifecycle-management/README.md)** - Product design, engineering change management, BOM versioning, design collaboration, R&D workflows
- **[Quality Management System (QMS)](./03-industry-specific/qms-gxp/README.md)** - GxP compliance, inspections, non-conformance tracking, AI-powered quality control, batch tracking
- **[Subcontracting](./03-industry-specific/subcontracting/README.md)** - Subcontractor management, outsourced production, component tracking, subcontractor invoicing
- **[Maintenance & CMMS](./03-industry-specific/maintenance-cmms/README.md)** - Computerized maintenance management, preventive maintenance, work order management, asset maintenance
- **[IoT & Industry 4.0](./03-industry-specific/iot-industry-4.0/README.md)** - IoT device integration, real-time machine data, predictive maintenance, smart factory

### Finance & Treasury (2 modules)

- **[Treasury Management](./03-industry-specific/treasury-management/README.md)** - Cash management hub with forecasting, FX risk management, investments, debt, liquidity planning
- **[Revenue Management (ASC 606)](./03-industry-specific/revenue-management/README.md)** - Revenue recognition, performance obligations, revenue allocation, ASC 606/IFRS 15 compliance

### Trade & Logistics (6 modules)

- **[Global Trade Management](./03-industry-specific/global-trade-management/README.md)** - Import/export compliance, customs documentation, trade finance, incoterms, HS codes
- **[Blanket & Framework Agreements](./03-industry-specific/blanket-agreements/README.md)** - Long-term procurement agreements, release orders, commitment tracking
- **[Fleet Management](./03-industry-specific/fleet-management/README.md)** - Vehicle registry, driver management, maintenance scheduling, GPS tracking, fuel management
- **[Logistics Operations](./03-industry-specific/logistics/README.md)** - Route optimization, shipment tracking, freight management, 3PL operations
- **[Logistics & Transportation](./03-industry-specific/logistics-transportation/README.md)** - Advanced logistics capabilities, warehouse management, cross-docking
- **[EDI (Electronic Data Interchange)](./03-industry-specific/edi/README.md)** - B2B electronic transactions, EDI standards (EDIFACT, X12), partner integration

### AI & Analytics (5 modules)

- **[AI Service Desk](./03-industry-specific/ai-service-desk/README.md)** - Autonomous technical support, configuration assistance, AI-powered troubleshooting
- **[AI Analytics & Insights](./03-industry-specific/ai-analytics/README.md)** - Predictive analytics across all modules, anomaly detection, forecasting, prescriptive insights
- **[Demand Forecasting](./03-industry-specific/demand-forecasting/README.md)** - AI-powered demand prediction, seasonal analysis, inventory optimization
- **[Knowledge Base](./03-industry-specific/knowledge-base/README.md)** - Internal knowledge management, documentation, FAQs, AI-powered search
- **[Ask Amani (AI Assistant)](./03-industry-specific/ask-amani/README.md)** - Intelligent ERP assistant, natural language queries, guided workflows

### Marketing & Communication (12 modules)

- **[Marketing Automation](./03-industry-specific/marketing-automation/README.md)** - Lead nurturing, drip campaigns, scoring, behavioral triggers, multi-touch attribution
- **[Campaign Management](./03-industry-specific/campaign-management/README.md)** - Multi-channel campaign orchestration, A/B testing, ROI tracking
- **[Social Media Management](./03-industry-specific/social-media-management/README.md)** - Multi-platform social media management, post scheduling, engagement tracking
- **[Social Media Marketing](./03-industry-specific/social-media-marketing/README.md)** - Social advertising, influencer management, social commerce
- **[SMS Marketing](./03-industry-specific/sms-marketing/README.md)** - SMS campaign management, automation, segmentation, TCPA/GDPR compliance
- **[Live Chat & Chatbots](./03-industry-specific/live-chat/README.md)** - Website chat with AI-powered bots, real-time customer support, chatbot builder
- **[Content Management System (CMS)](./03-industry-specific/content-management/README.md)** - Content creation, editorial workflows, SEO optimization, multi-author support, versioning
- **[Customer Feedback & Surveys](./03-industry-specific/feedback-surveys/README.md)** - NPS, CSAT, survey automation, feedback analysis
- **[Lead Nurturing](./03-industry-specific/lead-nurturing/README.md)** - Automated lead engagement, scoring, qualification, handoff to sales
- **[Marketing Analytics](./03-industry-specific/marketing-analytics/README.md)** - Campaign performance, channel analytics, ROI analysis, funnel analysis
- **[Website Builder](./03-industry-specific/website-builder/README.md)** - Drag-and-drop website builder with e-commerce, landing pages, SEO tools
- **[Website Management](./03-industry-specific/website/README.md)** - Website hosting, domain management, SSL certificates, CDN integration

### Messaging & Collaboration (4 modules)

- **[WhatsApp Business Integration](./03-industry-specific/whatsapp-business/README.md)** - WhatsApp API for customer engagement, automated messaging, chatbots
- **[Telegram Integration](./03-industry-specific/telegram/README.md)** - Bot management, business messaging, notifications
- **[Slack Integration](./03-industry-specific/slack/README.md)** - Team collaboration, ERP notifications, slash commands, workflow automation
- **[Microsoft Teams Integration](./03-industry-specific/ms-teams/README.md)** - Enterprise communication, bot integration, channel notifications

### Data & Infrastructure (5 modules)

- **[Data Warehouse & ETL](./03-industry-specific/data-warehouse-etl/README.md)** - Centralized data repository, transformations, dimensional modeling
- **[Data Warehouse (Additional)](./03-industry-specific/data_warehouse/README.md)** - Extended data warehousing capabilities
- **[Cloud Storage Integration](./03-industry-specific/cloud-storage/README.md)** - Multi-provider cloud storage (AWS S3, Azure Blob, Google Cloud, MinIO), CDN, encryption
- **[Mobile Applications](./03-industry-specific/mobile-apps/README.md)** - Native iOS & Android apps, offline sync, push notifications
- **[Offline Mode](./03-industry-specific/offline-mode/README.md)** - Sync capability for disconnected operations, conflict resolution

### Support & Services (3 modules)

- **[Support & Helpdesk](./03-industry-specific/support-helpdesk/README.md)** - Customer support ticketing, SLA management, knowledge base integration
- **[Advanced Service Management](./03-industry-specific/advanced-service-management/README.md)** - Field service management, service contracts, technician scheduling
- **[Support Operations](./03-industry-specific/support/README.md)** - Support analytics, escalation management, customer satisfaction tracking

### Specialized Business Modules (7 modules)

- **[Point of Sale (POS)](./03-industry-specific/pos/README.md)** - Omnichannel retail operations, offline POS, payment processing, inventory sync
- **[Project Portfolio Management](./03-industry-specific/project-portfolio-management/README.md)** - Enterprise portfolio management, resource capacity planning, program management
- **[Research & Development](./03-industry-specific/research-development/README.md)** - R&D project management, innovation tracking, patent management
- **[Package Management](./03-industry-specific/package-management/README.md)** - Software package and dependency management for custom apps
- **[Portals](./03-industry-specific/portals/README.md)** - Customer & supplier self-service portals, external collaboration
- **[Portal (Additional)](./03-industry-specific/portal/README.md)** - Extended portal capabilities
- **[Business Intelligence (Additional)](./03-industry-specific/business-intelligence/README.md)** - Industry-specific BI dashboards and analytics

### Industry Verticals (16 modules)

- **[Healthcare Management](./03-industry-specific/healthcare/README.md)** - HIPAA-compliant healthcare management, patient management, EHR, appointments, telemedicine, pharmacy, LIS, RIS, medical billing
- **[Financial Services](./03-industry-specific/financial-services/README.md)** - Banking, insurance, wealth management, loan origination, KYC/AML compliance, fraud detection, regulatory reporting
- **[Hospitality & Restaurant](./03-industry-specific/hospitality-restaurant/README.md)** - Hotel management, restaurant POS, reservations, housekeeping, menu management, online ordering
- **[Hospitality Operations](./03-industry-specific/hospitality/README.md)** - Extended hospitality capabilities, guest services, loyalty programs
- **[Retail Management](./03-industry-specific/retail/README.md)** - Retail operations, merchandising, customer loyalty, promotions
- **[Retail & E-Commerce](./03-industry-specific/retail-ecommerce/README.md)** - E-commerce platform, product catalog, order management, omnichannel retail
- **[Professional Services](./03-industry-specific/professional-services/README.md)** - Project & time tracking, resource management, billable hours, milestone billing, client management
- **[Automotive Industry](./03-industry-specific/automotive/README.md)** - Vehicle lifecycle management, parts tracking, service management, dealership operations, warranty management
- **[Energy & Utilities](./03-industry-specific/energy-utilities/README.md)** - Utility operations, meter management, billing, outage management, grid management
- **[Spa & Wellness Management](./03-industry-specific/spa-wellness/README.md)** - Spa operations, therapist scheduling, hour-based packages, franchise management, WhatsApp/UPI integration
- **[Travel & Expense Management](./03-industry-specific/travel-expense-management/README.md)** - AI-native T&E platform, autonomous expense processing, predictive compliance, blockchain-verified receipts
- **[CHA India (Customs House Agent)](./03-industry-specific/cha-india/README.md)** - India-specific customs clearance, documentation, regulatory compliance

**Additional Industry Verticals** (documented but folders may vary):
- Education Management
- Real Estate & Construction
- Agriculture Management
- Nonprofit Management
- Pharmaceutical & Life Sciences
- Media & Entertainment
- Telecommunications
- Government Management
- Environmental Services

**Total Industry-Specific Modules: 65+**

---

## Module Implementation Rules (Non-Negotiable)

### 1. Module Manifest (REQUIRED)
Every module MUST have `manifest.yaml`:

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

### 2. Module Structure (REQUIRED)

```
/module_name/
  __init__.py
  manifest.yaml
  models.py          # Django ORM models with tenant_id (CRITICAL)
  views.py           # DRF ViewSet and APIView classes
  serializers.py     # DRF serializers for validation
  urls.py            # URL routing configuration
  services.py        # Business logic (NOT in views)
  permissions.py     # DRF permission classes
  policies.py        # ABAC policy definitions
  workflows.py       # Workflow definitions
  search.py          # Search index configuration
  migrations/        # Django migrations (from manage.py makemigrations)
  tests/             # ≥90% coverage REQUIRED
```

### 3. Tenant Isolation (CRITICAL)
- All tenant-scoped tables MUST have `tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)` (Django ORM)
- All queries MUST filter by `tenant_id` from authenticated session
- Row-Level Security (RLS) optional for highest-risk tables

### 4. Session Authentication (REQUIRED - FROZEN ARCHITECTURE)
- Routes MUST use `get_current_user_from_session` dependency injection
- Never implement auth/login/logout/session management in modules
- Sessions contain identity snapshot (roles[], groups[], jit_grants[], policy_version) - authorization evaluated per-request by Policy Engine

### 5. Authorization (REQUIRED - FROZEN ARCHITECTURE)
- Declare permissions in `manifest.yaml`
- Use Policy Engine for authorization checks
- Sessions contain identity snapshot (NOT effective permissions or authorization decisions)
- Policy Engine evaluates: identity_snapshot + resource + context → allow/deny at request time

### 6. API Routes (REQUIRED)
- Prefix: `/api/v1/{module-name}/{resource}`
- Use Django URL routing: `path('api/v1/module_name/', include(module_urls))` in `backend/src/main.py`
- Return proper HTTP status codes (201 create, 204 delete, 404 not found, 403 forbidden)
- Include error details in response body

### 7. Testing (REQUIRED)
- ≥90% coverage enforced by CI
- Use fixtures from `backend/tests/conftest.py`
- Tests in `module/tests/` subdirectory
- Cover happy paths, edge cases, error scenarios

### 8. Database Migrations (REQUIRED)
- Django migrations per-module in `module/migrations/`
- Idempotent migrations (use `IF NOT EXISTS` checks)
- Never modify existing migrations - create new ones
- Handle concurrent execution safely

---

## Module Installation Model

### Foundation Modules
- **Installation**: Platform-level, always available
- **Access Control**: Not tenant-configurable
- **Rationale**: Required for platform operations

### Core Modules
- **Installation**: Auto-installed for all new tenants (default)
- **Access Control**: Cannot be uninstalled (tenant lifecycle dependency)
- **Rationale**: Essential for universal business operations

### Industry-Specific Modules
- **Installation**: Optional, tenant-selectable based on subscription plan
- **Access Control**: `ModuleAccessMiddleware` checks per-tenant installation before route access
- **Rationale**: Only relevant to specific industries or use cases

---

## Architectural Anti-Patterns (FORBIDDEN)

❌ **Modules implementing authentication, login, logout, session management, or credential handling**  
❌ **Omitted `tenant_id` columns in tenant-scoped models**  
❌ **Forgetting tenant filtering in queries (data leakage risk)**  
❌ **JWT tokens for interactive users (session-based auth only)**  
❌ **Modules without `manifest.yaml` contract**  
❌ **Dynamic route registration (static registration in `main.py` only)**  
❌ **Skipping tests (90% coverage mandatory)**  
❌ **Circular module dependencies**  
❌ **Modifying audit logs (they're immutable)**  
❌ **Bypassing pre-commit hooks**  
❌ **Using `any` type in TypeScript**  
❌ **Database transactions in route handlers (use services only)**  

---

## Summary

| Category | Count | Purpose |
|----------|-------|---------|
| **Foundation** | 22 | Platform infrastructure |
| **Core** | 21 | Universal business operations |
| **Industry-Specific** | 65+ | Vertical-specific modules |
| **TOTAL** | **108+** | **Complete ERP ecosystem** |

---

## References

- **[Module Framework](../architecture/module-framework.md)** - Detailed module architecture specification
- **[Application Architecture](../architecture/application-architecture.md)** - Overall system architecture
- **[Security Model](../architecture/security-model.md)** - Security, RBAC, ABAC, SoD specifications
- **[Authentication Spec](../architecture/authentication-and-session-management-spec.md)** - Session authentication details
- **[Policy Engine Spec](../architecture/policy-engine-spec.md)** - Authorization policy engine

---

**Document Authority**: This document is the authoritative baseline for SARAISE module organization. All implementations MUST align with this structure and architectural rules.

**Author**: SARAISE Architecture Team  
**Reviewed**: 2026-01-03  
**Next Review**: Quarterly or upon major architectural change
