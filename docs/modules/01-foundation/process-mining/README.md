<!-- SPDX-License-Identifier: Apache-2.0 -->
# Process Mining Module

**Version:** 1.0.0
**Last Updated:** 2025-01-20
**Status:** Production Ready
**Development Agent:** Agent 40

---

## Overview

The Process Mining module provides comprehensive process discovery, conformance checking, bottleneck analysis, and process optimization capabilities. It enables organizations to discover, analyze, and optimize their business processes using AI-powered process mining algorithms.

## Key Features

### 1. Process Discovery
- **Automatic Process Discovery**: Discover process patterns from event logs using multiple algorithms (alpha, inductive, heuristic)
- **Process Map Generation**: Generate visual process maps with nodes, edges, frequencies, and durations
- **Variant Analysis**: Identify and analyze process variants
- **Statistical Analysis**: Calculate process statistics (activity counts, path frequencies, case durations)

### 2. Conformance Checking
- **Reference Model Comparison**: Compare discovered processes against reference models from Workflow Automation
- **Conformance Metrics**: Calculate fitness, precision, and generalization scores
- **Violation Detection**: Identify and classify conformance violations
- **Compliance Reporting**: Generate compliance reports with detailed violation analysis

### 3. Bottleneck Analysis
- **Bottleneck Detection**: Identify bottlenecks in process flows
- **Wait Time Analysis**: Analyze wait times for each activity
- **Resource Utilization**: Analyze resource utilization patterns
- **Trend Analysis**: Track bottleneck trends over time

### 4. Process Optimization
- **Optimization Recommendations**: Generate AI-powered optimization recommendations
- **Impact Analysis**: Calculate estimated impact and effort for each recommendation
- **Recommendation Prioritization**: Prioritize recommendations by ROI
- **Workflow Integration**: Apply recommendations via Workflow Automation

### 5. Event Log Management
- **Event Log Upload**: Upload event logs from various sources (file upload, API, database)
- **Event Log Processing**: Process and analyze event log data
- **Event Log Storage**: Store and manage event logs with metadata
- **Event Log Archiving**: Archive and delete event logs

## AI Agents

The module includes 4 AI agents:

1. **Process Discoverer**: Discovers process patterns from event logs
2. **Conformance Checker**: Checks process conformance against reference models
3. **Process Optimizer**: Generates optimization recommendations
4. **Bottleneck Analyzer**: Identifies and analyzes bottlenecks

See [AGENT-CONFIGURATION.md](./AGENT-CONFIGURATION.md) for detailed agent configuration.

## Workflows

The module includes 4 workflows:

1. **Process Discovery Workflow**: Automated process discovery from event logs
2. **Conformance Checking Workflow**: Conformance checking against reference models
3. **Process Optimization Workflow**: Process optimization recommendations
4. **Bottleneck Analysis Workflow**: Bottleneck detection and analysis

## API Endpoints

See [API.md](./API.md) for complete API documentation.

### Process Discovery
- `POST /api/v1/process-mining/discovery` - Create discovery run
- `GET /api/v1/process-mining/discovery` - List discovery runs
- `GET /api/v1/process-mining/discovery/{id}` - Get discovery run
- `GET /api/v1/process-mining/discovery/{id}/map` - Get process map

### Conformance Checking
- `POST /api/v1/process-mining/conformance` - Create conformance run
- `GET /api/v1/process-mining/conformance` - List conformance runs
- `GET /api/v1/process-mining/conformance/{id}` - Get conformance run

### Optimization
- `GET /api/v1/process-mining/optimization/recommendations` - List recommendations
- `POST /api/v1/process-mining/optimization/recommendations/{id}/apply` - Apply recommendation

### Bottleneck Analysis
- `POST /api/v1/process-mining/bottlenecks` - Create bottleneck analysis
- `GET /api/v1/process-mining/bottlenecks` - List analyses
- `GET /api/v1/process-mining/bottlenecks/{id}` - Get analysis

### Event Logs
- `POST /api/v1/process-mining/event-logs` - Upload event log
- `GET /api/v1/process-mining/event-logs` - List event logs
- `GET /api/v1/process-mining/event-logs/{id}` - Get event log
- `DELETE /api/v1/process-mining/event-logs/{id}` - Delete event log

## UI/UX

The module provides a comprehensive user interface with the following pages:

1. **Dashboard** (`/process-mining/dashboard`): Overview metrics, recent runs, top bottlenecks, active recommendations
2. **Discovery** (`/process-mining/discovery`): Discovery run management and process map visualization
3. **Conformance** (`/process-mining/conformance`): Conformance checking and violation analysis
4. **Optimization** (`/process-mining/optimization`): Optimization recommendations and impact analysis
5. **Bottlenecks** (`/process-mining/bottlenecks`): Bottleneck analysis and heatmap visualization
6. **Event Logs** (`/process-mining/event-logs`): Event log management and upload

