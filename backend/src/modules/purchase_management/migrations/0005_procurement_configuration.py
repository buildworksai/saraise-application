from django.db import migrations

def validate_configuration_rows(apps, schema_editor):
    Config = apps.get_model("purchase_management", "ProcurementConfiguration")
    invalid = list(Config.objects.exclude(receipt_tolerance_percent__gte=0, receipt_tolerance_percent__lte=100).values_list("id", flat=True))
    if invalid: raise RuntimeError(f"Invalid procurement configuration rows: {invalid}")

class Migration(migrations.Migration):
    dependencies = [("purchase_management", "0004_rfq_and_quotes")]
    operations = [migrations.RunPython(validate_configuration_rows, migrations.RunPython.noop)]

