from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import uuid
from src.modules.tenant_management.models import Tenant


class EntityDefinition(models.Model):
    """
    Defines a custom entity type (e.g., 'Ticket', 'Asset').
    Can also extend system entities if code matches a system model name.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)  # Multi-tenancy
    name = models.CharField(max_length=255)
    code = models.SlugField(max_length=255)  # Unique code per tenant
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)  # If true, extends a hardcoded model

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant_id", "code")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class FieldDefinition(models.Model):
    """
    Defines a field on an entity.
    """

    FIELD_TYPES = [
        ("text", "Text"),
        ("number", "Number"),
        ("date", "Date"),
        ("boolean", "Boolean"),
        ("select", "Select"),
        ("reference", "Reference"),  # Link to another DynamicResource
        ("json", "JSON"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    entity_definition = models.ForeignKey(EntityDefinition, related_name="fields", on_delete=models.CASCADE)

    name = models.CharField(max_length=255)
    key = models.SlugField(max_length=255)  # Key in the JSON data
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)

    is_required = models.BooleanField(default=False)
    default_value = models.JSONField(null=True, blank=True)
    validation_rules = models.JSONField(default=dict, blank=True)  # e.g. {"min": 0, "max": 100, "regex": "..."}
    options = models.JSONField(default=list, blank=True)  # For 'select' type: ["Option A", "Option B"]

    order = models.IntegerField(default=0)

    class Meta:
        unique_together = ("entity_definition", "key")
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.name} ({self.key})"


class DynamicResource(models.Model):
    """
    Instance of a custom entity.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    entity_definition = models.ForeignKey(EntityDefinition, related_name="resources", on_delete=models.CASCADE)

    # Stores the actual field values: {"price": 100, "description": "foo"}
    data = models.JSONField(default=dict)

    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant_id", "entity_definition"]),
        ]

    def __str__(self):
        return f"{self.entity_definition.code} - {self.id}"
