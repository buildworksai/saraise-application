<!-- SPDX-License-Identifier: Apache-2.0 -->
# AI Agent Management - Customization Guide

**Module**: `ai_agent_management`
**Category**: AI Automation
**Version**: 1.0.0

---

## Overview

The AI Agent Management module supports extensive customization through the SARAISE Customization Framework. This guide documents all customization points, including server scripts, client scripts, webhooks, and custom API endpoints.

**Related Documentation**:
- [Customization Framework](../../01-foundation/customization-framework/README.md) - Complete customization framework documentation
- [EventBusEvent System](../../../architecture/11-event-system.md) - EventBusEvent-driven architecture patterns

---

## Server Scripts

Server scripts allow you to customize AI agent behavior on the backend without modifying core code. Scripts run in a sandboxed environment with full access to the SARAISE API.

### Model Scripts

Server scripts can be attached to the `AIAgent` Model to customize agent lifecycle events.

#### Available Events

| Event | Trigger | Use Case |
|-------|---------|----------|
| `before_insert` | Before agent is created | Validate agent configuration, set default values |
| `after_insert` | After agent is created | Initialize agent resources, send notifications |
| `before_validate` | Before validation runs | Custom validation logic |
| `validate` | During validation | Additional business rule validation |
| `before_save` | Before any save operation | Auto-calculate fields, transform data |
| `after_save` | After save operation | Update related records, trigger workflows |
| `before_submit` | Before agent activation | Final validation, resource checks |
| `after_submit` | After agent activated | Start background processes, notifications |
| `before_cancel` | Before agent deactivation | Check dependencies, cleanup validation |
| `after_cancel` | After agent deactivated | Cleanup resources, archive data |
| `before_delete` | Before agent deletion | Check for active executions, dependencies |
| `on_trash` | When agent moved to trash | Soft delete handling |

#### Example: Custom Agent Validation

```python
# Server Script: Custom agent validation
# EventBusEvent: validate
# Resource: AIAgent

def validate(doc, method):
    """Custom validation for AI agent configuration"""

    # Validate OpenAI API key format if agent type is OpenAI
    if doc.agent_type == "openai":
        config = doc.configuration or {}
        api_key_ref = config.get("api_key_ref")

        if not api_key_ref:
            frappe.throw("OpenAI agents require api_key_ref in configuration")

        # Verify secret exists
        try:
            secrets_manager = frappe.get_doc("Secrets Manager")
            secret = secrets_manager.get_secret(api_key_ref, doc.tenant_id)
            if not secret:
                frappe.throw(f"Secret reference '{api_key_ref}' not found")
        except Exception as e:
            frappe.throw(f"Invalid secret reference: {str(e)}")

    # Validate system prompt length
    if doc.system_prompt and len(doc.system_prompt) > 10000:
        frappe.throw("System prompt cannot exceed 10,000 characters")

    # Validate agent name uniqueness within tenant
    existing = frappe.db.get_value(
        "AIAgent",
        {"name": ["!=", doc.name], "tenant_id": doc.tenant_id, "name": doc.name},
        "name"
    )
    if existing:
        frappe.throw(f"Agent with name '{doc.name}' already exists in this tenant")
```

#### Example: Auto-Configure Agent on Creation

```python
# Server Script: Auto-configure agent settings
# EventBusEvent: after_insert
# Resource: AIAgent

def after_insert(doc, method):
    """Auto-configure agent after creation"""

    # Set default configuration if not provided
    if not doc.configuration:
        doc.configuration = {}

    # Set default model based on agent type
    if doc.agent_type == "openai":
        if "model" not in doc.configuration:
            doc.configuration["model"] = "gpt-4"
        if "temperature" not in doc.configuration:
            doc.configuration["temperature"] = 0.7
        if "max_tokens" not in doc.configuration:
            doc.configuration["max_tokens"] = 2000

    # Set default status
    if not doc.status:
        doc.status = "draft"

    # Save configuration
    doc.save()

    # Log agent creation
    frappe.log_error(
        f"Agent '{doc.name}' created for tenant '{doc.tenant_id}'",
        "Agent Created"
    )
```

