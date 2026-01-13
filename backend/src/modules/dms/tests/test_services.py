"""
Service Unit Tests for Dms module.

Tests business logic in services layer.
"""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from src.modules.dms.models import Document, DocumentVersion, Folder
from src.modules.dms.services import DocumentStorageService


@pytest.mark.django_db
class TestDocumentStorageService:
    """Test DocumentStorageService business logic."""

    def test_upload_document(self, db):
        """Test uploading a document."""
        service = DocumentStorageService()
        file = SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")

        document = service.upload_document(
            tenant_id="tenant-123",
            folder_id=None,
            file=file,
            filename="test.txt",
            user_id="user-123",
        )
        assert document.id is not None
        assert document.name == "test.txt"
        assert document.tenant_id == "tenant-123"
        assert document.size == len(b"test content")
        assert document.checksum is not None

        # Verify version was created
        assert document.versions.count() == 1
        version = document.versions.first()
        assert version.version_number == 1

    def test_upload_document_to_folder(self, db):
        """Test uploading a document to a folder."""
        service = DocumentStorageService()
        folder = Folder.objects.create(
            tenant_id="tenant-123",
            name="Test Folder",
            created_by="user-123",
        )
        file = SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")

        document = service.upload_document(
            tenant_id="tenant-123",
            folder_id=folder.id,
            file=file,
            filename="test.txt",
            user_id="user-123",
        )
        assert document.folder == folder

    def test_upload_document_wrong_folder_tenant(self, db):
        """Test that uploading to folder from different tenant raises error."""
        service = DocumentStorageService()
        folder = Folder.objects.create(
            tenant_id="tenant-456",
            name="Other Tenant Folder",
            created_by="user-456",
        )
        file = SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")

        with pytest.raises(ValueError, match="Folder.*not found"):
            service.upload_document(
                tenant_id="tenant-123",
                folder_id=folder.id,
                file=file,
                filename="test.txt",
                user_id="user-123",
            )

    def test_download_document(self, db):
        """Test downloading a document."""
        service = DocumentStorageService()
        file = SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")

        document = service.upload_document(
            tenant_id="tenant-123",
            folder_id=None,
            file=file,
            filename="test.txt",
            user_id="user-123",
        )

        downloaded_file, filename, mime_type = service.download_document("tenant-123", document.id)
        assert filename == "test.txt"
        assert mime_type == "text/plain"

    def test_download_document_wrong_tenant(self, db):
        """Test that downloading document from different tenant raises error."""
        service = DocumentStorageService()
        file = SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")

        document = service.upload_document(
            tenant_id="tenant-123",
            folder_id=None,
            file=file,
            filename="test.txt",
            user_id="user-123",
        )

        with pytest.raises(Document.DoesNotExist):
            service.download_document("tenant-456", document.id)

    def test_create_version(self, db):
        """Test creating a new version of a document."""
        service = DocumentStorageService()
        file1 = SimpleUploadedFile("test.txt", b"version 1", content_type="text/plain")

        document = service.upload_document(
            tenant_id="tenant-123",
            folder_id=None,
            file=file1,
            filename="test.txt",
            user_id="user-123",
        )

        file2 = SimpleUploadedFile("test.txt", b"version 2", content_type="text/plain")
        version = service.create_version(document.id, "tenant-123", file2, "user-123")

        assert version.version_number == 2
        assert document.versions.count() == 2
        document.refresh_from_db()
        assert document.size == len(b"version 2")

    def test_create_version_wrong_tenant(self, db):
        """Test that creating version for document from different tenant raises error."""
        service = DocumentStorageService()
        file1 = SimpleUploadedFile("test.txt", b"version 1", content_type="text/plain")

        document = service.upload_document(
            tenant_id="tenant-123",
            folder_id=None,
            file=file1,
            filename="test.txt",
            user_id="user-123",
        )

        file2 = SimpleUploadedFile("test.txt", b"version 2", content_type="text/plain")
        with pytest.raises(Document.DoesNotExist):
            service.create_version(document.id, "tenant-456", file2, "user-456")
