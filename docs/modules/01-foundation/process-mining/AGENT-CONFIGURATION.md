<!-- SPDX-License-Identifier: Apache-2.0 -->
# Process Mining - AI Agent Configuration

**Version:** 1.0.0
**Last Updated:** 2025-01-20
**Status:** Agent Configuration
**Development Agent:** Agent 40

---

## AI Agents Overview

This module includes 4 AI agents designed to automate process mining workflows, provide intelligent process analysis, and enhance user productivity.

### Agent 1: Process Discoverer

**Type:** Technical/Data
**Autonomy Level:** 3
**Human Oversight:** Required for production deployment of discovered processes

#### Purpose
Discovers process patterns from event logs using process mining algorithms. Analyzes event sequences to extract process models, identify variants, and calculate process statistics.

#### Capabilities
- Event log analysis and pattern extraction
- Process model generation (nodes, edges, frequencies)
- Process variant identification
- Statistical analysis (activity counts, path frequencies, case durations)

#### Configuration
```yaml
agent:
  name: "Process Discoverer"
  type: "openai"
  module: "process_mining"
  autonomy_level: 3
  triggers:
    - event: "event_log.uploaded"
      action: "discover_process"
      conditions:
        - field: "status"
          operator: "equals"
          value: "active"
  guardrails:
    - "Never modify source event logs"
    - "Always validate discovered process models"
    - "Log all discovery operations"
  governance:
    approval_required: false
    escalation_path: "tenant_admin"
    max_autonomous_actions: 5
```

#### Governance Rules
| Action | Approval Required | Escalation Path | Timeout |
|--------|-------------------|-----------------|---------|
| Discover Process | No | tenant_admin | 3600s |
| Generate Process Map | No | tenant_admin | 1800s |
| Export Process Model | Yes | tenant_admin | 300s |

#### Example Interactions
**Scenario:** User uploads event log and wants to discover the process
**User Input:** "Discover the process from event log Order-to-Cash-2024"
**Agent Response:** "I'll analyze the event log and discover the process patterns. This may take a few minutes."
**Actions Taken:**
- Analyzed event log with inductive algorithm
- Generated process map with 15 activities and 8 paths
- Identified 3 main process variants
- Calculated statistics (avg duration: 5.2 days, completion rate: 87%)

---

### Agent 2: Conformance Checker

**Type:** Technical/Compliance
**Autonomy Level:** 2
**Human Oversight:** Required for compliance violations

#### Purpose
Checks process conformance against reference models. Compares discovered processes with reference models from Workflow Automation, calculates conformance metrics, and identifies violations.

#### Capabilities
- Process model comparison
- Conformance metric calculation (fitness, precision, generalization)
- Violation detection and classification
- Compliance reporting

#### Configuration
```yaml
agent:
  name: "Conformance Checker"
  type: "openai"
  module: "process_mining"
  autonomy_level: 2
  triggers:
    - event: "process_map.discovered"
      action: "check_conformance"
      conditions:
        - field: "reference_model_id"
          operator: "not_equals"
          value: null
  guardrails:
    - "Always validate reference models exist"
    - "Never modify reference models"
    - "Log all conformance violations"
  governance:
    approval_required: true
    escalation_path: "tenant_admin"
    max_autonomous_actions: 3
```

#### Governance Rules
| Action | Approval Required | Escalation Path | Timeout |
|--------|-------------------|-----------------|---------|
| Check Conformance | No | tenant_admin | 1800s |
| Identify Violations | No | tenant_admin | 900s |
| Generate Compliance Report | Yes | tenant_admin | 600s |

#### Example Interactions
**Scenario:** User wants to check if discovered process conforms to reference model
**User Input:** "Check conformance of process map PM-001 against workflow WF-OrderProcessing"
**Agent Response:** "I'll check the conformance. The process has a fitness score of 0.85 and precision of 0.92. Found 3 violations: missing approval step in 12% of cases, extra validation step in 5% of cases."
**Actions Taken:**
- Loaded reference model from Workflow Automation
- Compared process models
- Calculated conformance scores
- Identified and classified violations

---

### Agent 3: Process Optimizer

**Type:** Technical/Strategic
**Autonomy Level:** 4
**Human Oversight:** Required for applying recommendations

#### Purpose
Generates optimization recommendations for business processes. Analyzes process models, identifies optimization opportunities, and provides actionable recommendations with impact analysis.

#### Capabilities
- Process efficiency analysis
- Optimization opportunity identification
- Impact and effort estimation
- Recommendation prioritization

#### Configuration
```yaml
agent:
  name: "Process Optimizer"
  type: "openai"
  module: "process_mining"
  autonomy_level: 4
  triggers:
    - event: "bottleneck.identified"
      action: "generate_recommendations"
      conditions:
        - field: "severity"
          operator: "equals"
          value: "high"
  guardrails:
    - "Never apply recommendations without approval"
    - "Always provide impact and effort estimates"
    - "Prioritize recommendations by ROI"
  governance:
    approval_required: true
    escalation_path: "tenant_admin"
    max_autonomous_actions: 10
```

