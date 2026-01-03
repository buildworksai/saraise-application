<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tenant Management Module

---

## ✅ IMPLEMENTATION PHASE STATUS

**IMPLEMENTATION STATUS:** ✅ **ACTIVE IMPLEMENTATION - Phase 1-5**

**CURRENT PHASE:** Phase 1 (Platform Foundations)

**WHEN TO IMPLEMENT:** NOW (Platform infrastructure priority)

**FOUNDATION MODULE CONTEXT:**
- **APPROVED FOR IMMEDIATE IMPLEMENTATION** - Foundation modules are Phase 1-5 priority
- This is a **critical platform infrastructure** module required for multi-tenancy
- Foundation modules enable the platform to function and support business modules
- Implementation follows frozen architecture (row-level multitenancy, session auth, policy engine)

**DEPENDENCIES:**
- Requires: Platform infrastructure (database, session management, policy engine)
- Enables: All other modules (provides tenant isolation and subscription management)
- Phase: Phase 1 (Platform Foundations) - Active implementation

**IMPLEMENTATION PRIORITY:** Foundation modules implement FIRST before any business modules.

---

## Executive Summary

The Tenant Management module is the cornerstone of SARAISE's multi-tenant architecture, handling the complete lifecycle of tenant organizations from initial signup through ongoing management and eventual off-boarding. This module ensures complete data isolation, enables flexible subscription management, and provides self-service capabilities for tenant administrators.

**Vision**: Enable frictionless tenant onboarding with zero-touch provisioning while maintaining enterprise-grade security, isolation, and customization capabilities.

## World-Class Features

### 1. Tenant Lifecycle Management (FROZEN ARCHITECTURE - Row-Level Multitenancy)
- **Instant Provisioning**: Create fully functional tenant in < 30 seconds
- **Row-Level Isolation**: Shared schema with mandatory tenant_id filtering (NO dedicated schemas per tenant)
- **White-Label Branding**: Custom logo, colors, domain name per tenant
- **Subdomain Management**: Auto-configure DNS for tenant.saraise.com
- **Custom Domain Support**: Use own domain (mycompany.com) with SSL certificates
- **Multi-Language Support**: 50+ languages with automatic locale detection
- **Timezone Configuration**: Automatic timezone detection and configuration
- **Currency Settings**: Multi-currency with automatic exchange rate updates
- **Fiscal Year Configuration**: Custom fiscal year start dates

### 2. Subscription & Module Management
- **Flexible Subscription Plans**: Starter, Professional, Enterprise, Custom
- **Per-Module Licensing**: Enable/disable modules based on subscription
- **Usage-Based Billing**: Track API calls, storage, users for metered billing
- **Trial Management**: 14/30-day trials with automatic conversion
- **Plan Upgrades/Downgrades**: Seamless plan transitions with pro-rated billing
- **Add-On Modules**: Purchase additional modules à la carte
- **User Seat Management**: Add/remove user licenses dynamically
- **Module Installation**: One-click module activation with dependency resolution
- **Module Uninstallation**: Safe removal with data export option

### 3. Tenant Administration
- **Admin Dashboard**: Comprehensive overview of tenant health and usage
- **User Management**: Invite users, assign roles, manage permissions
- **Department/Team Management**: Organize users into departments and teams
- **Branch/Location Management**: Multi-location support for retail/services
- **Company Profile**: Logo, business details, tax registration info
- **Contact Information**: Primary contact, billing contact, technical contact
- **Notification Preferences**: Configure email, SMS, push notification settings
- **Data Import**: Bulk import data from CSV, Excel, or previous system
- **Data Export**: Complete data export in JSON, CSV, or SQL format

### 4. Security & Access Control
- **SSO Integration**: SAML 2.0, OAuth 2.0, OpenID Connect support
- **Multi-Factor Authentication**: SMS, TOTP, hardware tokens, biometric
- **Password Policies**: Complexity, expiration, history requirements
- **Session Management**: Concurrent session limits, device management
- **IP Whitelisting**: Restrict access to known IP ranges
- **Audit Trail**: Complete log of all tenant administrative actions
- **Data Encryption**: At-rest encryption with tenant-specific keys
- **Backup & Recovery**: Automated daily backups with point-in-time recovery
- **GDPR Tools**: Right to access, right to erasure, data portability

