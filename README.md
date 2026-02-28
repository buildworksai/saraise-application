<p align="center">
  <img src="frontend/public/logos/logo.png" alt="SARAISE Logo" width="180"/>
</p>

# SARAISE

**Secure and Reliable AI Symphony ERP**

![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0-092E20.svg?logo=django&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB.svg?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6.svg?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1.svg?logo=postgresql&logoColor=white)

A next-generation, AI-native Enterprise Resource Planning platform built for the modern enterprise.
Multi-tenant SaaS architecture with enterprise-grade security, 108+ business modules, and autonomous AI agents.

[Features](#key-features) • [Architecture](#architecture) • [Quick Start](#quick-start) • [Docs](#documentation) • [Contributing](#contributing)

---

## Overview

**SARAISE** (Secure and Reliable AI Symphony ERP) is an enterprise-grade, multi-tenant SaaS ERP platform that combines traditional business process management with cutting-edge AI capabilities. Built from the ground up with security, scalability, and AI-native architecture at its core.

Unlike legacy ERP systems that bolt on AI features as afterthoughts, SARAISE integrates autonomous AI agents directly into business workflows—enabling intelligent automation, predictive insights, and natural language interaction across all 108+ business modules.

### Why SARAISE?

| Traditional ERP | SARAISE |
|-----------------|---------|
| Monolithic, single-tenant | Cloud-native, multi-tenant SaaS |
| Role-based access only | Dynamic RBAC + ABAC + SoD + JIT privileges |
| Manual workflows | AI-powered autonomous workflows |
| Periodic batch processing | Real-time event-driven architecture |
| Add-on AI features | AI-native from the ground up |

---

## Key Features

### 🏢 Enterprise Multi-Tenancy
- **Row-level isolation** with mandatory `tenant_id` scoping on all data
- **Row-Level Security (RLS)** policies for high-risk domains
- Per-tenant configuration, customization, and subscription management
- Cross-tenant data access is architecturally impossible

### 🔐 Zero-Trust Security Model
- **Server-managed stateful sessions** (no JWT for interactive users)
- **Policy Engine authorization** evaluated at runtime—never cached in sessions
- **Segregation of Duties (SoD)** enforcement at workflow transitions
- **Just-In-Time (JIT) privileges** with time-bounded, approval-gated elevation
- **ABAC conditions** on org unit, site, region, classification, device posture, risk score

### 🤖 AI-Native Architecture
- **108+ AI-enabled business modules** with natural language interfaces
- **Autonomous AI agents** for document processing, workflow automation, and analytics
- **Multi-provider AI support** (OpenAI, Anthropic, Google, Groq, Mistral, etc.)
- **AI guardrails** preventing privilege escalation and unauthorized data access
- **Process mining** with AI-powered bottleneck detection and optimization

### 📦 Modular Architecture
- **Foundation modules** (22): Platform infrastructure, AI, workflow, security
- **Core modules** (21): CRM, Finance, HR, Inventory, Sales, Purchase, Projects
- **Industry modules** (65+): Manufacturing, Healthcare, Retail, Hospitality, and more
- **Manifest-driven contracts** declaring permissions, dependencies, SoD actions
- **No microservices complexity**—one codebase, one schema, one runtime

### ⚡ Performance at Scale
- **p99 API latency ≤50ms** for reads, ≤200ms for writes
- **Session validation ≤5ms**, Policy Engine ≤7ms
- **Event-driven architecture** with append-only event stores
- **99.99% uptime SLA** for dedicated tiers
- Automated performance regression testing as release gate

---

## Architecture

SARAISE follows a layered architecture with strict separation of concerns:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Frontend (React 18 + TypeScript)               │
│              TanStack Query • Tailwind CSS • Shadcn/ui • Vite            │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         API Layer (Django REST Framework)                │
│                 Session Auth • Policy Engine • Rate Limiting             │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Module Framework                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  Foundation  │  │     Core     │  │   Industry   │  │ Integration│  │
│  │   Modules    │  │   Modules    │  │   Modules    │  │   Modules  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Core Services                               │
│        Auth Subsystem • Policy Engine • Workflow Engine • AI Agents      │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Data Layer                                     │
│     PostgreSQL 17 (Row-Level Security) • Redis 7 (Sessions/Cache)        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Core Architectural Decisions (Frozen)

| Decision | Rationale |
|----------|-----------|
| **Server-managed sessions** | Prevents XSS token theft, enables immediate invalidation |
| **Policy Engine at runtime** | Sessions contain identity only—permissions never cached |
| **Mandatory tenant_id** | Row-level multitenancy without cross-tenant data leaks |
| **Django + DRF** | Mature ecosystem, batteries included, proven at scale |
| **One codebase** | Modules are not microservices—simplicity over complexity |

---

## Technology Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Runtime |
| Django | 5.0.6 | Web framework |
| Django REST Framework | 3.15.1 | API layer |
| PostgreSQL | 17 | Database with RLS |
| Redis | 7+ | Sessions, cache, pub/sub |
| Celery | 5.3+ | Async task queue |
| Gunicorn | Latest | Production server |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18 | UI framework |
| TypeScript | 5 | Type safety |
| Vite | 6+ | Build tool |
| TanStack Query | 5 | Server state management |
| Tailwind CSS | 3.4+ | Utility-first styling |
| Shadcn/ui | Latest | Component library |
| Zustand | 4.5 | Client state |

### Infrastructure

| Technology | Purpose |
|------------|---------|
| Docker & Compose | Containerization |
| Prometheus | Metrics collection |
| Grafana | Observability dashboards |
| Locust | Load testing |

---

## Quick Start

### Prerequisites

- **Docker** and **Docker Compose** (v2.0+)
- **Node.js** 18+ and **npm** 9+
- **Python** 3.10+ with **pip**
- **Git**

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/saraise.git
cd saraise
```

### 2. Start Infrastructure Services

```bash
# Start PostgreSQL, Redis, and all platform services
docker compose -f docker-compose.dev.yml up -d
```

This starts:
- PostgreSQL on port `15432`
- Redis on port `16379`
- Auth service on port `18001`
- Policy Engine on port `18002`
- Control Plane on port `18003`
- Platform Core on port `18004`

### 3. Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .[dev]

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver 0.0.0.0:8000
```

### 4. Setup Frontend

```bash
cd frontend

# Install dependencies
npm ci

# Start development server
npm run dev
```

### 5. Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000/api/
- **API Documentation**: http://localhost:8000/api/schema/swagger/

---

## Development

### Project Structure

```
saraise/
├── backend/
│   ├── src/
│   │   ├── core/           # Platform core (auth, policy, events)
│   │   └── modules/        # Business modules
│   ├── tests/              # Test suite
│   └── manage.py           # Django management
├── frontend/
│   ├── src/
│   │   ├── components/     # Shared UI components
│   │   ├── modules/        # Module-specific UI
│   │   ├── pages/          # Route pages
│   │   └── services/       # API clients
│   └── tests/              # Test suite
├── docs/
│   ├── architecture/       # Architecture specifications
│   └── modules/            # Module documentation
├── scripts/                # Utility scripts
└── reports/                # Generated reports
```

### Running Tests

```bash
# Backend tests with coverage
cd backend
pytest tests/ -v --cov=src --cov-report=html --cov-fail-under=90

# Frontend tests with coverage
cd frontend
npm test -- --coverage
```

### Code Quality

All code must pass pre-commit hooks before commit:

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run checks manually
pre-commit run --all-files
```

| Tool | Purpose | Rule |
|------|---------|------|
| **Black** | Python formatting | Enforced |
| **isort** | Import sorting | Enforced |
| **Flake8** | Python linting | `max-line-length=120` |
| **MyPy** | Python type checking | Baseline enforced |
| **ESLint** | TypeScript linting | `--max-warnings 0` |
| **TypeScript** | Type checking | `--noEmit` must pass |

### Creating a New Module

1. **Create module structure**:

```
backend/src/modules/module_name/
├── __init__.py
├── manifest.yaml       # Required: module contract
├── models.py           # Django ORM with tenant_id
├── api.py              # DRF ViewSets
├── serializers.py      # DRF serializers
├── urls.py             # URL routing
├── services.py         # Business logic
├── migrations/         # Django migrations
└── tests/              # ≥90% coverage required
```

2. **Define module manifest** (`manifest.yaml`):

```yaml
name: module-name
version: 1.0.0
description: Module description
type: domain
lifecycle: managed
dependencies:
  - core-identity >=1.0
permissions:
  - module.resource:create
  - module.resource:read
  - module.resource:update
  - module.resource:delete
sod_actions:
  - module.resource:create
  - module.resource:approve
```

3. **Implement tenant isolation** (CRITICAL):

```python
def get_queryset(self):
    tenant_id = get_user_tenant_id(self.request.user)
    if not tenant_id:
        return Model.objects.none()
    return Model.objects.filter(tenant_id=tenant_id)
```

4. **Create frontend module** in `frontend/src/modules/module_name/`

5. **Reference**: Use `backend/src/modules/ai_agent_management/` as the template.

---

## Documentation

Architecture, rules, standards, module specifications, and reports are maintained in the documentation repository and published at:

**https://docs.saraise.com**

This repository contains only the runtime application (backend + frontend). For architecture specs, security model, module framework, phase reports, and operational guides, see the link above.

---

## Security

SARAISE implements defense-in-depth security:

### Authentication
- ✅ Server-managed stateful sessions
- ✅ HTTP-only secure cookies
- ✅ OIDC/SAML 2.0 federation
- ✅ Mandatory CSRF protection
- ❌ No JWT for interactive users

### Authorization
- ✅ Policy Engine evaluates every request
- ✅ RBAC with dynamic role management
- ✅ ABAC conditions (org, site, region, etc.)
- ✅ SoD enforcement at workflow transitions
- ✅ JIT privileges with approval workflow

### Data Protection
- ✅ Mandatory tenant_id on all data
- ✅ Row-Level Security for high-risk tables
- ✅ TLS everywhere
- ✅ KMS-managed encryption
- ✅ Immutable audit logs

### Reporting Security Issues

Please report security vulnerabilities to **security@saraise.com**. See [SECURITY.md](SECURITY.md) for our security policy.

---

## Performance

SARAISE enforces strict performance SLAs:

| Operation | p99 Target | Hard Limit |
|-----------|------------|------------|
| API Read (simple) | ≤50ms | 100ms |
| API Write | ≤200ms | 400ms |
| Session Validation | ≤5ms | 10ms |
| Policy Engine | ≤7ms | 15ms |
| Search Query | ≤200ms | 400ms |

### Availability Tiers

| Tier | Monthly Uptime | Max Downtime |
|------|---------------|--------------|
| Starter | 99.5% | 3.6 hours |
| Professional | 99.9% | 43 minutes |
| Enterprise | 99.95% | 21 minutes |
| Dedicated | 99.99% | 4 minutes |

**Performance regressions block release.**

---

## Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md) before submitting PRs.

### Development Requirements

1. All code must pass pre-commit hooks
2. Tests must maintain ≥90% coverage
3. TypeScript must have zero `any` types
4. All queries must include tenant_id filtering
5. Module changes require manifest.yaml updates

### Pull Request Process

1. Fork the repository
2. Create a feature branch (`feature/your-feature`)
3. Ensure all tests pass
4. Submit PR with description following our template
5. Address review feedback
6. Squash and merge after approval

---

## Roadmap

SARAISE is developed in phases:

| Phase | Focus | Status |
|-------|-------|--------|
| 1-5 | Platform Foundation, Auth, Policy Engine, AI Agents | ✅ Complete |
| 6 | Module Framework, Full-Stack Patterns | ✅ Complete |
| 7 | Event Store, Audit Foundation | 🚧 In Progress |
| 8 | Core Business Modules (CRM, Finance, HR, etc.) | 📋 Planned |
| 9+ | Industry-Specific Modules | 📋 Planned |

---

## License

SARAISE is licensed under the **Apache License 2.0**.

```
Copyright 2025-2026 SARAISE - Secure and Reliable AI Symphony ERP
Copyright 2025-2026 BuildWorks.AI

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

See [LICENSE](LICENSE) for full text.

---

## Support

- **Documentation**: [docs.saraise.com](https://docs.saraise.com)
- **Issues**: [GitHub Issues](https://github.com/your-org/saraise/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/saraise/discussions)
- **Email**: support@saraise.com

---

---

**Built by [BuildWorks.AI](https://www.buildworks.ai)** | [www.saraise.com](https://www.saraise.com)
