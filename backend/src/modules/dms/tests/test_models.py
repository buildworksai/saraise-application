"""
Model Unit Tests for Dms module.

Tests model creation, validation, and relationships.
"""
import pytest
from django.core.exceptions import ValidationError

from src.modules.dms.models import Document, DocumentPermission, DocumentShare, DocumentVersion, Folder


@pytest.mark.django_db
class TestFolderModel:
    """Test Folder model."""

    def test_create_folder(self, db):
        """Test creating a folder."""
        folder = Folder.objects.create(
            tenant_id="tenant-123",
            name="Test Folder",
            created_by="user-123",
        )
        assert folder.id is not None
        assert folder.name == "Test Folder"
        assert folder.tenant_id == "tenant-123"
        assert folder.path == ""

    def test_create_nested_folder(self, db):
        """Test creating a nested folder."""
        parent = Folder.objects.create(
            tenant_id="tenant-123",
            name="Parent",
            created_by="user-123",
        )
        child = Folder.objects.create(
            tenant_id="tenant-123",
            name="Child",
            parent=parent,
            created_by="user-123",
        )
        assert child.parent == parent
        assert child.path == ""

    def test_folder_str_representation(self, db):
        """Test folder string representation."""
        folder = Folder.objects.create(
            tenant_id="tenant-123",
            name="Test Folder",
            created_by="user-123",
        )
        assert "Test Folder" in str(folder)


@pytest.mark.django_db
class TestDocumentModel:
    """Test Document model."""

    def test_create_document(self, db):
        """Test creating a document."""
        document = Document.objects.create(
            tenant_id="tenant-123",
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by="user-123",
        )
        assert document.id is not None
        assert document.name == "Test Document"
        assert document.tenant_id == "tenant-123"
        assert document.size == 100

    def test_document_with_folder(self, db):
        """Test creating a document in a folder."""
        folder = Folder.objects.create(
            tenant_id="tenant-123",
            name="Test Folder",
            created_by="user-123",
        )
        document = Document.objects.create(
            tenant_id="tenant-123",
            name="Test Document",
            folder=folder,
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by="user-123",
        )
        assert document.folder == folder

    def test_document_str_representation(self, db):
        """Test document string representation."""
        document = Document.objects.create(
            tenant_id="tenant-123",
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by="user-123",
        )
        assert "Test Document" in str(document)


@pytest.mark.django_db
class TestDocumentVersionModel:
    """Test DocumentVersion model."""

    def test_create_document_version(self, db):
        """Test creating a document version."""
        document = Document.objects.create(
            tenant_id="tenant-123",
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by="user-123",
        )
        version = DocumentVersion.objects.create(
            document=document,
            version_number=1,
            file_path="tenants/123/documents/test",
            created_by="user-123",
        )
        assert version.id is not None
        assert version.document == document
        assert version.version_number == 1

    def test_multiple_versions(self, db):
        """Test creating multiple versions of a document."""
        document = Document.objects.create(
            tenant_id="tenant-123",
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by="user-123",
        )
        version1 = DocumentVersion.objects.create(
            document=document,
            version_number=1,
            file_path="tenants/123/documents/test1",
            created_by="user-123",
        )
        version2 = DocumentVersion.objects.create(
            document=document,
            version_number=2,
            file_path="tenants/123/documents/test2",
            created_by="user-123",
        )
        assert version1.version_number == 1
        assert version2.version_number == 2
        assert document.versions.count() == 2


@pytest.mark.django_db
class TestDocumentPermissionModel:
    """Test DocumentPermission model."""

    def test_create_document_permission(self, db):
        """Test creating a document permission."""
        document = Document.objects.create(
            tenant_id="tenant-123",
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by="user-123",
        )
        permission = DocumentPermission.objects.create(
            tenant_id="tenant-123",
            document=document,
            principal_type="user",
            principal_id="user-456",
            permission="read",
        )
        assert permission.id is not None
        assert permission.document == document
        assert permission.permission == "read"


@pytest.mark.django_db
class TestDocumentShareModel:
    """Test DocumentShare model."""

    def test_create_document_share(self, db):
        """Test creating a document share."""
        document = Document.objects.create(
            tenant_id="tenant-123",
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by="user-123",
        )
        share = DocumentShare.objects.create(
            tenant_id="tenant-123",
            document=document,
            share_token="test_token_123",
            permissions=["read"],
            created_by="user-123",
        )
        assert share.id is not None
        assert share.document == document
        assert share.share_token == "test_token_123"
        assert share.is_expired is False

    def test_expired_share(self, db):
        """Test expired share link."""
        from django.utils import timezone
        from datetime import timedelta

        document = Document.objects.create(
            tenant_id="tenant-123",
            name="Test Document",
            file_path="tenants/123/documents/test",
            mime_type="text/plain",
            size=100,
            checksum="abc123",
            created_by="user-123",
        )
        share = DocumentShare.objects.create(
            tenant_id="tenant-123",
            document=document,
            share_token="test_token_123",
            expires_at=timezone.now() - timedelta(days=1),
            permissions=["read"],
            created_by="user-123",
        )
        assert share.is_expired is True