#### Example: Custom Agent Execution Logic

```python
# Server Script: Custom agent execution preprocessing
# EventBusEvent: before_submit
# Resource: AIAgent

def before_submit(doc, method):
    """Validate agent is ready for activation"""

    # Check if agent has required tools configured
    if doc.agent_type == "crewai":
        tools = doc.configuration.get("tools", [])
        if not tools:
            frappe.throw("CrewAI agents require at least one tool to be configured")

    # Verify API credentials are valid
    if doc.agent_type in ["openai", "langgraph"]:
        config = doc.configuration or {}
        api_key_ref = config.get("api_key_ref")

        if api_key_ref:
            # Test API key by making a test call
            try:
                # This would call a test endpoint to verify credentials
                # Implementation depends on agent type
                pass
            except Exception as e:
                frappe.throw(f"API credentials validation failed: {str(e)}")

    # Check tenant subscription limits
    agent_count = frappe.db.count("AIAgent", {
        "tenant_id": doc.tenant_id,
        "status": ["in", ["active", "running"]]
    })

    max_agents = frappe.db.get_value(
        "Subscription Plan",
        {"tenant_id": doc.tenant_id},
        "max_agents"
    ) or 10

    if agent_count >= max_agents:
        frappe.throw(f"Tenant has reached maximum agent limit ({max_agents})")
```

#### Example: Post-Execution Processing

```python
# Server Script: Process agent execution results
# EventBusEvent: Custom (triggered via webhook or scheduled script)
# Resource: AIAgentWorkflow

def process_agent_execution(workflow_id):
    """Process completed agent execution"""

    workflow = frappe.get_doc("AIAgentWorkflow", workflow_id)

    if workflow.status != "completed":
        return

    # Extract output data
    output_data = workflow.output_data or {}

    # Store execution metrics
    metrics = {
        "execution_time": workflow.duration,
        "input_tokens": output_data.get("usage", {}).get("prompt_tokens", 0),
        "output_tokens": output_data.get("usage", {}).get("completion_tokens", 0),
        "total_tokens": output_data.get("usage", {}).get("total_tokens", 0),
    }

    # Create performance log
    frappe.get_doc({
        "resource_type": "AIAgentMetric",
        "agent_id": workflow.agent_id,
        "workflow_id": workflow_id,
        "tenant_id": workflow.tenant_id,
        "execution_time": metrics["execution_time"],
        "input_tokens": metrics["input_tokens"],
        "output_tokens": metrics["output_tokens"],
        "total_tokens": metrics["total_tokens"],
        "timestamp": workflow.completed_at,
    }).insert()

    # Update agent statistics
    agent = frappe.get_doc("AIAgent", workflow.agent_id)
    agent.total_executions += 1
    agent.total_tokens_used = (agent.total_tokens_used or 0) + metrics["total_tokens"]
    agent.save()
```

### API Scripts

Custom API endpoints can be created for agent-specific operations.

#### Example: Custom Agent Execution Endpoint

