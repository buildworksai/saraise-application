"""Backfill deterministic domain state for rows created by migration 0001.

``LEGACY_SYSTEM_ACTOR_ID`` is a reserved, non-user identity used only to make
the provenance of pre-audit records explicit. It must never be assigned to an
interactive user or accepted from an API request.
"""

from decimal import Decimal
from uuid import UUID

from django.db import migrations, models


LEGACY_SYSTEM_ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")


def backfill_budget_domain(apps, schema_editor):
    Budget = apps.get_model("budget_management", "Budget")
    BudgetLine = apps.get_model("budget_management", "BudgetLine")
    database = schema_editor.connection.alias

    Budget.objects.using(database).filter(budget_type__isnull=True).update(budget_type="operating")
    Budget.objects.using(database).filter(created_by__isnull=True).update(created_by=LEGACY_SYSTEM_ACTOR_ID)
    Budget.objects.using(database).filter(updated_by__isnull=True).update(updated_by=LEGACY_SYSTEM_ACTOR_ID)
    # Approval fields did not exist in 0001. Preserve the legacy lifecycle
    # state while making its system-derived provenance explicit.
    Budget.objects.using(database).filter(status__in=["approved", "closed"], approved_at__isnull=True).update(
        approved_at=models.F("updated_at"),
        approved_by=LEGACY_SYSTEM_ACTOR_ID,
    )

    BudgetLine.objects.using(database).filter(period_type__isnull=True).update(period_type="annual")
    BudgetLine.objects.using(database).filter(period_number__isnull=True).update(period_number=1)
    BudgetLine.objects.using(database).filter(created_by__isnull=True).update(created_by=LEGACY_SYSTEM_ACTOR_ID)
    BudgetLine.objects.using(database).filter(updated_by__isnull=True).update(updated_by=LEGACY_SYSTEM_ACTOR_ID)

    # The legacy model stored actual-budget. The governed definition is
    # budget-actual; update in SQL so every row changes atomically.
    BudgetLine.objects.using(database).update(variance=models.F("budget_amount") - models.F("actual_amount"))

    for budget in Budget.objects.using(database).all().iterator():
        result = BudgetLine.objects.using(database).filter(
            tenant_id=budget.tenant_id,
            budget_id=budget.pk,
            is_deleted=False,
        ).aggregate(total=models.Sum("budget_amount"))
        Budget.objects.using(database).filter(pk=budget.pk).update(
            total_budget=result["total"] or Decimal("0.00")
        )


def restore_legacy_domain(apps, schema_editor):
    Budget = apps.get_model("budget_management", "Budget")
    BudgetLine = apps.get_model("budget_management", "BudgetLine")
    database = schema_editor.connection.alias

    # Migration 0001's persisted formula was actual-budget. Restoring it is
    # required for a faithful latest -> 0001 rollback.
    BudgetLine.objects.using(database).update(variance=models.F("actual_amount") - models.F("budget_amount"))
    BudgetLine.objects.using(database).filter(created_by=LEGACY_SYSTEM_ACTOR_ID).update(created_by=None)
    BudgetLine.objects.using(database).filter(updated_by=LEGACY_SYSTEM_ACTOR_ID).update(updated_by=None)
    BudgetLine.objects.using(database).filter(period_type="annual", period_number=1).update(
        period_type=None,
        period_number=None,
    )
    Budget.objects.using(database).filter(created_by=LEGACY_SYSTEM_ACTOR_ID).update(created_by=None)
    Budget.objects.using(database).filter(updated_by=LEGACY_SYSTEM_ACTOR_ID).update(updated_by=None)
    Budget.objects.using(database).filter(approved_by=LEGACY_SYSTEM_ACTOR_ID).update(
        approved_at=None,
        approved_by=None,
    )
    Budget.objects.using(database).filter(budget_type="operating").update(budget_type=None)


class Migration(migrations.Migration):
    dependencies = [("budget_management", "0002_expand_budget_domain")]

    operations = [migrations.RunPython(backfill_budget_domain, restore_legacy_domain)]
