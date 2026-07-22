"""Record the runtime-contract migration boundary.

State machines, async handlers, statement parsers, and candidate providers use
the process-local registries in :mod:`src.core`; none has a persistence table.
Their owning modules perform idempotent runtime registration.  This deliberately
data-neutral migration gives deployments an explicit reversible contract version
without inventing database state that could drift from the executable registry.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("bank_reconciliation", "0004_domain_rls")]

    operations = []