### Key Components

- **ProcessMapVisualization**: ReactFlow-based process map visualization
- **ConformanceResults**: Visual conformance score display and violation highlights
- **RecommendationList**: List of optimization recommendations with filtering
- **BottleneckHeatmap**: Heatmap visualization of bottlenecks
- **ProcessMetrics**: Process metrics display (frequencies, durations, variants)

## Inter-Module Integrations

### Workflow Automation
- Import reference models from Workflow Automation
- Export discovered processes to Workflow Automation
- Apply optimization recommendations via Workflow Automation workflows

### AI Provider Configuration
- Use AI Provider Configuration for LLM access in all AI agents
- Track AI usage costs per tenant

### Analytics (Optional)
- Export process metrics to Analytics module
- Import analytics data for bottleneck analysis

### Business Modules
- Event log adapters for Order-to-Cash, Procure-to-Pay, Incident Management, Subscription Lifecycle
- Process analysis for all business modules (Sales, Purchase, HR, etc.)

## Customization

The module supports extensive customization through:

- **Server Scripts**: Custom process discovery algorithms, conformance checking logic, optimization rules
- **Client Scripts**: Custom process visualization, conformance dashboards, optimization UI
- **Webhooks**: Outgoing webhooks for process events, incoming webhooks for external integrations
- **Custom API Endpoints**: Create custom REST endpoints for process mining integrations
- **Workflow Customization**: Visual workflow designer for process workflows
- **Integration Framework**: Integrations with external process mining tools and BPM systems
- **Event Bus**: Publish/subscribe to process events
- **Custom Reports**: SQL/Python-based reports for process analytics

See [CUSTOMIZATION.md](./CUSTOMIZATION.md) for detailed customization patterns.

## Ask Amani Integration

Ask Amani can interact with the Process Mining module to:

- Discover processes from event logs
- Check process conformance
- Find bottlenecks
- Generate optimization recommendations

See [AGENT-CONFIGURATION.md](./AGENT-CONFIGURATION.md) for Ask Amani prompts and commands.

## Security & Permissions

All endpoints enforce RBAC (Role-Based Access Control):

- **tenant_user**: Can create discovery runs, conformance checks, bottleneck analyses, upload event logs
- **tenant_developer**: Can apply optimization recommendations
- **tenant_admin**: Can delete event logs

All operations are tenant-isolated and audit-logged.

## Database Schema

The module uses the following tables:

- `process_discovery_runs`: Discovery execution runs
- `process_maps`: Discovered process maps
- `conformance_runs`: Conformance checking runs
- `optimization_recommendations`: Process optimization recommendations
- `bottleneck_analyses`: Bottleneck analysis results
- `process_mining_event_logs`: Event log storage

See the migration file for complete schema definition.

## Testing

The module includes comprehensive tests:

- `test_models.py`: Tests for all 6 models
- `test_routes.py`: Tests for all API endpoints with RBAC
- `test_services.py`: Tests for all services with mocked integrations
- `test_ai_agents.py`: Tests for all 4 AI agents
- `test_workflows.py`: Tests for all 4 workflows

Target: 95% test coverage per SARAISE-27001.

## Documentation

- [API.md](./API.md): Complete API documentation
- [AGENT-CONFIGURATION.md](./AGENT-CONFIGURATION.md): AI agent configuration and Ask Amani integration
- [CUSTOMIZATION.md](./CUSTOMIZATION.md): Customization patterns and examples
- [ARCHITECTURE.md](./ARCHITECTURE.md): Architectural overview
- [INTEGRATIONS.md](./INTEGRATIONS.md): Inter-module integration patterns

## Quick Start

1. **Upload Event Log**: Navigate to Event Logs page and upload an event log
2. **Discover Process**: Create a discovery run from the uploaded event log
3. **View Process Map**: View the discovered process map with visualization
4. **Check Conformance**: Run conformance check against a reference model
5. **Analyze Bottlenecks**: Identify bottlenecks in the process
6. **Optimize Process**: Generate and apply optimization recommendations

## Demo Data

Demo data is available for the Demo Tenant including:
- Sample event logs (Order-to-Cash, Procure-to-Pay)
- Sample discovery runs and process maps
- Sample conformance runs
- Sample optimization recommendations
- Sample bottleneck analyses

---

**Last Updated:** 2025-01-20
**License:** Apache-2.0
