<!-- SPDX-License-Identifier: Apache-2.0 -->
# Process Mining - Customization Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02
**Status:** Customization Reference
**Development Agent:** Agent 40

---

This guide explains how to customize the Process Mining module to meet your specific business requirements using SARAISE's low-code customization features.

## Customization Options

The Process Mining module supports extensive customization through:

1. **Server Scripts** - Custom Python scripts for process discovery algorithms, conformance checking logic, optimization rules, and bottleneck detection
2. **Client Scripts** - Custom JavaScript for dynamic process visualization, conformance dashboards, and optimization recommendation UI
3. **Webhooks** - Outgoing webhooks for process events and incoming webhooks for external process system integrations
4. **Custom API Endpoints** - Create custom REST endpoints for process mining integrations
5. **Workflow Customization** - Visual workflow designer for process discovery workflows, conformance checking workflows, and optimization workflows
6. **Integration Framework** - Integrations with external process mining tools, BPM systems, and event log sources
7. **Event Bus** - Publish/subscribe to process events for decoupled process management
8. **Custom Reports** - SQL/Python-based reports for process analytics, conformance metrics, and optimization impact dashboards

---

## 1. Adding Custom Fields

### Example: Add Custom Field to [Resource Type]

**Use Case:** [Why you need this field]
**Steps:**

1. Navigate to **Customization Studio** → **Resources**
2. Search for "[Resource Name]"
3. Click "Customize"
4. Add Custom Field:

```json
{
  "fieldname": "custom_field_name",
  "label": "Custom Field Label",
  "fieldtype": "Data",
  "insert_after": "existing_field"
}
```

5. **Save** and **Update Resource**

**Result:** [What happens after adding the field]


### Common Custom Fields for Process Mining

| Field | Resource | Type | Use Case |
|-------|---------|------|----------|
| [Field Name] | [Resource Type] | [Type] | [Use case] |
| [Field Name] | [Resource Type] | [Type] | [Use case] |

---

## 2. Creating Custom Resources

### Example: Custom "[Resource Name]"

**Requirement:** [What you need to track]
**Resource Definition:**

```json
{
  "name": "Custom Resource",
  "module": "process-mining",
  "is_submittable": 0,
  "fields": [
    {"fieldname": "field1", "label": "Field 1", "fieldtype": "Data", "reqd": 1},
    {"fieldname": "field2", "label": "Field 2", "fieldtype": "Select", "options": "Option1\nOption2"},
  ],
  "permissions": [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1}
  ]
}
```


---

## 3. Custom Workflows

### Example: [Workflow Name]

**Use Case:** [What this workflow automates]
**Workflow Definition:**

```json
{
  "workflow_name": "Custom Workflow",
  "resource_type": "[Resource Type]",
  "states": [
    {"state": "Draft", "action": "Submit", "next_state": "Pending"},
    {"state": "Pending", "action": "Approve", "next_state": "Approved"},
  ],
  "transitions": [
    {"from_state": "Draft", "to_state": "Pending", "action": "Submit", "allowed": "Owner"},
  ]
}
```

---

## 4. Server Scripts

### Example: Custom Process Discovery Algorithm

**Use Case:** Implement custom process discovery algorithm
```python
# Server Script: Custom Discovery Algorithm
from src.modules.process_mining.agents.process_discoverer import ProcessDiscovererAgent

async def custom_discovery_algorithm(event_log_id: str, tenant_id: str, db):
    """Custom process discovery algorithm"""
    agent = ProcessDiscovererAgent(db)

    # Custom algorithm logic
    result = await agent.discover_process(
        event_log_id=event_log_id,
        tenant_id=tenant_id,
        algorithm="custom",
        config={
            "min_frequency": 0.1,
            "max_path_length": 20,
            "noise_threshold": 0.05
        }
    )

    return result
```

### Example: Custom Conformance Checking Logic

