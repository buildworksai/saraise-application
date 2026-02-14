"""
DRF ViewSets for BillingSubscriptions module.
Provides REST API endpoints for all models.
"""

import logging
import secrets

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication
from src.core.rate_limiting.service import RateLimitService
from src.modules.tenant_management.models import Tenant, TenantResourceUsage
from django.utils import timezone

from .models import Invoice, InvoiceLineItem, Payment, Subscription, SubscriptionPlan, UsageRecord
from .serializers import (
    InvoiceLineItemSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
    UsageRecordSerializer,
)
from .services import SubscriptionService

logger = logging.getLogger(__name__)


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for SubscriptionPlan read operations (platform-level).

    CRITICAL: This ViewSet provides read-only access to platform-level subscription plans.
    Plans are defined by the platform and shared across all tenants.

    Access Control:
    - READ: All authenticated users (tenants can view available plans)
    - WRITE: Not available via this endpoint (platform owners use admin interface)
    - DELETE: Not available via this endpoint (platform owners use admin interface)

    Rationale for ReadOnlyModelViewSet:
    - Prevents tenants from creating/modifying platform-level pricing plans
    - Ensures consistent pricing across all tenants
    - Platform owners manage plans via Django admin or platform admin interface
    - If write access is needed in the future, it MUST be restricted to platform_owner role

    Endpoints:
    - GET /api/v1/billing-subscriptions/plans/ - List all plans
    - GET /api/v1/billing-subscriptions/plans/{id}/ - Get plan detail
    """

    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """
        List all active plans (platform-level, no tenant filtering).

        CRITICAL: No tenant filtering because SubscriptionPlan is platform-level.
        All tenants see the same plan list.
        """
        queryset = SubscriptionPlan.objects.filter(is_active=True)

        # Filter by billing cycle
        billing_cycle = self.request.query_params.get("billing_cycle")
        if billing_cycle:
            queryset = queryset.filter(billing_cycle=billing_cycle)

        return queryset.order_by("price")

    # NOTE: If this ViewSet is ever changed to ModelViewSet to allow writes,
    # the following access control MUST be added:
    #
    # def perform_create(self, serializer):
    #     """Restrict create to platform owners only."""
    #     from src.core.auth_utils import get_user_platform_role
    #     if get_user_platform_role(self.request.user) != "platform_owner":
    #         raise PermissionDenied("Only platform owners can create subscription plans")
    #     serializer.save()
    #
    # def perform_update(self, serializer):
    #     """Restrict update to platform owners only."""
    #     from src.core.auth_utils import get_user_platform_role
    #     if get_user_platform_role(self.request.user) != "platform_owner":
    #         raise PermissionDenied("Only platform owners can update subscription plans")
    #     super().perform_update(serializer)
    #
    # def perform_destroy(self, instance):
    #     """Restrict delete to platform owners only."""
    #     from src.core.auth_utils import get_user_platform_role
    #     if get_user_platform_role(self.request.user) != "platform_owner":
    #         raise PermissionDenied("Only platform owners can delete subscription plans")
    #     # Soft delete via is_active flag instead of hard delete
    #     instance.is_active = False
    #     instance.save()


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Subscription CRUD operations.

    Endpoints:
    - GET /api/v1/billing-subscriptions/subscriptions/ - List all subscriptions
    - POST /api/v1/billing-subscriptions/subscriptions/ - Create subscription
    - GET /api/v1/billing-subscriptions/subscriptions/{id}/ - Get subscription detail
    - PUT /api/v1/billing-subscriptions/subscriptions/{id}/ - Update subscription
    - DELETE /api/v1/billing-subscriptions/subscriptions/{id}/ - Delete subscription
    - POST /api/v1/billing-subscriptions/subscriptions/{id}/cancel/ - Cancel subscription
    - POST /api/v1/billing-subscriptions/subscriptions/{id}/upgrade/ - Upgrade subscription
    """

    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter subscriptions by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Subscription.objects.none()

        queryset = Subscription.objects.filter(tenant_id=tenant_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id and create subscription via service."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")

        plan_id = serializer.validated_data.get("plan").id
        service = SubscriptionService()
        subscription = service.create_subscription(tenant_id, plan_id)
        serializer.instance = subscription

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel subscription."""
        subscription = self.get_object()
        reason = request.data.get("reason", "")

        service = SubscriptionService()
        updated = service.cancel_subscription(subscription.tenant_id, reason)

        serializer = self.get_serializer(updated)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def upgrade(self, request, pk=None):
        """Upgrade subscription to a new plan."""
        subscription = self.get_object()
        new_plan_id = request.data.get("plan_id")

        if not new_plan_id:
            return Response({"error": "plan_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        service = SubscriptionService()
        updated = service.upgrade_subscription(subscription.tenant_id, new_plan_id)

        serializer = self.get_serializer(updated)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Invoice read operations.

    Endpoints:
    - GET /api/v1/billing-subscriptions/invoices/ - List all invoices
    - GET /api/v1/billing-subscriptions/invoices/{id}/ - Get invoice detail
    - GET /api/v1/billing-subscriptions/invoices/{id}/pdf/ - Download invoice PDF
    """

    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter invoices by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Invoice.objects.none()

        queryset = Invoice.objects.filter(tenant_id=tenant_id)

        # Filter by subscription
        subscription_id = self.request.query_params.get("subscription_id")
        if subscription_id:
            queryset = queryset.filter(subscription_id=subscription_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-created_at")

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Generate and download invoice PDF."""
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from weasyprint import HTML

        invoice = self.get_object()

        try:
            # Render invoice template
            context = {
                "invoice": invoice,
                "line_items": invoice.line_items.all(),
                "tenant": getattr(request.user, "profile", None) if hasattr(request.user, "profile") else None,
            }

            # Render HTML template
            html_content = render_to_string("invoices/invoice.html", context)

            # Generate PDF
            pdf_file = HTML(string=html_content).write_pdf()

            # Return PDF response
            response = HttpResponse(pdf_file, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'
            return response

        except Exception as e:
            logger.error(f"PDF generation failed for invoice {invoice.id}: {e}", exc_info=True)
            return Response(
                {"error": f"PDF generation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Payment CRUD operations.

    Endpoints:
    - GET /api/v1/billing-subscriptions/payments/ - List all payments
    - POST /api/v1/billing-subscriptions/payments/ - Create payment
    - GET /api/v1/billing-subscriptions/payments/{id}/ - Get payment detail
    """

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter payments by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Payment.objects.none()

        queryset = Payment.objects.filter(tenant_id=tenant_id)

        # Filter by invoice
        invoice_id = self.request.query_params.get("invoice_id")
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id and process payment."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")

        payment = serializer.save(tenant_id=tenant_id)

        # Process payment through payment gateway
        from .services import PaymentService

        gateway = self.request.data.get("gateway", "stripe")
        payment_method_id = self.request.data.get("payment_method_id")

        result = PaymentService.process_payment(
            payment=payment,
            gateway=gateway,
            payment_method_id=payment_method_id,
        )

        if not result.get("success"):
            # Payment failed - update payment status
            payment.status = "failed"
            payment.save(update_fields=["status"])
            # Return error response
            from rest_framework.response import Response
            from rest_framework import status

            return Response(
                {"error": result.get("error", "Payment processing failed")},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UsageRecordViewSet(viewsets.ModelViewSet):
    """
    ViewSet for UsageRecord CRUD operations.

    Endpoints:
    - GET /api/v1/billing-subscriptions/usage-records/ - List all usage records
    - POST /api/v1/billing-subscriptions/usage-records/ - Record usage
    - GET /api/v1/billing-subscriptions/usage-records/{id}/ - Get usage record detail
    """

    serializer_class = UsageRecordSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter usage records by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return UsageRecord.objects.none()

        queryset = UsageRecord.objects.filter(tenant_id=tenant_id)

        # Filter by resource type
        resource_type = self.request.query_params.get("resource_type")
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

        return queryset.order_by("-recorded_at")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)


