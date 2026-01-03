<!-- SPDX-License-Identifier: Apache-2.0 -->
# Workflow Automation - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Workflow Automation module.

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
# Workflow Automation - Customization Guide

**Module**: `workflow_automation`
**Category**: AI Automation
**Version**: 1.0.0

---

## Overview

The Workflow Automation module supports extensive customization through the SARAISE Customization Framework. This guide documents all customization points, including server scripts, client scripts, webhooks, and custom API endpoints.

**Related Documentation**:
- [Customization Framework](../../01-foundation/customization-framework/README.md) - Complete customization framework documentation
- [EventBusEvent System](../../../architecture/11-event-system.md) - EventBusEvent-driven architecture patterns

---

## Server Scripts

Server scripts allow you to customize workflow behavior on the backend without modifying core code. Scripts run in a sandboxed environment with full access to the SARAISE API.

### Resource Scripts

Server scripts can be attached to the `Workflow` Resource to customize workflow lifecycle events.

#### Available Events

| EventBusEvent | Trigger | Use Case |
|-------|---------|----------|
| `before_insert` | Before workflow is created | Validate workflow definition, set default values |
| `after_insert` | After workflow is created | Initialize workflow resources, send notifications |
| `before_validate` | Before validation runs | Custom validation logic |
| `validate` | During validation | Additional business rule validation |
| `before_save` | Before any save operation | Auto-calculate fields, transform workflow definition |
| `after_save` | After save operation | Update related records, trigger workflows |
| `before_submit` | Before workflow activation | Final validation, resource checks |
| `after_submit` | After workflow activated | Start background processes, notifications |
| `before_cancel` | Before workflow deactivation | Check for active executions, dependencies |
| `after_cancel` | After workflow deactivated | Cleanup resources, archive data |
| `before_delete` | Before workflow deletion | Check for active executions, dependencies |
| `on_trash` | When workflow moved to trash | Soft delete handling |

#### Example: Custom Workflow Validation

```python
# Server Script: Custom workflow validation
# EventBusEvent: validate
# Resource: Workflow

def validate(doc, method):
    """Custom validation for workflow definition"""

    # Validate workflow definition structure
    if not doc.definition:
        frappe.throw("Workflow definition is required")

    # Validate nodes exist in definition
    nodes = doc.nodes or []
    if not nodes:
        frappe.throw("Workflow must have at least one node")

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

    # Validate workflow has at least one start node
    start_nodes = [node for node in nodes if node.get("type") == "start"]
    if not start_nodes:
        frappe.throw("Workflow must have at least one start node")

    # Validate timeout is reasonable
    if doc.timeout_seconds and doc.timeout_seconds > 3600:
        frappe.throw("Workflow timeout cannot exceed 3600 seconds (1 hour)")

    # Validate concurrent execution limit
    if doc.max_concurrent_executions and doc.max_concurrent_executions > 100:
        frappe.throw("Maximum concurrent executions cannot exceed 100")
```

#### Example: Auto-Configure Workflow on Creation

```python
# Server Script: Auto-configure workflow settings
# EventBusEvent: after_insert
# Resource: Workflow

def after_insert(doc, method):
    """Auto-configure workflow after creation"""

    # Set default status
    if not doc.status:
        doc.status = "draft"

    # Set default timeout if not specified
    if not doc.timeout_seconds:
        doc.timeout_seconds = 300  # 5 minutes default

    # Set default concurrent execution limit
    if not doc.max_concurrent_executions:
        doc.max_concurrent_executions = 10

    # Initialize execution counters
    doc.total_executions = 0
    doc.successful_executions = 0
    doc.failed_executions = 0

    # Save configuration
    doc.save()

    # Log workflow creation
    frappe.log_error(
        f"Workflow '{doc.name}' created for tenant '{doc.tenant_id}'",
        "Workflow Created"
    )
```

#### Example: Custom Workflow Step Execution

```python
# Server Script: Custom workflow step execution
# EventBusEvent: Custom (triggered during workflow execution)
# Resource: WorkflowStep

def execute_custom_step(step, execution_context):
    """Execute custom workflow step"""

    step_type = step.get("type")
    step_config = step.get("config", {})

    if step_type == "custom_action":
        # Execute custom action
        action_name = step_config.get("action_name")
        action_params = step_config.get("params", {})

        # Call custom action handler
        result = execute_custom_action(action_name, action_params, execution_context)

        return {
            "status": "completed",
            "output": result,
            "next_step": step_config.get("next_step")
        }

    elif step_type == "data_transformation":
        # Custom data transformation
        input_data = execution_context.get("input_data", {})
        transformation_script = step_config.get("script")

        # Execute transformation (sandboxed)
        transformed_data = execute_transformation_script(
            transformation_script,
            input_data
        )

        return {
            "status": "completed",
            "output": transformed_data
        }

    elif step_type == "external_api":
        # Call external API
        api_url = step_config.get("url")
        api_method = step_config.get("method", "POST")
        api_headers = step_config.get("headers", {})
        api_body = step_config.get("body", {})

        # Make API call
        response = frappe.utils.make_request(
            api_url,
            method=api_method,
            headers=api_headers,
            data=api_body
        )

        return {
            "status": "completed",
            "output": response.json() if response.ok else None,
            "error": None if response.ok else response.text
        }

    return {
        "status": "skipped",
        "output": None
    }

def execute_custom_action(action_name, params, context):
    """Execute custom action by name"""
    # Lookup custom action handler
    action_handler = get_custom_action_handler(action_name)

    if not action_handler:
        frappe.throw(f"Custom action '{action_name}' not found")

    # Execute handler
    return action_handler(params, context)
```

#### Example: Workflow Execution Post-Processing

