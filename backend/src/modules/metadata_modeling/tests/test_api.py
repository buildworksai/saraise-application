from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from src.modules.tenant_management.models import Tenant
from src.core.licensing.models import Organization, License, LicenseStatus
from src.modules.metadata_modeling.models import EntityDefinition, FieldDefinition, DynamicResource

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

        # 2. Add Fields (Directly in DB for simplicity of test, or via nested update if supported)
        # Assuming ViewSet supports standard model viewing, adding fields requires either nested write (not implemented in serializer)
        # or separate endpoint. For Phase 8 we probably rely on admin or direct usage.
        # But wait, Models allow separate editing. Let's create fields manually to test Resource API.
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
