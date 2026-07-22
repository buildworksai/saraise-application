# CRM migration runbook

Migrations `0001`–`0004` are applied history and must not be edited. The
production reconciliation begins at `0005` and follows expand, validate,
protect:

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

## Verification

On PostgreSQL 17, run:

```bash
python manage.py migrate crm 0008
python manage.py showmigrations crm
python manage.py sqlmigrate crm 0008
pytest src/modules/crm/tests/test_migrations.py -q
```

Confirm `relrowsecurity` and `relforcerowsecurity` are true for
`crm_leads`, `crm_accounts`, `crm_contacts`, `crm_opportunities`, and
`crm_activities`, and confirm each has a `tenant_isolation_<table>` policy.

## Rollback

Stop new CRM writes, retain a database snapshot, then run:

```bash
python manage.py migrate crm 0004
```

Reversal removes RLS policies, triggers, new constraints, and indexes before
restoring normalized legacy values and removing expansion columns. The physical
`created_by` columns intentionally remain `varchar(255)` during rollback even
though Django's `0004` state declares 36 characters. This is a safe compatibility
superset and prevents loss or rollback failure for actor identifiers written
after expansion. Old application versions continue to write 36-character actor
identifiers; a later forward migration recognizes the already-wide column.

Test the required forward/reverse/forward sequence against a production-sized
copy before rollout:

```bash
python manage.py migrate crm 0008
python manage.py migrate crm 0004
python manage.py migrate crm 0008
```