### 5. Tenant Collaboration
- **Multi-Tenant Groups**: Parent company with multiple subsidiary tenants
- **Cross-Tenant Reporting**: Consolidated reports across tenant group
- **Shared Resources**: Share users, documents, integrations across tenants
- **Tenant-to-Tenant Data Sharing**: Secure data exchange between tenants
- **Franchise Management**: Franchisor manages franchisee tenants
- **Partner Portal**: Allow partners limited access to specific data

### 6. Resource Management
- **Storage Quotas**: Set limits on file storage, database size
- **API Rate Limits**: Requests per minute/hour/day limits
- **User Limits**: Maximum active users per subscription plan
- **Bandwidth Monitoring**: Track data transfer in/out
- **Resource Usage Dashboard**: Real-time visibility into resource consumption
- **Overage Alerts**: Notify when approaching limits
- **Auto-Scaling**: Automatically increase resources (with billing adjustment)

### 7. Tenant Health Monitoring
- **Health Score**: Overall tenant health based on usage, errors, performance
- **Activity Monitoring**: Track user login frequency, feature usage
- **Error Rate Tracking**: Monitor application errors per tenant
- **Performance Metrics**: API response times, page load times per tenant
- **Churn Risk Prediction**: ML model predicts likelihood of cancellation
- **Usage Trends**: Analyze usage patterns over time
- **Feature Adoption**: Track which modules/features are actively used
- **Customer Success Alerts**: Notify CSM of at-risk tenants

### 8. Compliance & Governance
- **Data Residency**: Choose data center region (US, EU, Asia, etc.)
- **Data Retention Policies**: Configure retention periods per data type
- **Legal Hold**: Preserve data for litigation or regulatory requirements
- **Compliance Certifications**: Track tenant-specific compliance (HIPAA, PCI-DSS)
- **Terms of Service Acceptance**: Version-controlled ToS with acceptance tracking
- **Privacy Policy Management**: Manage and communicate privacy policy changes
- **Data Processing Agreements**: DPA management for GDPR compliance

## Database Schema

