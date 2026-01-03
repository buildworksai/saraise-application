<!-- SPDX-License-Identifier: Apache-2.0 -->
# Automation Orchestration - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Automation Orchestration module.

## Getting Started

<!-- TODO: Add getting started instructions -->

## Features

<!-- TODO: Add feature documentation -->

## Usage

<!-- TODO: Add usage instructions -->

## Customization

<!-- TODO: Add customization options -->

## Integrations

<!-- TODO: Add integration information -->


## Customization

<!-- SPDX-License-Identifier: Apache-2.0 -->
# Automation Orchestration - Customization Guide

**Module**: `automation`
**Category**: AI Automation
**Version**: 1.0.0

---

## Overview

The Automation Orchestration module supports extensive customization through the SARAISE Customization Framework. This guide documents all customization points, including server scripts, client scripts, webhooks, and custom API endpoints.

**Related Documentation**:
- [Customization Framework](../../01-foundation/customization-framework/README.md) - Complete customization framework documentation
- [EventBusEvent System](../../../architecture/11-event-system.md) - EventBusEvent-driven architecture patterns

---

## Server Scripts

Server scripts allow you to customize orchestration behavior on the backend without modifying core code. Scripts run in a sandboxed environment with full access to the SARAISE API.

### Resource Scripts

Server scripts can be attached to the `Workstream` Resource to customize orchestration lifecycle events.

#### Available Events

| EventBusEvent | Trigger | Use Case |
|-------|---------|----------|
| `before_insert` | Before workstream is created | Validate workstream definition, set default values |
| `after_insert` | After workstream is created | Initialize workstream resources, send notifications |
| `before_validate` | Before validation runs | Custom validation logic |
| `validate` | During validation | Additional business rule validation |
| `before_save` | Before any save operation | Auto-calculate fields, transform workstream definition |
| `after_save` | After save operation | Update related records, trigger workflows |
| `before_submit` | Before workstream activation | Final validation, resource checks |
| `after_submit` | After workstream activated | Start background processes, notifications |
| `before_cancel` | Before workstream deactivation | Check for active executions, dependencies |
| `after_cancel` | After workstream deactivated | Cleanup resources, archive data |
| `before_delete` | Before workstream deletion | Check for active executions, dependencies |
| `on_trash` | When workstream moved to trash | Soft delete handling |

#### Example: Custom Workstream Validation

```python
# Server Script: Custom workstream validation
# EventBusEvent: validate
# Resource: Workstream

def validate(doc, method):
    """Custom validation for workstream definition"""

    # Validate workstream definition structure
    if not doc.definition:
        frappe.throw("Workstream definition is required")

    # Validate nodes exist in definition
    nodes = doc.nodes or []
    if not nodes:
        frappe.throw("Workstream must have at least one node")

    # Validate node types are supported
    supported_node_types = ["agent", "workflow", "condition", "action", "start", "end"]
    for node in nodes:
        node_type = node.get("type")
        if node_type not in supported_node_types:
            frappe.throw(f"Unsupported node type: {node_type}")

    # Validate edges reference valid nodes
    edges = doc.edges or []
    node_ids = [node.get("id") for node in nodes]

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")

        if source not in node_ids:
            frappe.throw(f"Edge references invalid source node: {source}")
        if target not in node_ids:
            frappe.throw(f"Edge references invalid target node: {target}")

    # Validate workstream has exactly one start node
    start_nodes = [node for node in nodes if node.get("type") == "start"]
    if len(start_nodes) != 1:
        frappe.throw("Workstream must have exactly one start node")

    # Validate workstream has at least one end node
    end_nodes = [node for node in nodes if node.get("type") == "end"]
    if not end_nodes:
        frappe.throw("Workstream must have at least one end node")

    # Validate agent nodes reference valid agents
    agent_nodes = [node for node in nodes if node.get("type") == "agent"]
    for agent_node in agent_nodes:
        agent_id = agent_node.get("agent_id")
        if agent_id:
            agent = frappe.get_doc("AIAgent", agent_id)
            if not agent or agent.status != "active":
                frappe.throw(f"Agent '{agent_id}' is not active or does not exist")

    # Validate workflow nodes reference valid workflows
    workflow_nodes = [node for node in nodes if node.get("type") == "workflow"]
    for workflow_node in workflow_nodes:
        workflow_id = workflow_node.get("workflow_id")
        if workflow_id:
            workflow = frappe.get_doc("Workflow", workflow_id)
            if not workflow or workflow.status != "active":
                frappe.throw(f"Workflow '{workflow_id}' is not active or does not exist")
```

