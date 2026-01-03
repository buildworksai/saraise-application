# backend/src/

Purpose
- Backend source code root.

Conventions
- Keep business logic in services; keep route/controllers thin.
- Enforce tenant isolation (`tenant_id`) and deny-by-default authorization per request.

See also
- `docs/architecture/application-architecture.md`
- `docs/architecture/authentication-and-session-management-spec.md`
- `docs/architecture/policy-engine-spec.md`