```sql
-- Tenants (Main table)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE, -- URL-safe identifier
    subdomain VARCHAR(100) UNIQUE, -- tenant.saraise.com
    custom_domain VARCHAR(200) UNIQUE, -- mycompany.com
    status VARCHAR(50) NOT NULL DEFAULT 'active', -- 'trial', 'active', 'suspended', 'cancelled'
    subscription_plan_id UUID REFERENCES subscription_plans(id),
    trial_ends_at TIMESTAMPTZ,
    subscription_start_date DATE,
    subscription_end_date DATE,

    -- Contact Information
    primary_contact_name VARCHAR(200),
    primary_contact_email VARCHAR(200),
    primary_contact_phone VARCHAR(50),
    billing_email VARCHAR(200),
    technical_email VARCHAR(200),

    -- Company Information
    logo_url VARCHAR(500),
    website_url VARCHAR(500),
    industry VARCHAR(100),
    company_size VARCHAR(50), -- '1-10', '11-50', '51-200', '201-500', '500+'
    tax_id VARCHAR(100),

    -- Configuration
    timezone VARCHAR(100) DEFAULT 'UTC',
    default_language VARCHAR(10) DEFAULT 'en',
    default_currency VARCHAR(10) DEFAULT 'USD',
    fiscal_year_start_month INTEGER DEFAULT 1 CHECK (fiscal_year_start_month BETWEEN 1 AND 12),
    date_format VARCHAR(50) DEFAULT 'YYYY-MM-DD',
    time_format VARCHAR(50) DEFAULT 'HH:mm:ss',

    -- Branding
    primary_color VARCHAR(7), -- Hex color code
    secondary_color VARCHAR(7),
    accent_color VARCHAR(7),

    -- Feature Flags
    features_enabled JSONB DEFAULT '{}',

    -- Resource Limits
    max_users INTEGER DEFAULT 10,
    max_storage_gb INTEGER DEFAULT 10,
    max_api_calls_per_day INTEGER DEFAULT 10000,

    -- FROZEN ARCHITECTURE: Row-Level Multitenancy
    -- NO database_host, database_name, or database_schema fields
    -- ALL tenants share same schema with tenant_id filtering

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    onboarded_by UUID REFERENCES users(id),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_tenants_status ON tenants(status);
CREATE INDEX idx_tenants_subscription_plan ON tenants(subscription_plan_id);
CREATE INDEX idx_tenants_created_at ON tenants(created_at DESC);

-- Tenant Modules (Which modules are enabled for each tenant)
CREATE TABLE tenant_modules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    module_name VARCHAR(100) NOT NULL, -- 'accounting', 'crm', 'inventory'
    is_enabled BOOLEAN DEFAULT true,
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    installed_by UUID REFERENCES users(id),
    version VARCHAR(50),
    configuration JSONB DEFAULT '{}',
    last_used_at TIMESTAMPTZ,
    usage_count INTEGER DEFAULT 0,
    UNIQUE(tenant_id, module_name)
);

CREATE INDEX idx_tenant_modules_tenant ON tenant_modules(tenant_id);
CREATE INDEX idx_tenant_modules_enabled ON tenant_modules(tenant_id, is_enabled);

-- Tenant Resource Usage (Track actual resource consumption)
CREATE TABLE tenant_resource_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date DATE NOT NULL,

    -- Usage Metrics
    active_users INTEGER DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    storage_used_gb DECIMAL(10,2) DEFAULT 0,
    bandwidth_used_gb DECIMAL(10,2) DEFAULT 0,
    email_sent INTEGER DEFAULT 0,
    sms_sent INTEGER DEFAULT 0,

    -- Performance Metrics
    avg_response_time_ms DECIMAL(10,2),
    error_count INTEGER DEFAULT 0,
    slow_query_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, date)
);

CREATE INDEX idx_resource_usage_tenant_date ON tenant_resource_usage(tenant_id, date DESC);

-- Tenant Settings (Key-value configuration)
CREATE TABLE tenant_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL, -- 'email', 'notifications', 'security'
    key VARCHAR(200) NOT NULL,
    value JSONB NOT NULL,
    is_encrypted BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID REFERENCES users(id),
    UNIQUE(tenant_id, category, key)
);

CREATE INDEX idx_tenant_settings_tenant ON tenant_settings(tenant_id);
CREATE INDEX idx_tenant_settings_category ON tenant_settings(tenant_id, category);

-- Tenant Integrations (SSO, OAuth providers)
CREATE TABLE tenant_sso_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL, -- 'saml', 'oauth2', 'oidc'
    provider_name VARCHAR(200), -- 'Okta', 'Azure AD', 'Google Workspace'
    is_enabled BOOLEAN DEFAULT true,

    -- SAML Configuration
    saml_entity_id VARCHAR(500),
    saml_sso_url VARCHAR(500),
    saml_certificate TEXT,

    -- OAuth/OIDC Configuration
    oauth_client_id VARCHAR(200),
    oauth_client_secret VARCHAR(500), -- Encrypted
    oauth_authorization_url VARCHAR(500),
    oauth_token_url VARCHAR(500),
    oauth_userinfo_url VARCHAR(500),

    -- Attribute Mapping
    attribute_mapping JSONB, -- Map SSO attributes to user fields

    -- Settings
    auto_provision_users BOOLEAN DEFAULT false,
    default_role VARCHAR(100),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tenant_sso_tenant ON tenant_sso_config(tenant_id);

-- Tenant Audit Log
CREATE TABLE tenant_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL, -- 'user_invited', 'module_enabled', 'settings_changed'
    resource_type VARCHAR(100),
    resource_id UUID,
    changes JSONB, -- Before/after values
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('tenant_audit_log', 'timestamp');
CREATE INDEX idx_tenant_audit_tenant ON tenant_audit_log(tenant_id, timestamp DESC);

-- Tenant Data Export Requests
CREATE TABLE tenant_data_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    requested_by UUID NOT NULL REFERENCES users(id),
    export_type VARCHAR(50) NOT NULL, -- 'full', 'module_specific', 'gdpr_export'
    format VARCHAR(50) NOT NULL, -- 'json', 'csv', 'sql', 'excel'
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed'
    modules VARCHAR(100)[], -- Specific modules to export
    file_url VARCHAR(500), -- S3 URL for download
    file_size_bytes BIGINT,
    expires_at TIMESTAMPTZ, -- Download link expiration
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX idx_data_exports_tenant ON tenant_data_exports(tenant_id, requested_at DESC);

-- Tenant Health Scores
CREATE TABLE tenant_health_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    overall_score INTEGER CHECK (overall_score BETWEEN 0 AND 100),

    -- Component Scores
    usage_score INTEGER CHECK (usage_score BETWEEN 0 AND 100),
    engagement_score INTEGER CHECK (engagement_score BETWEEN 0 AND 100),
    performance_score INTEGER CHECK (performance_score BETWEEN 0 AND 100),
    support_score INTEGER CHECK (support_score BETWEEN 0 AND 100),

    -- Risk Indicators
    churn_risk VARCHAR(50), -- 'low', 'medium', 'high', 'critical'
    churn_probability DECIMAL(5,2), -- 0-100%

    -- Recommendations
    recommendations TEXT[],

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, date)
);

CREATE INDEX idx_health_scores_tenant ON tenant_health_scores(tenant_id, date DESC);
CREATE INDEX idx_health_scores_risk ON tenant_health_scores(churn_risk, date DESC);

-- Tenant Groups (For multi-tenant organizations)
CREATE TABLE tenant_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    parent_tenant_id UUID NOT NULL REFERENCES tenants(id),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tenant_group_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES tenant_groups(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, tenant_id)
);

CREATE INDEX idx_group_members_group ON tenant_group_members(group_id);
CREATE INDEX idx_group_members_tenant ON tenant_group_members(tenant_id);
```

