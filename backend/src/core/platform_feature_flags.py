"""
Platform Feature Flags Service

⚠️ MODE-AWARE ARCHITECTURE:
- Self-Hosted Mode: Queries local models (platform_management module)
- SaaS Mode: Queries Control Plane APIs (saraise-platform/saraise-control-plane/)

This service provides a convenience wrapper for runtime feature flag checks.
"""

import logging
from typing import Optional
from uuid import UUID

import requests
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)

# Control Plane API base URL (SaaS mode only)
CONTROL_PLANE_URL = getattr(settings, "SARAISE_PLATFORM_URL", "http://localhost:18004")


class PlatformFeatureFlagService:
    """
    Mode-aware service for checking feature flags at runtime.
    
    - Self-Hosted: Queries local FeatureFlag models
    - SaaS: Queries Control Plane API
    """

    @staticmethod
    def is_feature_enabled(
        name: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        default: bool = False,
    ) -> bool:
        """
        Check if a feature flag is enabled.
        
        Args:
            name: Feature flag name
            tenant_id: Optional tenant ID for tenant-specific flags
            user_id: Optional user ID for rollout percentage checks
            default: Default value if flag not found or API unavailable
            
        Returns:
            True if feature is enabled, False otherwise
        """
        # Mode-aware: Use local models in self-hosted, Control Plane in SaaS
        if settings.SARAISE_MODE in ('self-hosted', 'development'):
            return PlatformFeatureFlagService._check_local_flag(name, tenant_id, user_id, default)
        else:
            return PlatformFeatureFlagService._check_control_plane_flag(name, tenant_id, user_id, default)

    @staticmethod
    def _check_local_flag(
        name: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        default: bool = False,
    ) -> bool:
        """Check feature flag from local models (self-hosted mode)."""
        try:
            from src.modules.platform_management.models import FeatureFlag

            # Build query: tenant-specific or platform-wide
            query = models.Q(name=name)
            if tenant_id:
                query &= (models.Q(tenant_id=tenant_id) | models.Q(tenant_id__isnull=True))
            else:
                query &= models.Q(tenant_id__isnull=True)

            flag = FeatureFlag.objects.filter(query).first()
            if not flag:
                return default

            if not flag.enabled:
                return False

            # Check rollout percentage if applicable
            if flag.rollout_percentage < 100 and user_id:
                user_hash = hash(str(user_id)) % 100
                return user_hash < flag.rollout_percentage

            return True

        except Exception as e:
            logger.warning(f"Error checking local feature flag {name}: {e}")
            return default

    @staticmethod
    def _check_control_plane_flag(
        name: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        default: bool = False,
    ) -> bool:
        """Check feature flag from Control Plane API (SaaS mode)."""
        try:
            url = f"{CONTROL_PLANE_URL}/api/v1/platform/feature-flags/"
            params = {"name": name}
            if tenant_id:
                params["tenant_id"] = str(tenant_id)

            response = requests.get(url, params=params, timeout=2)
            if response.status_code != 200:
                logger.warning(f"Failed to check feature flag {name}: {response.status_code}")
                return default

            flags = response.json()
            if not flags or len(flags) == 0:
                return default

            flag = flags[0]
            if not flag.get("enabled", False):
                return False

            rollout_percentage = flag.get("rollout_percentage", 100)
            if rollout_percentage < 100 and user_id:
                user_hash = hash(str(user_id)) % 100
                return user_hash < rollout_percentage

            return True

        except Exception as e:
            logger.warning(f"Error checking Control Plane feature flag {name}: {e}")
            return default

    @staticmethod
    def get_setting(
        key: str,
        tenant_id: Optional[UUID] = None,
        default=None,
    ):
        """
        Get a platform setting value.
        
        Args:
            key: Setting key
            tenant_id: Optional tenant ID for tenant-specific settings
            default: Default value if setting not found or API unavailable
            
        Returns:
            Setting value or default
        """
        # Mode-aware: Use local models in self-hosted, Control Plane in SaaS
        if settings.SARAISE_MODE in ('self-hosted', 'development'):
            return PlatformFeatureFlagService._get_local_setting(key, tenant_id, default)
        else:
            return PlatformFeatureFlagService._get_control_plane_setting(key, tenant_id, default)

    @staticmethod
    def _get_local_setting(
        key: str,
        tenant_id: Optional[UUID] = None,
        default=None,
    ):
        """Get platform setting from local models (self-hosted mode)."""
        try:
            from src.modules.platform_management.models import PlatformSetting

            # Build query: tenant-specific or platform-wide
            query = models.Q(key=key)
            if tenant_id:
                query &= (models.Q(tenant_id=tenant_id) | models.Q(tenant_id__isnull=True))
            else:
                query &= models.Q(tenant_id__isnull=True)

            setting = PlatformSetting.objects.filter(query).first()
            if not setting:
                return default

            return setting.value

        except Exception as e:
            logger.warning(f"Error getting local platform setting {key}: {e}")
            return default

    @staticmethod
    def _get_control_plane_setting(
        key: str,
        tenant_id: Optional[UUID] = None,
        default=None,
    ):
        """Get platform setting from Control Plane API (SaaS mode)."""
        try:
            url = f"{CONTROL_PLANE_URL}/api/v1/platform/settings/"
            params = {"key": key}
            if tenant_id:
                params["tenant_id"] = str(tenant_id)

            response = requests.get(url, params=params, timeout=2)
            if response.status_code != 200:
                logger.warning(f"Failed to get platform setting {key}: {response.status_code}")
                return default

            settings_list = response.json()
            if not settings_list or len(settings_list) == 0:
                return default

            setting = settings_list[0]
            return setting.get("value", default)

        except Exception as e:
            logger.warning(f"Error getting Control Plane platform setting {key}: {e}")
            return default
