---
description: TypeScript coding standards, Vite + React development standards, and error handling for SARAISE frontend
globs: frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# 🔧 SARAISE Frontend Standards (TypeScript + Error Handling)

**Rule IDs**: SARAISE-03001 to SARAISE-03014, SARAISE-14001 to SARAISE-14004
**Consolidates**: `05-frontend-standards.md`, `05-frontend-standards.md`

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Module Framework: `docs/architecture/module-framework.md`

---

## TypeScript Standards

### SARAISE-03001 Strict Mode
- Enable strict TypeScript settings; no implicit any.
- Use Vite 5.0+ with TypeScript 5 strict configuration
- Enable all strict flags in `tsconfig.json`

### SARAISE-03002 Explicit Types
```ts
// Good
async function getUserById(id: string): Promise<User | null> { /* ... */ }

// Bad (inferred)
async function getUserById(id) { /* ... */ }
```

### SARAISE-03003 No `any`
```ts
// Forbidden
function handleData(data: any) {}

// Use generics or unknown
function handleData<T>(data: T) {}
function handleApiResponse(response: unknown) {}
```

### SARAISE-03004 Prefer Interface Over Type Alias for objects
```ts
interface UserConfig { theme: 'light' | 'dark'; language: string; notifications: boolean; }
```

### SARAISE-03005 React Component Standards
```tsx
// Good - Explicit props interface
interface UserCardProps {
  user: User;
  onEdit?: (user: User) => void;
  className?: string;
}

export default function UserCard({ user, onEdit, className }: UserCardProps) {
  // Component implementation
}

// Bad - Inline props
export default function UserCard(props: any) {
  // Component implementation
}
```

### SARAISE-03012 React Hooks Rules (CRITICAL)

**⚠️ CRITICAL**: All React hooks MUST be called before any conditional early returns.

**✅ CORRECT Hook Placement:**
```tsx
export function Component() {
  // ✅ ALL HOOKS FIRST (before any early returns)
  const navigate = useNavigate()
  const { hasRole } = useAuth()
  const [state, setState] = useState('')
  const { data } = useQuery(...)
  const memoized = useMemo(() => compute(data), [data])
  const callback = useCallback(() => handle(), [])

  // ✅ Early returns AFTER all hooks
  if (!hasRole('admin')) {
    return <AccessDenied />
  }

  if (isLoading) {
    return <Loading />
  }

  return <Content data={memoized} />
}
```

**❌ FORBIDDEN Hook Placement:**
```tsx
export function Component() {
  const navigate = useNavigate()
  const { hasRole } = useAuth()

  // ❌ Early return before all hooks
  if (!hasRole('admin')) {
    return <AccessDenied />
  }

  // ❌ Hook called after early return - VIOLATION!
  const memoized = useMemo(...)  // ERROR: "Rendered more hooks than during the previous render"

  return <Content />
}
```

**JSX Ternary Rules:**
```tsx
// ✅ CORRECT: Multiple elements wrapped in Fragment
{condition ? (
  <>
    <Table>...</Table>
    <Pagination />
  </>
) : (
  <EmptyState />
)}

// ❌ FORBIDDEN: Multiple elements without wrapper
{condition ? (
  <Table>...</Table>
  <Pagination />  // ERROR: "Unexpected token, expected ','"
) : (
  <EmptyState />
)}
```

**ESLint Enforcement:**
- `react-hooks/rules-of-hooks`: **error** - Catches hooks violations
- `react-hooks/exhaustive-deps`: **warn** - Warns about missing dependencies

### SARAISE-03006 Vite + React Component Standards
```tsx
// Good - Proper component typing with Vite
interface AppProps {
  title: string;
  children: React.ReactNode;
}

export default function App({ title, children }: AppProps) {
  return (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  );
}

// Good - Vite environment variables
const apiUrl = import.meta.env.VITE_API_URL;
const isDev = import.meta.env.DEV;
```

### SARAISE-03007 Form Validation with Zod
```tsx
// Good - Zod schema validation
import { z } from 'zod';

const userSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  email: z.string().email('Invalid email'),
  age: z.number().min(18, 'Must be 18 or older'),
});

type UserFormData = z.infer<typeof userSchema>;
```

### SARAISE-03008 API Integration Standards
```tsx
// Good - Typed API responses
interface ApiResponse<T> {
  data: T;
  status: 'success' | 'error';
  message?: string;
}

interface User {
  id: string;
  name: string;
  email: string;
}

async function fetchUser(id: string): Promise<ApiResponse<User>> {
  // API call implementation
}
```

### SARAISE-03009 Dependency Approvals
- All new dependencies require Architecture Change Proposal (ACP) approval. CI blocks unapproved changes.
- Prefer Radix UI components over custom implementations
- Use shadcn/ui patterns for consistent component design
- Use Zustand for client state management
- Use TanStack Query for server state management

### SARAISE-03013 Strict API Typing (NO `any` / `unknown` Blobs)
All `apiClient` calls in `frontend/src/**/*.{ts,tsx}` MUST:
- Use a concrete generic type parameter: `apiClient.get<MyDto>(...)`, `apiClient.post<MyDto>(...)`, etc.
- Use **DTO interfaces exported from the corresponding `*Service` modules** instead of redefining ad-hoc shapes in pages.

