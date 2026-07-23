from django.db import migrations

def validate_quote_rows(apps, schema_editor):
    QuoteLine = apps.get_model("purchase_management", "SupplierQuoteLine")
    invalid = list(QuoteLine.objects.filter(quantity__lte=0).values_list("id", flat=True))
    if invalid: raise RuntimeError(f"Invalid zero/negative quote line quantities: {invalid}")

class Migration(migrations.Migration):
    dependencies = [("purchase_management", "0003_requisition_lines")]
    operations = [migrations.RunPython(validate_quote_rows, migrations.RunPython.noop)]

