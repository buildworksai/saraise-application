"""Normalize legacy permission UUID arrays into auditable memberships."""

from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def normalize_memberships(apps, schema_editor) -> None:
    del schema_editor
    Permission = apps.get_model("security_access_control", "Permission")
    PermissionSet = apps.get_model("security_access_control", "PermissionSet")
    Membership = apps.get_model("security_access_control", "PermissionSetPermission")
    known = set(Permission.objects.values_list("id", flat=True))

    for permission_set in PermissionSet.objects.order_by("id").iterator():
        raw_ids = permission_set.permission_ids
        if not isinstance(raw_ids, list):
            raise RuntimeError(f"PermissionSet {permission_set.id} permission_ids must be a JSON array")
        parsed: list[uuid.UUID] = []
        for raw_id in raw_ids:
            if not isinstance(raw_id, str):
                raise RuntimeError(f"PermissionSet {permission_set.id} contains a non-string permission ID")
            try:
                permission_id = uuid.UUID(raw_id)
            except (ValueError, TypeError, AttributeError) as exc:
                raise RuntimeError(
                    f"PermissionSet {permission_set.id} contains malformed permission ID {raw_id!r}"
                ) from exc
            if permission_id not in known:
                raise RuntimeError(
                    f"PermissionSet {permission_set.id} references unknown permission ID {permission_id}"
                )
            parsed.append(permission_id)
        if len(set(parsed)) != len(parsed):
            raise RuntimeError(
                f"PermissionSet {permission_set.id} contains duplicate permission IDs; "
                "remove duplicates explicitly before normalization"
            )
        if parsed and permission_set.created_by is None:
            raise RuntimeError(
                f"PermissionSet {permission_set.id} lacks created_by provenance required for normalized membership"
            )
        Membership.objects.bulk_create(
            [
                Membership(
                    tenant_id=permission_set.tenant_id,
                    permission_set_id=permission_set.id,
                    permission_id=permission_id,
                    added_by=permission_set.created_by,
                )
                for permission_id in parsed
            ]
        )


def reconstruct_arrays(apps, schema_editor) -> None:
    del schema_editor
    PermissionSet = apps.get_model("security_access_control", "PermissionSet")
    Membership = apps.get_model("security_access_control", "PermissionSetPermission")
    for permission_set in PermissionSet.objects.order_by("id").iterator():
        permission_set.permission_ids = [
            str(value)
            for value in Membership.objects.filter(
                permission_set_id=permission_set.id,
                removed_at__isnull=True,
            )
            .order_by("permission_id")
            .values_list("permission_id", flat=True)
        ]
        permission_set.save(update_fields=["permission_ids"])


class Migration(migrations.Migration):
    dependencies = [("security_access_control", "0002_add_tenant_and_audit_fields")]

    operations = [
        migrations.CreateModel(
            name="PermissionSetPermission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("added_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("added_by", models.UUIDField()),
                ("removed_at", models.DateTimeField(blank=True, null=True)),
                ("removed_by", models.UUIDField(blank=True, null=True)),
                (
                    "permission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="permission_set_memberships",
                        to="security_access_control.permission",
                    ),
                ),
                (
                    "permission_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="security_access_control.permissionset",
                    ),
                ),
            ],
            options={"db_table": "security_permission_set_permissions"},
        ),
        migrations.RunPython(normalize_memberships, reconstruct_arrays),
    ]