**Forbidden patterns:**
- `const data = (await apiClient.get(url)) as any`
- Treating `response.data` as `{}` or `Record<string, unknown>` and then poking arbitrary properties onto it.
- Redefining API response interfaces in `pages/` when a typed service already exists for that endpoint.

If the backend shape is unclear, engineers MUST:
- First define or update the correct TypeScript interface in the service module.
- Only then wire UI code against that interface.

### SARAISE-03014 Shared UI Component Contracts

Shared UI components (e.g., `Tabs`, `MetricCard`, chart wrappers, `Popover`) MUST have **strict, closed prop types**:
- No index signatures (no `[key: string]: any`).
- No `any` props and no untyped `unknown` props.

**Tabs standards:**
- Use a **controlled** API only: `value` and `onValueChange` are required; `defaultValue` is banned unless explicitly supported.
- Route-specific or dashboard-specific Tabs MAY NOT add arbitrary props.

**MetricCard standards:**
- `value` MUST be a formatted display value (usually `string`), not a raw `number` or arbitrary object.
- `trend` MUST be a strict object shape (e.g., `{ value: number; isPositive: boolean }`).

**Charts standards:**
- All simple charts MUST take `Array<{ name: string; value: number }>` as their data shape.
- Arbitrary `{ [key: string]: any }` or `Record<string, unknown>` inputs to chart components are forbidden.

**Popover / Calendar standards:**
- Only exports that actually exist in `@/components/ui/popover` and `@/components/ui/calendar` may be imported.

### SARAISE-03010 Environment-Aware XSS Prevention
- **Development Environment:** Basic XSS prevention for development
- **Staging Environment:** Standard XSS prevention for testing
- **Production Environment:** Maximum XSS prevention and sanitization

See [XSS Prevention Class](docs/architecture/examples/frontend/lib/xss-prevention.ts).

See [Safe HTML Component](docs/architecture/examples/frontend/components/SafeHTML.tsx).

See [Environment-Aware Form Validation](docs/architecture/examples/frontend/lib/environment-aware-validation.ts).

### SARAISE-03011 Vite Build Configuration
- **Development Environment:** Fast HMR and dev server
- **Staging Environment:** Optimized builds with source maps
- **Production Environment:** Fully optimized builds

See [Vite Configuration](docs/architecture/examples/frontend/vite.config.ts).

---

## Error Handling & Troubleshooting

### SARAISE-14001 Error Handling Patterns

**Backend Error Handling:**

See [Backend Error Handling](docs/architecture/examples/backend/services/error-handling-backend.py).

**Key Error Classes:**
- `SARAISEError` (base), `AuthenticationError`, `AuthorizationError`, `ValidationError`
- `DatabaseError`, `ExternalServiceError`, `TenantIsolationError`
- `AIAgentError`, `WorkflowError`

**Key Handlers:**
- `handle_saraise_error()`, `handle_authentication_error()`, `handle_authorization_error()`
- `handle_validation_error()`, `handle_database_error()`, `handle_external_service_error()`
- `global_exception_handler()` for unhandled exceptions

**Frontend Error Handling:**

See [Frontend Error Handling](docs/architecture/examples/frontend/services/error-handling-frontend.ts).

**Key Components:**
- `SARAISEErrorHandler` class with error-specific handlers
- `useErrorHandler()` React hook
- `APIClient` class with automatic error handling

### SARAISE-14002 Troubleshooting Guide

**Common Issues and Solutions:**

1. **Authentication Issues** - User cannot log in / Session tokens not working
   See [Authentication Troubleshooting](docs/architecture/examples/troubleshooting/auth-issues.sh)

2. **Database Issues** - Database connection failures / Migration failures
   See [Database Troubleshooting](docs/architecture/examples/troubleshooting/database-issues.sh)

3. **Multi-Tenant Issues** - Tenant isolation failures
   See [Tenant Troubleshooting](docs/architecture/examples/troubleshooting/tenant-issues.sh)

4. **AI Agent Issues** - AI agents not responding

5. **Workflow Issues** - Workflows failing to execute
   See [Agent and Workflow Troubleshooting](docs/architecture/examples/troubleshooting/agent-workflow-issues.sh)

**Environment-Specific Troubleshooting:**

See [Environment Troubleshooting](docs/architecture/examples/troubleshooting/environment-troubleshooting.sh) for complete troubleshooting commands.

### SARAISE-14003 Monitoring and Alerting

**Health Check Endpoints:**

See [Health Check Endpoints](docs/architecture/examples/backend/services/health-check-endpoints.py).

**Logging Configuration:**

See [Logging Configuration](docs/architecture/examples/backend/core/logging-config.py).

### SARAISE-14004 Performance Troubleshooting

**Database Performance:**

See [Database Performance Queries](docs/architecture/examples/troubleshooting/database-performance-queries.sql) for complete SQL queries.

**Application Performance:**

See [Performance Monitoring](docs/architecture/examples/backend/core/performance-monitoring.py).

---

**Audit**: Version 7.0.0; Consolidated 2025-12-23
