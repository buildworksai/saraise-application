"""
Regional Services.

High-level service layer for Regional business logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.db import transaction

from .models import RegionalResource

logger = logging.getLogger(__name__)


class RegionalService:
    """Service for managing Regional resources."""

    def create_resource(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        config: Optional[Dict[str, Any]] = None,
        created_by: str = "",
    ) -> RegionalResource:
        """Create a new resource.

        Args:
            tenant_id: Tenant ID.
            name: Resource name.
            description: Resource description.
            config: Resource configuration.
            created_by: User ID who created the resource.

        Returns:
            Created RegionalResource instance.

        Raises:
            ValueError: If validation fails.
        """
        with transaction.atomic():
            resource = RegionalResource.objects.create(
                tenant_id=tenant_id,
                name=name,
                description=description,
                config=config or {},
                created_by=created_by,
            )

            logger.info(f"Created regional resource {resource.id} for tenant {tenant_id}")
            return resource

    def get_resource(self, resource_id: str, tenant_id: str) -> Optional[RegionalResource]:
        """Get resource by ID.

        Args:
            resource_id: Resource ID.
            tenant_id: Tenant ID.

        Returns:
            RegionalResource instance or None if not found.
        """
        return RegionalResource.objects.filter(
            id=resource_id,
            tenant_id=tenant_id
        ).first()

    def list_resources(self, tenant_id: str, is_active: Optional[bool] = None) -> list[RegionalResource]:
        """List all resources for tenant.

        Args:
            tenant_id: Tenant ID.
            is_active: Optional filter by active status.

        Returns:
            List of RegionalResource instances.
        """
        queryset = RegionalResource.objects.filter(tenant_id=tenant_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset)

    def update_resource(
        self,
        resource_id: str,
        tenant_id: str,
        **updates: Any
    ) -> Optional[RegionalResource]:
        """Update resource.

        Args:
            resource_id: Resource ID.
            tenant_id: Tenant ID.
            **updates: Fields to update.

        Returns:
            Updated RegionalResource instance or None if not found.
        """
        resource = self.get_resource(resource_id, tenant_id)
        if not resource:
            return None

        with transaction.atomic():
            for key, value in updates.items():
                if hasattr(resource, key):
                    setattr(resource, key, value)
            resource.save()

            logger.info(f"Updated regional resource {resource_id}")
            return resource

    def delete_resource(self, resource_id: str, tenant_id: str) -> bool:
        """Delete resource.

        Args:
            resource_id: Resource ID.
            tenant_id: Tenant ID.

        Returns:
            True if deleted, False if not found.
        """
        resource = self.get_resource(resource_id, tenant_id)
        if not resource:
            return False

        with transaction.atomic():
            resource.delete()
            logger.info(f"Deleted regional resource {resource_id}")
            return True

    def activate_resource(self, resource_id: str, tenant_id: str) -> Optional[RegionalResource]:
        """Activate resource.

        Args:
            resource_id: Resource ID.
            tenant_id: Tenant ID.

        Returns:
            Updated RegionalResource instance or None if not found.
        """
        return self.update_resource(resource_id, tenant_id, is_active=True)

    def deactivate_resource(self, resource_id: str, tenant_id: str) -> Optional[RegionalResource]:
        """Deactivate resource.

        Args:
            resource_id: Resource ID.
            tenant_id: Tenant ID.

        Returns:
            Updated RegionalResource instance or None if not found.
        """
        return self.update_resource(resource_id, tenant_id, is_active=False)
