"""
Localization Services.

High-level service layer for Localization business logic.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.core.cache import cache
from django.db import transaction

from .models import Language, LocaleConfig, Translation

logger = logging.getLogger(__name__)


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
