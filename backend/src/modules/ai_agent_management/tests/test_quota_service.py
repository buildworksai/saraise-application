"""Tests for Quota Service.

Task: 402.2 - AI Quota Enforcement
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from datetime import timedelta

from ..models import Agent, AgentExecution, AgentIdentityType
from ..quota_service import QuotaService
from ..quota_models import TenantQuota, QuotaUsage, QuotaType, QuotaPeriod


@pytest.mark.django_db
class TestQuotaService:
    """Test QuotaService."""

    def test_check_quota_allowed(self) -> None:
        """Test checking quota when allowed."""
        service = QuotaService()

        tenant_id = "test-tenant-1"

        # Create quota
        TenantQuota.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            limit_value=10000,
            period=QuotaPeriod.DAILY,
            is_active=True,
        )

        # Create usage
        QuotaUsage.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            usage_value=5000,
            period_start=timezone.now().date(),
        )

        allowed, quota, message = service.check_quota(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            requested_amount=3000,
        )

        assert allowed is True
        assert quota is not None
        assert "allowed" in message.lower()

    def test_check_quota_exceeded(self) -> None:
        """Test checking quota when exceeded."""
        service = QuotaService()

        tenant_id = "test-tenant-1"

        # Create quota
        TenantQuota.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            limit_value=10000,
            period=QuotaPeriod.DAILY,
            is_active=True,
        )

        # Create usage that exceeds limit
        QuotaUsage.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            usage_value=9000,
            period_start=timezone.now().date(),
        )

        allowed, quota, message = service.check_quota(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            requested_amount=2000,  # Would exceed limit
        )

        assert allowed is False
        assert quota is not None
        assert "exceeded" in message.lower() or "limit" in message.lower()

    def test_check_quota_no_quota(self) -> None:
        """Test checking quota when no quota defined."""
        service = QuotaService()

        tenant_id = "test-tenant-1"

        allowed, quota, message = service.check_quota(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            requested_amount=1000,
        )

        # Default behavior: allow if no quota defined
        assert allowed is True
        assert quota is None

    def test_record_usage(self) -> None:
        """Test recording quota usage."""
        service = QuotaService()

        tenant_id = "test-tenant-1"

        TenantQuota.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            limit_value=10000,
            period=QuotaPeriod.DAILY,
            is_active=True,
        )

        usage = service.record_usage(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            usage_amount=1000,
        )

        assert usage is not None
        assert usage.usage_value == 1000

    def test_get_quota_usage(self) -> None:
        """Test getting quota usage."""
        service = QuotaService()

        tenant_id = "test-tenant-1"

        TenantQuota.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            limit_value=10000,
            period=QuotaPeriod.DAILY,
            is_active=True,
        )

        QuotaUsage.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            usage_value=5000,
            period_start=timezone.now().date(),
        )

        usage = service.get_quota_usage(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
        )

        assert usage is not None
        assert usage["current_usage"] == 5000
        assert usage["limit"] == 10000
        assert usage["remaining"] == 5000

    def test_create_quota(self) -> None:
        """Test creating a quota."""
        service = QuotaService()

        tenant_id = "test-tenant-1"

        quota = service.create_quota(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            limit_value=10000,
            period=QuotaPeriod.DAILY,
            created_by="user-1",
        )

        assert quota is not None
        assert quota.tenant_id == tenant_id
        assert quota.quota_type == QuotaType.TOKENS_PER_DAY
        assert quota.limit_value == 10000
        assert quota.is_active is True

    def test_update_quota(self) -> None:
        """Test updating a quota."""
        service = QuotaService()

        tenant_id = "test-tenant-1"

        quota = TenantQuota.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            limit_value=10000,
            period=QuotaPeriod.DAILY,
            is_active=True,
        )

        updated = service.update_quota(
            tenant_id=tenant_id,
            quota_id=quota.id,
            limit_value=20000,
            updated_by="user-1",
        )

        assert updated.limit_value == 20000

    def test_delete_quota(self) -> None:
        """Test deleting a quota."""
        service = QuotaService()

        tenant_id = "test-tenant-1"

        quota = TenantQuota.objects.create(
            tenant_id=tenant_id,
            quota_type=QuotaType.TOKENS_PER_DAY,
            limit_value=10000,
            period=QuotaPeriod.DAILY,
            is_active=True,
        )

        service.delete_quota(
            tenant_id=tenant_id,
            quota_id=quota.id,
            deleted_by="user-1",
        )

        quota.refresh_from_db()
        assert quota.is_active is False

