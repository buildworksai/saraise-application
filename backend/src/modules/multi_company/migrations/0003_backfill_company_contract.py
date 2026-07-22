"""Backfill the legacy company table before enforcing the v2 contract."""

from django.db import migrations, models


MIGRATION_ACTOR = "system:migration:multi-company-v2"


def _tenant_currency(apps, tenant_id):
    Config = apps.get_model("multi_company", "MultiCompanyConfigurationVersion")
    active = Config.objects.filter(tenant_id=tenant_id, status="active").order_by("-version").first()
    if active:
        value = (active.settings or {}).get("default_currency")
        if isinstance(value, str) and len(value.strip()) == 3:
            return value.strip().upper()

    # Legacy tenant metadata is used only for this expand/contract migration.
    # Runtime code never imports or bypasses the published module interfaces.
    try:
        Tenant = apps.get_model("tenant_management", "Tenant")
    except LookupError:
        return None
    tenant = Tenant.objects.filter(pk=tenant_id).first()
    value = getattr(tenant, "default_currency", None) if tenant else None
    return value.strip().upper() if isinstance(value, str) and len(value.strip()) == 3 else None


def backfill_company_contract(apps, schema_editor):
    Company = apps.get_model("multi_company", "Company")
    seen = set()
    pending = []
    for company in Company.objects.all().order_by("tenant_id", "created_at", "id"):
        normalised = company.company_code.strip().upper()
        collision_key = (company.tenant_id, normalised)
        if collision_key in seen:
            raise RuntimeError(
                f"MULTI_COMPANY_CODE_COLLISION: tenant={company.tenant_id}; code={normalised}; remediate before migration"
            )
        seen.add(collision_key)
        currency = company.currency.strip().upper() if company.currency else _tenant_currency(apps, company.tenant_id)
        if not currency:
            raise RuntimeError(
                f"MULTI_COMPANY_CURRENCY_REQUIRED: tenant={company.tenant_id}; company={company.id}; "
                "configure an active default_currency before migration"
            )
        company.company_code = normalised
        company.legal_name = company.legal_name.strip() or company.company_name
        company.currency = currency
        company.created_by = company.created_by or MIGRATION_ACTOR
        company.updated_by = company.updated_by or MIGRATION_ACTOR
        pending.append(company)
    if pending:
        Company.objects.bulk_update(
            pending, ["company_code", "legal_name", "currency", "created_by", "updated_by"]
        )


def reverse_backfill(apps, schema_editor):
    # Legacy fields are intentionally retained. Normalisation is not reversed
    # because the preflight proves it is uniqueness-preserving and canonical.
    del apps, schema_editor


class Migration(migrations.Migration):
    dependencies = [("multi_company", "0002_companyaccessgrant_configurationauditrecord_and_more")]

    operations = [
        migrations.RunPython(backfill_company_contract, reverse_backfill),
        migrations.AlterField(
            model_name="company", name="legal_name", field=models.CharField(max_length=255)
        ),
        migrations.AlterField(model_name="company", name="currency", field=models.CharField(max_length=3)),
    ]
