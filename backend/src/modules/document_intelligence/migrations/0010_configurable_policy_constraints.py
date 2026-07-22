"""Remove fixed business thresholds while retaining structural integrity."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("document_intelligence", "0009_quota_reservation")]
    operations = [
        migrations.AlterField(
            model_name="extractiontemplate",
            name="match_threshold",
            field=models.DecimalField(decimal_places=4, max_digits=5),
        ),
        migrations.RemoveConstraint(model_name="classifiertrainingjob", name="docintel_training_minimum_count"),
        migrations.RemoveConstraint(model_name="documentclassification", name="docintel_classification_secondary_pair"),
        migrations.RemoveConstraint(
            model_name="documentclassification", name="docintel_classification_low_conf_review"
        ),
        migrations.AddConstraint(
            model_name="documentclassification",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(secondary_category="", secondary_confidence__isnull=True)
                    | (models.Q(secondary_category__gt="") & models.Q(secondary_confidence__isnull=False))
                ),
                name="docintel_classification_secondary_pair",
            ),
        ),
    ]
