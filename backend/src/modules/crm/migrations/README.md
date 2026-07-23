# CRM migration runbook

Migrations `0001`–`0004` are applied history. The empty `0001` placeholder was
repaired by moving the real initial schema operations from `0002` into `0001`;
`0002` remains as a schema-empty compatibility node so databases that
already recorded both migration names retain a coherent graph. New databases
create the schema in `0001`, while existing databases do not replay either
node. Its only operation verifies that all five initial tables exist and stops
with an explicit ledger-repair error if it encounters the partial legacy state
where the placeholder `0001` was recorded but the former schema-creating `0002`
was not. The production reconciliation begins at `0005` and follows expand,
validate, protect:

1. `0005_reconcile_crm_persistence` adds audit/version/provenance columns,
   widens actor identifiers, records original legacy values in each row's
   `__crm_0005_original__` metadata marker, and normalizes rows before any new
   constraint is installed. No pre-existing row is dropped.
2. `0006_validate_constraints_and_indexes` fails before constraint creation if
   any reconciled row is invalid. It then adds database constraints and creates
   composite indexes concurrently on PostgreSQL. This migration is non-atomic
   because PostgreSQL prohibits concurrent index creation in a transaction.
3. `0007_same_tenant_reference_guards` installs database triggers for the
   logical CRM UUID references and immutable activity evidence.
4. `0008_enable_crm_rls` installs typed policies keyed to `app.tenant_id`, then
   enables and forces RLS on all five CRM tables.
5. `0009_tenant_configuration` adds tenant-scoped configuration, version,
   immutable audit, and idempotency tables with RLS.
6. `0010_harden_activity_evidence_trigger` upgrades databases that already
   applied `0007` so the evidence guard covers both `UPDATE` and `DELETE`.
   Its reverse operation restores the exact prior function and trigger.

## Deployment order and compatibility window

Deploy application code that can read both the `0004` and expanded `0005`
shapes before applying `0005`. Apply migrations one application instance at a
time, then deploy writers that require `version`, `updated_by`, scoring
provenance, and transition history. Do not enable new writers before every
instance can read those fields.

`0005` takes brief metadata/row locks for column additions and type changes and
updates existing rows in deterministic primary-key order. Schedule it outside
peak write volume and monitor transaction age. `0006` validates with bounded
table scans and uses concurrent PostgreSQL index builds; those builds take
`SHARE UPDATE EXCLUSIVE` rather than blocking ordinary reads/writes, but they
can wait behind long transactions. Constraint installation takes a short schema
lock after validation. Trigger and RLS installation take short table locks.

After `0008`, web requests and workers must enter `tenant_context` or
`tenant_context_worker`. A missing or malformed `app.tenant_id` intentionally
returns no rows and rejects writes. Migration and verification roles should be
separate from the application role; RLS tests must use a `NOSUPERUSER
NOBYPASSRLS` non-owner role.

Apply through `0010` even when `0007` is already recorded as applied. Editing
an applied migration file cannot replace the trigger in a live database;
`0010` is the required forward repair.

## Verification

On PostgreSQL 17, run:

```bash
python manage.py migrate crm 0010
python manage.py showmigrations crm
python manage.py sqlmigrate crm 0010
pytest src/modules/crm/tests/test_migrations.py -q
```

Confirm `relrowsecurity` and `relforcerowsecurity` are true for
`crm_leads`, `crm_accounts`, `crm_contacts`, `crm_opportunities`, and
`crm_activities`, and confirm each has a `tenant_isolation_<table>` policy.
Also confirm `crm_activity_immutable_guard` fires on both `UPDATE` and
`DELETE`.

## Rollback

Stop new CRM writes, retain a database snapshot, then run:

```bash
python manage.py migrate crm 0004
```

Reversal removes RLS policies, triggers, new constraints, and indexes before
restoring normalized legacy values and removing expansion columns. The physical
`created_by` columns are restored to `varchar(36)`. Actor identifiers written
after the forward widening to `varchar(255)` that exceed the legacy width are first moved losslessly into a
reserved metadata key. A later forward migration widens the column, restores
those identifiers, and removes the reserved key. This compensating rollback
avoids both truncation and a state/database schema mismatch.

Test the required forward/reverse/forward sequence against a production-sized
copy before rollout:

```bash
python manage.py migrate crm 0010
python manage.py migrate crm 0004
python manage.py migrate crm 0010
```
