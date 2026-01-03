# Ask Amani Configuration for Compliance & Risk Management Module

<!-- SPDX-License-Identifier: Apache-2.0 -->

This document describes how to configure Ask Amani to work with the Compliance & Risk Management module.

## Module Concepts

Ask Amani understands the following concepts for the Compliance & Risk Management module:

### Core Concepts

1. **Compliance Framework Management**: Define and manage regulatory compliance frameworks (SOX, ISO 27001, GDPR, HIPAA, PCI-DSS, NIST, etc.)
2. **Risk Assessment**: Identify, assess, and prioritize risks with scoring and categorization
3. **Compliance Monitoring**: Continuous monitoring of compliance status across frameworks
4. **Compliance Violation Tracking**: Track and remediate compliance violations
5. **Audit Coordination**: Plan, execute, and report compliance audits
6. **Risk Mitigation**: Create and track risk mitigation plans

### Example Prompts

- "List all active compliance frameworks"
- "Show compliance status for ISO 27001"
- "Find all high-risk assessments"
- "List open compliance violations"
- "Show audit records for the last quarter"
- "Get compliance report for GDPR"
- "Find overdue risk mitigation plans"
- "Show compliance violations by framework"
- "List critical risks requiring immediate attention"
- "Get audit findings summary"

## Pre-Installed AI Agents

The Compliance & Risk Management module automatically installs the following AI agents during module installation:

### Compliance Monitor Agent

**Name**: `Compliance Monitor`

**Description**: AI agent for continuous monitoring of compliance status against defined frameworks

**Configuration**:
- **Agent Type**: OpenAI
- **Model**: GPT-4
- **Temperature**: 0.2 (low for accuracy)
- **Max Tokens**: 2000

**Capabilities**:
- Monitors compliance status across all frameworks
- Identifies compliance gaps and violations
- Generates compliance reports
- Provides compliance recommendations
- Tracks compliance trends over time
- Alerts on compliance threshold breaches

**Usage**:
```python
# Access via AI Agent Management API
GET /api/v1/ai-agents?name=Compliance Monitor&tenant_id={tenant_id}
```

### Risk Assessor Agent

**Name**: `Risk Assessor`

**Description**: AI agent for identifying, assessing, and prioritizing risks, and recommending mitigation strategies

**Configuration**:
- **Agent Type**: OpenAI
- **Model**: GPT-4
- **Temperature**: 0.3 (balanced for creativity and accuracy)
- **Max Tokens**: 2000

**Capabilities**:
- Identifies potential risks
- Assesses risk likelihood and impact
- Calculates risk scores
- Recommends mitigation strategies
- Prioritizes risks by severity
- Tracks risk trends

**Usage**:
```python
# Access via AI Agent Management API
GET /api/v1/ai-agents?name=Risk Assessor&tenant_id={tenant_id}
```

### Audit Coordinator Agent

**Name**: `Audit Coordinator`

**Description**: AI agent for coordinating compliance audits, managing findings, and generating audit reports

**Configuration**:
- **Agent Type**: OpenAI
- **Model**: GPT-4
- **Temperature**: 0.2 (low for accuracy)
- **Max Tokens**: 2000

**Capabilities**:
- Plans and schedules compliance audits
- Coordinates audit execution
- Documents audit findings
- Generates audit reports
- Tracks audit recommendations
- Manages audit follow-ups

**Usage**:
```python
# Access via AI Agent Management API
GET /api/v1/ai-agents?name=Audit Coordinator&tenant_id={tenant_id}
```

## Pre-Installed Workflows

The Compliance & Risk Management module automatically installs the following workflows during module installation:

### Compliance Monitoring Workflow

**Name**: `compliance_monitoring_workflow`

**Description**: Workflow for continuous compliance monitoring

**Steps**:
1. **Data Ingestion**: Collect compliance data from various sources
2. **Validation**: Validate data against framework rules and regulatory requirements
3. **Monitoring**: Perform status checks and compliance verification
4. **Reporting**: Generate compliance dashboard and reports

