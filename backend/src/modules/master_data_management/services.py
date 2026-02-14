"""
Business logic services for Master Data Management module.
"""

from .models import MasterDataEntity


class MasterDataService:
    """Service for master data operations."""

    @staticmethod
    def create_entity(tenant_id: str, entity_type: str, entity_code: str, entity_name: str, **kwargs) -> MasterDataEntity:
        """Create a new master data entity."""
        return MasterDataEntity.objects.create(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_code=entity_code,
            entity_name=entity_name,
            **kwargs,
        )
