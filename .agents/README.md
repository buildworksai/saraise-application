# .agents — AI Agent Workspace Configuration

This folder contains configuration, commands, and skills for AI agents working in this workspace.

## Structure

```
.agents/
├── rules/          # Code compliance and architecture rules (26 files)
├── commands/       # Slash commands for quick agent instructions
├── skills/         # Reusable agent skills and expertise
└── README.md       # This file
```

---

## 📋 Rules Index

**Location:** `.agents/rules/`

These rules define the authoritative standards for SARAISE development. Rules with `alwaysApply: true` are enforced automatically.

### Core & Getting Started

| Rule | Purpose | Always Apply |
|------|---------|--------------|
| `00-core-principles.md` | Fundamental architecture principles | ✅ |
| `01-getting-started.md` | Development setup and workflows | ❌ |

### Quality & Standards

| Rule | Purpose | Always Apply |
|------|---------|--------------|
| `02-quality-enforcement.md` | Test coverage, code quality gates | ✅ |
| `03-tech-stack.md` | Technology stack registry | ✅ |
| `04-backend-standards.md` | Python/Django coding standards | ❌ |
| `05-frontend-standards.md` | TypeScript/React coding standards | ❌ |
| `06-automated-enforcement.md` | CI/CD quality gates | ✅ |

### Security & Authentication

| Rule | Purpose | Always Apply |
|------|---------|--------------|
| `07-rbac-security.md` | Role-based access control | ✅ |
| `08-secrets-management.md` | Secrets and configuration | ✅ |
| `10-session-auth.md` | Session-based authentication (FROZEN) | ✅ |
| `11-audit-logging.md` | Immutable audit logs | ✅ |
| `12-auth-enforcement.md` | Authorization enforcement patterns | ✅ |

### Infrastructure & Operations

| Rule | Purpose | Always Apply |
|------|---------|--------------|
| `09-infrastructure-config.md` | Infrastructure patterns | ❌ |
| `13-performance-optimization.md` | Performance patterns | ❌ |
| `14-troubleshooting.md` | Debugging and troubleshooting | ❌ |
| `19-service-monitoring.md` | Observability and monitoring | ❌ |

### Module Development

| Rule | Purpose | Always Apply |
|------|---------|--------------|
| `15-module-architecture.md` | Module structure and dependencies | ✅ |
| `16-frontend.md` | Frontend module patterns | ❌ |
| `17-module-lifecycle-metadata.md` | Module manifest and lifecycle | ✅ |
| `20-module-development.md` | Module implementation standards | ✅ |

### Platform & Business

| Rule | Purpose | Always Apply |
|------|---------|--------------|
| `18-pricing.md` | Subscription and pricing patterns | ❌ |
| `21-platform-tenant.md` | Multi-tenancy patterns | ✅ |
| `22-billing.md` | Billing integration patterns | ❌ |
| `23-resource-quotas.md` | Resource quota enforcement | ❌ |

### Advanced Architecture (NEW)

| Rule | Purpose | Always Apply |
|------|---------|--------------|
| `24-performance-slas.md` | Performance SLA enforcement | ❌ |
| `25-event-architecture.md` | Event-driven patterns | ❌ |

---

## ⚡ Commands

**Location:** `.agents/commands/`

Quick slash command instructions that agents can execute.

| Command | Purpose |
|---------|---------|
| `approval.md` | Architecture approval workflow |
| `investigate.md` | Investigation and debugging |
| `review.md` | Code review checklist |

**Usage:** Type `/` in editor → Select command → Agent executes instruction

---

## 🎯 Skills

**Location:** `.agents/skills/`

Reusable agent expertise and knowledge patterns.

| Skill | Purpose |
|-------|---------|
| `react-best-practices/` | React 18 + TypeScript best practices |
| `security-audit/` | Security audit checklist |
| `testing-patterns/` | Testing strategies and patterns |

---

## 🔗 Related Documentation

### Architecture (Frozen)

- `docs/architecture/application-architecture.md` — System overview
- `docs/architecture/security-model.md` — Security architecture
- `docs/architecture/authentication-and-session-management-spec.md` — Session auth
- `docs/architecture/policy-engine-spec.md` — Authorization
- `docs/architecture/module-framework.md` — Module patterns

### New Architecture Documents

- `docs/architecture/performance-slas.md` — Performance targets
- `docs/architecture/test-architecture.md` — Test patterns
- `docs/architecture/event-driven-architecture.md` — Event patterns
- `docs/architecture/realtime-architecture.md` — WebSocket patterns

### Agent Instructions

- `AGENTS.md` — Root agent instructions
- `CLAUDE.md` — Claude-specific instructions (identical to AGENTS.md)
- `.github/copilot-instructions.md` — Copilot-specific instructions

---

## 🚀 Quick Start

### 1. Setup Development Environment

```bash
# Backend
cd backend && pip install -e .[dev] && pre-commit install

# Frontend
cd frontend && npm ci
```

### 2. Run Quality Checks

```bash
# Pre-commit hooks
pre-commit run --all-files

# Backend
cd backend && black src tests && flake8 src tests && mypy src && pytest tests/

# Frontend
cd frontend && npx tsc --noEmit && npx eslint src --max-warnings 0 && npm test
```

### 3. Reference Rules When Developing

- Before making changes, check relevant rules in `.agents/rules/`
- For architecture changes, reference `docs/architecture/`
- For module development, use `backend/src/modules/ai_agent_management/` as template

---

## ⚠️ Critical Rules Summary

### Non-Negotiable Architecture

1. **Multi-Tenancy**: ALL tenant-scoped tables MUST have `tenant_id`
2. **Session Auth**: NO JWT for interactive users (session-based only)
3. **Policy Engine**: ALL authorization via Policy Engine (deny-by-default)
4. **Modules**: MUST have `manifest.yaml`, NO auth implementation in modules

### Quality Gates

1. **Test Coverage**: ≥90% required
2. **TypeScript**: ZERO errors
3. **ESLint**: ZERO warnings
4. **Pre-commit**: MUST pass all hooks

### Forbidden Patterns

- Missing `tenant_id` in tenant-scoped models
- Missing tenant filtering in queries
- JWT tokens for interactive users
- Backend-only module stubs
- Bypassing pre-commit hooks

---

**Version:** 3.0.0  
**Last Updated:** January 5, 2026
