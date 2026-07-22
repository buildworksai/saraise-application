"""Complete the additive-copy-read-switch migration sequence.

Every legacy column was either retained with its original meaning or safely
evolved in-place; there is therefore no proven-unused business data to drop.
This final reversible state change switches runtime ordering to v2 execution
timestamps after compatibility readers have moved away from ``started_at``.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("workflow_automation", "0005_install_workflow_rls")]

    operations = [
        migrations.AlterModelOptions(
            name="workflow",
            options={"ordering": ("-updated_at",)},
        ),
        migrations.AlterModelOptions(
            name="workflowstep",
            options={"ordering": ("order", "id")},
        ),
        migrations.AlterModelOptions(
            name="workflowinstance",
            options={"ordering": ("-created_at",)},
        ),
        migrations.AlterModelOptions(
            name="workflowtask",
            options={"ordering": ("due_date", "created_at")},
        ),
    ]