```python
# Server Script: Process workflow execution results
# EventBusEvent: Custom (triggered via webhook or scheduled script)
# Resource: AutomationWorkflowExecution

def process_workflow_execution(execution_id):
    """Process completed workflow execution"""

    execution = frappe.get_doc("AutomationWorkflowExecution", execution_id)

    if execution.status != "completed":
        return

    # Extract output data
    output_data = execution.output_data or {}

    # Store execution metrics
    metrics = {
        "execution_time": execution.duration,
        "steps_executed": len(execution.steps or []),
        "steps_succeeded": sum(1 for s in execution.steps if s.get("status") == "completed"),
        "steps_failed": sum(1 for s in execution.steps if s.get("status") == "failed"),
    }

    # Update workflow statistics
    workflow = frappe.get_doc("Workflow", execution.workflow_id)
    workflow.total_executions += 1
    workflow.successful_executions += 1
    workflow.save()

    # Create execution log
    frappe.get_doc({
        "resource_type": "WorkflowLog",
        "workflow_id": execution.workflow_id,
        "execution_id": execution_id,
        "tenant_id": execution.tenant_id,
        "status": execution.status,
        "duration": execution.duration,
        "steps_executed": metrics["steps_executed"],
        "timestamp": execution.completed_at,
    }).insert()

    # Trigger post-execution actions
    trigger_post_execution_actions(execution, output_data)
```

### API Scripts

Custom API endpoints can be created for workflow-specific operations.

#### Example: Custom Workflow Execution Endpoint

```python
# API Script: Custom workflow execution with preprocessing
# Endpoint: POST /api/method/workflow_automation.api.custom_execute_workflow
# Method: POST

@frappe.whitelist(allow_guest=False)
def custom_execute_workflow(workflow_id, input_data, options=None):
    """Custom workflow execution with additional preprocessing"""

    # Get workflow
    workflow = frappe.get_doc("Workflow", workflow_id)

    # Validate workflow access
    if not frappe.has_permission("Workflow", "read", workflow=workflow):
        frappe.throw("Permission denied", frappe.PermissionError)

    # Preprocess input data
    processed_input = preprocess_workflow_input(input_data, workflow)

    # Execute workflow via service
    from src.modules.workflow_automation.services.workflow_service import WorkflowService
    service = WorkflowService(frappe.db)

    execute_data = {
        "input_data": processed_input,
        "options": options or {}
    }

    execution = service.execute_workflow(
        workflow_id=workflow_id,
        tenant_id=workflow.tenant_id,
        execute_data=execute_data,
        user_id=frappe.session.user
    )

    # Post-process results
    result = postprocess_workflow_output(execution.output_data, workflow)

    return {
        "execution_id": execution.id,
        "status": execution.status,
        "result": result,
        "execution_time": execution.duration
    }

def preprocess_workflow_input(input_data, workflow):
    """Preprocess input data based on workflow configuration"""
    # Add workflow context
    processed = {
        "input": input_data,
        "workflow_name": workflow.name,
        "workflow_id": workflow.id,
        "timestamp": frappe.utils.now()
    }

    # Add system context if configured
    if workflow.definition.get("include_context"):
        processed["context"] = get_workflow_context(workflow)

    # Validate required input fields
    required_fields = workflow.definition.get("required_input_fields", [])
    for field in required_fields:
        if field not in input_data:
            frappe.throw(f"Required input field '{field}' is missing")

    return processed

def postprocess_workflow_output(output_data, workflow):
    """Post-process workflow output"""
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

#### Example: Workflow Performance Analytics

```python
# API Script: Get workflow performance analytics
# Endpoint: GET /api/method/workflow_automation.api.get_workflow_analytics
# Method: GET

@frappe.whitelist(allow_guest=False)
def get_workflow_analytics(workflow_id, start_date=None, end_date=None):
    """Get comprehensive workflow performance analytics"""

    workflow = frappe.get_doc("Workflow", workflow_id)

    # Validate access
    if not frappe.has_permission("Workflow", "read", workflow=workflow):
        frappe.throw("Permission denied", frappe.PermissionError)

    # Default date range: last 30 days
    if not start_date:
        start_date = frappe.utils.add_days(frappe.utils.today(), -30)
    if not end_date:
        end_date = frappe.utils.today()

    # Get execution metrics
    metrics = frappe.db.sql("""
        SELECT
            COUNT(*) as total_executions,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_executions,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_executions,
            AVG(duration) as avg_execution_time,
            MIN(duration) as min_execution_time,
            MAX(duration) as max_execution_time
        FROM `tabAutomationWorkflowExecution`
        WHERE workflow_id = %s
          AND created_at BETWEEN %s AND %s
    """, (workflow_id, start_date, end_date), as_dict=True)[0]

    # Calculate success rate
    success_rate = (
        (metrics.successful_executions / metrics.total_executions * 100)
        if metrics.total_executions > 0 else 0
    )

    # Get step-level analytics
    step_analytics = frappe.db.sql("""
        SELECT
            step_name,
            COUNT(*) as execution_count,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success_count,
            AVG(duration) as avg_duration
        FROM `tabWorkflowTask`
        WHERE execution_id IN (
            SELECT id FROM `tabAutomationWorkflowExecution`
            WHERE workflow_id = %s AND created_at BETWEEN %s AND %s
        )
        GROUP BY step_name
    """, (workflow_id, start_date, end_date), as_dict=True)

    return {
        "workflow_id": workflow_id,
        "workflow_name": workflow.name,
        "period": {
            "start_date": start_date,
            "end_date": end_date
        },
        "executions": {
            "total": metrics.total_executions or 0,
            "successful": metrics.successful_executions or 0,
            "failed": metrics.failed_executions or 0,
            "success_rate": round(success_rate, 2)
        },
        "performance": {
            "avg_execution_time": round(metrics.avg_execution_time or 0, 2),
            "min_execution_time": round(metrics.min_execution_time or 0, 2),
            "max_execution_time": round(metrics.max_execution_time or 0, 2)
        },
        "step_analytics": step_analytics
    }
```

### Scheduled Scripts

Scheduled scripts can be used for workflow maintenance, monitoring, and cleanup tasks.

#### Example: Workflow Health Monitoring

```python
# Scheduled Script: Monitor workflow health
# Frequency: Every 15 minutes
# Cron: */15 * * * *