#### Governance Rules
| Action | Approval Required | Escalation Path | Timeout |
|--------|-------------------|-----------------|---------|
| Generate Recommendations | No | tenant_admin | 1200s |
| Calculate Impact | No | tenant_admin | 600s |
| Apply Recommendation | Yes | tenant_admin | 300s |

#### Example Interactions
**Scenario:** User wants optimization recommendations for a process
**User Input:** "Generate optimization recommendations for process map PM-001"
**Agent Response:** "I've identified 5 optimization opportunities. Top recommendation: Automate manual approval step (Impact: High, Effort: Medium, Estimated time savings: 2.5 days per case)."
**Actions Taken:**
- Analyzed process model for inefficiencies
- Identified 5 optimization opportunities
- Calculated impact and effort for each
- Prioritized recommendations by ROI

---

### Agent 4: Bottleneck Analyzer

**Type:** Technical/Analytical
**Autonomy Level:** 3
**Human Oversight:** Required for critical bottlenecks

#### Purpose
Identifies and analyzes bottlenecks in business processes. Analyzes process timing data, identifies bottlenecks, calculates wait times, and provides bottleneck statistics and trends.

#### Capabilities
- Bottleneck detection
- Wait time analysis
- Resource utilization analysis
- Trend analysis

#### Configuration
```yaml
agent:
  name: "Bottleneck Analyzer"
  type: "openai"
  module: "process_mining"
  autonomy_level: 3
  triggers:
    - event: "process_map.discovered"
      action: "analyze_bottlenecks"
      conditions:
        - field: "status"
          operator: "equals"
          value: "completed"
  guardrails:
    - "Always validate timing data exists"
    - "Never modify process models"
    - "Log all bottleneck analyses"
  governance:
    approval_required: false
    escalation_path: "tenant_admin"
    max_autonomous_actions: 5
```

#### Governance Rules
| Action | Approval Required | Escalation Path | Timeout |
|--------|-------------------|-----------------|---------|
| Analyze Bottlenecks | No | tenant_admin | 1800s |
| Calculate Statistics | No | tenant_admin | 600s |
| Generate Trend Report | No | tenant_admin | 900s |

#### Example Interactions
**Scenario:** User wants to identify bottlenecks in a process
**User Input:** "Analyze bottlenecks in process map PM-001"
**Agent Response:** "I've identified 2 bottlenecks: Manual Approval (avg wait time: 3.2 days, frequency: 100%) and Credit Check (avg wait time: 1.8 days, frequency: 45%)."
**Actions Taken:**
- Analyzed process timing data
- Identified 2 bottlenecks
- Calculated wait times and frequencies
- Generated bottleneck statistics

---

## Ask Amani Integration

Ask Amani is SARAISE's conversational AI assistant that can interact with all modules. This section documents how Ask Amani works with the Process Mining module.

### Supported Queries

| Query Type | Example | Response | Context Required |
|------------|---------|----------|------------------|
| Information | "What is process mining?" | Explanation of process mining concepts | None |
| Status | "What is the status of discovery run DR-001?" | Current status and results | Discovery run ID |
| Action | "Discover process from event log EL-001" | Confirmation and discovery initiation | Event log ID |
| Analysis | "Show me bottlenecks in process PM-001" | Bottleneck analysis results | Process map ID |

### Module-Specific Commands

#### Command: Discover Process
**Syntax:** `discover process from event log <event_log_id> [algorithm: <algorithm>]`
**Description:** Initiates process discovery from an event log
**Parameters:**
- `event_log_id` (string): ID of the event log to analyze
- `algorithm` (string, optional): Discovery algorithm (alpha, inductive, heuristic)
**Example:**
```
User: Discover process from event log EL-001 using inductive algorithm
Amani: I'll start the process discovery. This will analyze the event log and generate a process map. The discovery run has been created with ID DR-001.
```

#### Command: Check Conformance
**Syntax:** `check conformance of process <process_map_id> against <reference_model_id>`
**Description:** Checks process conformance against a reference model
**Parameters:**
- `process_map_id` (string): ID of the process map to check
- `reference_model_id` (string): ID of the reference model from Workflow Automation
**Example:**
```
User: Check conformance of process PM-001 against workflow WF-OrderProcessing
Amani: I'll check the conformance. The process has a fitness score of 0.85 and precision of 0.92. Found 3 violations.
```

#### Command: Find Bottlenecks
**Syntax:** `find bottlenecks in process <process_map_id> [period: <start> to <end>]`
**Description:** Identifies bottlenecks in a process
**Parameters:**
- `process_map_id` (string): ID of the process map to analyze
- `period` (optional): Time period for analysis
**Example:**
```
User: Find bottlenecks in process PM-001 for period 2024-01-01 to 2024-12-31
Amani: I've identified 2 bottlenecks: Manual Approval (avg wait time: 3.2 days) and Credit Check (avg wait time: 1.8 days).
```

