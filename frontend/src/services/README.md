# frontend/src/services/

Purpose
- Typed API client layer.

Conventions
- Use a single base client (e.g., `api-client.ts`) that relies on session cookies.
- Do not manually manage tokens for interactive users.
- Do not hardcode API URLs; use environment/config.
