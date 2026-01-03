# Frontend container build notes

This frontend uses a multi-stage Docker build.

- Build stage installs devDependencies and runs `npm run build` to produce `dist/`.
- Runtime stage serves only `dist/` via Nginx.

This ensures production images do **not** include `node_modules` and do **not** ship devDependencies.

Entrypoint
- See `frontend/Dockerfile`.