## API Specification

### Tenant Management

```
POST   /api/v1/tenants                    # Create new tenant (signup)
GET    /api/v1/tenants/:id                # Get tenant details
PUT    /api/v1/tenants/:id                # Update tenant
DELETE /api/v1/tenants/:id                # Delete tenant (with confirmation)
GET    /api/v1/tenants/:id/health         # Get tenant health score
GET    /api/v1/tenants/:id/usage          # Get resource usage
POST   /api/v1/tenants/:id/suspend        # Suspend tenant
POST   /api/v1/tenants/:id/activate       # Reactivate tenant
```

### Module Management

```
GET    /api/v1/tenants/:id/modules        # List installed modules
POST   /api/v1/tenants/:id/modules        # Install module
DELETE /api/v1/tenants/:id/modules/:name  # Uninstall module
PUT    /api/v1/tenants/:id/modules/:name  # Update module configuration
GET    /api/v1/tenants/:id/modules/available # List available modules for subscription
```

### Tenant Settings

```
GET    /api/v1/tenants/:id/settings       # Get all settings
GET    /api/v1/tenants/:id/settings/:category # Get settings by category
PUT    /api/v1/tenants/:id/settings/:category/:key # Update specific setting
POST   /api/v1/tenants/:id/settings/bulk # Bulk update settings
```

### SSO Configuration

```
GET    /api/v1/tenants/:id/sso            # Get SSO configuration
POST   /api/v1/tenants/:id/sso            # Configure SSO
PUT    /api/v1/tenants/:id/sso/:provider  # Update SSO provider
DELETE /api/v1/tenants/:id/sso/:provider  # Remove SSO provider
POST   /api/v1/tenants/:id/sso/:provider/test # Test SSO connection
```

### Data Export

```
POST   /api/v1/tenants/:id/export         # Request data export
GET    /api/v1/tenants/:id/export/:exportId # Get export status
GET    /api/v1/tenants/:id/export/:exportId/download # Download export file
```

### Audit Log

```
GET    /api/v1/tenants/:id/audit-log      # Get audit log entries
GET    /api/v1/tenants/:id/audit-log/export # Export audit log
```

### Tenant Groups

```
GET    /api/v1/tenant-groups              # List all groups
POST   /api/v1/tenant-groups              # Create group
PUT    /api/v1/tenant-groups/:id          # Update group
DELETE /api/v1/tenant-groups/:id          # Delete group
POST   /api/v1/tenant-groups/:id/members  # Add tenant to group
DELETE /api/v1/tenant-groups/:id/members/:tenantId # Remove from group
```