**Configuration**:
```json
{
  "name": "compliance_monitoring_workflow",
  "description": "Workflow for continuous compliance monitoring",
  "steps": [
    {
      "type": "data_ingestion",
      "config": {"source": "compliance_data"}
    },
    {
      "type": "validation",
      "config": {"rules": ["framework_rules", "regulatory_requirements"]}
    },
    {
      "type": "monitoring",
      "config": {"status_checks": true}
    },
    {
      "type": "reporting",
      "config": {"destination": "compliance_dashboard"}
    }
  ]
}
```

### Risk Assessment Workflow

**Name**: `risk_assessment_workflow`

**Description**: Workflow for identifying, assessing, and mitigating risks

**Steps**:
1. **Data Ingestion**: Collect risk data from various sources
2. **Analysis**: Perform risk scoring and categorization
3. **Mitigation**: Generate mitigation plans and recommendations
4. **Tracking**: Track mitigation status and effectiveness

**Configuration**:
```json
{
  "name": "risk_assessment_workflow",
  "description": "Workflow for identifying, assessing, and mitigating risks",
  "steps": [
    {
      "type": "data_ingestion",
      "config": {"source": "risk_data"}
    },
    {
      "type": "analysis",
      "config": {"risk_scoring": true}
    },
    {
      "type": "mitigation",
      "config": {"plan_generation": true}
    },
    {
      "type": "tracking",
      "config": {"mitigation_status": true}
    }
  ]
}
```

### Compliance Audit Workflow

**Name**: `compliance_audit_workflow`

**Description**: Workflow for planning, executing, and reporting compliance audits

**Steps**:
1. **Data Ingestion**: Collect audit scope and requirements
2. **Execution**: Perform audit procedures and testing
3. **Documentation**: Document findings and recommendations
4. **Reporting**: Generate audit reports and track follow-ups

**Configuration**:
```json
{
  "name": "compliance_audit_workflow",
  "description": "Workflow for planning, executing, and reporting compliance audits",
  "steps": [
    {
      "type": "data_ingestion",
      "config": {"source": "audit_scope"}
    },
    {
      "type": "execution",
      "config": {"procedures": true}
    },
    {
      "type": "documentation",
      "config": {"findings": true}
    },
    {
      "type": "reporting",
      "config": {"destination": "audit_report"}
    }
  ]
}
```

## Code Generation Patterns

Ask Amani can generate code for the following customization points:

### Server Scripts

Ask Amani can generate server scripts for:
- Compliance framework validation
- Risk assessment calculations
- Compliance violation tracking
- Audit coordination logic

**Example Prompt**:
```
Generate a server script that automatically calculates risk scores
when likelihood or impact values change in a Risk Assessment.
```

### Client Scripts

Ask Amani can generate client scripts for:
- Dynamic form fields based on compliance framework
- Real-time risk score calculations
- Compliance status indicators

**Example Prompt**:
```
Generate a client script that shows a compliance status indicator
on the Compliance Framework form based on the number of open violations.
```

### Webhooks

Ask Amani can generate webhook handlers for:
- Compliance violation notifications
- Risk threshold alerts
- Audit completion notifications

**Example Prompt**:
```
Generate a webhook handler that sends an email notification when
a critical risk is identified.
```

## Cross-Module Queries

Ask Amani can query compliance data across modules:

### QMS Integration

- "Show compliance status from QMS module"
- "List QMS audit findings"
- "Get QMS compliance violations"

### Audit Integration

- "Show audit findings from Audit module"
- "List completed audits"
- "Get audit recommendations"

### MDM Integration

- "Check master data compliance"
- "List data quality issues"
- "Get MDM compliance status"

### Sustainability Integration

- "Show ESG compliance metrics"
- "List ESG compliance violations"
- "Get sustainability compliance status"