```python
# Server Script: Custom Conformance Check
from src.modules.process_mining.agents.conformance_checker import ConformanceCheckerAgent

async def custom_conformance_check(process_map_id: str, reference_model_id: str, tenant_id: str, db):
    """Custom conformance checking with business rules"""
    agent = ConformanceCheckerAgent(db)

    # Add custom business rules
    result = await agent.check_conformance(
        process_map_id=process_map_id,
        tenant_id=tenant_id,
        reference_model_id=reference_model_id
    )

    # Apply custom validation rules
    if result["conformance_score"] < 0.8:
        # Trigger alert or workflow
        pass

    return result
```

### Example: Custom Optimization Rules

```python
# Server Script: Custom Optimization Rules
from src.modules.process_mining.agents.process_optimizer import ProcessOptimizerAgent

async def custom_optimization_rules(process_map_id: str, tenant_id: str, db):
    """Custom optimization rules based on business context"""
    agent = ProcessOptimizerAgent(db)

    # Apply custom optimization criteria
    result = await agent.generate_recommendations(
        process_map_id=process_map_id,
        tenant_id=tenant_id
    )

    # Filter recommendations by custom criteria
    filtered = [
        r for r in result["recommendations"]
        if r["impact_score"] > 0.7 and r["effort_score"] < 0.5
    ]

    return {"recommendations": filtered}
```

### Example: Custom Bottleneck Detection

```python
# Server Script: Custom Bottleneck Detection
from src.modules.process_mining.agents.bottleneck_analyzer import BottleneckAnalyzerAgent

async def custom_bottleneck_detection(process_map_id: str, tenant_id: str, db):
    """Custom bottleneck detection with business thresholds"""
    agent = BottleneckAnalyzerAgent(db)

    result = await agent.analyze_bottlenecks(
        process_map_id=process_map_id,
        tenant_id=tenant_id
    )

    # Apply custom thresholds
    critical_bottlenecks = [
        b for b in result["bottlenecks"]
        if b["wait_time"] > 2.0  # 2 days threshold
    ]

    return {"bottlenecks": critical_bottlenecks}
```

---

## 5. Client Scripts

### Example: Dynamic Process Visualization

**Use Case:** Custom process map visualization with interactive features
```javascript
// Client Script: Dynamic Process Visualization
import { ProcessMapVisualization } from '@/modules/process-mining/components/ProcessMapVisualization';

export function customProcessMapVisualization(processMap) {
    // Custom visualization logic
    const visualization = new ProcessMapVisualization({
        processMap: processMap,
        interactive: true,
        showFrequencies: true,
        showDurations: true,
        customStyling: {
            nodeColor: (node) => {
                if (node.frequency > 0.8) return 'green';
                if (node.frequency > 0.5) return 'yellow';
                return 'red';
            }
        }
    });

    return visualization;
}
```

### Example: Custom Conformance Dashboard

```javascript
// Client Script: Custom Conformance Dashboard
export function customConformanceDashboard(conformanceRun) {
    // Custom dashboard with business-specific metrics
    return {
        score: conformanceRun.conformance_score,
        violations: conformanceRun.violations,
        complianceStatus: conformanceRun.compliance_status,
        customMetrics: {
            criticalViolations: conformanceRun.violations.filter(v => v.severity === 'critical').length,
            warningViolations: conformanceRun.violations.filter(v => v.severity === 'warning').length
        }
    };
}
```

### Example: Custom Optimization Recommendation UI

```javascript
// Client Script: Custom Recommendation UI
export function customRecommendationUI(recommendation) {
    // Custom UI with impact/effort matrix
    return {
        recommendation: recommendation,
        impactEffortMatrix: {
            highImpactLowEffort: recommendation.impact_score > 0.7 && recommendation.effort_score < 0.3,
            highImpactHighEffort: recommendation.impact_score > 0.7 && recommendation.effort_score > 0.7,
            lowImpactLowEffort: recommendation.impact_score < 0.3 && recommendation.effort_score < 0.3,
            lowImpactHighEffort: recommendation.impact_score < 0.3 && recommendation.effort_score > 0.7
        },
        priority: calculatePriority(recommendation)
    };
}
```