```python
# API Script: Custom agent execution with preprocessing
# Endpoint: POST /api/method/ai_agent_management.api.custom_execute_agent
# Method: POST

@frappe.whitelist(allow_guest=False)
def custom_execute_agent(agent_id, input_data, options=None):
    """Custom agent execution with additional preprocessing"""

    # Get agent
    agent = frappe.get_doc("AIAgent", agent_id)

    # Validate agent access
    if not frappe.has_permission("AIAgent", "read", agent=agent):
        frappe.throw("Permission denied", frappe.PermissionError)

    # Preprocess input data
    processed_input = preprocess_agent_input(input_data, agent)

    # Execute agent via service
    from src.modules.ai_agent_management.services.agent_service import AgentService
    service = AgentService(frappe.db)

    execute_data = {
        "input_data": processed_input,
        "options": options or {}
    }

    workflow = service.execute_agent(
        agent_id=agent_id,
        tenant_id=agent.tenant_id,
        execute_data=execute_data,
        user_id=frappe.session.user
    )

    # Post-process results
    result = postprocess_agent_output(workflow.output_data, agent)

    return {
        "workflow_id": workflow.id,
        "status": workflow.status,
        "result": result,
        "execution_time": workflow.duration
    }

def preprocess_agent_input(input_data, agent):
    """Preprocess input data based on agent configuration"""
    # Add agent context
    processed = {
        "input": input_data,
        "agent_name": agent.name,
        "agent_type": agent.agent_type,
        "timestamp": frappe.utils.now()
    }

    # Add system context if configured
    if agent.configuration.get("include_context"):
        processed["context"] = get_agent_context(agent)

    return processed

def postprocess_agent_output(output_data, agent):
    """Post-process agent output"""
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

#### Example: Agent Performance Analytics

```python
# API Script: Get agent performance analytics
# Endpoint: GET /api/method/ai_agent_management.api.get_agent_analytics
# Method: GET

