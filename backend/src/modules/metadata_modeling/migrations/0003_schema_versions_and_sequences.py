"""Create immutable schema/resource histories and naming sequences."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

UNKNOWN_ACTOR_ID = uuid.UUID(int=0)


class Migration(migrations.Migration):
    dependencies = [("metadata_modeling", "0002_tenant_foundation_and_audit")]

    operations = [
        migrations.CreateModel(
            name="EntitySchemaVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("candidate", "Candidate"),
                            ("published", "Published"),
                            ("superseded", "Superseded"),
                            ("rejected", "Rejected"),
                        ],
                        default="candidate",
                        max_length=16,
                    ),
                ),
                ("schema", models.JSONField()),
                ("schema_hash", models.CharField(max_length=64)),
                ("change_summary", models.TextField(blank=True)),
                (
                    "compatibility",
                    models.CharField(
                        choices=[
                            ("compatible", "Compatible"),
                            ("requires_backfill", "Requires backfill"),
                            ("breaking", "Breaking"),
                        ],
                        default="compatible",
                        max_length=24,
                    ),
                ),
                ("validation_report", models.JSONField(blank=True, default=dict)),
                ("published_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("published_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("created_by", models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "based_on_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="derived_versions",
                        to="metadata_modeling.entityschemaversion",
                    ),
                ),
                (
                    "entity_definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="metadata_modeling.entitydefinition",
                    ),
                ),
            ],
            options={"ordering": ["-version"]},
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="active_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="metadata_modeling.entityschemaversion",
            ),
        ),
        migrations.AddField(
            model_name="fielddefinition",
            name="schema_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fields",
                to="metadata_modeling.entityschemaversion",
            ),
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="schema_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="resources",
                to="metadata_modeling.entityschemaversion",
            ),
        ),
        migrations.CreateModel(
            name="DynamicResourceVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                (
                    "state",
                    models.CharField(
                        choices=[("draft", "Draft"), ("submitted", "Submitted"), ("cancelled", "Cancelled")],
                        max_length=16,
                    ),
                ),
                ("record_key", models.CharField(max_length=160)),
                ("display_name", models.CharField(max_length=255)),
                ("data", models.JSONField(blank=True)),
                ("changed_fields", models.JSONField(blank=True, default=list)),
                (
                    "operation",
                    models.CharField(
                        choices=[
                            ("create", "Create"),
                            ("update", "Update"),
                            ("submit", "Submit"),
                            ("cancel", "Cancel"),
                            ("delete", "Delete"),
                            ("restore", "Restore"),
                        ],
                        max_length=16,
                    ),
                ),
                ("changed_by", models.UUIDField()),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "resource",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="metadata_modeling.dynamicresource",
                    ),
                ),
                (
                    "schema_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="metadata_modeling.entityschemaversion",
                    ),
                ),
            ],
            options={"ordering": ["-version"]},
        ),
        migrations.CreateModel(
            name="NamingSequence",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sequence_key", models.SlugField(default="default", max_length=100)),
                ("prefix_template", models.CharField(max_length=120)),
                ("next_value", models.PositiveBigIntegerField(default=1)),
                ("padding", models.PositiveSmallIntegerField(default=5)),
                (
                    "reset_period",
                    models.CharField(
                        choices=[("never", "Never"), ("yearly", "Yearly"), ("monthly", "Monthly")],
                        default="never",
                        max_length=12,
                    ),
                ),
                ("period_key", models.CharField(blank=True, max_length=10)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "entity_definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="naming_sequences",
                        to="metadata_modeling.entitydefinition",
                    ),
                ),
            ],
            options={"ordering": ["entity_definition", "sequence_key", "period_key"]},
        ),
    ]