def monitor_workflow_health():
    """Monitor workflow health and send alerts"""

    # Get all active workflows
    active_workflows = frappe.get_all(
        "Workflow",
        filters={"status": "active", "is_active": 1},
        fields=["name", "tenant_id", "trigger_type", "last_execution_at"]
    )

    for workflow in active_workflows:
        # Check if workflow has executed recently (within last hour)
        if workflow.last_execution_at:
            last_execution = frappe.utils.get_datetime(workflow.last_execution_at)
            hours_since_execution = (
                frappe.utils.now_datetime() - last_execution
            ).total_seconds() / 3600

            # Alert if no execution in 24 hours for active workflow
            if hours_since_execution > 24:
                send_workflow_inactivity_alert(workflow)

        # Check for recent failures
        recent_failures = frappe.db.count("AutomationWorkflowExecution", {
            "workflow_id": workflow.name,
            "status": "failed",
            "created_at": [">", frappe.utils.add_hours(frappe.utils.now(), -1)]
        })

        if recent_failures >= 5:
            send_workflow_failure_alert(workflow, recent_failures)

        # Check for stuck executions
        stuck_executions = frappe.db.count("AutomationWorkflowExecution", {
            "workflow_id": workflow.name,
            "status": "running",
            "created_at": ["<", frappe.utils.add_hours(frappe.utils.now(), -2)]
        })

        if stuck_executions > 0:
            send_stuck_execution_alert(workflow, stuck_executions)

def send_workflow_inactivity_alert(workflow):
    """Send alert for inactive workflow"""
    frappe.sendmail(
        recipients=get_tenant_admins(workflow.tenant_id),
        subject=f"Workflow Inactivity Alert: {workflow.name}",
        message=f"""
            Workflow '{workflow.name}' has not executed in the last 24 hours.

            Consider checking:
            - Workflow trigger configuration
            - Trigger conditions
            - Workflow status
        """
    )

def send_workflow_failure_alert(workflow, failure_count):
    """Send alert for workflow failures"""
    frappe.sendmail(
        recipients=get_tenant_admins(workflow.tenant_id),
        subject=f"Workflow Failure Alert: {workflow.name}",
        message=f"""
            Workflow '{workflow.name}' has failed {failure_count} times in the last hour.

            Please review:
            - Workflow logs
            - Step configurations
            - Input data format
            - External service availability
        """
    )

def send_stuck_execution_alert(workflow, stuck_count):
    """Send alert for stuck executions"""
    frappe.sendmail(
        recipients=get_tenant_admins(workflow.tenant_id),
        subject=f"Stuck Execution Alert: {workflow.name}",
        message=f"""
            Workflow '{workflow.name}' has {stuck_count} execution(s) stuck in running state.

            Please review:
            - Execution logs
            - Step timeouts
            - External service responses
        """
    )
```

#### Example: Cleanup Old Executions

```python
# Scheduled Script: Cleanup old workflow executions
# Frequency: Daily at 2 AM
# Cron: 0 2 * * *

def cleanup_old_executions():
    """Archive and cleanup old workflow executions"""

    # Archive executions older than 90 days
    cutoff_date = frappe.utils.add_days(frappe.utils.today(), -90)

    old_executions = frappe.get_all(
        "AutomationWorkflowExecution",
        filters={
            "created_at": ["<", cutoff_date],
            "status": ["in", ["completed", "failed"]]
        },
        fields=["name"]
    )

    for execution in old_executions:
        # Archive to external storage (implementation depends on storage solution)
        archive_execution(execution.name)

        # Delete from database
        frappe.delete_doc("AutomationWorkflowExecution", execution.name, force=1)

    frappe.log_error(
        f"Cleaned up {len(old_executions)} old workflow executions",
        "Workflow Cleanup"
    )
```

---

## Client Scripts

Client scripts run in the browser and customize the workflow automation UI behavior.

### Form Events

Client scripts can be attached to the `Workflow` form to customize UI behavior.

#### Example: Dynamic Workflow Builder UI

```javascript
// Client Script: Dynamic workflow builder UI
// Resource: Workflow
// EventBusEvent: onload

frappe.ui.form.on('Workflow', {
    onload: function(frm) {
        // Setup workflow builder
        setup_workflow_builder(frm);

        // Setup trigger configuration
        setup_trigger_config(frm);

        // Setup step editor
        setup_step_editor(frm);
    },

    trigger_type: function(frm) {
        // Update UI when trigger type changes
        update_trigger_fields(frm);
    },

    validate: function(frm) {
        // Client-side validation
        if (!frm.doc.name) {
            frappe.msgprint('Workflow name is required');
            validated = false;
        }

        if (!frm.doc.definition || !frm.doc.definition.nodes || frm.doc.definition.nodes.length === 0) {
            frappe.msgprint('Workflow must have at least one node');
            validated = false;
        }
    }
});

function setup_workflow_builder(frm) {
    // Initialize workflow visual builder
    if (frm.is_new()) {
        // Show workflow builder canvas
        frm.dashboard.add_section(
            frappe.render_template('workflow_builder', {
                workflow: frm.doc
            })
        );
    } else {
        // Load existing workflow into builder
        load_workflow_into_builder(frm);
    }
}

function setup_trigger_config(frm) {
    // Setup trigger type selector
    frm.set_query('trigger_type', function() {
        return {
            filters: {
                'is_active': 1
            }
        };
    });

    // Show/hide trigger-specific fields
    update_trigger_fields(frm);
}

function update_trigger_fields(frm) {
    const trigger_type = frm.doc.trigger_type;

    // Hide all trigger config sections
    frm.toggle_display('manual_trigger_config', false);
    frm.toggle_display('api_trigger_config', false);
    frm.toggle_display('scheduled_trigger_config', false);
    frm.toggle_display('event_trigger_config', false);

    // Show relevant config section
    if (trigger_type === 'manual') {
        frm.toggle_display('manual_trigger_config', true);
    } else if (trigger_type === 'api') {
        frm.toggle_display('api_trigger_config', true);
    } else if (trigger_type === 'scheduled') {
        frm.toggle_display('scheduled_trigger_config', true);
    } else if (trigger_type === 'event') {
        frm.toggle_display('event_trigger_config', true);
    }
}

function setup_step_editor(frm) {
    // Custom step editor with drag-and-drop
    frm.add_custom_button('Edit Steps', function() {
        open_step_editor(frm);
    }, 'Actions');
}