## AI Agent Integration

### Tenant Onboarding Agent
- **Type**: Configuration Agent
- **Framework**: LangGraph with multi-step workflows
- **Autonomy Level**: Full Autonomy (within onboarding scope)

**Capabilities**:
1. **Interactive Onboarding**: Guide users through setup with natural language
2. **Smart Configuration**: Suggest optimal settings based on industry and company size
3. **Data Migration**: Assist with importing data from previous systems
4. **Module Recommendations**: Suggest relevant modules based on business needs
5. **Initial Setup**: Configure users, roles, departments automatically
6. **Training**: Provide contextual help and training during onboarding

**Example Conversation**:
```
User: "I need to set up accounting for my retail business"

Agent: "I'll help you set up accounting! I see you're in retail. I recommend:
1. Accounting module (already included in your plan)
2. Inventory module (for product tracking)
3. POS module (for in-store sales)

Would you like me to enable these modules and configure them for retail?"

User: "Yes, enable all three"

Agent: *Enables modules, creates default accounts for retail, sets up tax codes*
"Done! I've configured:
- Standard retail chart of accounts
- Sales tax settings for your state
- Payment methods (cash, card, etc.)
- Inventory tracking with FIFO costing

Would you like me to import your existing products?"
```

### Tenant Health Monitoring Agent
- **Type**: Analytics Agent
- **Framework**: CrewAI with scheduled tasks
- **Autonomy Level**: Read-Only + Notifications

**Capabilities**:
1. **Health Score Calculation**: Daily computation of tenant health metrics
2. **Churn Risk Prediction**: ML-based prediction of cancellation likelihood
3. **Usage Anomaly Detection**: Detect unusual patterns (sudden drop in usage)
4. **Proactive Outreach**: Alert CSM team about at-risk tenants
5. **Feature Adoption Analysis**: Identify underutilized features
6. **Performance Monitoring**: Track tenant-specific performance issues

## Customization Framework Integration

The Tenant Management module supports extensive customization through the SARAISE Customization Framework, enabling tenant-specific customizations without modifying core code.

### Customization Points

The module exposes the following customization points:

#### Tenant Resource
- **Server Scripts**:
  - `before_insert`: Execute custom logic before creating a new tenant (e.g., validation, default values)
  - `after_update`: Execute custom logic after tenant updates (e.g., sync with external systems, notifications)
- **Custom Reports**: Create tenant-specific reports for tenant analytics and management
- **Custom Forms**: Customize the tenant form layout per organization

#### TenantModule Resource
- **Server Scripts**:
  - `after_update`: Execute custom logic after module installation/update (e.g., custom configuration, data migration)
- **Custom Reports**: Create module usage and adoption reports
- **Custom Forms**: Customize module configuration forms

#### TenantQuotaUsage Resource
- **Server Scripts**:
  - `on_quota_exceeded`: Execute custom logic when quotas are exceeded (e.g., custom alerts, auto-scaling)
- **Custom Reports**: Create quota utilization and forecasting reports
- **Custom Forms**: Customize quota display and management forms

#### TenantHealthScore Resource
- **Server Scripts**:
  - `on_health_score_change`: Execute custom logic when health scores change (e.g., custom notifications, workflows)
- **Custom Reports**: Create health score trend analysis and predictive reports
- **Custom Forms**: Customize health score dashboard displays

### Demo Customizations

The demo tenant (`demo@saraise.com`) includes example server scripts demonstrating:
- Tenant creation validation and auto-configuration
- Module installation workflows
- Quota monitoring and alerting
- Health score change notifications

These can be found in the demo data seeder and serve as templates for tenant-specific customizations.

### AI-Powered Code Generation

The Customization Automation Agent can generate server scripts, custom reports, and forms for Tenant Management based on natural language specifications. For example:

```
"Create a server script that automatically sends a welcome email when a new tenant is created"
```

The agent will generate the appropriate Python server script with email integration and proper error handling.

---

## Workflow Automation

The Tenant Management module includes automated workflows for tenant lifecycle operations.

### Tenant Onboarding Workflow

**Description**: Automated tenant onboarding workflow

