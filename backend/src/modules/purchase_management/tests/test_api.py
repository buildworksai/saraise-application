"""
API tests for Purchase Management module.
"""

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APIRequestFactory

from src.core.api import OperationFailed
from src.modules.purchase_management import api as purchase_api
from src.modules.purchase_management.api import (
    ConfigurationViewSet,
    PurchaseOrderViewSet,
    PurchaseViewSet,
    QuoteViewSet,
    ReceiptViewSet,
    RequisitionViewSet,
    RFQViewSet,
    SupplierViewSet,
)
from src.modules.purchase_management.models import Supplier
from src.modules.purchase_management.permissions import PurchaseRequiresAccess

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def authenticated_user(db):
    """Create authenticated user with tenant."""
    from unittest.mock import patch

    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestSupplierAPI:
    """Test Supplier API endpoints."""

    def test_list_suppliers(self, api_client, authenticated_user):
        """Test listing suppliers."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Supplier.objects.create(
            tenant_id=tenant_id,
            supplier_code="SUP-001",
            supplier_name="Test Supplier",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/purchase-management/suppliers/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_supplier(self, api_client, authenticated_user):
        """Test creating a supplier."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "supplier_code": "SUP-002",
            "supplier_name": "Another Supplier",
        }

        response = api_client.post("/api/v1/purchase-management/suppliers/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["supplier_code"] == "SUP-002"


@pytest.mark.django_db
def test_purchase_order_retrieve_uses_drf_dispatch_not_domain_dispatch(api_client, authenticated_user, monkeypatch):
    monkeypatch.setattr(PurchaseRequiresAccess, "has_permission", lambda self, request, view: True)
    api_client.force_authenticate(user=authenticated_user)

    missing_id = "00000000-0000-4000-8000-000000000000"
    response = api_client.get(f"/api/v2/purchase-management/purchase-orders/{missing_id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_purchase_viewset_rejects_overlong_idempotency_key():
    request = APIRequestFactory().post("/", HTTP_IDEMPOTENCY_KEY="x" * 256)
    view = PurchaseViewSet()
    view.request = request

    with pytest.raises(ValidationError) as exc:
        view._idempotency()

    assert str(exc.value.detail["Idempotency-Key"]) == "Must not exceed 255 characters."


class _InputSerializer:
    payload = {}

    def __init__(self, *args, **kwargs):
        self.validated_data = dict(self.payload)

    def is_valid(self, raise_exception=False):
        return True


class _OutputSerializer:
    def __init__(self, value=None, *args, **kwargs):
        self.value = value

    @property
    def data(self):
        value = self.value
        if isinstance(value, dict):
            return value
        return {"id": str(getattr(value, "id", "resource")), "status": getattr(value, "status", "ok")}


def _serializer(payload):
    return type("Serializer", (_InputSerializer,), {"payload": payload})


def _request(*, data=None, headers=None, query_params=None, method="POST"):
    return SimpleNamespace(
        data=data or {},
        headers=headers or {},
        query_params=query_params or {},
        user=SimpleNamespace(id=uuid.uuid4()),
        method=method,
    )


def _prepared_view(view_class, monkeypatch, *, data=None, headers=None, query_params=None, method="POST"):
    tenant_id = uuid.uuid4()
    view = view_class()
    view.request = _request(data=data, headers=headers, query_params=query_params, method=method)
    monkeypatch.setattr(purchase_api, "get_user_tenant_id", lambda user: str(tenant_id))
    return view, tenant_id


def _resource(status_value="ok"):
    return SimpleNamespace(id=uuid.uuid4(), status=status_value, lock_version=2)


def test_purchase_viewset_core_helpers_validate_tenant_lock_query_and_correlation(monkeypatch):
    view, tenant_id = _prepared_view(
        SupplierViewSet,
        monkeypatch,
        headers={"If-Match": '"7"', "X-Correlation-ID": "corr-header", "Idempotency-Key": "idem"},
        query_params={"unknown": "x"},
    )
    view.action = "approve"

    assert view.tenant_id == tenant_id
    assert view.correlation_id == "corr-header"
    assert view._lock_version() == 7
    assert view._idempotency() == "idem"
    assert purchase_api._actor(SimpleNamespace(id="not-a-uuid")) == uuid.uuid5(
        uuid.NAMESPACE_URL, "saraise:user:not-a-uuid"
    )
    assert purchase_api._route_value("abc") == "abc"
    assert purchase_api._text_value(tenant_id) == tenant_id
    with pytest.raises(ValidationError):
        view._validate_query()

    view.request.query_params = {"ordering": "unsupported"}
    with pytest.raises(ValidationError):
        view._filter(Supplier.objects.none())

    monkeypatch.setattr(purchase_api, "get_user_tenant_id", lambda user: "bad")
    with pytest.raises(OperationFailed):
        _ = view.tenant_id


def test_supplier_viewset_forwards_create_update_and_status_actions(monkeypatch):
    view, tenant_id = _prepared_view(SupplierViewSet, monkeypatch, headers={"If-Match": "2", "Idempotency-Key": "idem"})
    supplier_id = uuid.uuid4()
    calls = []
    monkeypatch.setattr(purchase_api, "SupplierWriteSerializer", _serializer({"supplier_name": "Changed"}))
    monkeypatch.setattr(purchase_api, "SupplierStatusSerializer", _serializer({"reason": "governed"}))
    monkeypatch.setattr(purchase_api, "SupplierDetailSerializer", _OutputSerializer)
    monkeypatch.setattr(
        purchase_api.SupplierService,
        "create_supplier",
        lambda *args: calls.append(("create", args)) or _resource("created"),
    )
    monkeypatch.setattr(
        purchase_api.SupplierService,
        "update_supplier",
        lambda *args: calls.append(("update", args)) or _resource("updated"),
    )
    monkeypatch.setattr(
        purchase_api.SupplierService,
        "archive_supplier",
        lambda *args: calls.append(("archive", args)) or _resource("archived"),
    )
    monkeypatch.setattr(
        purchase_api.SupplierService,
        "restore_supplier",
        lambda *args: calls.append(("restore", args)) or _resource("active"),
    )
    monkeypatch.setattr(
        purchase_api.SupplierService,
        "set_supplier_status",
        lambda *args: calls.append(("set_status", args)) or _resource("inactive"),
    )

    assert view.create(view.request).status_code == status.HTTP_201_CREATED
    assert view.partial_update(view.request, str(supplier_id)).data["status"] == "updated"
    assert view.destroy(view.request, str(supplier_id)).data["status"] == "archived"
    assert view.activate(view.request, str(supplier_id)).data["status"] == "active"
    assert view.deactivate(view.request, str(supplier_id)).data["status"] == "inactive"

    assert calls[0][1][0] == tenant_id
    assert calls[1][1][2] == str(supplier_id)
    assert calls[1][1][4] == 2
    assert calls[2][1][4] == "idem"
    assert calls[4][1][3] == "inactive"


def test_requisition_viewset_forwards_mutations_and_convert(monkeypatch):
    view, tenant_id = _prepared_view(
        RequisitionViewSet,
        monkeypatch,
        headers={"If-Match": "4", "Idempotency-Key": "idem"},
    )
    requisition_id = uuid.uuid4()
    calls = []
    monkeypatch.setattr(purchase_api, "RequisitionWriteSerializer", _serializer({"purpose": "Need"}))
    monkeypatch.setattr(purchase_api, "EmptyTransitionSerializer", _serializer({}))
    monkeypatch.setattr(purchase_api, "ReasonTransitionSerializer", _serializer({"reason": "reject"}))
    monkeypatch.setattr(
        purchase_api,
        "RequisitionConvertSerializer",
        _serializer({"supplier_id": uuid.uuid4(), "line_selections": [{"line": 1}]}),
    )
    monkeypatch.setattr(purchase_api, "RequisitionDetailSerializer", _OutputSerializer)
    monkeypatch.setattr(purchase_api, "PurchaseOrderDetailSerializer", _OutputSerializer)
    for name in (
        "create_requisition",
        "update_requisition",
        "delete_draft_requisition",
        "submit_requisition",
        "approve_requisition",
        "reject_requisition",
        "revise_requisition",
        "cancel_requisition",
        "convert_to_purchase_order",
    ):
        monkeypatch.setattr(
            purchase_api.RequisitionService,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)) or _resource(_name),
        )

    assert view.create(view.request).status_code == status.HTTP_201_CREATED
    assert view.update(view.request, str(requisition_id)).data["status"] == "update_requisition"
    assert view.destroy(view.request, str(requisition_id)).data["status"] == "delete_draft_requisition"
    assert view.submit(view.request, str(requisition_id)).data["status"] == "submit_requisition"
    assert view.approve(view.request, str(requisition_id)).data["status"] == "approve_requisition"
    assert view.reject(view.request, str(requisition_id)).data["status"] == "reject_requisition"
    assert view.revise(view.request, str(requisition_id)).data["status"] == "revise_requisition"
    assert view.cancel(view.request, str(requisition_id)).data["status"] == "cancel_requisition"
    assert view.convert_to_order(view.request, str(requisition_id)).data["status"] == "convert_to_purchase_order"

    assert calls[0][1][0] == tenant_id
    assert calls[1][1][4] == 4
    assert calls[3][2]["idempotency_key"] == "idem"
    assert calls[-1][1][2] == str(requisition_id)