#### Example: Custom Workstream Node Execution

```python
# Server Script: Custom workstream node execution
# EventBusEvent: Custom (triggered during workstream execution)
# Resource: WorkstreamNode

def execute_custom_node(node, execution_context):
    """Execute custom workstream node"""

    node_type = node.get("type")
    node_config = node.get("config", {})

    if node_type == "custom_action":
        # Execute custom action
        action_name = node_config.get("action_name")
        action_params = node_config.get("params", {})

        # Call custom action handler
        result = execute_custom_action(action_name, action_params, execution_context)

        return {
            "status": "completed",
            "output": result,
            "next_nodes": node_config.get("next_nodes", [])
        }

    elif node_type == "condition":
        # Evaluate condition
        condition_expression = node_config.get("expression")
        condition_result = evaluate_condition(condition_expression, execution_context)

        # Determine next node based on condition
        if condition_result:
            next_node = node_config.get("true_node")
        else:
            next_node = node_config.get("false_node")

        return {
            "status": "completed",
            "output": {"condition_result": condition_result},
            "next_nodes": [next_node] if next_node else []
        }

    elif node_type == "agent":
        # Execute AI agent
        agent_id = node.get("agent_id")
        agent_input = node_config.get("input", {})

        # Merge execution context into agent input
        agent_input = merge_context(agent_input, execution_context)

        # Execute agent
        from src.modules.ai_agent_management.services.agent_service import AgentService
        agent_service = AgentService(frappe.db)

        execution = agent_service.execute_agent(
            agent_id=agent_id,
            input_data=agent_input,
            tenant_id=execution_context.get("tenant_id"),
            user_id=execution_context.get("user_id")
        )

        return {
            "status": execution.status,
            "output": execution.output_data,
            "next_nodes": node_config.get("next_nodes", [])
        }

    elif node_type == "workflow":
        # Execute workflow
        workflow_id = node.get("workflow_id")
        workflow_input = node_config.get("input", {})

        # Merge execution context into workflow input
        workflow_input = merge_context(workflow_input, execution_context)

        # Execute workflow
        from src.modules.workflow_automation.services.workflow_service import WorkflowService
        workflow_service = WorkflowService(frappe.db)

        execution = workflow_service.execute_workflow(
            workflow_id=workflow_id,
            tenant_id=execution_context.get("tenant_id"),
            execute_data={"input_data": workflow_input},
            user_id=execution_context.get("user_id")
        )

        return {
            "status": execution.status,
            "output": execution.output_data,
            "next_nodes": node_config.get("next_nodes", [])
        }

    return {
        "status": "skipped",
        "output": None
    }

def evaluate_condition(expression, context):
    """Evaluate condition expression"""
    # Simple condition evaluation (can be extended)
    # Replace variables with context values
    for key, value in context.items():
        expression = expression.replace(f"{{{{{key}}}}}", str(value))

    # Evaluate expression safely
    try:
        result = eval(expression)
        return bool(result)
    except:
        frappe.throw(f"Invalid condition expression: {expression}")

def merge_context(data, context):
    """Merge execution context into data"""
    merged = data.copy()

    # Add context variables
    for key, value in context.items():
        if key not in merged:
            merged[key] = value

    return merged
```

#### Example: Workstream Execution Orchestration

