# Frontend container build notes

This frontend uses a multi-stage Docker build.

- Build stage installs devDependencies and runs `npm run build` to produce `dist/`.
- Runtime stage serves only `dist/` via Nginx as the non-root `nginx` user on port 8080.

This ensures production images do **not** include `node_modules` and do **not** ship devDependencies.

Entrypoint
- See `frontend/Dockerfile`.
