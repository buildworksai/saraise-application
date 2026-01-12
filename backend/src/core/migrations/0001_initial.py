# Generated manually for UserProfile model

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="profile",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Tenant ID for tenant-scoped users (null for platform users)",
                        max_length=36,
                        null=True,
                    ),
                ),
                (
                    "platform_role",
                    models.CharField(
                        blank=True,
                        choices=[("platform_owner", "Platform Owner"), ("platform_operator", "Platform Operator")],
                        db_index=True,
                        help_text="Platform-level role",
                        max_length=50,
                        null=True,
                    ),
                ),
                (
                    "tenant_role",
                    models.CharField(
                        blank=True,
                        choices=[("tenant_admin", "Tenant Admin"), ("tenant_user", "Tenant User")],
                        db_index=True,
                        help_text="Tenant-level role",
                        max_length=50,
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "user_profiles",
            },
        ),
        migrations.AddIndex(
            model_name="userprofile",
            index=models.Index(fields=["tenant_id"], name="user_profil_tenant_id_idx"),
        ),
        migrations.AddIndex(
            model_name="userprofile",
            index=models.Index(fields=["platform_role"], name="user_profil_platform_role_idx"),
        ),
        migrations.AddIndex(
            model_name="userprofile",
            index=models.Index(fields=["tenant_role"], name="user_profil_tenant_role_idx"),
        ),
        migrations.AddIndex(
            model_name="userprofile",
            index=models.Index(fields=["tenant_id", "tenant_role"], name="user_profil_tenant_role_combo_idx"),
        ),
    ]
