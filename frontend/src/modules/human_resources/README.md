# Human Resources frontend

The open-source HR core provides tenant-governed department hierarchy, employee lifecycle, attendance, leave allocation, and leave requests. Payroll, recruitment, performance, learning, compensation, and AI recommendations are intentionally not implemented here.

## Architecture

- `contracts.ts` owns every DTO, enum, endpoint, UI route, query parameter, envelope guard, and TanStack Query key.
- `services/hr-service.ts` strictly decodes API v2 envelopes and normalizes authentication, policy, validation, conflict, capability, and network failures.
- `routes.ts` owns five sidebar routes and fifteen contextual routes. The tenant route registry discovers it automatically.
- `components/` contains accessible page states, confirmation flows, unsaved-change protection, and typed resource forms.
- `pages/` contains all overview, list, detail, create, and edit workflows.

Mutations are shown only when the API returns the exact required capability. Missing decisions fail closed. Lifecycle, clock, and leave actions use one idempotency key per user intent; leave submission retains its key through refresh until a successful response.

## Extension surface

Paid modules add verified routes and consume versioned HR events. They do not patch these DTOs with provider fields or render invented payroll/performance data. Optional self/team leave views return an explicit capability-unavailable failure until a secure actor-to-employee resolver is installed.

## Verification

```bash
npm run typecheck
npx eslint src/modules/human_resources --ext .ts,.tsx --max-warnings 0
npx vitest run src/modules/human_resources
npm run build
```