```python
# Server Script: Orchestrate workstream execution
# EventBusEvent: Custom (triggered via API or scheduled script)
# Resource: WorkstreamExecution

def orchestrate_workstream(workstream_id, input_data, user_id=None):
    """Orchestrate workstream execution"""

    workstream = frappe.get_doc("Workstream", workstream_id)

    # Create execution record
    execution = frappe.get_doc({
        "resource_type": "WorkstreamExecution",
        "workstream_id": workstream_id,
        "tenant_id": workstream.tenant_id,
        "user_id": user_id or frappe.session.user,
        "status": "running",
        "input_data": input_data,
        "started_at": frappe.utils.now()
    })
    execution.insert()

    # Initialize execution context
    execution_context = {
        "workstream_id": workstream_id,
        "execution_id": execution.name,
        "tenant_id": workstream.tenant_id,
        "user_id": user_id or frappe.session.user,
        "input_data": input_data,
        "output_data": {},
        "node_outputs": {}
    }

    # Find start node
    start_node = next(
        (node for node in workstream.nodes if node.get("type") == "start"),
        None
    )

    if not start_node:
        frappe.throw("Workstream must have a start node")

    # Execute workstream nodes
    current_node = start_node
    visited_nodes = set()

    try:
        while current_node:
            node_id = current_node.get("id")

            # Check for cycles
            if node_id in visited_nodes:
                frappe.throw(f"Circular reference detected in workstream: {node_id}")

            visited_nodes.add(node_id)

            # Execute node
            node_result = execute_custom_node(current_node, execution_context)

            # Store node output
            execution_context["node_outputs"][node_id] = node_result.get("output")

            # Update execution context with node output
            if node_result.get("output"):
                execution_context["output_data"].update(node_result.get("output", {}))

            # Check if execution should stop
            if current_node.get("type") == "end":
                execution.status = "completed"
                execution.output_data = execution_context["output_data"]
                execution.completed_at = frappe.utils.now()
                execution.save()
                break

            # Move to next node
            next_nodes = node_result.get("next_nodes", [])
            if not next_nodes:
                # No next nodes - execution complete
                execution.status = "completed"
                execution.output_data = execution_context["output_data"]
                execution.completed_at = frappe.utils.now()
                execution.save()
                break

            # Get next node (handle multiple paths)
            next_node_id = next_nodes[0]  # Take first path (can be extended for parallel execution)
            current_node = next(
                (node for node in workstream.nodes if node.get("id") == next_node_id),
                None
            )

            if not current_node:
                frappe.throw(f"Next node '{next_node_id}' not found in workstream")

    except Exception as e:
        # Handle execution failure
        execution.status = "failed"
        execution.error_message = str(e)
        execution.completed_at = frappe.utils.now()
        execution.save()

        frappe.log_error(
            f"Workstream execution failed: {str(e)}",
            "Workstream Execution Error"
        )

        raise

    return execution
```

### API Scripts

Custom API endpoints can be created for orchestration-specific operations.

#### Example: Custom Workstream Execution Endpoint

```python
# API Script: Custom workstream execution with preprocessing
# Endpoint: POST /api/method/automation.api.custom_execute_workstream
# Method: POST

@frappe.whitelist(allow_guest=False)
def custom_execute_workstream(workstream_id, input_data, options=None):
    """Custom workstream execution with additional preprocessing"""

    # Get workstream
    workstream = frappe.get_doc("Workstream", workstream_id)

    # Validate workstream access
    if not frappe.has_permission("Workstream", "read", workstream=workstream):
        frappe.throw("Permission denied", frappe.PermissionError)

    # Preprocess input data
    processed_input = preprocess_workstream_input(input_data, workstream)

    # Execute workstream
    execution = orchestrate_workstream(
        workstream_id=workstream_id,
        input_data=processed_input,
        user_id=frappe.session.user
    )

    # Post-process results
    result = postprocess_workstream_output(execution.output_data, workstream)

    return {
        "execution_id": execution.name,
        "status": execution.status,
        "result": result,
        "execution_time": (
            (execution.completed_at - execution.started_at).total_seconds()
            if execution.completed_at else None
        )
    }

def preprocess_workstream_input(input_data, workstream):
    """Preprocess input data based on workstream configuration"""
    # Add workstream context
    processed = {
        "input": input_data,
        "workstream_name": workstream.name,
        "workstream_id": workstream.id,
        "timestamp": frappe.utils.now()
    }

    # Add system context if configured
    if workstream.definition.get("include_context"):
        processed["context"] = get_workstream_context(workstream)

    # Validate required input fields
    required_fields = workstream.definition.get("required_input_fields", [])
    for field in required_fields:
        if field not in input_data:
            frappe.throw(f"Required input field '{field}' is missing")

    return processed

def postprocess_workstream_output(output_data, workstream):
    """Post-process workstream output"""
    if not output_data:
        return None

    # Extract structured output if available
    if isinstance(output_data, dict) and "output" in output_data:
        output = output_data["output"]

        # Parse JSON if output is JSON string
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except:
                pass

        return output

    return output_data
```

### Scheduled Scripts

Scheduled scripts can be used for workstream monitoring, cleanup, and maintenance tasks.

#### Example: Workstream Health Monitoring

