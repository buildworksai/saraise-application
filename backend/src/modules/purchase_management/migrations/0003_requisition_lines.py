from django.db import migrations

def validate_and_backfill(apps, schema_editor):
    Line = apps.get_model("purchase_management", "PurchaseRequisitionLine")
    invalid = list(Line.objects.filter(quantity__lte=0).values_list("id", flat=True))
    if invalid: raise RuntimeError(f"Invalid zero/negative requisition line quantities: {invalid}")
    Requisition = apps.get_model("purchase_management", "PurchaseRequisition")
    Requisition.objects.filter(total_amount__isnull=True).update(total_amount=0)

class Migration(migrations.Migration):
    dependencies = [("purchase_management", "0002_adopt_tenant_foundation")]
    operations = [migrations.RunPython(validate_and_backfill, migrations.RunPython.noop)]

