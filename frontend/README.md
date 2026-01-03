# frontend/

Purpose
- Frontend web application (React + TypeScript + Vite).

Key entrypoints
- App bootstrap: `frontend/src/main.tsx`
- Root UI: `frontend/src/App.tsx`

Boundaries
- Static assets belong in `frontend/public/`.
- Frontend services belong in `frontend/src/services/` (typed API clients; no hardcoded base URLs).