---

## 6. Custom Reports

### Example: [Report Name]

**Purpose:** [What this report shows]
**Report Definition:**

```json
{
  "report_name": "Custom Report",
  "ref_resource": "[Resource Type]",
  "columns": [
    {"fieldname": "field1", "label": "Field 1", "fieldtype": "Data"},
    {"fieldname": "field2", "label": "Field 2", "fieldtype": "Currency"},
  ],
  "filters": [
    {"fieldname": "status", "label": "Status", "fieldtype": "Select"},
  ]
}
```

---

## 7. Hooks & Events

| Hook | Description | Use Case | Example |
|------|-------------|----------|---------|
| before_insert | Runs before document is inserted | Custom validation | Validate business rules |
| before_save | Runs before document is saved | Calculate fields | Auto-calculate totals |
| after_insert | Runs after document is inserted | Send notifications | Email confirmation |
| on_update | Runs when document is updated | Sync with external systems | Update CRM |

### Hook Implementation Example

```python
# hooks.py
hooks = {
    "process-mining.[Resource Type].before_save": "process-mining.customizations.[resource_type].before_save"
}
```

---

## 8. Integration Customization

### Custom API Endpoints

#### Endpoint: Custom Process Discovery
**Path:** `/api/v1/process-mining/custom/discovery`
**Method:** POST
**Purpose:** Custom process discovery with business-specific algorithms

```python
# Custom API Endpoint
from rest_framework import routers, viewsets
from src.modules.process_mining.views import ProcessMiningViewSet

router = routers.DefaultRouter()
router.register(r'custom', ProcessMiningViewSet, basename='process-mining-custom')

@custom_router.post("/discovery")
async def custom_discovery_endpoint(
    event_log_id: str,
    custom_algorithm: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireTenantUser)
):
    """Custom discovery endpoint with business-specific algorithm"""
    service = ProcessDiscoveryService(db)
    # Custom logic here
    return await service.discover_process(...)
```

### Webhook Customization

#### Outgoing Webhooks

**Event: process.discovered**
**Payload:**
```json
{
    "event": "process.discovered",
    "data": {
        "discovery_run_id": "DR-001",
        "process_map_id": "PM-001",
        "tenant_id": "tenant-123",
        "statistics": {
            "total_activities": 15,
            "total_paths": 8
        }
    }
}
```
**Use Case:** Notify external systems when a process is discovered

**Event: conformance.checked**
**Payload:**
```json
{
    "event": "conformance.checked",
    "data": {
        "conformance_run_id": "CR-001",
        "process_map_id": "PM-001",
        "conformance_score": 0.85,
        "violations": [...]
    }
}
```
**Use Case:** Alert compliance systems when conformance violations are detected

**Event: bottleneck.detected**
**Payload:**
```json
{
    "event": "bottleneck.detected",
    "data": {
        "analysis_id": "BA-001",
        "process_map_id": "PM-001",
        "bottlenecks": [
            {
                "activity": "Manual Approval",
                "wait_time": 3.2,
                "severity": "high"
            }
        ]
    }
}
```
**Use Case:** Trigger alerts or workflows when critical bottlenecks are identified

#### Incoming Webhooks

**Webhook: External Process System Integration**
**Path:** `/api/v1/process-mining/webhooks/external-process`
**Method:** POST
**Purpose:** Receive process events from external systems

```python
@router.post("/webhooks/external-process")
async def external_process_webhook(
    payload: dict,
    db: AsyncSession = Depends(get_db)
):
    """Receive process events from external systems"""
    # Convert external format to SARAISE event log format
    # Store in EventLog table
    pass
```

### Workflow Customization

#### Custom Process Discovery Workflow

