from django.db import migrations

EVENTS = ("purchase.rfq.publish.v1", "purchase.rfq.awarded.v1", "purchase.order.approved.v1", "purchase.order.dispatch.v1", "purchase.receipt.completed.v1", "purchase.inventory.post-receipt.v1", "purchase.configuration.activated.v1")

def validate_contract(apps, schema_editor):
    if len(EVENTS) != len(set(EVENTS)): raise RuntimeError("Duplicate purchase domain event contract")

class Migration(migrations.Migration):
    dependencies = [("purchase_management", "0007_purchase_management_rls")]
    operations = [migrations.RunPython(validate_contract, migrations.RunPython.noop)]