function open_step_editor(frm) {
    // Open step editor dialog
    const dialog = new frappe.ui.Dialog({
        title: `Step Editor: ${frm.doc.name}`,
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'step_editor',
                options: '<div id="step-editor"></div>'
            }
        ]
    });

    dialog.show();

    // Initialize step editor
    initialize_step_editor(frm.doc.definition);
}
```

#### Example: Real-time Workflow Execution Monitoring

```javascript
// Client Script: Real-time execution monitoring
// Resource: Workflow
// EventBusEvent: refresh

frappe.ui.form.on('Workflow', {
    refresh: function(frm) {
        // Add custom button for execution monitoring
        if (frm.doc.status === 'active') {
            frm.add_custom_button('Monitor Executions', function() {
                open_execution_monitor(frm);
            }, 'Actions');
        }

        // Listen to real-time execution updates
        frappe.realtime.on('workflow_execution_update', function(data) {
            if (data.workflow_id === frm.doc.name) {
                update_execution_status(frm, data);
            }
        });
    }
});

function open_execution_monitor(frm) {
    // Open execution monitor dialog
    const dialog = new frappe.ui.Dialog({
        title: `Execution Monitor: ${frm.doc.name}`,
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'execution_list',
                options: '<div id="execution-list"></div>'
            }
        ]
    });

    dialog.show();

    // Fetch recent executions
    frappe.call({
        method: 'workflow_automation.api.get_recent_executions',
        args: {
            workflow_id: frm.doc.name,
            limit: 20
        },
        callback: function(r) {
            if (r.message) {
                render_execution_list(r.message);
            }
        }
    });
}

function update_execution_status(frm, data) {
    // Update execution status in real-time
    frappe.show_alert({
        message: `Execution ${data.status}: ${data.execution_id}`,
        indicator: data.status === 'completed' ? 'green' : 'red'
    }, 5);
}
```

#### Example: Workflow Template Wizard

```javascript
// Client Script: Workflow template wizard
// Resource: Workflow
// EventBusEvent: onload

frappe.ui.form.on('Workflow', {
    onload: function(frm) {
        // Add wizard button for new workflows
        if (frm.is_new()) {
            frm.add_custom_button('Template Wizard', function() {
                open_template_wizard(frm);
            }, 'Setup');
        }
    }
});

function open_template_wizard(frm) {
    const steps = [
        {
            title: 'Workflow Type',
            fields: [
                {
                    fieldtype: 'Select',
                    fieldname: 'workflow_type',
                    label: 'Workflow Type',
                    options: ['data_processing', 'ai_automation', 'integration', 'custom'],
                    reqd: 1
                }
            ]
        },
        {
            title: 'Basic Configuration',
            fields: [
                {
                    fieldtype: 'Data',
                    fieldname: 'name',
                    label: 'Workflow Name',
                    reqd: 1
                },
                {
                    fieldtype: 'Small Text',
                    fieldname: 'description',
                    label: 'Description'
                }
            ]
        },
        {
            title: 'Trigger Configuration',
            fields: [
                {
                    fieldtype: 'Select',
                    fieldname: 'trigger_type',
                    label: 'Trigger Type',
                    options: ['manual', 'api', 'scheduled', 'event'],
                    reqd: 1
                }
            ]
        }
    ];

    const wizard = new frappe.ui.Wizard({
        title: 'Workflow Template Wizard',
        steps: steps,
        primary_action_label: 'Create Workflow',
        primary_action: function(values) {
            // Set form values
            Object.keys(values).forEach(key => {
                frm.set_value(key, values[key]);
            });

            // Load template definition
            load_template_definition(frm, values.workflow_type);

            // Close wizard
            wizard.hide();
        }
    });

    wizard.show();
}
```

---

## Webhooks

Webhooks allow external systems to be notified of workflow events. Webhooks are configured per tenant and can subscribe to specific event types.

### Available Events

| EventBusEvent Type | Description | Payload |
|------------|-------------|---------|
| `workflow.executed` | Workflow execution started | `{workflow_id, execution_id, tenant_id, user_id, input_data, timestamp}` |
| `workflow.completed` | Workflow execution completed successfully | `{workflow_id, execution_id, tenant_id, output_data, execution_time, timestamp}` |
| `workflow.failed` | Workflow execution failed | `{workflow_id, execution_id, tenant_id, error_message, timestamp}` |
| `workflow.step_completed` | Workflow step completed | `{workflow_id, execution_id, step_id, step_name, output_data, timestamp}` |
| `workflow.step_failed` | Workflow step failed | `{workflow_id, execution_id, step_id, step_name, error_message, timestamp}` |
| `workflow.created` | New workflow created | `{workflow_id, workflow_name, tenant_id, user_id, timestamp}` |
| `workflow.updated` | Workflow configuration updated | `{workflow_id, workflow_name, updates, tenant_id, user_id, timestamp}` |
| `workflow.activated` | Workflow activated | `{workflow_id, workflow_name, tenant_id, timestamp}` |
| `workflow.deactivated` | Workflow deactivated | `{workflow_id, workflow_name, tenant_id, timestamp}` |

### Webhook Configuration

Webhooks are configured through the Customization Framework API:

```python
# Create webhook for workflow execution events
POST /api/v1/webhooks
{
    "name": "Workflow Execution Notifier",
    "event_type": "workflow.completed",
    "url": "https://example.com/webhooks/workflow-completed",
    "method": "POST",
    "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
    },
    "tenant_id": "tenant-123",
    "is_active": true
}
```

### Example: Workflow Execution Completion Webhook

```python
# Webhook Handler: Process workflow execution completion
# EventBusEvent: workflow.completed
# URL: https://your-system.com/webhooks/workflow-completed

def handle_workflow_completed(payload):
    """Handle workflow execution completion webhook"""

    workflow_id = payload.get("workflow_id")
    execution_id = payload.get("execution_id")
    output_data = payload.get("output_data")

    # Process workflow output
    process_workflow_output(workflow_id, output_data)

    # Update external system
    update_external_system(workflow_id, execution_id, output_data)

    # Send notification
    send_notification(workflow_id, "Workflow execution completed")
```

### Example: Workflow Step Failure Alert Webhook

```python
# Webhook Handler: Alert on workflow step failures
# EventBusEvent: workflow.step_failed
# URL: https://your-system.com/webhooks/workflow-step-failed