def test_rfq_quote_order_and_receipt_viewsets_forward_actions(monkeypatch):
    headers = {"If-Match": "3", "Idempotency-Key": "idem"}
    calls = []

    rfq_view, tenant_id = _prepared_view(RFQViewSet, monkeypatch, headers=headers)
    monkeypatch.setattr(purchase_api, "RFQWriteSerializer", _serializer({"title": "RFQ"}))
    monkeypatch.setattr(
        purchase_api,
        "RFQPublishSerializer",
        _serializer({"supplier_ids": [uuid.uuid4(), uuid.uuid4()]}),
    )
    monkeypatch.setattr(
        purchase_api,
        "RFQAwardSerializer",
        _serializer({"quote_id": uuid.uuid4(), "create_purchase_order": True}),
    )
    monkeypatch.setattr(purchase_api, "RFQDetailSerializer", _OutputSerializer)
    monkeypatch.setattr(purchase_api, "QuoteDetailSerializer", _OutputSerializer)
    monkeypatch.setattr(purchase_api, "PurchaseOrderDetailSerializer", _OutputSerializer)
    for name in ("create_rfq", "update_rfq", "delete_draft_rfq", "close_rfq", "cancel_rfq"):
        monkeypatch.setattr(
            purchase_api.RFQService,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)) or _resource(_name),
        )
    monkeypatch.setattr(
        purchase_api.RFQService,
        "publish_rfq",
        lambda *args: calls.append(("publish_rfq", args, {})) or (_resource("open"), SimpleNamespace(id=uuid.uuid4())),
    )
    monkeypatch.setattr(
        purchase_api.RFQService,
        "compare_quotes",
        lambda *args: calls.append(("compare", args, {})) or {"quotes": []},
    )
    monkeypatch.setattr(
        purchase_api.RFQService,
        "award_quote",
        lambda *args: calls.append(("award", args, {})) or (_resource("accepted"), _resource("draft")),
    )

    assert rfq_view.create(rfq_view.request).status_code == status.HTTP_201_CREATED
    assert rfq_view.update(rfq_view.request, "rfq-id").data["status"] == "update_rfq"
    assert rfq_view.destroy(rfq_view.request, "rfq-id").data["status"] == "delete_draft_rfq"
    assert rfq_view.publish(rfq_view.request, "rfq-id").status_code == status.HTTP_202_ACCEPTED
    assert rfq_view.close(rfq_view.request, "rfq-id").data["status"] == "close_rfq"
    assert rfq_view.cancel(rfq_view.request, "rfq-id").data["status"] == "cancel_rfq"
    assert rfq_view.compare_quotes(rfq_view.request, "rfq-id").data == {"quotes": []}
    assert rfq_view.award(rfq_view.request, "rfq-id").data["quote"]["status"] == "accepted"

    quote_view, _ = _prepared_view(QuoteViewSet, monkeypatch, headers=headers)
    monkeypatch.setattr(purchase_api, "QuoteWriteSerializer", _serializer({"quote_number": "Q"}))
    for name in ("create_quote", "update_quote", "delete_draft_quote", "submit_quote", "withdraw_quote"):
        monkeypatch.setattr(
            purchase_api.QuoteService,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)) or _resource(_name),
        )
    assert quote_view.create(quote_view.request).status_code == status.HTTP_201_CREATED
    assert quote_view.partial_update(quote_view.request, "quote-id").data["status"] == "update_quote"
    assert quote_view.destroy(quote_view.request, "quote-id").data == {"status": "deleted"}
    assert quote_view.submit(quote_view.request, "quote-id").data["status"] == "submit_quote"
    assert quote_view.withdraw(quote_view.request, "quote-id").data["status"] == "withdraw_quote"

    order_view, _ = _prepared_view(PurchaseOrderViewSet, monkeypatch, headers=headers)
    monkeypatch.setattr(purchase_api, "PurchaseOrderWriteSerializer", _serializer({"po_number": "PO"}))
    for name in (
        "create_purchase_order",
        "update_purchase_order",
        "delete_draft_purchase_order",
        "submit_purchase_order",
        "approve_purchase_order",
        "reject_purchase_order",
        "acknowledge_purchase_order",
        "cancel_purchase_order",
    ):
        monkeypatch.setattr(
            purchase_api.PurchaseOrderService,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)) or _resource(_name),
        )
    monkeypatch.setattr(
        purchase_api.PurchaseOrderService,
        "dispatch_purchase_order",
        lambda *args: calls.append(("dispatch_purchase_order", args, {}))
        or (_resource("sent"), SimpleNamespace(id=uuid.uuid4())),
    )
    assert order_view.create(order_view.request).status_code == status.HTTP_201_CREATED
    assert order_view.update(order_view.request, "po-id").data["status"] == "update_purchase_order"
    assert order_view.destroy(order_view.request, "po-id").data["status"] == "delete_draft_purchase_order"
    assert order_view.submit(order_view.request, "po-id").data["status"] == "submit_purchase_order"
    assert order_view.approve(order_view.request, "po-id").data["status"] == "approve_purchase_order"
    assert order_view.reject(order_view.request, "po-id").data["status"] == "reject_purchase_order"
    assert order_view.acknowledge(order_view.request, "po-id").data["status"] == "acknowledge_purchase_order"
    assert order_view.cancel(order_view.request, "po-id").data["status"] == "cancel_purchase_order"
    assert order_view.dispatch_order(order_view.request, "po-id").status_code == status.HTTP_202_ACCEPTED

    receipt_view, _ = _prepared_view(ReceiptViewSet, monkeypatch, headers=headers)
    monkeypatch.setattr(purchase_api, "ReceiptWriteSerializer", _serializer({"receipt_number": "GRN"}))
    monkeypatch.setattr(purchase_api, "ReceiptCompleteSerializer", _serializer({}))
    monkeypatch.setattr(purchase_api, "ReceiptDetailSerializer", _OutputSerializer)
    for name in (
        "create_receipt",
        "update_receipt",
        "delete_draft_receipt",
        "complete_receipt",
        "cancel_receipt",
    ):
        monkeypatch.setattr(
            purchase_api.PurchaseReceiptService,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)) or _resource(_name),
        )
    assert receipt_view.create(receipt_view.request).status_code == status.HTTP_201_CREATED
    assert receipt_view.partial_update(receipt_view.request, "receipt-id").data["status"] == "update_receipt"
    assert receipt_view.destroy(receipt_view.request, "receipt-id").data == {"status": "deleted"}
    assert receipt_view.complete(receipt_view.request, "receipt-id").data["status"] == "complete_receipt"
    assert receipt_view.cancel(receipt_view.request, "receipt-id").data["status"] == "cancel_receipt"

    assert calls[0][1][0] == tenant_id
    assert ("publish_rfq",) == (calls[3][0],)
    assert any(call[0] == "dispatch_purchase_order" and call[1][3] == "idem" for call in calls)


