---
description: Quick start guide for SARAISE with pure session-based authentication
globs: **/*
alwaysApply: true
---

# SARAISE Getting Started Guide

**⚠️ TECH STACK CONFIGURATION**: All technology versions are defined in `03-tech-stack.md`.
This file references tech versions with fallback defaults.
To change tech versions, update the environment variables in `03-tech-stack.md`.

## SARAISE-00001 Project Overview

SARAISE is a multi-tenant AI agent management platform with:
- **AI Agent Management**: Create and deploy AI agents
- **Workflow Automation**: Visual workflow design
- **Multi-Tenant**: Complete tenant isolation
- **Session-Based Auth**: Pure session authentication (no JWT)
- **RBAC**: Platform and tenant role-based access control
- **Enterprise SaaS**: Billing, subscriptions, plans, discounts, coupons, partners, rate limiting, user quotas

## SARAISE-00002 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 17
- Redis 7

### 1. Clone and Setup
```bash
git clone https://github.com/buildworksai/saraise.git
cd saraise

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -e .

# Frontend setup
cd ../frontend
npm install

# Environment files
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

### 2. Start Services
```bash
docker-compose up -d  # Starts PostgreSQL, Redis
```

### 3. Initialize Database
```bash
cd backend
python manage.py migrate
python scripts/init_db.py
```

### 4. Run Application
```bash
# Backend (terminal 1)
cd backend
python manage.py runserver 0.0.0.0:8000

# Frontend (terminal 2)
cd frontend
npm run dev
```

Access: http://localhost:${FRONTEND_HOST_PORT:-5173}

## SARAISE-00003 Authentication Architecture

**Pure Session-Based (No JWT)**

### Backend Session Setup (`backend/src/core/session_manager.py`)
```python
from django.contrib.sessions.backends.cache import SessionStore
from redis import Redis
import secrets

class SessionCookieManager:
    def __init__(self):
        self.redis = Redis(host='localhost', port=6379, decode_responses=True)
        self.session_timeout = int(os.getenv('SESSION_TIMEOUT', '7200'))  # 2 hours

    def create_session(self, user_id: str, user_data: dict) -> str:
        """Create session with identity snapshot (FROZEN ARCHITECTURE - Django synchronous)"""
        session_id = secrets.token_urlsafe(32)
        key = f"saraise:session:{session_id}"

        # CRITICAL: Store identity snapshot ONLY - NOT effective permissions or authorization decisions
        # FROZEN ARCHITECTURE: Sessions contain roles[], groups[], jit_grants[], policy_version
        # Policy Engine evaluates authorization at runtime using this identity snapshot
        session_data = {
            "session_id": session_id,
            "user_id": user_data["user_id"],
            "email": user_data["email"],
            "tenant_id": user_data.get("tenant_id"),
            "policy_version": user_data.get("policy_version", "v1.0.0"),  # FROZEN: Policy version gating
            "roles": user_data.get("roles", []),  # Identity snapshot - NOT effective permissions
            "groups": user_data.get("groups", []),  # Identity snapshot
            "jit_grants": user_data.get("jit_grants", []),  # Time-bounded grants
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat()
        }
        # ANTI-PATTERNS (FORBIDDEN):
        # ❌ session_data["effective_permissions"] = ["finance.ledger:post", ...]
        # ❌ session_data["resource_access"] = {"invoices": True, ...}
        # ❌ session_data["cached_decisions"] = {...}

        self.redis.setex(key, self.session_timeout, json.dumps(session_data))
        return session_id

    def get_session(self, session_id: str) -> dict:
        """Get session data with identity snapshot (FROZEN ARCHITECTURE - Django synchronous)"""
        key = f"saraise:session:{session_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None

    def invalidate_user_sessions(self, user_id: str):
        """Invalidate all user sessions (on role/policy change, policy_version increment)"""
        pattern = f"saraise:session:*"
        for key in self.redis.scan_iter(match=pattern):
            data = self.redis.get(key)
            if data and json.loads(data).get("user_id") == user_id:
                self.redis.delete(key)
```

### Login Endpoint (`backend/src/modules/auth/views.py`)
```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from src.core.session_manager import SessionCookieManager
from django.contrib.auth import authenticate

@api_view(['POST'])
def login(request):
    """Login endpoint using session-based authentication (Django/DRF - NO async)"""
    credentials = request.data

    # 1. Validate credentials using Django's authenticate
    user = authenticate(username=credentials.get('email'), password=credentials.get('password'))

    if not user:
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # 2. Fetch user roles, groups for identity snapshot (FROZEN ARCHITECTURE)
    # Use services to get identity snapshot components
    from src.modules.auth.services import AuthService
    auth_service = AuthService()

    user_roles = auth_service.get_user_roles(user.id)  # Returns ["platform_owner", ...] or ["tenant_admin", ...]
    user_groups = auth_service.get_user_groups(user.id)  # Returns ["finance_team", "managers", ...]
    policy_version = auth_service.get_current_policy_version()  # Returns "v1.2.3"

    # 3. Build identity snapshot (FROZEN: NO effective permissions or authorization decisions)
    session_data = {
        "user_id": str(user.id),
        "email": user.email,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "policy_version": policy_version,  # FROZEN: Policy version gating
        "roles": user_roles,  # Identity snapshot - NOT effective permissions
        "groups": user_groups,  # Identity snapshot
        "jit_grants": []  # Populated on JIT privilege grants (time-bounded)
    }

    # 4. Create session with identity snapshot (Policy Engine uses this for authorization)
    scm = SessionCookieManager()
    session_id = scm.create_session(str(user.id), session_data)

    # 5. Set HTTP-only cookie (server-managed session authentication)
    response = Response({
        "user": {
            "id": str(user.id),
            "email": user.email,
            "tenant_id": str(user.tenant_id) if user.tenant_id else None
        }
    }, status=status.HTTP_200_OK)

    response.set_cookie(
        key="saraise_session",
        value=session_id,
        httponly=True,
        secure=True,  # HTTPS only in production
        samesite="lax",
        max_age=7200  # 2 hours
    )

    # Return user identity (Policy Engine evaluates authorization using identity snapshot from session)
    return response
```

### Auth Dependency (`backend/src/core/auth_decorators.py`)
```python
from rest_framework.exceptions import AuthenticationFailed
from src.core.session_manager import SessionCookieManager
from src.modules.auth.models import User

def get_current_user_from_session(request) -> User:
    """Get user identity from session with identity snapshot (FROZEN ARCHITECTURE - Django/DRF)"""
    session_id = request.COOKIES.get("saraise_session")
    if not session_id:
        raise AuthenticationFailed("Not authenticated - session cookie missing")

    scm = SessionCookieManager()
    session_data = scm.get_session(session_id)

    if not session_data:
        raise AuthenticationFailed("Invalid or expired session")

    # CRITICAL: Verify policy_version matches current runtime version (FROZEN: Policy version gating)
    # This ensures sessions are invalidated when policies change
    from src.modules.auth.services import AuthService
    auth_service = AuthService()
    current_policy_version = auth_service.get_current_policy_version()

    if session_data.get("policy_version") != current_policy_version:
        # Force re-authentication when policy version is stale
        raise AuthenticationFailed(
            "Session policy version stale - please re-authenticate",
            code="DENY_POLICY_VERSION_STALE"
        )

    # Return user with identity snapshot from session (NOT effective permissions)
    # Policy Engine will use this identity snapshot for authorization evaluation
    user = User(
        id=session_data["user_id"],
        email=session_data["email"],
        tenant_id=session_data.get("tenant_id"),
        # Identity snapshot fields (used by Policy Engine for authorization):
        roles=session_data.get("roles", []),  # e.g., ["platform_owner"] or ["tenant_admin"]
        groups=session_data.get("groups", []),  # e.g., ["finance_team", "managers"]
        jit_grants=session_data.get("jit_grants", [])  # Time-bounded privilege grants
    )

    return user

# ✅ CORRECT: DRF ViewSet with Policy Engine authorization
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session

class PlatformUserViewSet(viewsets.ViewSet):
    """Platform-level operations (platform_owner only)."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get all platform users - requires platform_owner role."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        # Policy Engine authorization check
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=None,  # Platform operation
            resource="platform.users",
            action="manage",
            context={"operation": "list_all"}
        )
        
        if not decision.allowed:
            return Response(
                {"error": "Requires platform_owner role"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # ... implementation ...
        return Response({"users": []})

class TenantUserViewSet(viewsets.ViewSet):
    """Tenant-level operations (tenant_admin required)."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """List tenant users - requires tenant_admin role."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        # Policy Engine authorization check
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            resource="tenant.users",
            action="manage",
            context={"operation": "list"}
        )
        
        if not decision.allowed:
            return Response(
                {"error": "Requires tenant_admin role"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # ... implementation ...
        return Response({"users": []})
```

## SARAISE-00004 Frontend Auth

### Auth Context (`frontend/src/lib/auth-context.tsx`)
```typescript
import { createContext, useContext, useState, useEffect } from 'react'

interface User {
  id: string
  email: string
  tenant_id: string | null
  // Note: roles/permissions not in session - queried from backend via Policy Engine
}

const AuthContext = createContext<{
  user: User | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasRole: (role: string) => boolean
  hasTenantRole: (role: string) => boolean
} | undefined>(undefined)

export function AuthProvider({ children }) {
  const [user, setUser] = useState<User | null>(null)

  const login = async (email: string, password: string) => {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      credentials: 'include',  // Include cookies
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    })

    if (res.ok) {
      const data = await res.json()
      setUser(data.user)
    }
  }

  const logout = async () => {
    await fetch('/api/v1/auth/logout', {
      method: 'POST',
      credentials: 'include'
    })
    setUser(null)
  }

  // Authorization checks query backend Policy Engine
  const hasRole = async (role: string) => {
    const res = await fetch(`/api/v1/auth/check-role?role=${role}`, {
      credentials: 'include'
    })
    return res.ok && (await res.json()).allowed
  }
  const hasTenantRole = async (role: string) => {
    const res = await fetch(`/api/v1/auth/check-tenant-role?role=${role}`, {
      credentials: 'include'
    })
    return res.ok && (await res.json()).allowed
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, hasRole, hasTenantRole }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)!
```

## SARAISE-00005 Core Configuration

### Backend Settings (`backend/src/config/settings.py`)
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    POSTGRES_CONNECTION_STRING: str = "postgresql://postgres:postgres@localhost:25432/saraise"
    REDIS_URL: str = "redis://localhost:26379"

    # Application
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    # Multi-tenant (FROZEN ARCHITECTURE - Row-Level Multitenancy)
    DEFAULT_TENANT_ID: str = "default"
    TENANT_ISOLATION_MODE: str = "row-level-multitenancy"  # Shared schema with mandatory tenant_id filtering

    # CORS
    cors_origins: list = ["http://localhost:20000", "http://localhost:30000"]

    class Config:
        env_file = ".env"

settings = Settings()
```

### Frontend Config (`frontend/lib/config.ts`)
```typescript
export const config = {
  api: {
    baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:30000'
  },
  app: {
    env: process.env.NODE_ENV || 'development'
  }
}
```

## SARAISE-00006 Row-Level Multitenancy (CRITICAL - FROZEN ARCHITECTURE)

SARAISE uses **Row-Level Multitenancy** with **shared schema** (NOT schema-per-tenant).

### Non-Negotiable Rules

1. **ALL tenant-scoped tables MUST have `tenant` ForeignKey** to Tenant model
2. **ALL queries MUST filter by `tenant_id`** (service layer responsibility)
3. **Schema-per-tenant is BANNED** - shared schema only
4. **Manual tenant_id filtering is REQUIRED** - no automatic isolation

### Django ORM Model Pattern (MANDATORY)

```python
from django.db import models
import uuid

class Tenant(models.Model):
    """Platform-level tenant model (no tenant_id - this IS the tenant)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenants'

class AIAgent(models.Model):
    """Tenant-scoped AI agent (MUST have tenant ForeignKey)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ai_agents')  # MANDATORY
    name = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_agents'
        indexes = [
            models.Index(fields=['tenant', 'created_at']),  # Tenant-scoped queries
        ]
```

### Service Layer Tenant Isolation (MANDATORY Pattern)

```python
from rest_framework.exceptions import PermissionDenied

class AIAgentService:
    """Service layer enforces tenant isolation"""

    def get_agent(self, agent_id: str, tenant_id: str):
        """Get agent with mandatory tenant isolation"""
        try:
            # CRITICAL: Always filter by tenant_id
            return AIAgent.objects.get(id=agent_id, tenant_id=tenant_id)
        except AIAgent.DoesNotExist:
            raise PermissionDenied("Agent not found or access denied")

    def list_agents(self, tenant_id: str):
        """List agents for tenant with mandatory filtering"""
        # CRITICAL: Explicit tenant_id filtering provides isolation
        return AIAgent.objects.filter(tenant_id=tenant_id)
```

### DRF ViewSet Tenant Isolation (MANDATORY Pattern)

```python
from rest_framework import viewsets, status
from rest_framework.response import Response

class AIAgentViewSet(viewsets.ViewSet):
    """AI Agent management with mandatory tenant isolation"""

    def list(self, request):
        # MANDATORY: Filter by authenticated user's tenant_id
        current_user = request.user
        if not current_user.tenant_id:
            return Response(
                {"error": "User must be associated with a tenant"},
                status=status.HTTP_403_FORBIDDEN
            )

        # CRITICAL: Explicit tenant_id filtering provides isolation
        agents = AIAgent.objects.filter(tenant_id=current_user.tenant_id)
        serializer = AIAgentSerializer(agents, many=True)
        return Response(serializer.data)

    def create(self, request):
        current_user = request.user
        # MANDATORY: Associate new record with user's tenant
        data = request.data.copy()
        data['tenant'] = current_user.tenant_id

        serializer = AIAgentSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
```

### Anti-Patterns (FORBIDDEN)

```python
# ❌ FORBIDDEN: Query without tenant_id filter
agents = AIAgent.objects.all()  # DATA LEAKAGE!

# ❌ FORBIDDEN: Client-provided tenant_id without validation
tenant_id = request.data.get('tenant_id')  # SECURITY HOLE!

# ✅ CORRECT: Use authenticated user's tenant_id
tenant_id = request.user.tenant_id
agents = AIAgent.objects.filter(tenant_id=tenant_id)
```

## SARAISE-00007 Database Models

See `backend/src/models/base.py` for complete models:
- `Tenant` - Multi-tenant organizations (platform-level, no tenant_id)
- `User` - Users with mandatory tenant association
- `AIAgent` - AI agent definitions (tenant-scoped, MUST have tenant ForeignKey)
- `AuditLog` - Immutable audit trail (see rule 11)
- `SubscriptionPlan` - Subscription plan definitions
- `Subscription` - Tenant subscriptions
- `Coupon` - Discount coupons
- `Partner` - Partner/affiliate records

**CRITICAL**: ALL tenant-scoped models MUST include `tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)`

## SARAISE-00008 RBAC Roles

**Platform Roles** (session.roles):
- `platform_owner` - Full platform control
- `platform_operator` - Platform operations
- `platform_auditor` - Read-only audit access
- `platform_billing_manager` - Billing management

**Tenant Roles** (session.tenant_roles):
- `tenant_admin` - Full tenant control
- `tenant_developer` - Development access
- `tenant_operator` - Operations access
- `tenant_billing_manager` - Tenant billing
- `tenant_auditor` - Tenant audit access
- `tenant_user` - Standard user access
- `tenant_viewer` - Read-only access

See [1000-rbac-roles.md](1000-rbac-roles.md) for complete role definitions.

## SARAISE-00009 Next Steps

1. **Authentication**: Review `10-session-auth.md`
2. **RBAC**: Review `12-auth-enforcement.md`
3. **Step-Up Auth**: Review [07-rbac-security.md](07-rbac-security.md)
4. **Audit Logging**: Review `11-audit-logging.md`
5. **Frontend**: Review `16-frontend.md`
6. **Testing**: Review `02-quality-enforcement.md`
7. **Module Development**: Review `20-module-development.md`
8. **Enterprise SaaS**: Review [32-40] for billing, subscriptions, and tenant management

## SARAISE-00010 Development Workflow

```bash
# Start development (Django + DRF stack)
docker-compose up -d
cd backend && python manage.py runserver 0.0.0.0:8000  # Django development server
cd frontend && npm run dev  # Vite dev server (port 5173)

# Run tests
cd backend && pytest tests/ --cov=src --cov-report=html
cd frontend && npm test

# Database migrations (Django ORM - MANDATORY)
cd backend && python manage.py makemigrations module_name
cd backend && python manage.py migrate

# Code quality checks (pre-commit enforcement)
cd backend && black src/ && flake8 src/ --max-line-length=120 && mypy src/
cd frontend && npx tsc --noEmit && npx eslint src/ --ext .ts,.tsx --max-warnings 0
```

## SARAISE-00011 Key Principles (FROZEN ARCHITECTURE)

✅ **Pure Session Auth**: No JWT tokens for interactive users
✅ **Identity Snapshot**: Sessions contain identity snapshot (roles[], groups[], jit_grants[], policy_version) - NOT effective permissions
✅ **Policy Engine**: All authorization evaluated at runtime by Policy Engine using identity snapshot from session
✅ **Policy Version Gating**: Sessions invalidated when policy_version changes (forced re-authentication)
✅ **Session Invalidation**: On logout, role/policy changes, privilege elevation
✅ **Deny-by-Default**: Explicit authorization via Policy Engine
✅ **Row-Level Multitenancy**: Shared schema with mandatory tenant_id filtering (NOT schema-per-tenant)
✅ **Immutable Audit**: All sensitive operations logged
✅ **Modular Architecture**: Self-contained module system
✅ **Metadata Modeling**: Dynamic customization framework

---

**For detailed implementation**: See individual rule files (02-40)