```python
# Scheduled Script: Monitor workstream health
# Frequency: Every 15 minutes
# Cron: */15 * * * *

def monitor_workstream_health():
    """Monitor workstream health and send alerts"""

    # Get all active workstreams
    active_workstreams = frappe.get_all(
        "Workstream",
        filters={"status": "active", "is_active": 1},
        fields=["name", "tenant_id", "last_execution_at"]
    )

    for workstream in active_workstreams:
        # Check if workstream has executed recently
        if workstream.last_execution_at:
            last_execution = frappe.utils.get_datetime(workstream.last_execution_at)
            hours_since_execution = (
                frappe.utils.now_datetime() - last_execution
            ).total_seconds() / 3600

            # Alert if no execution in 24 hours for active workstream
            if hours_since_execution > 24:
                send_workstream_inactivity_alert(workstream)

        # Check for recent failures
        recent_failures = frappe.db.count("WorkstreamExecution", {
            "workstream_id": workstream.name,
            "status": "failed",
            "created_at": [">", frappe.utils.add_hours(frappe.utils.now(), -1)]
        })

        if recent_failures >= 5:
            send_workstream_failure_alert(workstream, recent_failures)

        # Check for stuck executions
        stuck_executions = frappe.db.count("WorkstreamExecution", {
            "workstream_id": workstream.name,
            "status": "running",
            "created_at": ["<", frappe.utils.add_hours(frappe.utils.now(), -2)]
        })

        if stuck_executions > 0:
            send_stuck_execution_alert(workstream, stuck_executions)
```

---

## Client Scripts

Client scripts run in the browser and customize the orchestration UI behavior.

### Form Events

Client scripts can be attached to the `Workstream` form to customize UI behavior.

#### Example: Dynamic Workstream Builder UI

```javascript
// Client Script: Dynamic workstream builder UI
// Resource: Workstream
// EventBusEvent: onload

frappe.ui.form.on('Workstream', {
    onload: function(frm) {
        // Setup workstream builder
        setup_workstream_builder(frm);

        // Setup node editor
        setup_node_editor(frm);
    },

    validate: function(frm) {
        // Client-side validation
        if (!frm.doc.name) {
            frappe.msgprint('Workstream name is required');
            validated = false;
        }

        if (!frm.doc.definition || !frm.doc.definition.nodes || frm.doc.definition.nodes.length === 0) {
            frappe.msgprint('Workstream must have at least one node');
            validated = false;
        }
    }
});

function setup_workstream_builder(frm) {
    // Initialize workstream visual builder
    if (frm.is_new()) {
        // Show workstream builder canvas
        frm.dashboard.add_section(
            frappe.render_template('workstream_builder', {
                workstream: frm.doc
            })
        );
    } else {
        // Load existing workstream into builder
        load_workstream_into_builder(frm);
    }
}

function setup_node_editor(frm) {
    // Custom node editor with drag-and-drop
    frm.add_custom_button('Edit Nodes', function() {
        open_node_editor(frm);
    }, 'Actions');
}

function open_node_editor(frm) {
    // Open node editor dialog
    const dialog = new frappe.ui.Dialog({
        title: `Node Editor: ${frm.doc.name}`,
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'node_editor',
                options: '<div id="node-editor"></div>'
            }
        ]
    });

    dialog.show();

    // Initialize node editor
    initialize_node_editor(frm.doc.definition);
}
```

---

## Webhooks

Webhooks allow external systems to be notified of workstream events. Webhooks are configured per tenant and can subscribe to specific event types.

### Available Events

| EventBusEvent Type | Description | Payload |
|------------|-------------|---------|
| `workstream.executed` | Workstream execution started | `{workstream_id, execution_id, tenant_id, user_id, input_data, timestamp}` |
| `workstream.completed` | Workstream execution completed successfully | `{workstream_id, execution_id, tenant_id, output_data, execution_time, timestamp}` |
| `workstream.failed` | Workstream execution failed | `{workstream_id, execution_id, tenant_id, error_message, timestamp}` |
| `workstream.node_completed` | Workstream node completed | `{workstream_id, execution_id, node_id, node_type, output_data, timestamp}` |
| `workstream.node_failed` | Workstream node failed | `{workstream_id, execution_id, node_id, node_type, error_message, timestamp}` |
| `workstream.created` | New workstream created | `{workstream_id, workstream_name, tenant_id, user_id, timestamp}` |
| `workstream.updated` | Workstream configuration updated | `{workstream_id, workstream_name, updates, tenant_id, user_id, timestamp}` |
| `workstream.activated` | Workstream activated | `{workstream_id, workstream_name, tenant_id, timestamp}` |
| `workstream.deactivated` | Workstream deactivated | `{workstream_id, workstream_name, tenant_id, timestamp}` |

