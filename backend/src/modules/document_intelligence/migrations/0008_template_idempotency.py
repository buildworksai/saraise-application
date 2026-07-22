"""Make template creation tenant-idempotent."""

from django.db import migrations, models


def populate_keys(apps, schema_editor) -> None:
    Template = apps.get_model("document_intelligence", "ExtractionTemplate")
    for template in Template.objects.using(schema_editor.connection.alias).filter(idempotency_key="").iterator():
        template.idempotency_key = f"legacy:{template.id}"
        template.save(update_fields=["idempotency_key"])


class Migration(migrations.Migration):
    dependencies = [("document_intelligence", "0007_immutable_evidence_guards")]
    operations = [
        migrations.AddField(
            model_name="extractiontemplate",
            name="idempotency_key",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.RunPython(populate_keys, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="extractiontemplate",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"), name="docintel_template_tenant_idem_uniq"
            ),
        ),
    ]