**Workflow Steps**:
1. **Data Ingestion**: Collect tenant data and configuration
2. **Validation**: Validate tenant data and subscription requirements
3. **Notification**: Send welcome email to tenant admin
4. **Data Output**: Create onboarded tenant with default configuration

**Implementation**:
- Service: `TenantAutomationService.automate_tenant_onboarding()`
- Automation: `AutoProvisioningService`
- Trigger: Manual or automated via API

**Use Cases**:
- Self-service tenant onboarding
- Automated tenant provisioning
- Initial configuration setup

### Quota Enforcement Workflow

**Description**: Workflow for enforcing tenant quotas

**Workflow Steps**:
1. **Data Ingestion**: Collect tenant usage data
2. **Validation**: Check quota limits against current usage
3. **Conditional Enforcement**: Enforce quota limits if exceeded
4. **Notification**: Notify tenant admin of quota exceeded
5. **Data Output**: Update quota status and violation records

**Implementation**:
- Service: `TenantAutomationService.automate_quota_management()`
- Automation: `AutoQuotaManagementService`
- Scheduled: Runs every hour via scheduler

**Use Cases**:
- Automated quota monitoring
- Quota violation enforcement
- Usage-based service limiting

---

## Ask Amani Integration

The Tenant Management module's AI agents are automatically discovered and integrated into Ask Amani (SARAISE's AI Assistant) through the module registry system.

### Dynamic Agent Discovery

Ask Amani dynamically discovers all AI agents from registered modules, including:

- **AI Onboarding Agent**: Guides new tenants through setup and configuration
- **Tenant Health Monitoring Agent**: Monitors tenant health and predicts churn risk
- **Tenant Analytics Agent**: Provides tenant usage analytics and insights
- **Tenant Optimization Agent**: Suggests tenant-specific optimizations

### Usage Example

Users can interact with these agents through Ask Amani:

```
User: "Help me set up my tenant for a retail business"

Amani: "I'll help you set up your tenant! [Uses AI Onboarding Agent]
        I recommend:
        1. Accounting module (for financial management)
        2. Inventory module (for product tracking)
        3. POS module (for in-store sales)

        Would you like me to enable these modules and configure them for retail?"
```

### Entry Point: "Show tenant usage and rate limits"

Users can query tenant usage and rate limits through Ask Amani:

```
User: "Show tenant usage and rate limits"

Amani: "I'll get your usage and rate limit information. [Uses Tenant Analytics Agent]

        Current Usage:
        - API Calls: 8,450 / 10,000 per month (84.5% used)
        - Users: 45 / 50 (90% used)
        - Storage: 12.5 GB / 20 GB (62.5% used)

        Rate Limits:
        - API Requests: 100 / minute (current: 45/min average)
        - Workflow Executions: 20 / hour (current: 8/hour average)

        Recommendations:
        - You're approaching your user limit. Consider upgrading to Pro plan for 100 users.
        - API usage is healthy, no action needed."
```

### Agent Capabilities in Ask Amani

All Tenant Management AI agents are accessible through Ask Amani with their full capabilities:
- Interactive onboarding guidance
- Health score calculation and monitoring
- Churn risk prediction
- Usage analytics and recommendations
- Tenant-specific optimizations

---

## Security & Compliance

### Security Measures
- **Data Isolation**: Complete database schema isolation per tenant
- **Encryption**: Tenant data encrypted at rest with unique keys
- **Network Isolation**: VPC per tenant (enterprise plan)
- **Access Control**: Row-level security enforces tenant boundaries
- **SSO Integration**: Enterprise-grade SAML 2.0, OIDC support
- **MFA Enforcement**: Require MFA for admin users
- **IP Whitelisting**: Restrict access by IP range
- **Session Security**: Secure, HTTP-only cookies with CSRF protection

### Compliance
- **GDPR**: Right to access, right to erasure, data portability tools
- **CCPA**: California privacy rights compliance
- **SOC 2 Type II**: Security, availability, confidentiality controls
- **ISO 27001**: Information security management
- **Data Residency**: Choose data center region (US, EU, Asia)
- **Data Retention**: Configurable retention policies
- **Audit Trails**: Immutable log of all data access and changes

## Implementation Roadmap