### Webhook Configuration

Webhooks are configured through the Customization Framework API:

```python
# Create webhook for workstream execution events
POST /api/v1/webhooks
{
    "name": "Workstream Execution Notifier",
    "event_type": "workstream.completed",
    "url": "https://example.com/webhooks/workstream-completed",
    "method": "POST",
    "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
    },
    "tenant_id": "tenant-123",
    "is_active": true
}
```

### Example: Workstream Execution Completion Webhook

```python
# Webhook Handler: Process workstream execution completion
# EventBusEvent: workstream.completed
# URL: https://your-system.com/webhooks/workstream-completed

def handle_workstream_completed(payload):
    """Handle workstream execution completion webhook"""

    workstream_id = payload.get("workstream_id")
    execution_id = payload.get("execution_id")
    output_data = payload.get("output_data")

    # Process workstream output
    process_workstream_output(workstream_id, output_data)

    # Update external system
    update_external_system(workstream_id, execution_id, output_data)

    # Send notification
    send_notification(workstream_id, "Workstream execution completed")
```

---

## Custom API Endpoints

Custom API endpoints can be created for orchestration-specific operations that extend the standard API.

### Example: Batch Workstream Execution

```python
# Custom API Endpoint: Execute multiple workstreams in batch
# Endpoint: POST /api/method/automation.api.batch_execute_workstreams
# Method: POST

@frappe.whitelist(allow_guest=False)
def batch_execute_workstreams(workstream_ids, input_data, options=None):
    """Execute multiple workstreams in batch"""

    if not isinstance(workstream_ids, list):
        frappe.throw("workstream_ids must be a list")

    results = []

    for workstream_id in workstream_ids:
        try:
            # Get workstream
            workstream = frappe.get_doc("Workstream", workstream_id)

            # Validate access
            if not frappe.has_permission("Workstream", "read", workstream=workstream):
                results.append({
                    "workstream_id": workstream_id,
                    "status": "error",
                    "error": "Permission denied"
                })
                continue

            # Execute workstream
            execution = orchestrate_workstream(
                workstream_id=workstream_id,
                input_data=input_data,
                user_id=frappe.session.user
            )

            results.append({
                "workstream_id": workstream_id,
                "execution_id": execution.name,
                "status": execution.status,
                "output_data": execution.output_data
            })

        except Exception as e:
            results.append({
                "workstream_id": workstream_id,
                "status": "error",
                "error": str(e)
            })

    return {
        "total": len(workstream_ids),
        "results": results
    }
```

---

## EventBusEvent Bus Integration

Workstream events are automatically published to the SARAISE EventBusEvent Bus, allowing other modules and customizations to subscribe to orchestration events. The EventBusEvent Bus uses Redis pub/sub for distributed event communication and supports both tenant-scoped and global events.

### EventBusEvent Types

The following workstream events are published to the EventBusEvent Bus:

| EventBusEvent Type | Description | When Published |
|------------|-------------|----------------|
| `workstream.started` | Workstream execution started | When workstream execution begins |
| `workstream.completed` | Workstream execution completed successfully | When workstream execution completes successfully |
| `workstream.failed` | Workstream execution failed | When workstream execution fails with error |
| `workstream.node_completed` | Workstream node completed | When individual workstream node completes |

### Publishing Events from Services

When extending the Automation Orchestration service, you can publish custom events:

```python
# In orchestration_service.py or custom server script
from src.core.event_bus import event_bus, EventType

# Publish workstream started event
await event_bus.publish(
    event_type=EventType.WORKSTREAM_STARTED,
    data={
        "workstream_id": workstream.id,
        "execution_id": execution.id,
        "input_data": input_data,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)

# Publish workstream completed event
await event_bus.publish(
    event_type=EventType.WORKSTREAM_COMPLETED,
    data={
        "workstream_id": workstream.id,
        "execution_id": execution.id,
        "output_data": output_data,
        "execution_time": execution_time,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)

# Publish workstream failed event
await event_bus.publish(
    event_type=EventType.WORKSTREAM_FAILED,
    data={
        "workstream_id": workstream.id,
        "execution_id": execution.id,
        "error_message": str(error),
        "error_type": type(error).__name__,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)

# Publish workstream node completed event
await event_bus.publish(
    event_type=EventType.WORKSTREAM_NODE_COMPLETED,
    data={
        "workstream_id": workstream.id,
        "execution_id": execution.id,
        "node_id": node.id,
        "node_type": node.type,
        "output_data": node_output,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)
```

