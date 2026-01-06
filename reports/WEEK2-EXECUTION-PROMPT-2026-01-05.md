# Week 2 Execution Prompt — Phase 6 Implementation

**Date:** January 5, 2026
**Duration:** 5 days
**Objective:** Implement Authentication UI + AI Agent Management Frontend UI

---

## Task Overview

You are implementing **Week 2 of Phase 6** for SARAISE. This week establishes the frontend UI foundation by:

1. Installing frontend dependencies (routing, state management, UI components)
2. Implementing Authentication UI (login, session management, protected routes)
3. Implementing AI Agent Management UI (5 pages: list, detail, create, execution monitor, approval queue)

**Context**: Review these documents first:
- `/Users/raghunathchava/Code/saraise/reports/PHASE6-ONWARDS-IMPLEMENTATION-PLAN-2026-01-05.md` (overall plan)
- `/Users/raghunathchava/Code/saraise/reports/WEEK1-COMPLETION-SUMMARY-2026-01-05.md` (Week 1 completion)
- `/Users/raghunathchava/Code/saraise/backend/src/modules/ai_agent_management/` (backend API reference)

---

## Task 1: Install Frontend Dependencies (Day 1 Morning)

### Objective
Install all required frontend dependencies for routing, state management, forms, and UI components.

### Implementation Steps

**Step 1.1: Install Core Dependencies**

```bash
cd /Users/raghunathchava/Code/saraise/frontend

# Routing & State Management
npm install react-router-dom@6.22.0 zustand@4.5.0 @tanstack/react-query@5.28.0

# Form & Validation
npm install react-hook-form@7.54.1 @hookform/resolvers@3.9.1 zod@3.24.1

# UI Components (Radix UI primitives)
npm install @radix-ui/react-dialog@1.1.1 \
            @radix-ui/react-dropdown-menu@2.1.1 \
            @radix-ui/react-select@2.1.1 \
            @radix-ui/react-tabs@1.1.0 \
            @radix-ui/react-toast@1.2.1 \
            @radix-ui/react-label@2.1.0 \
            @radix-ui/react-slot@1.1.0

# Icons & Utilities
npm install lucide-react@0.454.0 \
            date-fns@2.30.0 \
            clsx@2.1.1 \
            tailwind-merge@2.3.0

# Styling
npm install -D tailwindcss@3.4.17 postcss@8.4.38 autoprefixer@10.4.19
```

**Step 1.2: Configure Tailwind CSS**

Create `frontend/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

Create `frontend/postcss.config.js`:
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

Update `frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

**Acceptance Criteria**:
- ✅ All dependencies installed
- ✅ Tailwind CSS configured
- ✅ Build succeeds: `npm run build`
- ✅ Dev server starts: `npm run dev`

---

## Task 2: Extend API Client (Day 1 Afternoon)

### Objective
Extend ApiClient with all HTTP methods (POST, PUT, DELETE, PATCH) and proper error handling.

### Implementation Steps

**Step 2.1: Extend ApiClient**

Update `frontend/src/services/api-client.ts` to include:
- POST, PUT, DELETE, PATCH methods
- Request/response interceptors
- Error handling with proper types
- Session cookie handling (already done via credentials: 'include')

**Acceptance Criteria**:
- ✅ All HTTP methods implemented
- ✅ Error handling with typed errors
- ✅ Request/response interceptors working
- ✅ Session cookies handled automatically

---

## Task 3: Authentication UI (Days 2-3)

### Objective
Implement complete authentication UI with login, session management, and protected routes.

### Implementation Steps

**Step 3.1: Create Auth Service**

Create `frontend/src/services/auth-service.ts`:
- `login(email, password)` - POST to `/api/v1/auth/login`
- `logout()` - POST to `/api/v1/auth/logout`
- `getCurrentUser()` - GET from `/api/v1/auth/me`
- `refreshSession()` - Refresh session validity

**Step 3.2: Create Auth Store (Zustand)**