class QuotaViewSet(viewsets.ViewSet):
    """
    ViewSet for quota management operations.

    Endpoints:
    - GET /api/v1/billing-subscriptions/quotas/ - Get current quota usage and limits
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def list(self, request):
        """Get current quota usage and limits for tenant."""
        tenant_id = get_user_tenant_id(request.user)
        if not tenant_id:
            return Response({"error": "User must belong to a tenant"}, status=status.HTTP_403_FORBIDDEN)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({"error": "Tenant not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get current usage from TenantResourceUsage (today's record)
        today = timezone.now().date()
        usage_record, _ = TenantResourceUsage.objects.get_or_create(
            tenant=tenant,
            date=today,
            defaults={
                "active_users": 0,
                "api_calls": 0,
                "storage_used_gb": 0,
                "bandwidth_used_gb": 0,
            },
        )

        # Get API calls from rate limiting service
        api_calls_used = RateLimitService.get_usage(tenant_id, "api_calls")
        api_calls_limit = RateLimitService.get_limit(tenant_id, "api_calls")

        # Get active users count (simplified - in production, count from UserProfile)
        active_users_used = usage_record.active_users
        active_users_limit = tenant.max_users

        # Get storage usage
        storage_used = float(usage_record.storage_used_gb)
        storage_limit = tenant.max_storage_gb

        return Response(
            {
                "users": {
                    "used": active_users_used,
                    "limit": active_users_limit,
                },
                "storage": {
                    "used": storage_used,
                    "limit": storage_limit,
                },
                "api_calls": {
                    "used": api_calls_used,
                    "limit": api_calls_limit,
                },
            },
            status=status.HTTP_200_OK,
        )
