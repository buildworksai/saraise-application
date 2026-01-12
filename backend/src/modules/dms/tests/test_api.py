"""
API Integration Tests for Dms module.

Tests all DRF ViewSet endpoints:
- CRUD operations
- Authentication/authorization
- Tenant isolation
- Custom actions
"""
import io
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from ..models import Document, DocumentPermission, DocumentShare, DocumentVersion, Folder
from src.core.auth_utils import get_user_tenant_id

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_user(db):
    """Create a test user with tenant."""
    from src.core.user_models import UserProfile
    from src.core.licensing.models import Organization
    import uuid

    # Create a valid Organization for the tenant
    org = Organization.objects.create(name="Test Organization")
    tenant_id = str(org.id)

    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = tenant_id
    profile.tenant_role = "tenant_admin"
    profile.save()

    return User.objects.get(pk=user.pk)


@pytest.fixture
def authenticated_client(api_client, tenant_user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.mark.django_db
class TestFolderViewSet:
    """Test FolderViewSet CRUD operations."""

    def test_list_folders(self, authenticated_client, tenant_user):
        """Test listing folders for authenticated user."""
        tenant_id = get_user_tenant_id(tenant_user)

        # Create test folders
        Folder.objects.create(
            tenant_id=tenant_id,
            name="Folder 1",
            created_by=str(tenant_user.id),
        )
        Folder.objects.create(
            tenant_id=tenant_id,
            name="Folder 2",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get("/api/v1/dms/folders/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 2

    def test_create_folder(self, authenticated_client, tenant_user):
        """Test creating a folder."""
        tenant_id = get_user_tenant_id(tenant_user)

        data = {"name": "New Folder"}

        response = authenticated_client.post("/api/v1/dms/folders/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Folder"
        assert response.data["tenant_id"] == tenant_id

    def test_get_folder_detail(self, authenticated_client, tenant_user):
        """Test getting folder detail."""
        tenant_id = get_user_tenant_id(tenant_user)

        folder = Folder.objects.create(
            tenant_id=tenant_id,
            name="Test Folder",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get(f"/api/v1/dms/folders/{folder.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == folder.id
        assert response.data["name"] == "Test Folder"

    def test_move_folder(self, authenticated_client, tenant_user):
        """Test moving a folder to a different parent."""
        tenant_id = get_user_tenant_id(tenant_user)

        parent = Folder.objects.create(
            tenant_id=tenant_id,
            name="Parent Folder",
            created_by=str(tenant_user.id),
        )
        child = Folder.objects.create(
            tenant_id=tenant_id,
            name="Child Folder",
            created_by=str(tenant_user.id),
        )

        data = {"parent_id": parent.id}
        response = authenticated_client.post(f"/api/v1/dms/folders/{child.id}/move/", data, format="json")
        assert response.status_code == status.HTTP_200_OK
        child.refresh_from_db()
        assert child.parent == parent


@pytest.mark.django_db
class TestDocumentViewSet:
    """Test DocumentViewSet CRUD operations."""

    def test_list_documents(self, authenticated_client, tenant_user):
        """Test listing documents for authenticated user."""
        tenant_id = get_user_tenant_id(tenant_user)

        # Create test documents
        Document.objects.create(
            tenant_id=tenant_id,
            name="Document 1",
            file_path="tenants/123/documents/test1",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_user.id),
        )
        Document.objects.create(
            tenant_id=tenant_id,
            name="Document 2",
            file_path="tenants/123/documents/test2",
            mime_type="text/plain",
            size=200,
            checksum="def456",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get("/api/v1/dms/documents/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 2

    def test_get_document_detail(self, authenticated_client, tenant_user):
        """Test getting document detail."""
        tenant_id = get_user_tenant_id(tenant_user)

        document = Document.objects.create(
            tenant_id=tenant_id,
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get(f"/api/v1/dms/documents/{document.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == document.id
        assert response.data["name"] == "Test Document"


@pytest.mark.django_db
class TestDocumentVersionViewSet:
    """Test DocumentVersionViewSet read operations."""

    def test_list_document_versions(self, authenticated_client, tenant_user):
        """Test listing document versions."""
        tenant_id = get_user_tenant_id(tenant_user)

        document = Document.objects.create(
            tenant_id=tenant_id,
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_user.id),
        )

        DocumentVersion.objects.create(
            document=document,
            version_number=1,
            file_path="tenants/123/documents/test",
            created_by=str(tenant_user.id),
        )
        DocumentVersion.objects.create(
            document=document,
            version_number=2,
            file_path="tenants/123/documents/test2",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get(f"/api/v1/dms/document-versions/?document_id={document.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 2


@pytest.mark.django_db
class TestDocumentPermissionViewSet:
    """Test DocumentPermissionViewSet CRUD operations."""

    def test_create_document_permission(self, authenticated_client, tenant_user):
        """Test creating a document permission."""
        tenant_id = get_user_tenant_id(tenant_user)

        document = Document.objects.create(
            tenant_id=tenant_id,
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_user.id),
        )

        data = {
            "document": document.id,
            "principal_type": "user",
            "principal_id": "user-456",
            "permission": "read",
        }

        response = authenticated_client.post("/api/v1/dms/document-permissions/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["permission"] == "read"
        assert response.data["tenant_id"] == tenant_id


@pytest.mark.django_db
class TestDocumentShareViewSet:
    """Test DocumentShareViewSet CRUD operations."""

    def test_create_document_share(self, authenticated_client, tenant_user):
        """Test creating a document share."""
        tenant_id = get_user_tenant_id(tenant_user)

        document = Document.objects.create(
            tenant_id=tenant_id,
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by=str(tenant_user.id),
        )

        data = {
            "document": document.id,
            "permissions": ["read"],
        }

        response = authenticated_client.post("/api/v1/dms/document-shares/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["share_token"] is not None
        assert response.data["tenant_id"] == tenant_id
        assert "read" in response.data["permissions"]
