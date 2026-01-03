# Data Migration Framework Integrations

<!-- SPDX-License-Identifier: Apache-2.0 -->

## Inter-Module Integrations

### Master Data Management (MDM)

**Integration Points:**
- Data quality validation using MDM quality rules
- Duplicate detection using MDM deduplication service
- Master data entity creation as migration target

**Services:**
- `MDMAdapterService`: Adapter for MDM integration
- `validate_migration_data()`: Validates data against MDM rules
- `check_duplicates()`: Checks duplicates using MDM
- `create_master_data_entities()`: Creates MDM entities

### Quality Management System (QMS/GxP)

**Integration Points:**
- Audit trail logging for all migration operations
- Change control workflows for regulated data
- Validation records for migration validation

**Services:**
- `QMSAdapterService`: Adapter for QMS integration
- `log_migration_audit_trail()`: Logs to QMS audit trail
- `create_change_control_for_migration()`: Creates change control
- `create_validation_for_migration()`: Creates validation record

### Workflow Automation

**Integration Points:**
- Approval gates for migration jobs
- Error handling workflows
- Migration job orchestration

**Services:**
- `WorkflowOrchestratorService`: Orchestrator for workflows
- `create_migration_approval_workflow()`: Creates approval workflow
- `execute_migration_with_workflow()`: Executes via workflow

### Module-Specific Adapters

**CRM Module:**
- `CRMAdapter`: Handles Customer, Contact, Lead, Opportunity migrations
- Validates CRM-specific requirements
- Transforms data to CRM format

**Inventory Module:**
- Adapter for Item, Warehouse, Stock Entry migrations
- (To be implemented)

**Accounting Module:**
- Adapter for Account, Journal Entry, Invoice migrations
- (To be implemented)

## Source System Connectors

### SAP Connector
- Connects to SAP systems via RFC
- Extracts data from SAP tables
- Supports SAP-specific data types

### Salesforce Connector
- Connects via Salesforce API
- Extracts data using SOQL queries
- Handles Salesforce object relationships

### Database Connector
- Supports PostgreSQL, MySQL, SQL Server, Oracle
- Generic SQL query execution
- Connection pooling

## Event Bus Integration

**Published Events:**
- `migration_started`: When migration starts
- `migration_completed`: When migration completes
- `migration_failed`: When migration fails
- `migration_progress`: Progress updates

**Event Publisher:**
- `EventPublisherService`: Publishes events to event bus

## Webhook Integration

**Supported Events:**
- Migration started/completed/failed
- Validation complete
- Record imported
- Migration rolled back

**Webhook Service:**
- `register_webhook()`: Register webhook for event
- `trigger_webhook()`: Trigger webhook notification
