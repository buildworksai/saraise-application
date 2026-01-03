#!/bin/bash
# ✅ APPROVED: AI Agent and Workflow Troubleshooting Commands
# Reference: docs/architecture/ai-agent-execution-and-safety-spec.md § 5 (Error Handling)
# Also: docs/architecture/operational-runbooks.md § 2 (Troubleshooting)
# 
# CRITICAL NOTES:
# - Agents inherit session context (user_id, email, tenant_id, roles)
# - Agent execution timeouts indicate resource exhaustion or external API latency
# - Workflow steps must include error handling and rollback logic
# - All agent API calls include session cookie automatically (no manual token management)

# Problem: AI agents not responding
# Symptoms
# - Agent execution timeouts
# - "Agent not available" errors
# - Poor response quality

# Diagnosis
# 1. Check agent configuration
# 2. Verify external API keys
# 3. Check agent health status
# 4. Validate input data

# Solutions
# Check agent configuration
psql -h localhost -p 5432 -U postgres -d saraise -c "SELECT name, agent_type, configuration FROM ai_agents;"

# Verify API keys
echo $OPENAI_API_KEY
echo $GOOGLE_API_KEY

# Check agent health (session cookie automatically included)
curl -b cookies.txt http://localhost:30000/agents/health

# Test agent execution (session cookie automatically included)
curl -X POST -b cookies.txt -H "Content-Type: application/json" \
  -d '{"agent_id": "agent-123", "input": "test"}' \
  http://localhost:30000/agents/execute

# Problem: Workflows failing to execute
# Symptoms
# - Workflow execution timeouts
# - "Workflow step failed" errors
# - Incomplete workflow execution

# Diagnosis
# 1. Check workflow definition
# 2. Verify step configurations
# 3. Check external service availability
# 4. Validate data flow

# Solutions
# Check workflow definition
psql -h localhost -p 5432 -U postgres -d saraise -c "SELECT name, steps FROM workflows;"

# Check workflow execution logs
docker logs saraise-api | grep -i workflow

# Test individual workflow steps (session cookie automatically included)
curl -X POST -b cookies.txt -H "Content-Type: application/json" \
  -d '{"workflow_id": "workflow-123", "step": 1}' \
  http://localhost:30000/workflows/execute-step

# Check external service status
curl -f https://api.external-service.com/health