def test_configuration_viewset_forwards_version_preview_import_export(monkeypatch):
    view, tenant_id = _prepared_view(
        ConfigurationViewSet,
        monkeypatch,
        headers={"If-Match": "9"},
        query_params={"environment": "development"},
        method="GET",
    )
    calls = []
    monkeypatch.setattr(purchase_api, "ConfigurationSerializer", _OutputSerializer)
    monkeypatch.setattr(purchase_api, "ConfigurationWriteSerializer", _serializer({"default_currency": "USD"}))
    monkeypatch.setattr(
        purchase_api,
        "ConfigurationPreviewSerializer",
        _serializer({"environment": "development", "simulations": [{"amount": "10"}], "default_currency": "USD"}),
    )
    monkeypatch.setattr(purchase_api, "ConfigurationRollbackSerializer", _serializer({"reason": "audit"}))
    monkeypatch.setattr(purchase_api, "ConfigurationImportSerializer", _serializer({"document": {"schema": "x"}}))
    for name in (
        "get_active_configuration",
        "create_draft",
        "get_version",
        "update_draft",
        "activate_configuration",
        "rollback_configuration",
        "import_configuration",
    ):
        monkeypatch.setattr(
            purchase_api.ProcurementConfigurationService,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)) or _resource(_name),
        )
    monkeypatch.setattr(
        purchase_api.ProcurementConfigurationService,
        "list_versions",
        lambda *args: calls.append(("list_versions", args, {})) or [],
    )
    monkeypatch.setattr(
        purchase_api.ProcurementConfigurationService,
        "preview_configuration",
        lambda *args: calls.append(("preview", args, {})) or {"valid": True},
    )
    monkeypatch.setattr(
        purchase_api.ProcurementConfigurationService,
        "export_configuration",
        lambda *args: calls.append(("export", args, {})) or {"schema": "exported"},
    )

    assert view.active(view.request).data["status"] == "get_active_configuration"
    view._list = lambda queryset, serializer: purchase_api.Response({"listed": True})
    assert view.versions(view.request).data is not None
    post_view, _ = _prepared_view(
        ConfigurationViewSet,
        monkeypatch,
        method="POST",
        query_params={},
        data={"environment": "development"},
    )
    assert post_view.versions(post_view.request).status_code == status.HTTP_201_CREATED
    assert view.version_detail(view.request, "version-id").data["status"] == "get_version"
    patch_view, _ = _prepared_view(
        ConfigurationViewSet,
        monkeypatch,
        method="PATCH",
        headers={"If-Match": "9"},
    )
    assert patch_view.version_detail(patch_view.request, "version-id").data["status"] == "update_draft"
    assert view.preview(view.request).data == {"valid": True}
    assert view.activate_version(view.request, "version-id").data["status"] == "activate_configuration"
    assert view.rollback(view.request, "version-id").data["status"] == "rollback_configuration"
    assert view.export_configuration(view.request).data == {"schema": "exported"}
    assert view.import_configuration(view.request).status_code == status.HTTP_201_CREATED

    assert calls[0][1] == (tenant_id, "development")
    assert any(call[0] == "update_draft" and call[1][4] == 9 for call in calls)
