# AI Agent Management User Guide

**Module:** `ai-agent-management`  
**Version:** 1.0.0

---

## Overview

The AI Agent Management module allows you to create, manage, and monitor AI agents that can execute tasks, interact with tools, and require approvals for sensitive operations.

---

## Getting Started

### Prerequisites

- Access to SARAISE platform
- Appropriate permissions for AI Agent Management module
- Understanding of agent frameworks (LangGraph, CrewAI, etc.)

### Accessing the Module

1. Log in to SARAISE
2. Navigate to **AI Agents** in the sidebar
3. You'll see the Agent List page

---

## Creating an Agent

### Step 1: Navigate to Create Page

Click the **"Create Agent"** button on the Agent List page.

### Step 2: Fill in Agent Details

**Required Fields:**
- **Name:** Descriptive name for your agent
- **Identity Type:** Choose between:
  - **User-Bound:** Agent runs in context of a specific user session
  - **System-Bound:** Agent runs as a system role (no user session)
- **Subject ID:** User ID (for user-bound) or system role ID (for system-bound)
- **Framework:** Choose from LangGraph, CrewAI, AutoGen, or Custom

**Optional Fields:**
- **Description:** Detailed description of agent's purpose
- **Session ID:** Required for user-bound agents
- **Configuration:** JSON configuration for agent framework

### Step 3: Configure Agent

Example configuration for LangGraph:
```json
{
  "temperature": 0.7,
  "max_tokens": 2000,
  "model": "gpt-4"
}
```

### Step 4: Submit

Click **"Create Agent"** to save. The agent will appear in your agent list.

---

## Managing Agents

### Viewing Agent Details

1. Click **"View"** on any agent in the list
2. See agent information, configuration, and execution history

### Editing an Agent

1. Click **"Edit"** on an agent
2. Modify fields as needed
3. Save changes

### Deleting an Agent

1. Click **"Delete"** on an agent
2. Confirm deletion
3. Agent and all associated data will be removed

---

## Executing Agents

### Manual Execution

1. Navigate to agent detail page
2. Click **"Execute"** button
3. Enter task definition (JSON):
   ```json
   {
     "task": "process_invoice",
     "invoice_id": "inv-123",
     "params": {}
   }
   ```
4. Execution starts immediately

### Execution States

- **Running:** Agent is actively executing
- **Paused:** Execution paused (can be resumed)
- **Completed:** Execution finished successfully
- **Failed:** Execution encountered an error

### Controlling Execution

**Pause:**
- Click pause icon on running execution
- Execution pauses, can be resumed later

**Resume:**
- Click play icon on paused execution
- Execution continues from pause point

**Terminate:**
- Click stop icon on running execution
- Execution stops immediately (cannot be resumed)

---

## Monitoring Executions

### Execution Monitor Page

Navigate to **Executions** in the sidebar to see:
- All active executions (highlighted)
- Recent execution history
- Execution duration
- Error messages

### Execution Details

Click on any execution to see:
- Full task definition
- Execution logs
- Tool invocations
- Results or error details

---

## Handling Approvals

### Approval Queue

Navigate to **Approvals** in the sidebar to see:
- All pending approval requests
- Approval details (tool, agent, justification)
- Approve/reject actions

### Approving Requests

1. Review approval request details
2. Check justification
3. Click **"Approve"** button
4. Agent execution continues

### Rejecting Requests

1. Review approval request
2. Enter rejection reason (optional)
3. Click **"Reject"** button
4. Agent execution stops

### SoD Violations

If an approval violates Separation of Duties (SoD) policies:
- Warning badge appears
- Review SoD policy details
- Ensure compliance before approving

---

## Quotas & Limits

### Viewing Quota Usage

Agent detail page shows:
- Current quota usage
- Remaining quota
- Quota reset date

### Quota Types

- **Execution Time:** Total execution time per period
- **API Calls:** Number of API calls per period
- **Token Usage:** LLM token consumption

### Exceeding Quotas

When quota is exceeded:
- New executions blocked
- Existing executions continue
- Upgrade subscription to increase limits

---

## Troubleshooting

### Agent Won't Execute

**Check:**
1. Agent is active (`is_active: true`)
2. Quota not exceeded
3. Agent configuration is valid
4. Required tools are available

### Execution Fails

**Check:**
1. Execution logs for error details
2. Tool availability
3. Network connectivity
4. API credentials

### Approval Not Appearing

**Check:**
1. Tool requires approval (`requires_approval: true`)
2. Approval request status
3. User has approval permissions
4. SoD policies not blocking

### Performance Issues

**Check:**
1. Execution monitor for bottlenecks
2. Quota usage
3. Agent configuration (timeouts, retries)
4. Backend service health

---

## Best Practices

### Agent Design

1. **Clear Purpose:** Each agent should have a single, well-defined purpose
2. **Proper Configuration:** Set appropriate timeouts, retries, and error handling
3. **Resource Management:** Monitor quota usage and optimize agent efficiency

### Security

1. **Least Privilege:** Grant agents only necessary permissions
2. **Approval Workflows:** Use approvals for sensitive operations
3. **Audit Trails:** Review execution history regularly

### Monitoring

1. **Regular Checks:** Monitor execution status daily
2. **Error Alerts:** Set up alerts for failed executions
3. **Performance Metrics:** Track execution times and success rates

---

## API Integration

For programmatic access, see [API Documentation](./API.md).

Example: Create agent via API
```bash
curl -X POST http://localhost:8000/api/v1/ai-agents/agents/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API Agent",
    "identity_type": "system_bound",
    "subject_id": "system-role-1",
    "framework": "langgraph",
    "config": {}
  }'
```

---

## Support

For issues or questions:
1. Check this user guide
2. Review API documentation
3. Contact support team

---

**Last Updated:** January 5, 2026