def handle_workflow_step_failure(payload):
    """Handle workflow step failure webhook"""

    workflow_id = payload.get("workflow_id")
    step_name = payload.get("step_name")
    error_message = payload.get("error_message")

    # Send alert to monitoring system
    send_alert({
        "severity": "medium",
        "message": f"Workflow step '{step_name}' failed in workflow {workflow_id}",
        "error": error_message,
        "timestamp": payload.get("timestamp")
    })

    # Retry step if configured
    if should_retry_step(workflow_id, step_name):
        retry_workflow_step(workflow_id, step_name)
```

---

## Custom API Endpoints

Custom API endpoints can be created for workflow-specific operations that extend the standard API.

### Example: Batch Workflow Execution

```python
# Custom API Endpoint: Execute multiple workflows in batch
# Endpoint: POST /api/method/workflow_automation.api.batch_execute_workflows
# Method: POST

@frappe.whitelist(allow_guest=False)
def batch_execute_workflows(workflow_ids, input_data, options=None):
    """Execute multiple workflows in batch"""

    if not isinstance(workflow_ids, list):
        frappe.throw("workflow_ids must be a list")

    results = []

    for workflow_id in workflow_ids:
        try:
            # Get workflow
            workflow = frappe.get_doc("Workflow", workflow_id)

            # Validate access
            if not frappe.has_permission("Workflow", "read", workflow=workflow):
                results.append({
                    "workflow_id": workflow_id,
                    "status": "error",
                    "error": "Permission denied"
                })
                continue

            # Execute workflow
            from src.modules.workflow_automation.services.workflow_service import WorkflowService
            service = WorkflowService(frappe.db)

            execute_data = {
                "input_data": input_data,
                "options": options or {}
            }

            execution = service.execute_workflow(
                workflow_id=workflow_id,
                tenant_id=workflow.tenant_id,
                execute_data=execute_data,
                user_id=frappe.session.user
            )

            results.append({
                "workflow_id": workflow_id,
                "execution_id": execution.id,
                "status": execution.status,
                "output_data": execution.output_data
            })

        except Exception as e:
            results.append({
                "workflow_id": workflow_id,
                "status": "error",
                "error": str(e)
            })

    return {
        "total": len(workflow_ids),
        "results": results
    }
```

### Example: Workflow Comparison API

```python
# Custom API Endpoint: Compare workflow performance
# Endpoint: GET /api/method/workflow_automation.api.compare_workflows
# Method: GET

@frappe.whitelist(allow_guest=False)
def compare_workflows(workflow_ids, start_date=None, end_date=None):
    """Compare performance of multiple workflows"""

    if not isinstance(workflow_ids, list) or len(workflow_ids) < 2:
        frappe.throw("At least 2 workflow IDs required for comparison")

    comparison = []

    for workflow_id in workflow_ids:
        workflow = frappe.get_doc("Workflow", workflow_id)

        # Get workflow analytics
        analytics = get_workflow_analytics(workflow_id, start_date, end_date)

        comparison.append({
            "workflow_id": workflow_id,
            "workflow_name": workflow.name,
            "trigger_type": workflow.trigger_type,
            "analytics": analytics
        })

    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date
        },
        "comparison": comparison
    }
```

### Example: Workflow Template API

```python
# Custom API Endpoint: Create workflow from template
# Endpoint: POST /api/method/workflow_automation.api.create_from_template
# Method: POST

@frappe.whitelist(allow_guest=False)
def create_from_template(template_id, name, customizations=None):
    """Create workflow from template with customizations"""

    # Get template
    template = frappe.get_doc("WorkflowTemplate", template_id)

    # Validate access
    if not template.is_public and template.tenant_id != frappe.session.user.tenant_id:
        frappe.throw("Permission denied", frappe.PermissionError)

    # Create workflow from template
    workflow_data = {
        "name": name,
        "description": template.description,
        "trigger_type": template.trigger_type,
        "definition": template.definition,
        "nodes": template.nodes,
        "edges": template.edges
    }

    # Apply customizations
    if customizations:
        workflow_data = apply_template_customizations(workflow_data, customizations)

    # Create workflow
    from src.modules.workflow_automation.services.workflow_service import WorkflowService
    service = WorkflowService(frappe.db)

    workflow = service.create_workflow(
        workflow_data=workflow_data,
        tenant_id=frappe.session.user.tenant_id,
        user_id=frappe.session.user.id
    )

    return {
        "workflow_id": workflow.id,
        "workflow_name": workflow.name,
        "template_id": template_id
    }
```

---

## EventBusEvent Bus Integration

Workflow events are automatically published to the SARAISE EventBusEvent Bus, allowing other modules and customizations to subscribe to workflow events. The EventBusEvent Bus uses Redis pub/sub for distributed event communication and supports both tenant-scoped and global events.

### EventBusEvent Types

The following workflow events are published to the EventBusEvent Bus:

| EventBusEvent Type | Description | When Published |
|------------|-------------|----------------|
| `workflow.started` | Workflow execution started | When workflow execution begins |
| `workflow.completed` | Workflow execution completed successfully | When workflow execution completes successfully |
| `workflow.failed` | Workflow execution failed | When workflow execution fails with error |
| `workflow.step_completed` | Workflow step completed | When individual workflow step completes |

### Publishing Events from Services

When extending the Workflow Automation service, you can publish custom events:

```python
# In workflow_service.py or custom server script
from src.core.event_bus import event_bus, EventType

