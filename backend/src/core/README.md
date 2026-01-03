# backend/src/core/

Purpose
- Platform-level backend primitives (session handling, auth boundaries, policy engine integration, cross-cutting middleware).

Boundaries
- Application modules must NOT implement login/logout/session management.
- Keep module-agnostic components here; module-specific logic belongs in `backend/src/modules/`.