### Subscribing to Workstream Events

#### Using EventBusEvent System (Recommended)

```python
# Server Script: Subscribe to workstream events using EventBusEvent System
from src.core.event_bus import event_bus, EventType

# Subscribe to workstream execution events
event_bus.subscribe(
    EventType.WORKSTREAM_STARTED,
    handle_workstream_started
)

event_bus.subscribe(
    EventType.WORKSTREAM_COMPLETED,
    handle_workstream_completed
)

event_bus.subscribe(
    EventType.WORKSTREAM_FAILED,
    handle_workstream_failed
)

event_bus.subscribe(
    EventType.WORKSTREAM_NODE_COMPLETED,
    handle_workstream_node_completed
)

async def handle_workstream_started(event):
    """Handle workstream execution started event"""
    workstream_id = event.data.get("workstream_id")
    execution_id = event.data.get("execution_id")
    tenant_id = event.tenant_id

    # Log execution start
    logger.info(f"Workstream {workstream_id} execution started: {execution_id} for tenant {tenant_id}")

    # Trigger custom logic
    await process_workstream_execution_start(workstream_id, execution_id, tenant_id)

async def handle_workstream_completed(event):
    """Handle workstream execution completed event"""
    workstream_id = event.data.get("workstream_id")
    output_data = event.data.get("output_data")
    tenant_id = event.tenant_id

    # Process completed execution
    await process_completed_workstream(workstream_id, output_data, tenant_id)

async def handle_workstream_failed(event):
    """Handle workstream execution failed event"""
    workstream_id = event.data.get("workstream_id")
    error_message = event.data.get("error_message")
    tenant_id = event.tenant_id

    # Send failure notification
    await send_failure_notification(workstream_id, error_message, tenant_id)

async def handle_workstream_node_completed(event):
    """Handle workstream node completed event"""
    node_type = event.data.get("node_type")
    output_data = event.data.get("output_data")
    tenant_id = event.tenant_id

    # Process node output
    await process_node_output(node_type, output_data, tenant_id)
```

#### Using EventBusEvent Bus Directly (Advanced)

For more control, you can subscribe directly to the EventBusEvent Bus:

```python
# Server Script: Direct EventBusEvent Bus subscription
from src.core.event_bus import event_bus, EventBusEvent

async def handle_workstream_event(event: EventBusEvent):
    """Handle workstream event from EventBusEvent Bus"""
    event_type = event.event_type
    data = event.data
    tenant_id = event.tenant_id

    if event_type == "workstream.started":
        # Handle workstream execution started
        await process_workstream_execution(data, tenant_id)
    elif event_type == "workstream.completed":
        # Handle workstream execution completed
        await process_workstream_completion(data, tenant_id)
    elif event_type == "workstream.failed":
        # Handle workstream execution failed
        await process_workstream_failure(data, tenant_id)
    elif event_type == "workstream.node_completed":
        # Handle workstream node completed
        await process_workstream_node_completion(data, tenant_id)

# Subscribe to all workstream events for specific tenant
await event_bus.subscribe(
    event_type="workstream.*",  # Wildcard subscription
    handler=handle_workstream_event,
    tenant_id="tenant-123"  # Tenant-scoped subscription
)

# Subscribe to specific event type globally
await event_bus.subscribe(
    event_type="workstream.completed",
    handler=handle_workstream_event,
    use_global=True  # Global subscription
)
```

### Integration with Customization Framework

The EventBusEvent Bus integrates seamlessly with the Customization Framework:

#### Webhooks Triggered by Events

Webhooks can be configured to trigger on workstream events:

```python
# Webhook Configuration
# EventBusEvent: workstream.completed
# URL: https://your-system.com/webhooks/workstream-completed

def handle_workstream_completed_webhook(payload):
    """Webhook handler for workstream completion events"""
    workstream_id = payload.get("workstream_id")
    output_data = payload.get("output_data")

    # Process webhook payload
    process_webhook_payload(workstream_id, output_data)
```