@frappe.whitelist(allow_guest=False)
def get_agent_analytics(agent_id, start_date=None, end_date=None):
    """Get comprehensive agent performance analytics"""

    agent = frappe.get_doc("AIAgent", agent_id)

    # Validate access
    if not frappe.has_permission("AIAgent", "read", agent=agent):
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
            SUM(input_length) as total_input_length,
            SUM(output_length) as total_output_length,
            SUM(total_tokens) as total_tokens_used
        FROM `tabAIAgentWorkflow`
        WHERE agent_id = %s
          AND created_at BETWEEN %s AND %s
    """, (agent_id, start_date, end_date), as_dict=True)[0]

    # Calculate success rate
    success_rate = (
        (metrics.successful_executions / metrics.total_executions * 100)
        if metrics.total_executions > 0 else 0
    )

    # Get token usage by model (if available)
    token_usage = frappe.db.sql("""
        SELECT
            JSON_EXTRACT(output_data, '$.model') as model,
            SUM(total_tokens) as tokens_used,
            COUNT(*) as execution_count
        FROM `tabAIAgentMetric`
        WHERE agent_id = %s
          AND timestamp BETWEEN %s AND %s
        GROUP BY model
    """, (agent_id, start_date, end_date), as_dict=True)

    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
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
            "total_input_length": metrics.total_input_length or 0,
            "total_output_length": metrics.total_output_length or 0
        },
        "token_usage": {
            "total_tokens": metrics.total_tokens_used or 0,
            "by_model": token_usage
        }
    }
```

### Scheduled Scripts

Scheduled scripts can be used for agent maintenance, monitoring, and cleanup tasks.

#### Example: Agent Health Monitoring

```python
# Scheduled Script: Monitor agent health
# Frequency: Every 15 minutes
# Cron: */15 * * * *

def monitor_agent_health():
    """Monitor agent health and send alerts"""

    # Get all active agents
    active_agents = frappe.get_all(
        "AIAgent",
        filters={"status": "active"},
        fields=["name", "tenant_id", "agent_type", "last_execution_at"]
    )

    for agent in active_agents:
        # Check if agent has executed recently (within last hour)
        if agent.last_execution_at:
            last_execution = frappe.utils.get_datetime(agent.last_execution_at)
            hours_since_execution = (
                frappe.utils.now_datetime() - last_execution
            ).total_seconds() / 3600

            # Alert if no execution in 24 hours for active agent
            if hours_since_execution > 24:
                send_agent_inactivity_alert(agent)

        # Check for recent failures
        recent_failures = frappe.db.count("AIAgentWorkflow", {
            "agent_id": agent.name,
            "status": "failed",
            "created_at": [">", frappe.utils.add_hours(frappe.utils.now(), -1)]
        })

        if recent_failures >= 5:
            send_agent_failure_alert(agent, recent_failures)

def send_agent_inactivity_alert(agent):
    """Send alert for inactive agent"""
    frappe.sendmail(
        recipients=get_tenant_admins(agent.tenant_id),
        subject=f"Agent Inactivity Alert: {agent.name}",
        message=f"""
            Agent '{agent.name}' has not executed in the last 24 hours.

            Consider checking:
            - Agent configuration
            - API credentials
            - Trigger conditions
        """
    )

def send_agent_failure_alert(agent, failure_count):
    """Send alert for agent failures"""
    frappe.sendmail(
        recipients=get_tenant_admins(agent.tenant_id),
        subject=f"Agent Failure Alert: {agent.name}",
        message=f"""
            Agent '{agent.name}' has failed {failure_count} times in the last hour.

            Please review:
            - Agent logs
            - Configuration
            - API credentials
            - Input data format
        """
    )
```

#### Example: Cleanup Old Executions

```python
# Scheduled Script: Cleanup old agent executions
# Frequency: Daily at 2 AM
# Cron: 0 2 * * *

def cleanup_old_executions():
    """Archive and cleanup old agent executions"""

    # Archive executions older than 90 days
    cutoff_date = frappe.utils.add_days(frappe.utils.today(), -90)

    old_executions = frappe.get_all(
        "AIAgentWorkflow",
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
        frappe.delete_doc("AIAgentWorkflow", execution.name, force=1)

    frappe.log_error(
        f"Cleaned up {len(old_executions)} old agent executions",
        "Agent Cleanup"
    )
```

---

## Client Scripts

Client scripts run in the browser and customize the AI agent management UI behavior.

### Form Events

Client scripts can be attached to the `AIAgent` form to customize UI behavior.

#### Example: Dynamic Configuration UI

```javascript
// Client Script: Dynamic agent configuration UI
// Resource: AIAgent
// EventBusEvent: onload

frappe.ui.form.on('AIAgent', {
    onload: function(frm) {
        // Show/hide fields based on agent type
        setup_agent_type_fields(frm);

        // Setup tool selector
        setup_tool_selector(frm);

        // Setup API key reference selector
        setup_api_key_selector(frm);
    },

    agent_type: function(frm) {
        // Update UI when agent type changes
        update_agent_type_fields(frm);
    },

    validate: function(frm) {
        // Client-side validation
        if (!frm.doc.name) {
            frappe.msgprint('Agent name is required');
            validated = false;
        }

        if (frm.doc.agent_type === 'openai' && !frm.doc.configuration?.api_key_ref) {
            frappe.msgprint('OpenAI agents require API key reference');
            validated = false;
        }
    }
});

function setup_agent_type_fields(frm) {
    // Hide all type-specific fields initially
    frm.toggle_display('openai_config', false);
    frm.toggle_display('crewai_config', false);
    frm.toggle_display('langgraph_config', false);

    // Show relevant fields based on agent type
    update_agent_type_fields(frm);
}

function update_agent_type_fields(frm) {
    const agent_type = frm.doc.agent_type;

    // Hide all config sections
    frm.toggle_display('openai_config', false);
    frm.toggle_display('crewai_config', false);
    frm.toggle_display('langgraph_config', false);

    // Show relevant config section
    if (agent_type === 'openai') {
        frm.toggle_display('openai_config', true);
    } else if (agent_type === 'crewai') {
        frm.toggle_display('crewai_config', true);
    } else if (agent_type === 'langgraph') {
        frm.toggle_display('langgraph_config', true);
    }
}

function setup_tool_selector(frm) {
    // Custom tool selector with search
    frm.set_query('tools', 'agent_tools', function() {
        return {
            filters: {
                'is_active': 1,
                'agent_type': frm.doc.agent_type
            }
        };
    });
}

function setup_api_key_selector(frm) {
    // API key reference selector
    frm.set_query('api_key_ref', function() {
        return {
            filters: {
                'tenant_id': frm.doc.tenant_id,
                'secret_type': 'api_key'
            }
        };
    });
}
```

#### Example: Real-time Agent Execution Monitoring

```javascript
// Client Script: Real-time execution monitoring
// Resource: AIAgent
// EventBusEvent: refresh

frappe.ui.form.on('AIAgent', {
    refresh: function(frm) {
        // Add custom button for execution monitoring
        if (frm.doc.status === 'active') {
            frm.add_custom_button('Monitor Executions', function() {
                open_execution_monitor(frm);
            }, 'Actions');
        }

        // Listen to real-time execution updates
        frappe.realtime.on('agent_execution_update', function(data) {
            if (data.agent_id === frm.doc.name) {
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
        method: 'ai_agent_management.api.get_recent_executions',
        args: {
            agent_id: frm.doc.name,
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
        message: `Execution ${data.status}: ${data.workflow_id}`,
        indicator: data.status === 'completed' ? 'green' : 'red'
    }, 5);
}
```

#### Example: Agent Configuration Wizard

```javascript
// Client Script: Agent configuration wizard
// Resource: AIAgent
// EventBusEvent: onload

frappe.ui.form.on('AIAgent', {
    onload: function(frm) {
        // Add wizard button for new agents
        if (frm.is_new()) {
            frm.add_custom_button('Configuration Wizard', function() {
                open_configuration_wizard(frm);
            }, 'Setup');
        }
    }
});

function open_configuration_wizard(frm) {
    const steps = [
        {
            title: 'Agent Type',
            fields: [
                {
                    fieldtype: 'Select',
                    fieldname: 'agent_type',
                    label: 'Agent Type',
                    options: ['openai', 'crewai', 'langgraph'],
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
                    label: 'Agent Name',
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
            title: 'API Configuration',
            fields: [
                {
                    fieldtype: 'Link',
                    fieldname: 'api_key_ref',
                    label: 'API Key Reference',
                    options: 'Secret',
                    reqd: 1
                }
            ]
        }
    ];

    const wizard = new frappe.ui.Wizard({
        title: 'Agent Configuration Wizard',
        steps: steps,
        primary_action_label: 'Create Agent',
        primary_action: function(values) {
            // Set form values
            Object.keys(values).forEach(key => {
                frm.set_value(key, values[key]);
            });

            // Close wizard
            wizard.hide();
        }
    });

    wizard.show();
}
```

---

## Webhooks

Webhooks allow external systems to be notified of AI agent events. Webhooks are configured per tenant and can subscribe to specific event types.

### Available Events

| EventBusEvent Type | Description | Payload |
|------------|-------------|---------|
| `agent.executed` | Agent execution started | `{agent_id, workflow_id, tenant_id, user_id, input_data, timestamp}` |
| `agent.completed` | Agent execution completed successfully | `{agent_id, workflow_id, tenant_id, output_data, execution_time, timestamp}` |
| `agent.failed` | Agent execution failed | `{agent_id, workflow_id, tenant_id, error_message, timestamp}` |
| `agent.created` | New agent created | `{agent_id, agent_name, agent_type, tenant_id, user_id, timestamp}` |
| `agent.updated` | Agent configuration updated | `{agent_id, agent_name, updates, tenant_id, user_id, timestamp}` |
| `agent.activated` | Agent activated | `{agent_id, agent_name, tenant_id, timestamp}` |
| `agent.deactivated` | Agent deactivated | `{agent_id, agent_name, tenant_id, timestamp}` |

### Webhook Configuration

Webhooks are configured through the Customization Framework API:

```python
# Create webhook for agent execution events
POST /api/v1/webhooks
{
    "name": "Agent Execution Notifier",
    "event_type": "agent.completed",
    "url": "https://example.com/webhooks/agent-completed",
    "method": "POST",
    "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
    },
    "tenant_id": "tenant-123",
    "is_active": true
}
```

### Example: Agent Execution Completion Webhook

```python
# Webhook Handler: Process agent execution completion
# EventBusEvent: agent.completed
# URL: https://your-system.com/webhooks/agent-completed

def handle_agent_completed(payload):
    """Handle agent execution completion webhook"""

    agent_id = payload.get("agent_id")
    workflow_id = payload.get("workflow_id")
    output_data = payload.get("output_data")

    # Process agent output
    process_agent_output(agent_id, output_data)

    # Update external system
    update_external_system(agent_id, workflow_id, output_data)

    # Send notification
    send_notification(agent_id, "Agent execution completed")
```

### Example: Agent Failure Alert Webhook

```python
# Webhook Handler: Alert on agent failures
# EventBusEvent: agent.failed
# URL: https://your-system.com/webhooks/agent-failed

def handle_agent_failure(payload):
    """Handle agent execution failure webhook"""

    agent_id = payload.get("agent_id")
    error_message = payload.get("error_message")

    # Send alert to monitoring system
    send_alert({
        "severity": "high",
        "message": f"Agent {agent_id} execution failed",
        "error": error_message,
        "timestamp": payload.get("timestamp")
    })

    # Create incident ticket
    create_incident_ticket({
        "title": f"Agent Execution Failure: {agent_id}",
        "description": error_message,
        "priority": "high"
    })
```

---

## Custom API Endpoints

Custom API endpoints can be created for agent-specific operations that extend the standard API.

### Example: Batch Agent Execution

```python
# Custom API Endpoint: Execute multiple agents in batch
# Endpoint: POST /api/method/ai_agent_management.api.batch_execute_agents
# Method: POST

@frappe.whitelist(allow_guest=False)
def batch_execute_agents(agent_ids, input_data, options=None):
    """Execute multiple agents in batch"""

    if not isinstance(agent_ids, list):
        frappe.throw("agent_ids must be a list")

    results = []

    for agent_id in agent_ids:
        try:
            # Get agent
            agent = frappe.get_doc("AIAgent", agent_id)

            # Validate access
            if not frappe.has_permission("AIAgent", "read", agent=agent):
                results.append({
                    "agent_id": agent_id,
                    "status": "error",
                    "error": "Permission denied"
                })
                continue

            # Execute agent
            from src.modules.ai_agent_management.services.agent_service import AgentService
            service = AgentService(frappe.db)

            execute_data = {
                "input_data": input_data,
                "options": options or {}
            }

            workflow = service.execute_agent(
                agent_id=agent_id,
                tenant_id=agent.tenant_id,
                execute_data=execute_data,
                user_id=frappe.session.user
            )

            results.append({
                "agent_id": agent_id,
                "workflow_id": workflow.id,
                "status": workflow.status,
                "output_data": workflow.output_data
            })

        except Exception as e:
            results.append({
                "agent_id": agent_id,
                "status": "error",
                "error": str(e)
            })

    return {
        "total": len(agent_ids),
        "results": results
    }
```

### Example: Agent Comparison API

```python
# Custom API Endpoint: Compare agent performance
# Endpoint: GET /api/method/ai_agent_management.api.compare_agents
# Method: GET

@frappe.whitelist(allow_guest=False)
def compare_agents(agent_ids, start_date=None, end_date=None):
    """Compare performance of multiple agents"""

    if not isinstance(agent_ids, list) or len(agent_ids) < 2:
        frappe.throw("At least 2 agent IDs required for comparison")

    comparison = []

    for agent_id in agent_ids:
        agent = frappe.get_doc("AIAgent", agent_id)

        # Get agent analytics
        analytics = get_agent_analytics(agent_id, start_date, end_date)

        comparison.append({
            "agent_id": agent_id,
            "agent_name": agent.name,
            "agent_type": agent.agent_type,
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

---

## EventBusEvent Bus Integration

AI agent events are automatically published to the SARAISE EventBusEvent Bus, allowing other modules and customizations to subscribe to agent events. The EventBusEvent Bus uses Redis pub/sub for distributed event communication and supports both tenant-scoped and global events.

### EventBusEvent Types

The following agent events are published to the EventBusEvent Bus:

| EventBusEvent Type | Description | When Published |
|------------|-------------|----------------|
| `agent.executed` | Agent execution started | When agent execution begins |
| `agent.completed` | Agent execution completed successfully | When agent execution completes successfully |
| `agent.failed` | Agent execution failed | When agent execution fails with error |

### Publishing Events from Services

When extending the AI Agent Management service, you can publish custom events:

```python
# In agent_service.py or custom server script
from src.core.event_bus import event_bus, EventType

# Publish agent executed event
await event_bus.publish(
    event_type=EventType.AGENT_EXECUTED,
    data={
        "agent_id": agent.id,
        "workflow_id": workflow_id,
        "input_data": input_data,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)

# Publish agent completed event
await event_bus.publish(
    event_type=EventType.AGENT_COMPLETED,
    data={
        "agent_id": agent.id,
        "workflow_id": workflow_id,
        "output_data": output_data,
        "execution_time": execution_time,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)

# Publish agent failed event
await event_bus.publish(
    event_type=EventType.AGENT_FAILED,
    data={
        "agent_id": agent.id,
        "workflow_id": workflow_id,
        "error_message": str(error),
        "error_type": type(error).__name__,
        "tenant_id": tenant_id
    },
    tenant_id=tenant_id,
    user_id=user_id
)
```

### Subscribing to Agent Events

#### Using EventBusEvent System (Recommended)

```python
# Server Script: Subscribe to agent events using EventBusEvent System
from src.core.event_bus import event_bus, EventType

# Subscribe to agent execution events
event_bus.subscribe(
    EventType.AGENT_EXECUTED,
    handle_agent_executed
)

event_bus.subscribe(
    EventType.AGENT_COMPLETED,
    handle_agent_completed
)

event_bus.subscribe(
    EventType.AGENT_FAILED,
    handle_agent_failed
)

async def handle_agent_executed(event):
    """Handle agent execution started event"""
    agent_id = event.data.get("agent_id")
    workflow_id = event.data.get("workflow_id")
    tenant_id = event.tenant_id

    # Log execution start
    logger.info(f"Agent {agent_id} execution started: {workflow_id} for tenant {tenant_id}")

    # Trigger custom logic
    await process_agent_execution_start(agent_id, workflow_id, tenant_id)

async def handle_agent_completed(event):
    """Handle agent execution completed event"""
    agent_id = event.data.get("agent_id")
    output_data = event.data.get("output_data")
    tenant_id = event.tenant_id

    # Process completed execution
    await process_completed_execution(agent_id, output_data, tenant_id)

async def handle_agent_failed(event):
    """Handle agent execution failed event"""
    agent_id = event.data.get("agent_id")
    error_message = event.data.get("error_message")
    tenant_id = event.tenant_id

    # Send failure notification
    await send_failure_notification(agent_id, error_message, tenant_id)
```

#### Using EventBusEvent Bus Directly (Advanced)

For more control, you can subscribe directly to the EventBusEvent Bus:

```python
# Server Script: Direct EventBusEvent Bus subscription
from src.core.event_bus import event_bus, EventBusEvent

async def handle_agent_event(event: EventBusEvent):
    """Handle agent event from EventBusEvent Bus"""
    event_type = event.event_type
    data = event.data
    tenant_id = event.tenant_id

    if event_type == "agent.executed":
        # Handle agent execution started
        await process_agent_execution(data, tenant_id)
    elif event_type == "agent.completed":
        # Handle agent execution completed
        await process_agent_completion(data, tenant_id)
    elif event_type == "agent.failed":
        # Handle agent execution failed
        await process_agent_failure(data, tenant_id)

# Subscribe to all agent events for specific tenant
await event_bus.subscribe(
    event_type="agent.*",  # Wildcard subscription
    handler=handle_agent_event,
    tenant_id="tenant-123"  # Tenant-scoped subscription
)

# Subscribe to specific event type globally
await event_bus.subscribe(
    event_type="agent.completed",
    handler=handle_agent_event,
    use_global=True  # Global subscription
)
```

### Integration with Customization Framework

The EventBusEvent Bus integrates seamlessly with the Customization Framework:

#### Webhooks Triggered by Events

Webhooks can be configured to trigger on agent events:

```python
# Webhook Configuration
# EventBusEvent: agent.completed
# URL: https://your-system.com/webhooks/agent-completed

def handle_agent_completed_webhook(payload):
    """Webhook handler for agent completion events"""
    agent_id = payload.get("agent_id")
    output_data = payload.get("output_data")

    # Process webhook payload
    process_webhook_payload(agent_id, output_data)
```

#### Server Scripts Subscribing to Events

Server scripts can subscribe to events for custom processing:

```python
# Server Script: Custom agent analytics on completion
# EventBusEvent: agent.completed
# Script Type: Scheduled (runs on event)

def process_agent_analytics(event):
    """Process agent analytics when agent completes"""
    agent_id = event.data.get("agent_id")
    execution_time = event.data.get("execution_time")

    # Update agent analytics
    update_agent_analytics(agent_id, execution_time)
```

### Tenant-Scoped vs Global Events

Events can be published as tenant-scoped or global:

```python
# Tenant-scoped event (default)
await event_bus.publish(
    event_type=EventType.AGENT_EXECUTED,
    data={"agent_id": "agent-123"},
    tenant_id="tenant-456"  # Only subscribers for this tenant receive event
)

# Global event (cross-tenant)
await event_bus.publish(
    event_type="agent.executed",
    data={"agent_id": "agent-123"},
    use_global=True  # All subscribers receive event
)
```

### EventBusEvent Payload Structure

```python
# Agent Executed EventBusEvent
{
    "event_type": "agent.executed",
    "data": {
        "agent_id": "agent-123",
        "workflow_id": "workflow-456",
        "tenant_id": "tenant-789",
        "user_id": "user-abc",
        "input_data": {...},
        "timestamp": "2025-01-15T10:30:00Z"
    },
    "tenant_id": "tenant-789",
    "user_id": "user-abc"
}

# Agent Completed EventBusEvent
{
    "event_type": "agent.completed",
    "data": {
        "agent_id": "agent-123",
        "workflow_id": "workflow-456",
        "tenant_id": "tenant-789",
        "output_data": {...},
        "execution_time": 2.5,
        "timestamp": "2025-01-15T10:30:05Z"
    },
    "tenant_id": "tenant-789"
}

# Agent Failed EventBusEvent
{
    "event_type": "agent.failed",
    "data": {
        "agent_id": "agent-123",
        "workflow_id": "workflow-456",
        "tenant_id": "tenant-789",
        "error_message": "API key invalid",
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

### Client Scripts

1. **User Experience**: Provide immediate feedback for user actions
2. **Validation**: Use client-side validation for better UX, but always validate on server
3. **Real-time Updates**: Use WebSocket events for real-time status updates
4. **Error Handling**: Show user-friendly error messages

### Webhooks

1. **Idempotency**: Design webhook handlers to be idempotent
2. **Retry Logic**: Implement retry logic for failed webhook deliveries
3. **Security**: Validate webhook signatures and use HTTPS
4. **Rate Limiting**: Respect rate limits when calling external APIs

### Custom API Endpoints

1. **Authentication**: Always use `@frappe.whitelist(allow_guest=False)` for authenticated endpoints
2. **Permission Checks**: Validate user permissions before processing
3. **Input Validation**: Validate and sanitize all input data
4. **Error Responses**: Return consistent error response format

---

## Examples Repository

For more examples, see:
- `backend/scripts/demo_customizations/ai_agent_management/` - Demo customization examples
- [Customization Framework Examples](../../01-foundation/customization-framework/README.md#examples)

---

## Support

For questions or issues with AI Agent Management customizations:
- Review [Customization Framework Documentation](../../01-foundation/customization-framework/README.md)
- Check [EventBusEvent System Documentation](../../../architecture/11-event-system.md)
- Contact the development team
