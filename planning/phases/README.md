# SARAISE Implementation Phases

This folder contains detailed phase execution documents for AI agents.

## Phase Index

| Phase | Duration | Focus | Status |
|-------|----------|-------|--------|
| **Phase 7** | Weeks 1-5 | Foundation Part 1: Platform, Tenant, Security | 🟢 READY |
| **Phase 8** | Weeks 6-10 | Foundation Part 2: Workflow, Metadata, DMS, Integration | 🟡 PENDING |
| **Phase 9** | Weeks 11-15 | Foundation Part 3: Billing, Migration, AI, Localization | 🟡 PENDING |
| **Phase 10** | Weeks 16-20 | Core Part 1: CRM, Accounting | ⏸️ BLOCKED |
| **Phase 11** | Weeks 21-25 | Core Part 2: Sales, Purchase, Inventory | ⏸️ BLOCKED |
| **Phase 12** | Weeks 26-30 | Core Part 3: HR, Projects, BI | ⏸️ BLOCKED |
| **Phase 13+** | TBD | Industry Modules | ⏸️ BLOCKED |

## Document Contents

Each phase document contains:

1. **Module Overview** — Name, priority, dependencies, timeline
2. **Key Entities** — Data models from specification
3. **API Endpoints** — REST API contracts
4. **Implementation Tasks** — Day-by-day execution steps
5. **Code Examples** — Reference implementations
6. **Tests** — Mandatory test cases including isolation tests
7. **Validation Gates** — Quality checkpoints

## AI Agent Execution Protocol

### Starting a Phase

```bash
# 1. Read the phase document
cat planning/phases/phase-X-*.md

# 2. Verify prerequisites complete
# Check previous phase completion reports in reports/

# 3. Read module specifications
ls docs/modules/0X-*/[module-name]/

# 4. Begin Day 1 tasks
```

### Per-Module Sequence

```
Day 1: Specification Review
├── Read README.md, API.md from docs/modules/
├── Extract data models
├── Extract API endpoints
└── Create implementation checklist

Day 2-3: Backend Implementation
├── Create module directory structure
├── Implement models.py (with tenant_id)
├── Implement serializers.py
├── Implement api.py (ViewSets)
├── Implement urls.py
├── Implement services.py
├── Create manifest.yaml
└── Create migrations

Day 3-4: Backend Tests
├── test_api.py (CRUD operations)
├── test_services.py (business logic)
├── test_isolation.py (MANDATORY - tenant isolation)
└── Verify ≥90% coverage

Day 4-5: Frontend Implementation
├── Create module structure
├── Implement types/index.ts
├── Implement services/module-service.ts
├── Implement pages/
└── Add routes

Day 5: Validation & Completion
├── Run all quality checks
├── Generate OpenAPI schema
├── Generate TypeScript types
└── Create completion report
```

## Quality Gates (Non-Negotiable)

Every module must pass:

| Gate | Requirement |
|------|-------------|
| TypeScript | `tsc --noEmit` with 0 errors |
| ESLint | `--max-warnings 0` |
| Black | Python formatted |
| Flake8 | No errors |
| MyPy | ≤ baseline errors |
| Tests | ≥90% coverage |
| Isolation | Tenant isolation tests pass |

## Architecture Compliance

All modules must:
- ✅ Use Django ORM (no SQLAlchemy)
- ✅ Have `tenant_id` in all tenant-scoped models
- ✅ Filter by `tenant_id` in all queries
- ✅ Use session authentication (no JWT)
- ✅ Include `manifest.yaml`
- ✅ Follow template structure from `ai_agent_management`

## References

- Master Plan: `planning/README.md`
- Architecture: `docs/architecture/`
- Module Specs: `docs/modules/`
- Agent Rules: `.agents/rules/`
- Template Module: `backend/src/modules/ai_agent_management/`

---

**Last Updated:** January 5, 2026

