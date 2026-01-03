# backend/tests/

Purpose
- Backend test suite (unit/integration) with coverage enforcement.

Conventions
- Prefer fixtures from `backend/tests/conftest.py` once implemented.
- Tests must validate tenant isolation and deny-by-default authorization behavior.
