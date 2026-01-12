"""
Tenant Isolation Tests for Dms module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from ..models import Document, DocumentPermission, DocumentShare, DocumentVersion, Folder
from src.core.auth_utils import get_user_tenant_id

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
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
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


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
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
class TestFolderTenantIsolation:
    """Tenant isolation tests for Folder model."""

    def test_user_cannot_list_other_tenant_folders(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's folders in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create folder for tenant A
        folder_a = Folder.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Folder",
            created_by=str(tenant_a_user.id),
        )

        # Create folder for tenant B
        folder_b = Folder.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Folder",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/dms/folders/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        folder_ids = [f["id"] for f in data]

        # User A should see tenant A's folder, but NOT tenant B's folder
        assert folder_a.id in folder_ids
        assert folder_b.id not in folder_ids

    def test_user_cannot_get_other_tenant_folder_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's folder by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create folder for tenant B
        folder_b = Folder.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Folder",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's folder
        response = api_client.get(f"/api/v1/dms/folders/{folder_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_folder(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot UPDATE other tenant's folder (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create folder for tenant B
        folder_b = Folder.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Folder",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to update tenant B's folder
        data = {"name": "Hacked Name"}
        response = api_client.put(f"/api/v1/dms/folders/{folder_b.id}/", data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify folder was not modified
        folder_b.refresh_from_db()
        assert folder_b.name == "Tenant B Folder"


@pytest.mark.django_db
class TestDocumentTenantIsolation:
    """Tenant isolation tests for Document model."""

    def test_user_cannot_list_other_tenant_documents(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's documents in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create document for tenant A
        document_a = Document.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Document",
            file_path="tenants/a/documents/test1",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_a_user.id),
        )

        # Create document for tenant B
        document_b = Document.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Document",
            file_path="tenants/b/documents/test2",
            mime_type="text/plain",
            size=200,
            checksum="def456",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/dms/documents/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        document_ids = [d["id"] for d in data]

        # User A should see tenant A's document, but NOT tenant B's document
        assert document_a.id in document_ids
        assert document_b.id not in document_ids

    def test_user_cannot_get_other_tenant_document_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's document by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create document for tenant B
        document_b = Document.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Document",
            file_path="tenants/b/documents/test2",
            mime_type="text/plain",
            size=200,
            checksum="def456",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's document
        response = api_client.get(f"/api/v1/dms/documents/{document_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_download_other_tenant_document(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot download other tenant's document (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create document for tenant B
        document_b = Document.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Document",
            file_path="tenants/b/documents/test2",
            mime_type="text/plain",
            size=200,
            checksum="def456",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to download tenant B's document
        response = api_client.get(f"/api/v1/dms/documents/{document_b.id}/download/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestDocumentVersionTenantIsolation:
    """Tenant isolation tests for DocumentVersion model."""

    def test_user_cannot_list_other_tenant_document_versions(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's document versions."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create documents
        document_a = Document.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Document",
            file_path="tenants/a/documents/test1",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_a_user.id),
        )

        document_b = Document.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Document",
            file_path="tenants/b/documents/test2",
            mime_type="text/plain",
            size=200,
            checksum="def456",
            created_by=str(tenant_b_user.id),
        )

        # Create versions
        version_a = DocumentVersion.objects.create(
            document=document_a,
            version_number=1,
            file_path="tenants/a/documents/test1",
            created_by=str(tenant_a_user.id),
        )

        version_b = DocumentVersion.objects.create(
            document=document_b,
            version_number=1,
            file_path="tenants/b/documents/test2",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/dms/document-versions/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        version_ids = [v["id"] for v in data]

        # User A should see tenant A's version, but NOT tenant B's version
        assert version_a.id in version_ids
        assert version_b.id not in version_ids


@pytest.mark.django_db
class TestDocumentPermissionTenantIsolation:
    """Tenant isolation tests for DocumentPermission model."""

    def test_user_cannot_list_other_tenant_document_permissions(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's document permissions."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create documents
        document_a = Document.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Document",
            file_path="tenants/a/documents/test1",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_a_user.id),
        )

        document_b = Document.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Document",
            file_path="tenants/b/documents/test2",
            mime_type="text/plain",
            size=200,
            checksum="def456",
            created_by=str(tenant_b_user.id),
        )

        # Create permissions
        permission_a = DocumentPermission.objects.create(
            tenant_id=tenant_a_id,
            document=document_a,
            principal_type="user",
            principal_id=str(tenant_a_user.id),
            permission="read",
        )

        permission_b = DocumentPermission.objects.create(
            tenant_id=tenant_b_id,
            document=document_b,
            principal_type="user",
            principal_id=str(tenant_b_user.id),
            permission="read",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/dms/document-permissions/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        permission_ids = [p["id"] for p in data]

        # User A should see tenant A's permission, but NOT tenant B's permission
        assert permission_a.id in permission_ids
        assert permission_b.id not in permission_ids


@pytest.mark.django_db
class TestDocumentShareTenantIsolation:
    """Tenant isolation tests for DocumentShare model."""

    def test_user_cannot_list_other_tenant_document_shares(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's document shares."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create documents
        document_a = Document.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Document",
            file_path="tenants/a/documents/test1",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_a_user.id),
        )

        document_b = Document.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Document",
            file_path="tenants/b/documents/test2",
            mime_type="text/plain",
            size=200,
            checksum="def456",
            created_by=str(tenant_b_user.id),
        )

        # Create shares
        share_a = DocumentShare.objects.create(
            tenant_id=tenant_a_id,
            document=document_a,
            share_token="token_a_123",
            permissions=["read"],
            created_by=str(tenant_a_user.id),
        )

        share_b = DocumentShare.objects.create(
            tenant_id=tenant_b_id,
            document=document_b,
            share_token="token_b_456",
            permissions=["read"],
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/dms/document-shares/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        share_ids = [s["id"] for s in data]

        # User A should see tenant A's share, but NOT tenant B's share
        assert share_a.id in share_ids
        assert share_b.id not in share_ids
