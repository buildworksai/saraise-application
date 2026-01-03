# backend/src/modules/

Purpose
- Business modules (manifest-driven, per-tenant installable units).

Conventions
- Each module is self-contained and declares dependencies in `manifest.yaml`.
- All tenant-scoped persistence must include `tenant_id` and must be filtered by it.
- No auth/session issuance inside modules.

See also
- `docs/architecture/module-framework.md`
- `docs/architecture/security-model.md`