```json
{
    "name": "custom_process_discovery_workflow",
    "description": "Custom discovery workflow with business-specific steps",
    "steps": [
        {
            "name": "validate_event_log",
            "type": "validation",
            "config": {
                "rules": ["min_events", "required_fields"]
            }
        },
        {
            "name": "run_custom_algorithm",
            "type": "ai_processing",
            "config": {
                "agent": "process_discoverer",
                "algorithm": "custom",
                "custom_config": {
                    "business_rules": "..."
                }
            }
        },
        {
            "name": "apply_business_filters",
            "type": "data_processing",
            "config": {
                "filters": ["exclude_test_data", "filter_by_department"]
            }
        }
    ]
}
```

### Integration Framework

#### External Process Mining Tool Integration

```python
# Integration with external process mining tool (e.g., Celonis, Signavio)
from src.modules.process_mining.services.integration_service import ProcessMiningIntegrationService

async def integrate_external_tool(external_tool_config: dict, tenant_id: str, db):
    """Integrate with external process mining tool"""
    integration_service = ProcessMiningIntegrationService(db)

    # Import process models from external tool
    external_models = await fetch_from_external_tool(external_tool_config)

    # Convert to SARAISE format
    for model in external_models:
        await integration_service.import_reference_model(
            workflow_id=model.id,
            tenant_id=tenant_id
        )
```

#### BPM System Integration

```python
# Integration with BPM systems (e.g., Camunda, Activiti)
async def integrate_bpm_system(bpm_config: dict, tenant_id: str, db):
    """Integrate with BPM system"""
    # Export discovered processes to BPM system
    # Import reference models from BPM system
    pass
```

### Event Bus

#### Publishing Process Events

```python
from src.core.event_bus import EventBus

async def publish_process_event(event_type: str, data: dict):
    """Publish process event to event bus"""
    event_bus = EventBus()
    await event_bus.publish(
        event=f"process_mining.{event_type}",
        data=data
    )
```

#### Subscribing to Process Events

```python
from src.core.event_bus import EventBus

async def subscribe_to_process_events():
    """Subscribe to process events"""
    event_bus = EventBus()
    await event_bus.subscribe(
        event_pattern="process_mining.*",
        handler=handle_process_event
    )

async def handle_process_event(event: dict):
    """Handle process event"""
    if event["type"] == "process.discovered":
        # Trigger downstream actions
        pass
```

### Custom Reports

#### Process Analytics Report

```sql
-- Custom SQL Report: Process Analytics
SELECT
    pm.name as process_name,
    COUNT(dr.id) as discovery_runs,
    AVG(cr.conformance_score) as avg_conformance,
    COUNT(ba.id) as bottleneck_analyses
FROM process_maps pm
LEFT JOIN process_discovery_runs dr ON pm.discovery_run_id = dr.id
LEFT JOIN conformance_runs cr ON cr.process_map_id = pm.id
LEFT JOIN bottleneck_analyses ba ON ba.process_map_id = pm.id
WHERE pm.tenant_id = :tenant_id
GROUP BY pm.id, pm.name
```

#### Conformance Metrics Report

```python
# Custom Python Report: Conformance Metrics
from src.modules.process_mining.models import ConformanceRun

async def generate_conformance_report(tenant_id: str, db):
    """Generate custom conformance metrics report"""
    runs = await db.execute(
        select(ConformanceRun).where(ConformanceRun.tenant_id == tenant_id)
    )

    metrics = {
        "total_checks": len(runs),
        "avg_fitness": sum(r.fitness_score for r in runs) / len(runs),
        "avg_precision": sum(r.precision_score for r in runs) / len(runs),
        "violation_count": sum(len(r.violations or []) for r in runs)
    }

    return metrics
```

---

## Best Practices

### Naming Conventions
- Use descriptive field names: `customer_preferred_contact_method` not `field1`
- Prefix custom fields with module name: `process-mining_custom_field`
- Use consistent naming across Resources

### Performance Considerations
- Avoid complex calculations in client scripts
- Use server scripts for heavy processing
- Index frequently queried custom fields

### Maintenance
- Document all customizations
- Version control custom scripts
- Test customizations in staging before production

---

**Last Updated:** 2025-12-02
**License:** Apache-2.0
