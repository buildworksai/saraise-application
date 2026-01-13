"""Module Registry Database Models.

Database models for module registry and installation tracking.
Task: 501.2 - Module Registry & Compatibility Validation
"""

from __future__ import annotations

import uuid

from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class ModuleRegistryEntry(models.Model):
    """Module registry entry model.

    Tracks registered modules in the registry.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    version = models.CharField(max_length=50, db_index=True)
    description = models.TextField(blank=True, null=True)
    module_type = models.CharField(
        max_length=50,
        choices=[
            ("core", "Core"),
            ("domain", "Domain"),
            ("industry", "Industry"),
            ("integration", "Integration"),
            ("foundation", "Foundation"),
        ],
        db_index=True,
    )
    lifecycle = models.CharField(
        max_length=50,
        choices=[
            ("core", "Core"),
            ("managed", "Managed"),
            ("integration", "Integration"),
        ],
        db_index=True,
    )
    manifest_content = models.TextField(help_text="Full manifest YAML content")
    manifest_hash = models.CharField(max_length=64, db_index=True, help_text="SHA-256 hash of manifest")
    signature = models.TextField(null=True, blank=True, help_text="Manifest signature")
    signature_algorithm = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Signature algorithm (RS256, HMAC-SHA256)",
    )
    dependencies = models.JSONField(default=list, help_text="Module dependencies")
    permissions = models.JSONField(default=list, help_text="Declared permissions")
    sod_actions = models.JSONField(default=list, help_text="SoD actions")
    search_indexes = models.JSONField(default=list, help_text="Search indexes")
    ai_tools = models.JSONField(default=list, help_text="AI tools")
    metadata = models.JSONField(default=dict, help_text="Additional metadata")
    is_active = models.BooleanField(default=True, db_index=True, help_text="Module active in registry")
    registered_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "module_registry_entries"
        unique_together = [["name", "version"]]
        indexes = [
            models.Index(fields=["name", "version"]),
            models.Index(fields=["module_type"]),
            models.Index(fields=["lifecycle"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class TenantModuleInstallation(models.Model):
    """Tenant module installation model.

    Tracks which modules are installed for each tenant.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    tenant_id = models.CharField(max_length=36, db_index=True)
    module_name = models.CharField(max_length=255, db_index=True)
    module_version = models.CharField(max_length=50, db_index=True)
    registry_entry = models.ForeignKey(
        ModuleRegistryEntry,
        on_delete=models.PROTECT,
        related_name="installations",
        db_index=True,
    )
    installed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    installed_by = models.CharField(max_length=36, help_text="User/system who installed")
    status = models.CharField(
        max_length=50,
        choices=[
            ("installed", "Installed"),
            ("upgrading", "Upgrading"),
            ("rollback", "Rolling Back"),
            ("uninstalled", "Uninstalled"),
        ],
        default="installed",
        db_index=True,
    )
    metadata = models.JSONField(default=dict, help_text="Installation metadata")

    class Meta:
        db_table = "tenant_module_installations"
        unique_together = [["tenant_id", "module_name"]]
        indexes = [
            models.Index(fields=["tenant_id", "module_name"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "installed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.module_name} v{self.module_version} (Tenant: {self.tenant_id})"
