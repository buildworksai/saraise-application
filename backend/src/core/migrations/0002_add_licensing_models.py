# Generated for Phase 7.5: Licensing Subsystem
# Django models for license storage in self-hosted mode

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("domain", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Organization",
                "verbose_name_plural": "Organizations",
                "db_table": "licensing_organization",
            },
        ),
        migrations.CreateModel(
            name="License",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("license_key", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("trial", "Trial"),
                            ("active", "Active"),
                            ("expired", "Expired"),
                            ("grace", "Grace Period"),
                            ("locked", "Locked"),
                        ],
                        default="trial",
                        max_length=20,
                    ),
                ),
                ("core_tier", models.CharField(default="free", max_length=20)),
                ("max_companies", models.IntegerField(default=1)),
                ("max_users", models.IntegerField(default=-1)),
                ("industry_modules", models.JSONField(default=list)),
                ("trial_started_at", models.DateTimeField(blank=True, null=True)),
                ("trial_ends_at", models.DateTimeField(blank=True, null=True)),
                ("license_issued_at", models.DateTimeField(blank=True, null=True)),
                ("license_expires_at", models.DateTimeField(blank=True, null=True)),
                ("grace_ends_at", models.DateTimeField(blank=True, null=True)),
                ("last_validated_at", models.DateTimeField(blank=True, null=True)),
                ("validation_failures", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.organization"),
                ),
            ],
            options={
                "verbose_name": "License",
                "verbose_name_plural": "Licenses",
                "db_table": "licensing_license",
            },
        ),
        migrations.CreateModel(
            name="LicenseValidationLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("validation_type", models.CharField(max_length=20)),
                ("success", models.BooleanField()),
                ("error_message", models.TextField(blank=True)),
                ("server_response", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("license", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.license")),
            ],
            options={
                "verbose_name": "License Validation Log",
                "verbose_name_plural": "License Validation Logs",
                "db_table": "licensing_validation_log",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="licensevalidationlog",
            index=models.Index(fields=["license", "-created_at"], name="licensing_v_license_id_idx"),
        ),
        migrations.AddIndex(
            model_name="licensevalidationlog",
            index=models.Index(fields=["validation_type", "success"], name="licensing_v_valid_type_idx"),
        ),
    ]