#### Server Scripts Subscribing to Events

Server scripts can subscribe to events for custom processing:

```python
# Server Script: Custom workstream analytics on completion
# EventBusEvent: workstream.completed
# Script Type: Scheduled (runs on event)

def process_workstream_analytics(event):
    """Process workstream analytics when workstream completes"""
    workstream_id = event.data.get("workstream_id")
    execution_time = event.data.get("execution_time")

    # Update workstream analytics
    update_workstream_analytics(workstream_id, execution_time)
```

### Tenant-Scoped vs Global Events

Events can be published as tenant-scoped or global:

```python
# Tenant-scoped event (default)
await event_bus.publish(
    event_type=EventType.WORKSTREAM_STARTED,
    data={"workstream_id": "workstream-123"},
    tenant_id="tenant-456"  # Only subscribers for this tenant receive event
)

# Global event (cross-tenant)
await event_bus.publish(
    event_type="workstream.started",
    data={"workstream_id": "workstream-123"},
    use_global=True  # All subscribers receive event
)
```

### EventBusEvent Payload Structure

```python
# Workstream Executed EventBusEvent
{
    "event_type": "workstream.executed",
    "data": {
        "workstream_id": "workstream-123",
        "execution_id": "execution-456",
        "tenant_id": "tenant-789",
        "user_id": "user-abc",
        "input_data": {...},
        "timestamp": "2025-01-15T10:30:00Z"
    },
    "tenant_id": "tenant-789",
    "user_id": "user-abc"
}

# Workstream Completed EventBusEvent
{
    "event_type": "workstream.completed",
    "data": {
        "workstream_id": "workstream-123",
        "execution_id": "execution-456",
        "tenant_id": "tenant-789",
        "output_data": {...},
        "execution_time": 12.5,
        "timestamp": "2025-01-15T10:30:12Z"
    },
    "tenant_id": "tenant-789"
}

# Workstream Node Completed EventBusEvent
{
    "event_type": "workstream.node_completed",
    "data": {
        "workstream_id": "workstream-123",
        "execution_id": "execution-456",
        "node_id": "node-789",
        "node_type": "agent",
        "output_data": {...},
        "timestamp": "2025-01-15T10:30:05Z"
    },
    "tenant_id": "tenant-789"
}
```

---

## Best Practices

### Server Scripts

1. **Error Handling**: Always use `frappe.throw()` for validation errors, `frappe.log_error()` for logging
2. **Performance**: Use `frappe.enqueue()` for long-running operations
3. **Security**: Validate user permissions and tenant isolation
4. **Transactions**: Be aware of database transaction boundaries
5. **Node Execution**: Ensure custom nodes are idempotent and can handle retries

### Client Scripts

1. **User Experience**: Provide immediate feedback for user actions
2. **Validation**: Use client-side validation for better UX, but always validate on server
3. **Real-time Updates**: Use WebSocket events for real-time execution status updates
4. **Error Handling**: Show user-friendly error messages
5. **Workstream Builder**: Provide visual feedback in workstream builder UI

### Webhooks

1. **Idempotency**: Design webhook handlers to be idempotent
2. **Retry Logic**: Implement retry logic for failed webhook deliveries
3. **Security**: Validate webhook signatures and use HTTPS
4. **Rate Limiting**: Respect rate limits when calling external APIs
5. **Node Events**: Consider subscribing to node-level events for granular monitoring

### Custom API Endpoints

1. **Authentication**: Always use `@frappe.whitelist(allow_guest=False)` for authenticated endpoints
2. **Permission Checks**: Validate user permissions before processing
3. **Input Validation**: Validate and sanitize all input data
4. **Error Responses**: Return consistent error response format
5. **Batch Operations**: Consider rate limiting for batch operations

---

## Examples Repository

For more examples, see:
- `backend/scripts/demo_customizations/automation_orchestration/` - Demo customization examples
- [Customization Framework Examples](../../01-foundation/customization-framework/README.md#examples)

---

## Support

For questions or issues with Automation Orchestration customizations:
- Review [Customization Framework Documentation](../../01-foundation/customization-framework/README.md)
- Check [EventBusEvent System Documentation](../../../architecture/11-event-system.md)
- Contact the development team

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