### Phase 1: Core Tenant Management (Q2 2025) - 6 weeks
- Tenant CRUD operations
- Basic subscription management
- Resource quota enforcement
- Subdomain configuration
- Database schema provisioning

### Phase 2: Module Management (Q2 2025) - 4 weeks
- Module installation/uninstallation
- Dependency resolution
- Module configuration per tenant
- Usage tracking per module

### Phase 3: Advanced Configuration (Q3 2025) - 6 weeks
- SSO integration (SAML, OAuth, OIDC)
- Custom domain support with SSL
- White-label branding
- Multi-language support
- Timezone and currency configuration

### Phase 4: Resource Management (Q3 2025) - 4 weeks
- Resource usage tracking
- Quota enforcement
- Overage alerts
- Auto-scaling with billing adjustment

### Phase 5: Tenant Health & Analytics (Q4 2025) - 6 weeks
- Health score calculation
- Churn risk prediction
- Usage analytics
- Feature adoption tracking
- Customer success dashboards

### Phase 6: AI-Powered Onboarding (Q4 2025) - 8 weeks
- Onboarding agent development
- Interactive setup wizard
- Smart configuration recommendations
- Data migration assistance
- Health monitoring agent

## Competitive Analysis

| Feature | SARAISE | Salesforce | ServiceNow | Odoo | Zoho |
|---------|---------|-----------|------------|------|------|
| Provisioning Time | < 30 seconds | 2-5 minutes | 5-10 minutes | 1-2 minutes | 1-2 minutes |
| Schema-per-Tenant | ✅ Yes | ❌ Shared | ❌ Shared | ✅ Yes | ❌ Shared |
| Custom Domains | ✅ Free | ✅ $300/month | ✅ Enterprise | ⚠️ Limited | ✅ Paid add-on |
| SSO (SAML) | ✅ All plans | ❌ Enterprise only | ❌ Enterprise only | ⚠️ Limited | ❌ Enterprise only |
| Module Installation | ✅ One-click | ⚠️ Complex | ⚠️ Complex | ✅ Easy | ✅ Easy |
| AI Onboarding | ✅ Full AI guidance | ❌ No | ❌ No | ❌ No | ❌ No |
| Data Export | ✅ Comprehensive | ⚠️ Limited | ⚠️ Limited | ✅ Good | ⚠️ Limited |
| Multi-Tenant Groups | ✅ Yes | ✅ Yes | ⚠️ Limited | ❌ No | ⚠️ Limited |
| Cost per Tenant | $0 base + usage | $25+/user | $100+/user | $20+/user | $15+/user |

**SARAISE Advantages**:
1. **True Isolation**: Schema-per-tenant vs shared-schema = better security and performance
2. **Fastest Provisioning**: < 30 seconds vs 2-10 minutes for competitors
3. **AI-Powered Onboarding**: 80% reduction in time-to-value vs manual onboarding
4. **Flexible Pricing**: Pay for what you use vs forced user-based pricing
5. **Enterprise Features for All**: SSO, custom domains, white-label on all plans

## Success Metrics

### Provisioning & Onboarding
- **Provisioning Time**: < 30 seconds (vs industry average of 5 minutes)
- **Onboarding Completion Rate**: > 85% complete setup within 24 hours
- **Time to First Value**: < 2 hours (vs industry average of 2-5 days)
- **AI Onboarding Usage**: > 60% of new tenants use AI guidance

### Tenant Health
- **Active Tenant Rate**: > 80% of tenants active monthly
- **Churn Rate**: < 5% monthly churn (target < 3%)
- **NPS Score**: > 50 (vs industry average of 30)
- **Health Score**: > 80 average across all tenants

### Performance & Reliability
- **Module Installation Time**: < 10 seconds
- **Settings Update Response**: < 100ms
- **Data Export Generation**: < 5 minutes for 10GB
- **Uptime per Tenant**: 99.95%+

### Resource Management
- **Quota Enforcement Accuracy**: 100% (no overages undetected)
- **Resource Prediction Accuracy**: > 85% for 30-day forecast
- **Cost per Tenant**: < $10/month for infrastructure

---

**Document Version**: 1.0
**Last Updated**: November 2024
**Owner**: Tenant Management Team
**Review Cycle**: Quarterly
