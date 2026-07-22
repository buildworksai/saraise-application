# Budget Management API v2

Base path: `/api/v2/budget-management/`

All successful JSON responses use `{"data": ..., "meta": ...}`. Collection
metadata includes governed pagination. Errors use the stable core error envelope
and carry a correlation ID. Session authentication, strict CSRF, tenant identity,
entitlement, action permission, and quota checks fail closed.

## Resources and commands

| Path | Methods |
| --- | --- |
| `budgets/` | `GET`, `POST` |
| `budgets/{id}/` | `GET`, `PATCH`, `DELETE` |
| `budgets/{id}/allocations/` | `PUT` |
| `budgets/{id}/submit/` | `POST` |
| `budgets/{id}/approve/` | `POST` |
| `budgets/{id}/reject/` | `POST` |
| `budgets/{id}/revise/` | `POST` |
| `budgets/{id}/close/` | `POST` |
| `budgets/{id}/variance/` | `GET` |
| `budgets/{id}/sync-actuals/` | `POST` (`202`) |
| `budget-lines/` | `GET`, `POST` |
| `budget-lines/{id}/` | `GET`, `PATCH`, `DELETE` |
| `approvals/`, `approvals/{id}/` | `GET` |
| `variance-alerts/`, `variance-alerts/{id}/` | `GET` |
| `variance-alerts/generate/` | `POST` (`202`) |
| `variance-alerts/{id}/acknowledge/` | `POST` |
| `availability/` | `POST` |
| `health/` | `GET` |

`PATCH`, `DELETE`, and allocation replacement require `expected_updated_at`.
Lifecycle and durable-work commands require an idempotency key. Cross-tenant
identifiers are indistinguishable from missing resources and return `404`.

## Stable domain failures

| Code | Status | Meaning |
| --- | ---: | --- |
| `CONCURRENT_UPDATE` | 409 | The aggregate changed since it was loaded. |
| `ILLEGAL_STATE` | 409 | The requested mutation is not legal now. |
| `IDEMPOTENCY_CONFLICT` | 409 | A key was already used for another command. |
| `CEILING_MISMATCH` | 409 | Allocations do not exactly match the ceiling. |
| `SELF_APPROVAL_FORBIDDEN` | 403 | A submitter attempted their own decision. |
| `NOT_FOUND` | 404 | No resource exists in the active tenant. |
| `CAPABILITY_UNAVAILABLE` | 503 | A required optional adapter is absent. |
| `DEPENDENCY_UNAVAILABLE` | 503 | Timeout, open circuit, or transport failure. |

Availability returns `200` for both sufficient and insufficient results because
insufficiency is a valid deterministic business result. Missing allocations set
`unbudgeted=true` and can never be treated as sufficient.
