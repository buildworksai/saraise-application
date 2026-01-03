# Project Management Module - AI Agent Configuration

## Overview

The Project Management module exposes an AI agent for intelligent project health analysis and risk assessment. This agent is automatically discovered by Ask Amani and can be invoked through the SARAISE AI Assistant interface.

## Registered AI Agents

### 1. Project Health Analyst (`project_health_analyst`)

**Description:** AI agent for project health analysis and risk assessment

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.3
- **Max Tokens:** 1000

**Use Cases:**
- Analyze project health metrics
- Identify project risks
- Predict project completion dates
- Generate project status reports
- Recommend corrective actions
- Analyze resource utilization
- Detect project bottlenecks

**Integration Points:**
- Project monitoring
- Risk management
- Status reporting
- Resource planning
- Milestone tracking

**Ask Amani Entry Points:**
- "Analyze health of this project"
- "What are the risks for this project?"
- "Predict completion date for this project"
- "Generate project status report"
- "Identify bottlenecks in this project"
- "Recommend actions to improve project health"

## Workflows

### 1. Project Approval Workflow (`project_approval`)

**Description:** Project approval workflow

**Steps:**
1. Data Ingestion: Extract project data
2. Validation: Verify budget and manager requirements
3. Approval Workflow: Two-level approval process
4. Data Output: Create approved project

**AI Agent Integration:**
- Uses `project_health_analyst` for initial risk assessment
- Automatically triggers on project creation

## Ask Amani Integration

The Project Management AI agent is automatically discoverable by Ask Amani through the module registry. Users can interact with this agent through natural language queries:

**Example Queries:**
- "Analyze the health of Project Alpha"
- "What are the risks for this project?"
- "Predict when this project will complete"
- "Generate a status report for all active projects"
- "Identify any bottlenecks in Project Beta"
- "Recommend actions to get Project Gamma back on track"

## Configuration

AI agents are configured in `MODULE_MANIFEST` in `backend/src/modules/projects/__init__.py`. To modify agent configurations:

1. Update the `ai_agents` array in `MODULE_MANIFEST`
2. Restart the application to reload module configuration
3. Ask Amani will automatically discover the updated agents

## Customization

AI agents can be customized through:
- Server Scripts: Modify agent behavior programmatically
- Client Scripts: Customize agent UI interactions
- Webhooks: Integrate with external project management systems
- Custom API Endpoints: Expose agent functionality via REST APIs

See `CUSTOMIZATION.md` for detailed customization options.
