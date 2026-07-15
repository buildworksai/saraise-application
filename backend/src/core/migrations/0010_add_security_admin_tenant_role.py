from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0009_audit_log_immutability")]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="tenant_role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("tenant_admin", "Tenant Admin"),
                    ("security_admin", "Security Administrator"),
                    ("tenant_user", "Tenant User"),
                ],
                db_index=True,
                help_text="Tenant-level role",
                max_length=50,
                null=True,
            ),
        )
    ]