Create `frontend/src/stores/auth-store.ts`:
- User state (current user, isAuthenticated)
- Login/logout actions
- Session refresh logic

**Step 3.3: Create Login Page**

Create `frontend/src/pages/auth/LoginPage.tsx`:
- Email/password form (React Hook Form + Zod)
- Error handling
- MFA challenge UI (TOTP input)
- Redirect after successful login

**Step 3.4: Create Protected Route**

Create `frontend/src/components/auth/ProtectedRoute.tsx`:
- Check authentication status
- Redirect to login if unauthenticated
- Render children if authenticated

**Step 3.5: Update App.tsx with Routing**

Update `frontend/src/App.tsx`:
- React Router setup
- Login route (public)
- Protected routes structure
- 404 handling

**Acceptance Criteria**:
- ✅ Login page functional
- ✅ Session management working
- ✅ Protected routes enforced
- ✅ Logout functionality working

---

## Task 4: AI Agent Management UI (Days 3-5)

### Objective
Implement 5 pages for AI Agent Management module.

### Implementation Steps

**Step 4.1: Create Service Client**

Create `frontend/src/modules/ai_agent_management/services/ai-agent-service.ts`:
- All CRUD operations
- Custom actions (execute, pause, resume, terminate)
- Use generated TypeScript types (when available)

**Step 4.2: Create Agent List Page**

Create `frontend/src/modules/ai_agent_management/pages/AgentListPage.tsx`:
- Table with agents (TanStack Query)
- Filters (by type, status)
- Search functionality
- Create agent button
- Pagination

**Step 4.3: Create Agent Detail Page**

Create `frontend/src/modules/ai_agent_management/pages/AgentDetailPage.tsx`:
- Agent overview
- Execution history table
- Quota usage display
- Pause/resume/terminate controls
- Edit button

**Step 4.4: Create Agent Creation Form**

Create `frontend/src/modules/ai_agent_management/pages/CreateAgentPage.tsx`:
- Form with validation (React Hook Form + Zod)
- Identity type selection (user-bound/system-bound)
- Framework selection
- Config JSON editor
- Submit handler

**Step 4.5: Create Execution Monitor Page**

Create `frontend/src/modules/ai_agent_management/pages/ExecutionMonitorPage.tsx`:
- Real-time execution status (TanStack Query polling)
- Logs display
- Tool invocation history
- Approval queue integration

**Step 4.6: Create Approval Queue Page**

Create `frontend/src/modules/ai_agent_management/pages/ApprovalQueuePage.tsx`:
- Pending approvals list
- SoD violation warnings
- Approve/reject actions
- Approval details modal

**Step 4.7: Add Module Routes**

Update `frontend/src/App.tsx`:
- Add routes for all 5 pages
- Lazy loading for code splitting
- Protected route wrapper

**Acceptance Criteria**:
- ✅ All 5 pages operational
- ✅ Full CRUD operations working
- ✅ Real-time updates via TanStack Query
- ✅ Form validation working
- ✅ Error handling implemented

---

## Success Criteria (Week 2 Complete)

### Functional Requirements
- ✅ Login page functional
- ✅ Protected routes enforced
- ✅ Agent list page displays agents
- ✅ Agent detail page shows execution history
- ✅ Agent creation form validates and submits
- ✅ Execution monitor shows real-time status
- ✅ Approval queue allows approve/reject

### Quality Requirements
- ✅ TypeScript strict mode passes
- ✅ ESLint passes with zero warnings
- ✅ Components use proper TypeScript types
- ✅ Error boundaries implemented
- ✅ Loading states displayed

---

## Next Steps (Week 3)

After Week 2 completion:
1. **Week 3**: Module Routing Framework + Reusable UI Components
2. **Week 4**: Testing + Documentation + Deployment

See `reports/PHASE6-ONWARDS-IMPLEMENTATION-PLAN-2026-01-05.md` for complete timeline.

---

**END OF WEEK 2 EXECUTION PROMPT**

