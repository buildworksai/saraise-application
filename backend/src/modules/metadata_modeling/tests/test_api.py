import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APITestCase

from src.core.licensing.models import License, LicenseStatus, Organization
from src.modules.metadata_modeling import api
from src.modules.metadata_modeling import services as metadata_services
from src.modules.metadata_modeling.models import EntityDefinition, FieldDefinition, NamingSequence
from src.modules.tenant_management.models import Tenant

User = get_user_model()


class MetadataAPITestCase(APITestCase):
    def setUp(self):
        # Setup Organization & License & Tenant & User
        self.org = Organization.objects.create(name="Test Org", domain="example.com")
        License.objects.create(organization=self.org, status=LicenseStatus.ACTIVE, license_key="key", max_users=-1)
        self.tenant = Tenant.objects.create(id=self.org.id, name="Test Tenant", slug="test-tenant")
        self.user = User.objects.create_user(username="testuser", password="password", email="test@example.com")

        profile = self.user.profile
        profile.tenant_id = self.org.id
        profile.save()
        self.user.refresh_from_db()

        self.client.force_authenticate(user=self.user)

    def test_entity_lifecycle(self):
        # 1. Create Entity
        url = reverse("entity-definition-list")
        data = {"name": "Ticket", "code": "ticket", "description": "Support Ticket"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entity_id = response.data["id"]

        # 2. Add Fields - Create fields manually to test Resource API.
        entity = EntityDefinition.objects.get(id=entity_id)
        FieldDefinition.objects.create(
            tenant_id=self.tenant.id,
            entity_definition=entity,
            name="Title",
            key="title",
            field_type="text",
            is_required=True,
        )
        FieldDefinition.objects.create(
            tenant_id=self.tenant.id,
            entity_definition=entity,
            name="Priority",
            key="priority",
            field_type="number",
            is_required=False,
        )

        # 3. Create Resource
        res_url = reverse("dynamic-resource-list")
        res_data = {"entity_definition": entity_id, "data": {"title": "My Issue", "priority": 1}}
        res_response = self.client.post(res_url, res_data, format="json")
        self.assertEqual(res_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_response.data["data"]["title"], "My Issue")

        # 4. Filter Resource
        list_response = self.client.get(res_url, {"entity_code": "ticket"})
        self.assertEqual(len(list_response.data), 1)

    def test_validation_error_api(self):
        # Setup
        entity = EntityDefinition.objects.create(tenant_id=self.tenant.id, name="Asset", code="asset")
        FieldDefinition.objects.create(
            tenant_id=self.tenant.id,
            entity_definition=entity,
            name="Tag",
            key="tag",
            field_type="text",
            is_required=True,
        )

        res_url = reverse("dynamic-resource-list")

        # Missing Required Field
        res_data = {"entity_definition": entity.id, "data": {"other": "value"}}  # 'tag' missing
        response = self.client.post(res_url, res_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tag", response.data)

    def test_page_returns_unpaginated_serializer_data_when_pagination_is_disabled(self):
        entity = EntityDefinition.objects.create(tenant_id=self.tenant.id, name="Asset", code="asset")
        view = api.EntityDefinitionViewSet()
        view.paginate_queryset = lambda queryset: None

        response = view._page(EntityDefinition.objects.filter(id=entity.id), api.EntityDefinitionListSerializer)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["id"], str(entity.id))

    def test_api_guard_helpers_fail_closed_and_parse_request_contracts(self):
        tenant_id = uuid.uuid4()
        request = SimpleNamespace(
            user=SimpleNamespace(id=tenant_id),
            headers={"Idempotency-Key": "create-1", "If-Match": 'W/"3"'},
            data={},
            query_params={"from": "2026-08-03T10:00:00Z", "bad": "not-a-date"},
        )

        original_get_user_tenant_id = api.get_user_tenant_id
        try:
            api.get_user_tenant_id = lambda user: str(tenant_id)
            self.assertEqual(api._tenant_id(request), tenant_id)
            self.assertEqual(api._actor_id(request), tenant_id)
            self.assertEqual(api._idempotency_key(request), "create-1")
            self.assertEqual(api._lock_version(request), 3)
            self.assertIsNotNone(api._date_param(request, "from"))
            self.assertIsNone(api._uuid_param("", "optional_id"))
            parsed = api._required_uuid(str(tenant_id), "definition_id")
            self.assertEqual(parsed, tenant_id)

            api.get_user_tenant_id = lambda user: None
            with self.assertRaises(PermissionDenied):
                api._tenant_id(request)

            api.get_user_tenant_id = lambda user: "not-a-uuid"
            with self.assertRaises(PermissionDenied):
                api._tenant_id(request)
        finally:
            api.get_user_tenant_id = original_get_user_tenant_id

        with self.assertRaises(ValidationError):
            api._date_param(request, "bad")
        with self.assertRaises(ValidationError):
            api._uuid_param("not-a-uuid", "optional_id")
        with self.assertRaises(ValidationError):
            api._required_uuid("", "definition_id")

        request.headers = {}
        with self.assertRaises(ValidationError):
            api._idempotency_key(request)
        request.headers = {"Idempotency-Key": "x" * 256}
        with self.assertRaises(ValidationError):
            api._idempotency_key(request)

        request.headers = {}
        request.data = {}
        with self.assertRaises(ValidationError):
            api._lock_version(request)
        request.headers = {"If-Match": "0"}
        with self.assertRaises(ValidationError):
            api._lock_version(request)
        request.headers = {}
        request.data = {"lock_version": "4"}
        self.assertEqual(api._lock_version(request), 4)

    def test_governed_metadata_viewset_v1_and_v2_permission_response_branches(self):
        view = api.EntityDefinitionViewSet()
        view.action = "list"
        view.request = SimpleNamespace(path="/api/v1/metadata-modeling/entities/")
        self.assertEqual(len(view.get_permissions()), 1)

        view.request = SimpleNamespace(path="/api/v2/metadata-modeling/entities/")
        permissions = view.get_permissions()
        self.assertEqual(len(permissions), 2)
        self.assertEqual(view.required_permission, "metadata_modeling.schema:read")

        response = api.Response({})
        request = SimpleNamespace()
        original_finalize = api.viewsets.GenericViewSet.finalize_response
        original_correlation = api.correlation_id_for_request
        try:
            api.viewsets.GenericViewSet.finalize_response = lambda self, request, response, *args, **kwargs: response
            api.correlation_id_for_request = lambda request: "corr-api"
            finalized = view.finalize_response(request, response)
        finally:
            api.viewsets.GenericViewSet.finalize_response = original_finalize
            api.correlation_id_for_request = original_correlation
        self.assertEqual(finalized["X-Correlation-ID"], "corr-api")

    def test_metadata_configuration_import_rejects_malformed_and_bad_checksum_documents(self):
        request = SimpleNamespace(data="not-an-object", query_params={}, user=self.user)
        view = api.MetadataConfigurationViewSet()

        with self.assertRaises(ValidationError):
            view.import_config(request)

        request.data = {"document": "not-an-object"}
        with self.assertRaises(ValidationError):
            view.import_config(request)

        request.data = {"validate_only": True, "document": {"checksum": "wrong", "values": {}}}
        with self.assertRaises(ValidationError) as exc:
            view.import_config(request)
        self.assertIn("checksum", exc.exception.detail)

    def test_metadata_configuration_import_validate_only_previews_verified_document(self):
        request = SimpleNamespace(
            data={"validate_only": True, "document": {"checksum": "expected", "values": {"record_soft_delete": True}}},
            query_params={"environment": "staging"},
            user=self.user,
            headers={},
        )
        view = api.MetadataConfigurationViewSet()
        view.request = request

        original_hash = metadata_services._schema_hash
        original_preview = api.MetadataConfigurationService.preview_configuration
        try:
            metadata_services._schema_hash = lambda document: "expected"
            api.MetadataConfigurationService.preview_configuration = lambda tenant_id, environment, values: {
                "environment": environment,
                "values": values,
            }
            response = view.import_config(request)
        finally:
            metadata_services._schema_hash = original_hash
            api.MetadataConfigurationService.preview_configuration = original_preview

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["environment"], "staging")
        self.assertTrue(response.data["values"]["record_soft_delete"])

    def test_naming_sequence_queryset_filters_and_preview_rejects_non_object_data(self):
        entity = EntityDefinition.objects.create(tenant_id=self.tenant.id, name="Asset", code="asset")
        active = NamingSequence.objects.create(
            tenant_id=self.tenant.id,
            entity_definition=entity,
            sequence_key="asset",
            prefix_template="AST-{seq}",
            next_value=1,
            is_active=True,
        )
        NamingSequence.objects.create(
            tenant_id=self.tenant.id,
            entity_definition=entity,
            sequence_key="archived",
            prefix_template="OLD-{seq}",
            next_value=1,
            is_active=False,
        )
        request = SimpleNamespace(
            user=self.user,
            query_params={"entity_id": str(entity.id), "is_active": "true"},
            data={"entity_id": str(entity.id), "data": ["not", "an", "object"]},
            headers={},
        )
        view = api.NamingSequenceViewSet()
        view.request = request

        rows = list(view.get_queryset())
        self.assertEqual(rows, [active])
        with self.assertRaises(ValidationError):
            view.preview(request)


def test_metadata_configuration_rollback_requires_integer_version(monkeypatch):
    view = api.MetadataConfigurationViewSet()
    tenant_id = uuid.uuid4()
    request = SimpleNamespace(query_params={}, user=SimpleNamespace(id=tenant_id), headers={})
    view.request = request
    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: tenant_id)

    with pytest.raises(ValueError):
        view.rollback(request, version="not-a-number")
