# Bash Helper Functions

This file consolidates all Bash helper functions and environment variable definitions from rule files.

## Environment Variables

All environment variables are defined in the rule files:
- Ports: `.cursor/rules/16-ports-cors.mdc`
- Timeouts: `.cursor/rules/15-secrets-management.mdc`
- Logging: `.cursor/rules/15-secrets-management.mdc`
- Paths: `.cursor/rules/15-secrets-management.mdc`

## Usage

Source environment variables from `.env` files:

```bash
# Load environment variables
source .env

# Use in scripts
echo "Frontend URL: ${FRONTEND_BASE_URL}"
echo "API Port: ${API_HOST_PORT}"
echo "Session Timeout: ${SESSION_TIMEOUT}"
```

