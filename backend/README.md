# backend/

Purpose
- Backend runtime application (server, auth, policy enforcement, modules).

Key entrypoints
- (Scaffold) Intended main app entrypoint: `backend/src/main.py` (not yet implemented in this scaffold).
- Modules live under `backend/src/modules/`.

Boundaries
- Do not place architecture specs here; use `docs/architecture/`.
- Do not place scripts here unless they are backend-only; repo-wide scripts belong in `scripts/`.
