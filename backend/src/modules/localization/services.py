"""
Localization Services.

High-level service layer for Localization business logic.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.core.cache import cache
from django.db import transaction

from .models import Language, LocaleConfig, LocalizationResource, Translation

logger = logging.getLogger(__name__)


class LocalizationService:
    """Service boundary for tenant-scoped localization resources."""

    _UPDATABLE_FIELDS = frozenset({"name", "description", "config", "is_active"})

    def create_resource(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        config: Optional[dict[str, Any]] = None,
        created_by: str = "",
    ) -> LocalizationResource:
        """Create a resource inside an explicit tenant boundary."""
        with transaction.atomic():
            return LocalizationResource.objects.create(
                tenant_id=tenant_id,
                name=name,
                description=description,
                config=config or {},
                created_by=created_by,
            )

    def get_resource(
        self,
        resource_id: str,
        tenant_id: str,
    ) -> Optional[LocalizationResource]:
        """Return a resource only when it belongs to the requested tenant."""
        return LocalizationResource.objects.filter(
            id=resource_id,
            tenant_id=tenant_id,
        ).first()

    def list_resources(
        self,
        tenant_id: str,
        is_active: Optional[bool] = None,
    ) -> list[LocalizationResource]:
        """List resources belonging to one tenant."""
        queryset = LocalizationResource.objects.filter(tenant_id=tenant_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset)

    def update_resource(
        self,
        resource_id: str,
        tenant_id: str,
        **updates: Any,
    ) -> Optional[LocalizationResource]:
        """Update allowed fields without permitting tenant reassignment."""
        accepted_updates = {field: value for field, value in updates.items() if field in self._UPDATABLE_FIELDS}
        with transaction.atomic():
            resource = (
                LocalizationResource.objects.select_for_update()
                .filter(
                    id=resource_id,
                    tenant_id=tenant_id,
                )
                .first()
            )
            if resource is None:
                return None
            for field, value in accepted_updates.items():
                setattr(resource, field, value)
            resource.save()
            return resource

    def delete_resource(self, resource_id: str, tenant_id: str) -> bool:
        """Delete only a resource belonging to the requested tenant."""
        with transaction.atomic():
            deleted_count, _ = LocalizationResource.objects.filter(
                id=resource_id,
                tenant_id=tenant_id,
            ).delete()
        return deleted_count == 1

    def activate_resource(
        self,
        resource_id: str,
        tenant_id: str,
    ) -> Optional[LocalizationResource]:
        """Activate a tenant-owned resource."""
        return self.update_resource(resource_id, tenant_id, is_active=True)

    def deactivate_resource(
        self,
        resource_id: str,
        tenant_id: str,
    ) -> Optional[LocalizationResource]:
        """Deactivate a tenant-owned resource."""
        return self.update_resource(resource_id, tenant_id, is_active=False)


class TranslationService:
    """Service for managing translations with caching."""

    CACHE_TIMEOUT = 3600  # 1 hour

    def translate(
        self,
        key: str,
        language_code: str,
        tenant_id: str,
        default: Optional[str] = None,
        context: Optional[str] = None,
    ) -> str:
        """Get translation for a key.

        Args:
            key: Translation key.
            language_code: Language code (e.g., 'en', 'fr').
            tenant_id: Tenant ID.
            default: Default value if translation not found.
            context: Optional context.

        Returns:
            Translated string or default.
        """
        # Check cache first
        cache_key = f"translation:{tenant_id}:{language_code}:{key}:{context or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Get language
        language = Language.objects.filter(code=language_code, is_active=True).first()
        if not language:
            return default or key

        # Get translation
        queryset = Translation.objects.filter(
            tenant_id=tenant_id,
            language=language,
            key=key,
        )
        if context:
            queryset = queryset.filter(context=context)
        else:
            queryset = queryset.filter(context="")

        translation = queryset.first()

        if translation:
            result = translation.value
        else:
            result = default or key

        # Cache result
        cache.set(cache_key, result, self.CACHE_TIMEOUT)

        return result

    def get_tenant_locale(self, tenant_id: str) -> Optional[LocaleConfig]:
        """Get tenant locale configuration.

        Args:
            tenant_id: Tenant ID.

        Returns:
            LocaleConfig instance or None if not found.
        """
        return LocaleConfig.objects.filter(tenant_id=tenant_id).first()

    def invalidate_cache(self, tenant_id: str, language_code: Optional[str] = None) -> None:
        """Invalidate translation cache for tenant.

        Args:
            tenant_id: Tenant ID.
            language_code: Optional language code to invalidate (all if None).
        """
        # TODO: Implement cache invalidation
        # This would clear all cache keys matching the pattern
        logger.info(f"Invalidating translation cache for tenant {tenant_id}, language {language_code}")