#### Command: Generate Recommendations
**Syntax:** `generate optimization recommendations for process <process_map_id>`
**Description:** Generates optimization recommendations for a process
**Parameters:**
- `process_map_id` (string): ID of the process map to optimize
**Example:**
```
User: Generate optimization recommendations for process PM-001
Amani: I've identified 5 optimization opportunities. Top recommendation: Automate manual approval step (Impact: High, Effort: Medium).
```

### Natural Language Understanding

Ask Amani understands various phrasings for module operations:

**Intent:** Discover Process
**Example Phrases:**
- "Discover the process from event log EL-001"
- "Analyze event log EL-001 and find the process"
- "I need to discover the process pattern from EL-001"
**Action:** Triggers process discovery operation

**Intent:** Check Conformance
**Example Phrases:**
- "Check if process PM-001 conforms to workflow WF-001"
- "Compare process PM-001 with reference model WF-001"
- "Verify conformance of PM-001"
**Action:** Triggers conformance checking operation

**Intent:** Find Bottlenecks
**Example Phrases:**
- "Find bottlenecks in process PM-001"
- "Identify bottlenecks in PM-001"
- "Show me bottlenecks for process PM-001"
**Action:** Triggers bottleneck analysis operation

**Intent:** Generate Recommendations
**Example Phrases:**
- "Generate optimization recommendations for PM-001"
- "What optimizations can be made to process PM-001?"
- "Suggest improvements for process PM-001"
**Action:** Triggers recommendation generation operation

### Context Awareness

Ask Amani maintains context across conversations:
- **User Context:** Current user, tenant, permissions
- **Session Context:** Recent discovery runs, active analyses
- **Module Context:** Current process maps, event logs
- **Workflow Context:** Ongoing conformance checks, pending recommendations

---

## Agent Workflow Integration

### Workflow Triggers

| Workflow | Trigger Event | Agent Action | Outcome |
|----------|---------------|--------------|---------|
| Process Discovery | event_log.uploaded | ProcessDiscoverer.discover_process | Process map generated |
| Conformance Checking | process_map.discovered | ConformanceChecker.check_conformance | Conformance results generated |
| Process Optimization | bottleneck.identified | ProcessOptimizer.generate_recommendations | Recommendations generated |
| Bottleneck Analysis | process_map.discovered | BottleneckAnalyzer.analyze_bottlenecks | Bottleneck analysis completed |

### Automated Decision Making

#### Decision: Auto-discover Process
**Condition:** Event log uploaded with auto-discovery enabled
**Agent Action:** ProcessDiscoverer automatically starts discovery
**Approval Required:** No
**Fallback:** Manual discovery required

#### Decision: Auto-check Conformance
**Condition:** Process map discovered with reference model configured
**Agent Action:** ConformanceChecker automatically checks conformance
**Approval Required:** No
**Fallback:** Manual conformance check required

---

## Agent Configuration Examples

### Basic Configuration

```yaml
# Minimal agent configuration
agent:
  name: "process-discoverer-basic"
  type: "openai"
  module: "process_mining"
  autonomy_level: 2
  triggers:
    - event: "event_log.uploaded"
      action: "discover_process"
```

### Advanced Configuration

```yaml
# Full agent configuration with all options
agent:
  name: "process-optimizer-advanced"
  type: "openai"
  module: "process_mining"
  autonomy_level: 4
  triggers:
    - event: "bottleneck.identified"
      action: "generate_recommendations"
      conditions:
        - field: "severity"
          operator: "equals"
          value: "high"
    - event: "process_map.discovered"
      action: "analyze_optimization_opportunities"
  guardrails:
    - "Never apply recommendations without approval"
    - "Always provide impact and effort estimates"
    - "Prioritize recommendations by ROI"
  governance:
    approval_required: true
    escalation_path: "tenant_admin"
    max_autonomous_actions: 10
    timeout: 1200
  capabilities:
    - "process_analysis"
    - "optimization_identification"
    - "impact_calculation"
```

---

## Testing Agent Behavior

### Test Scenarios

#### Scenario 1: Process Discovery
**Setup:** Event log uploaded with 1000 events
**Input:** User requests process discovery
**Expected Behavior:** ProcessDiscoverer analyzes event log and generates process map
**Validation:** Process map contains nodes, edges, and statistics

#### Scenario 2: Conformance Checking
**Setup:** Process map discovered, reference model exists
**Input:** User requests conformance check
**Expected Behavior:** ConformanceChecker compares models and calculates scores
**Validation:** Conformance scores and violations are generated

#### Scenario 3: Bottleneck Analysis
**Setup:** Process map with timing data
**Input:** User requests bottleneck analysis
**Expected Behavior:** BottleneckAnalyzer identifies bottlenecks and calculates statistics
**Validation:** Bottleneck list and statistics are generated

---

**Last Updated:** 2025-01-20
**License:** Apache-2.0
