# reports/changes/

Purpose
- Immutable, reviewable change evidence (audit results, security remediations, compliance notes) associated with code changes.

Conventions
- One report per change-set, dated in the filename.
- Reports should include: intent, exact version changes, commands run, and rollback steps.

Boundaries
- Do not store architecture specs here; use `docs/architecture/`.
- Do not store temporary output; prefer reproducible commands.