# Publish workflow started event
await event_bus.publish(
    event_type=EventType.WORKFLOW_STARTED,
    data={
        "workflow_id": workflow.id,
        "execution_id": execution.id,
        "input_data": input_data,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)

# Publish workflow completed event
await event_bus.publish(
    event_type=EventType.WORKFLOW_COMPLETED,
    data={
        "workflow_id": workflow.id,
        "execution_id": execution.id,
        "output_data": output_data,
        "execution_time": execution_time,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)

# Publish workflow failed event
await event_bus.publish(
    event_type=EventType.WORKFLOW_FAILED,
    data={
        "workflow_id": workflow.id,
        "execution_id": execution.id,
        "error_message": str(error),
        "error_type": type(error).__name__,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)

# Publish workflow step completed event
await event_bus.publish(
    event_type=EventType.WORKFLOW_STEP_COMPLETED,
    data={
        "workflow_id": workflow.id,
        "execution_id": execution.id,
        "step_id": step.id,
        "step_name": step.name,
        "output_data": step_output,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)
```

### Subscribing to Workflow Events

#### Using EventBusEvent System (Recommended)

```python
# Server Script: Subscribe to workflow events using EventBusEvent System
from src.core.event_bus import event_bus, EventType

# Subscribe to workflow execution events
event_bus.subscribe(
    EventType.WORKFLOW_STARTED,
    handle_workflow_started
)

event_bus.subscribe(
    EventType.WORKFLOW_COMPLETED,
    handle_workflow_completed
)

event_bus.subscribe(
    EventType.WORKFLOW_FAILED,
    handle_workflow_failed
)

event_bus.subscribe(
    EventType.WORKFLOW_STEP_COMPLETED,
    handle_workflow_step_completed
)

async def handle_workflow_started(event):
    """Handle workflow execution started event"""
    workflow_id = event.data.get("workflow_id")
    execution_id = event.data.get("execution_id")
    tenant_id = event.tenant_id

    # Log execution start
    logger.info(f"Workflow {workflow_id} execution started: {execution_id} for tenant {tenant_id}")

    # Trigger custom logic
    await process_workflow_execution_start(workflow_id, execution_id, tenant_id)

async def handle_workflow_completed(event):
    """Handle workflow execution completed event"""
    workflow_id = event.data.get("workflow_id")
    output_data = event.data.get("output_data")
    tenant_id = event.tenant_id

    # Process completed execution
    await process_completed_workflow(workflow_id, output_data, tenant_id)

async def handle_workflow_failed(event):
    """Handle workflow execution failed event"""
    workflow_id = event.data.get("workflow_id")
    error_message = event.data.get("error_message")
    tenant_id = event.tenant_id

    # Send failure notification
    await send_failure_notification(workflow_id, error_message, tenant_id)

async def handle_workflow_step_completed(event):
    """Handle workflow step completed event"""
    step_name = event.data.get("step_name")
    output_data = event.data.get("output_data")
    tenant_id = event.tenant_id

    # Process step output
    await process_step_output(step_name, output_data, tenant_id)
```

#### Using EventBusEvent Bus Directly (Advanced)

For more control, you can subscribe directly to the EventBusEvent Bus:

```python
# Server Script: Direct EventBusEvent Bus subscription
from src.core.event_bus import event_bus, EventBusEvent

async def handle_workflow_event(event: EventBusEvent):
    """Handle workflow event from EventBusEvent Bus"""
    event_type = event.event_type
    data = event.data
    tenant_id = event.tenant_id

    if event_type == "workflow.started":
        # Handle workflow execution started
        await process_workflow_execution(data, tenant_id)
    elif event_type == "workflow.completed":
        # Handle workflow execution completed
        await process_workflow_completion(data, tenant_id)
    elif event_type == "workflow.failed":
        # Handle workflow execution failed
        await process_workflow_failure(data, tenant_id)
    elif event_type == "workflow.step_completed":
        # Handle workflow step completed
        await process_workflow_step_completion(data, tenant_id)

# Subscribe to all workflow events for specific tenant
await event_bus.subscribe(
    event_type="workflow.*",  # Wildcard subscription
    handler=handle_workflow_event,
    tenant_id="tenant-123"  # Tenant-scoped subscription
)

# Subscribe to specific event type globally
await event_bus.subscribe(
    event_type="workflow.completed",
    handler=handle_workflow_event,
    use_global=True  # Global subscription
)
```

### Integration with Customization Framework

The EventBusEvent Bus integrates seamlessly with the Customization Framework:

#### Webhooks Triggered by Events

Webhooks can be configured to trigger on workflow events:

```python
# Webhook Configuration
# EventBusEvent: workflow.completed
# URL: https://your-system.com/webhooks/workflow-completed

def handle_workflow_completed_webhook(payload):
    """Webhook handler for workflow completion events"""
    workflow_id = payload.get("workflow_id")
    output_data = payload.get("output_data")

    # Process webhook payload
    process_webhook_payload(workflow_id, output_data)
```

#### Server Scripts Subscribing to Events

Server scripts can subscribe to events for custom processing:

```python
# Server Script: Custom workflow analytics on completion
# EventBusEvent: workflow.completed
# Script Type: Scheduled (runs on event)

def process_workflow_analytics(event):
    """Process workflow analytics when workflow completes"""
    workflow_id = event.data.get("workflow_id")
    execution_time = event.data.get("execution_time")

    # Update workflow analytics
    update_workflow_analytics(workflow_id, execution_time)
```

### Tenant-Scoped vs Global Events

Events can be published as tenant-scoped or global:

```python
# Tenant-scoped event (default)
await event_bus.publish(
    event_type=EventType.WORKFLOW_STARTED,
    data={"workflow_id": "workflow-123"},
    tenant_id="tenant-456"  # Only subscribers for this tenant receive event
)

# Global event (cross-tenant)
await event_bus.publish(
    event_type="workflow.started",
    data={"workflow_id": "workflow-123"},
    use_global=True  # All subscribers receive event
)
```

### EventBusEvent Payload Structure

```python
# Workflow Executed EventBusEvent
{
    "event_type": "workflow.executed",
    "data": {
        "workflow_id": "workflow-123",
        "execution_id": "execution-456",
        "tenant_id": "tenant-789",
        "user_id": "user-abc",
        "input_data": {...},
        "timestamp": "2025-01-15T10:30:00Z"
    },
    "tenant_id": "tenant-789",
    "user_id": "user-abc"
}

# Workflow Completed EventBusEvent
{
    "event_type": "workflow.completed",
    "data": {
        "workflow_id": "workflow-123",
        "execution_id": "execution-456",
        "tenant_id": "tenant-789",
        "output_data": {...},
        "execution_time": 5.2,
        "timestamp": "2025-01-15T10:30:05Z"
    },
    "tenant_id": "tenant-789"
}

# Workflow Step Completed EventBusEvent
{
    "event_type": "workflow.step_completed",
    "data": {
        "workflow_id": "workflow-123",
        "execution_id": "execution-456",
        "step_id": "step-789",
        "step_name": "data_transformation",
        "output_data": {...},
        "timestamp": "2025-01-15T10:30:03Z"
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
5. **Step Execution**: Ensure custom steps are idempotent and can handle retries

### Client Scripts

1. **User Experience**: Provide immediate feedback for user actions
2. **Validation**: Use client-side validation for better UX, but always validate on server
3. **Real-time Updates**: Use WebSocket events for real-time execution status updates
4. **Error Handling**: Show user-friendly error messages
5. **Workflow Builder**: Provide visual feedback in workflow builder UI

### Webhooks

1. **Idempotency**: Design webhook handlers to be idempotent
2. **Retry Logic**: Implement retry logic for failed webhook deliveries
3. **Security**: Validate webhook signatures and use HTTPS
4. **Rate Limiting**: Respect rate limits when calling external APIs
5. **Step Events**: Consider subscribing to step-level events for granular monitoring

### Custom API Endpoints

1. **Authentication**: Always use `@frappe.whitelist(allow_guest=False)` for authenticated endpoints
2. **Permission Checks**: Validate user permissions before processing
3. **Input Validation**: Validate and sanitize all input data
4. **Error Responses**: Return consistent error response format
5. **Batch Operations**: Consider rate limiting for batch operations

---

## Examples Repository

For more examples, see:
- `backend/scripts/demo_customizations/workflow_automation/` - Demo customization examples
- [Customization Framework Examples](../../01-foundation/customization-framework/README.md#examples)

---

## Support

For questions or issues with Workflow Automation customizations:
- Review [Customization Framework Documentation](../../01-foundation/customization-framework/README.md)
- Check [EventBusEvent System Documentation](../../../architecture/11-event-system.md)
- Contact the development team


## Integrations

<!-- SPDX-License-Identifier: Apache-2.0 -->
# Workflow Automation Frontend - Integration Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-01
**Status:** Integration Reference
**Development Agent:** Agent 64

---

This document describes all integration points for the Workflow Automation Frontend module, including internal module integrations, external system integrations, and webhook events.

---

## Integration Overview

The Workflow Automation Frontend module integrates with:

- **Internal Modules**: [List of SARAISE modules]
- **External Systems**: [List of external systems]
- **Third-Party APIs**: [List of APIs]

---

## Internal Module Integration

### Integration Matrix

| Module | Integration Type | Data Flow | Trigger | Frequency |
|--------|------------------|-----------|---------|-----------|
| [Module] | API/EventBusEvent/Shared Data | [Direction] | [Trigger] | Real-time/Batch |

### Integration: [Module Name]

**Type:** [API/EventBusEvent/Shared Data]
**Purpose:** [Why this integration exists]

**Data Flow:**
```
[Module] → [This Module] → [Action]
```

**Implementation:**
```python
# Integration code example
from src.modules.[module] import [Service]

async def integrate_with_[module](data):
    """Integration logic"""
    pass
```

**Configuration:**
```json
{
  "module": "[module_name]",
  "type": "[type]",
  "enabled": true
}
```

[Repeat for all internal integrations]

---

## External System Integration

### Integration Matrix

| System | Protocol | Purpose | Authentication | Status |
|--------|----------|---------|----------------|--------|
| [System] | REST/SOAP/Webhook | [Purpose] | OAuth/API Key | Active/Planned |

### Integration: [System Name]

**Protocol:** REST/SOAP/Webhook
**Purpose:** [What this integration does]
**Status:** Active/Planned

**Authentication:**
- **Method:** OAuth 2.0 / API Key
- **Credentials:** Stored in Vault
- **Refresh:** Automatic / Manual

**API Endpoints:**
- **GET** `https://api.example.com/v1/resource`
  - **Purpose:** [What it does]
  - **Request:**
  ```json
  {
    "param1": "value1"
  }
  ```
  - **Response:**
  ```json
  {
    "data": [...]
  }
  ```

**Error Handling:**
- **401**: Unauthorized - Refresh token
- **429**: Rate limited - Retry with backoff
- **500**: Server error - Log and alert

**Configuration:**
```json
{
  "system": "[system_name]",
  "base_url": "https://api.example.com",
  "auth": {
    "type": "oauth2",
    "credentials": "[stored in vault]"
  }
}
```

[Repeat for all external integrations]

---

## Webhook Events

### Outgoing Webhooks

| EventBusEvent | Payload | Use Case | Recipient |
|-------|---------|----------|-----------|
| [event.created] | [Payload structure] | [Use case] | [System] |

#### Webhook: [event.name]

**Description:** [What this webhook notifies]
**Trigger:** [When it fires]
**Payload:**
```json
{
  "event": "[event.name]",
  "timestamp": "[ISO 8601]",
  "data": {
    "id": "[resource_id]",
    "type": "[resource_type]",
    "changes": {...}
  }
}
```

**Security:**
- **Signature:** HMAC-SHA256
- **Verification:** [How recipient verifies]
- **Retry:** 3 attempts with exponential backoff

[Repeat for all outgoing webhooks]

### Incoming Webhooks

| EventBusEvent | Endpoint | Handler | Use Case |
|-------|----------|---------|----------|
| [event.name] | `/api/v1/workflow-automation/webhooks/[path]` | [Handler function] | [Use case] |

#### Webhook Endpoint: [path]

**EventBusEvent:** [event.name]
**Method:** POST
**Authentication:** API Key / Signature

**Request:**
```json
{
  "event": "[event.name]",
  "data": {...}
}
```

**Handler:**
```python
@router.post("/webhooks/[path]")
async def handle_webhook(payload: dict):
    """Handle incoming webhook"""
    # Handler logic
    pass
```

**Response:**
```json
{
  "status": "success",
  "message": "Webhook processed"
}
```

[Repeat for all incoming webhooks]

---

## Data Synchronization

### Sync Strategies

#### Strategy: Real-time Sync
**Type:** EventBusEvent-driven
**Frequency:** Immediate
**Direction:** Bidirectional
**Conflict Resolution:** Last-write-wins / Manual resolution

**Implementation:**
```python
async def sync_realtime(event):
    """Real-time synchronization"""
    # Sync logic
    pass
```

#### Strategy: Batch Sync
**Type:** Scheduled
**Frequency:** Daily/Hourly
**Direction:** Unidirectional
**Conflict Resolution:** Source system wins

**Implementation:**
```python
async def sync_batch():
    """Batch synchronization"""
    # Sync logic
    pass
```

---

## Integration Testing

### Test Scenarios

#### Scenario 1: [Integration Name] - [Test Name]
**Integration:** [System/Module]
**Setup:** [Initial state]
**Steps:**
1. [Step 1]
2. [Step 2]
**Expected Result:** [What should happen]
**Validation:** [How to verify]

[Repeat for all integration scenarios]

---

## Troubleshooting

### Common Issues

#### Issue: Authentication Failures
**Symptoms:** 401 errors, token expired
**Cause:** Expired credentials, invalid tokens
**Solution:** Refresh credentials, verify token validity
**Prevention:** Automatic token refresh, monitoring

#### Issue: Rate Limiting
**Symptoms:** 429 errors, throttling
**Cause:** Exceeding API rate limits
**Solution:** Implement backoff, reduce request frequency
**Prevention:** Rate limit monitoring, request queuing

---

**Last Updated:** 2025-12-01
**License:** Apache-2.0


## Demo Data

<!-- SPDX-License-Identifier: Apache-2.0 -->
# Workflow Automation Frontend - Demo Data

**Version:** 1.0.0
**Last Updated:** 2025-12-01
**Status:** Demo Data Reference
**Development Agent:** Agent 64

---

This document describes the comprehensive demo data included with the Workflow Automation Frontend module for testing and training purposes.

## Overview

The demo data seed script (`backend/scripts/seed_workflow-automation_demo.py`) creates a fully functional Workflow Automation Frontend setup for the demo tenant `demo@saraise.com` with:

- [Number] [entities] (e.g., 10 customers, 5 products)
- [Number] [entities]
- [Number] [entities]

---

## Sample Data Sets

### Basic Demo (10 records)

**Purpose:** Minimal data for quick demos and initial testing.

**Includes:**
- [Entity type 1]: [Number] records
- [Entity type 2]: [Number] records
- [Entity type 3]: [Number] records

**Usage:**
```bash
python backend/scripts/seed_workflow-automation_demo.py --size basic
```

### Full Demo (100+ records)

**Purpose:** Comprehensive data for thorough testing, training, and demonstrations.

**Includes:**
- [Entity type 1]: [Number] records
- [Entity type 2]: [Number] records
- [Entity type 3]: [Number] records
- [Entity type 4]: [Number] records

**Usage:**
```bash
python backend/scripts/seed_workflow-automation_demo.py --size full
```

---

## Demo Data Structure

### Entity 1: [Name]

**Count:** [Number]
**Purpose:** [What this entity represents]

**Sample Record:**

```json
{
  "id": "[id]",
  "name": "[Name]",
  "field1": "[value]",
  "field2": "[value]"
}
```

**Key Fields:**
| Field | Value | Description |
|-------|-------|-------------|
| [field] | [value] | [description] |

[Repeat for all entity types]

---

## Relationships & Dependencies

The demo data includes realistic relationships between entities:

- **[Entity A]** → **[Entity B]**: [How they relate]
- **[Entity B]** → **[Entity C]**: [How they relate]

### Data Dependency Order

The following order ensures all dependencies are created correctly:

1. [Base entity] (no dependencies)
2. [Dependent entity 1] (depends on step 1)
3. [Dependent entity 2] (depends on steps 1-2)

---

## Data Generation Scripts

### Main Seed Script

**File:** `backend/scripts/seed_workflow-automation_demo.py`

**Usage:**
```bash
# Basic demo
python backend/scripts/seed_workflow-automation_demo.py --size basic --tenant demo@saraise.com

# Full demo
python backend/scripts/seed_workflow-automation_demo.py --size full --tenant demo@saraise.com

# Custom count
python backend/scripts/seed_workflow-automation_demo.py --count 50 --tenant demo@saraise.com
```

**Options:**
- `--size`: `basic` or `full` (default: `basic`)
- `--count`: Custom number of records per entity
- `--tenant`: Tenant ID or email (default: `demo@saraise.com`)
- `--reset`: Clear existing demo data before seeding

### Helper Functions

#### `generate_workflow-automation_data(count)`
**Purpose:** Generate [entity type] records
**Parameters:**
- `count` (int): Number of records to generate

```python
def generate_workflow-automation_data(count: int):
    """Generate demo data"""
    # Implementation
    pass
```

---

## Sample Data Examples

### Example 1: [Entity Name]

**Type:** [Resource Type]
**Description:** [What this example demonstrates]

**Data:**
```json
{
  "name": "Example Record",
  "field1": "value1",
  "field2": "value2"
}
```

**Use Case:** [When to use this example]

[Repeat for key examples]

---

## Reset Instructions

### Clearing Demo Data

**Method 1: Using Script**
```bash
python backend/scripts/seed_workflow-automation_demo.py --reset --tenant demo@saraise.com
```

**Method 2: Manual Deletion**
1. Delete dependent entities first
2. Delete base entities
3. Verify all data cleared

### Verification

After reset, verify:
- [ ] All demo records deleted
- [ ] No orphaned relationships
- [ ] Database constraints satisfied

---

## Testing Scenarios

### Scenario 1: Basic Functionality

**Data Required:** Basic demo set
**Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

### Scenario 2: Advanced Features

**Data Required:** Full demo set
**Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

---

## Data Quality Standards

### Realistic Data
- All data values are realistic and representative
- Relationships follow business logic
- Dates are within valid ranges

### Completeness
- All required fields populated
- No null values in critical fields
- Relationships properly linked

### Consistency
- Naming conventions followed
- Data formats consistent
- Business rules validated

---

## Customization

### Extending Demo Data

To add custom demo data:

1. **Create Custom Seed Function:**
```python
def generate_custom_data():
    """Generate custom demo data"""
    # Your custom logic
    pass
```

2. **Add to Seed Script:**
```python
if __name__ == "__main__":
    # ... existing code ...
    generate_custom_data()
```

3. **Run:**
```bash
python backend/scripts/seed_workflow-automation_demo.py --custom
```

---

**Last Updated:** 2025-12-01
**License:** Apache-2.0

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
