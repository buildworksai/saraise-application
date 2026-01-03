# Master Data Management - AI Agent Configuration

## Overview

The Master Data Management (MDM) module exposes AI agents for data quality validation, deduplication, and data enrichment. These agents are automatically discovered by Ask Amani and can be invoked through the SARAISE AI Assistant interface.

## Registered AI Agents

### 1. Duplicate Detector (`duplicate_detector`)

**Description:** AI agent for identifying potential duplicate records across master data entities.

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.3
- **Max Tokens:** 1000

**Use Cases:**
- Identify duplicate customers across CRM and ERP
- Find duplicate product entries with different SKUs
- Detect duplicate vendor records

**Integration Points:**
- Customer creation workflow
- Product catalog import
- Vendor onboarding

**Ask Amani Entry Points:**
- "Find duplicate customers"
- "Check for duplicate products"
- "Are there any duplicate vendors?"

### 2. Data Quality Validator (`data_quality_validator`)

**Description:** AI agent for validating master data against quality rules and standards.

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.2
- **Max Tokens:** 500

**Use Cases:**
- Validate address formats
- Check for missing mandatory fields
- Verify data consistency across systems
- Identify data anomalies

**Integration Points:**
- Data import pipelines
- Record update triggers
- Periodic quality audits

**Ask Amani Entry Points:**
- "Validate customer addresses"
- "Check product data quality"
- "Show data quality report"

### 3. Data Enrichment Agent (`data_enrichment_agent`)

**Description:** AI agent for enriching master data with external information.

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.5
- **Max Tokens:** 800

**Use Cases:**
- Enrich customer profiles with public data
- Add product descriptions and attributes
- Update vendor information

**Integration Points:**
- Customer onboarding
- Product catalog management
- Vendor management

**Ask Amani Entry Points:**
- "Enrich customer data for Acme Corp"
- "Suggest product descriptions"
- "Update vendor details"

## Workflows

### 1. Duplicate Detection Workflow (`duplicate_detection`)

**Description:** Automated workflow to detect and resolve duplicates.

**Steps:**
1. Data Ingestion: Monitor new record creation
2. Analysis: Run `duplicate_detector` agent
3. Flagging: Mark potential duplicates
4. Resolution: Create task for data steward

**AI Agent Integration:**
- Uses `duplicate_detector` for analysis
- Triggers on record creation or update

### 2. Data Quality Validation Workflow (`data_quality_validation`)

**Description:** Automated workflow to validate data quality.

**Steps:**
1. Trigger: Periodic schedule or manual trigger
2. Validation: Run `data_quality_validator` agent
3. Reporting: Generate quality report
4. Alerting: Notify data stewards of issues

**AI Agent Integration:**
- Uses `data_quality_validator` for validation
- Triggers on schedule or demand

### 3. Data Enrichment Workflow (`data_enrichment`)

**Description:** Automated workflow to enrich master data.

**Steps:**
1. Trigger: New record or manual request
2. Enrichment: Run `data_enrichment_agent`
3. Review: Present suggestions to user
4. Update: Apply approved changes

**AI Agent Integration:**
- Uses `data_enrichment_agent` for enrichment
- Triggers on demand

## Ask Amani Integration

All MDM AI agents are automatically discoverable by Ask Amani through the module registry. Users can interact with these agents through natural language queries:

**Example Queries:**
- "Find duplicate customers in the system"
- "Validate the quality of product data"
- "Enrich the vendor record for TechSupplies Inc"
- "Show me the latest data quality report"

## Configuration

AI agents are configured in `MODULE_MANIFEST` in `backend/src/modules/master_data_management/__init__.py`. To modify agent configurations:

1. Update the `ai_agents` array in `MODULE_MANIFEST`
2. Restart the application to reload module configuration
3. Ask Amani will automatically discover the updated agents

## Customization

AI agents can be customized through:
- Server Scripts: Modify agent behavior programmatically
- Client Scripts: Customize agent UI interactions
- Webhooks: Integrate with external systems
- Custom API Endpoints: Expose agent functionality via REST APIs

See `CUSTOMIZATION.md` for detailed customization options.
