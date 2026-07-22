# Inventory Management Backend

This module implements the open-source inventory core at
`/api/v2/inventory-management/`: tenant-owned warehouses, storage locations,
items, batches, serial numbers, governed stock entries, immutable valued ledger
evidence, balances, reservations, cycle counts, and runtime configuration.

Mutation rules live in `services.py`; API adapters never save models directly.
State changes pass through `state_machines.py`. PostgreSQL FORCE RLS and
composite tenant foreign keys provide database-level isolation, while every
query path also uses the canonical tenant manager. Configuration is
environment-specific, validated, revisioned, previewable, audited, portable,
and rollback-capable without a restart.

Paid and industry capabilities register against the immutable protocols in
`extensions.py` and consume the stable `/v1` domain events from `events.py`.
They do not receive unrestricted querysets and cannot alter core ledger
invariants. Missing extensions fail explicitly as unavailable while the core
continues to operate.

Verification uses the repository-provided interpreter and the exact command in
`UNIT_BRIEF.md`; mutation testing is not wired and no mutation score is claimed.
