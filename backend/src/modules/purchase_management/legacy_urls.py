"""Deprecated v1 compatibility API. New capabilities are intentionally v2-only."""

from django.urls import include, path
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from src.core.auth_utils import get_user_tenant_id

from .models import PurchaseOrder, PurchaseReceipt, PurchaseRequisition, Supplier
from .services import SupplierService


class LegacySupplierSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Supplier
        fields = (
            "id",
            "tenant_id",
            "supplier_code",
            "supplier_name",
            "email",
            "phone",
            "address",
            "payment_terms",
            "currency",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "tenant_id", "is_active", "created_at", "updated_at")


class LegacyReadSerializer(serializers.ModelSerializer):
    class Meta:
        fields = "__all__"


class LegacyRequisitionSerializer(LegacyReadSerializer):
    class Meta(LegacyReadSerializer.Meta):
        model = PurchaseRequisition


class LegacyOrderSerializer(LegacyReadSerializer):
    class Meta(LegacyReadSerializer.Meta):
        model = PurchaseOrder


class LegacyReceiptSerializer(LegacyReadSerializer):
    class Meta(LegacyReadSerializer.Meta):
        model = PurchaseReceipt


class LegacyTenantViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    model = Supplier

    def get_queryset(self):
        value = get_user_tenant_id(self.request.user)
        try:
            return self.model.objects.for_tenant(value)
        except (TypeError, ValueError):
            return self.model.objects.none()


class LegacySupplierViewSet(LegacyTenantViewSet):
    serializer_class = LegacySupplierSerializer
    model = Supplier

    def create(self, request):
        serializer = LegacySupplierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant_id = get_user_tenant_id(request.user)
        supplier = SupplierService.create_supplier(
            tenant_id, tenant_id, serializer.validated_data, getattr(request, "correlation_id", "legacy")
        )
        return Response(LegacySupplierSerializer(supplier).data, status=201)


class LegacyRequisitionViewSet(LegacyTenantViewSet):
    serializer_class = LegacyRequisitionSerializer
    model = PurchaseRequisition


class LegacyOrderViewSet(LegacyTenantViewSet):
    serializer_class = LegacyOrderSerializer
    model = PurchaseOrder


class LegacyReceiptViewSet(LegacyTenantViewSet):
    serializer_class = LegacyReceiptSerializer
    model = PurchaseReceipt


router = DefaultRouter()
router.register("suppliers", LegacySupplierViewSet, basename="legacy-supplier")
router.register("requisitions", LegacyRequisitionViewSet, basename="legacy-requisition")
router.register("purchase-orders", LegacyOrderViewSet, basename="legacy-order")
router.register("receipts", LegacyReceiptViewSet, basename="legacy-receipt")
urlpatterns = [path("", include(router.urls))]
