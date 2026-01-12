"""
Dms Services.

High-level service layer for Dms business logic.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from .models import Document, DocumentVersion, Folder

logger = logging.getLogger(__name__)


class DocumentStorageService:
    """Service for handling document file storage with tenant isolation."""

    def upload_document(
        self,
        tenant_id: str,
        folder_id: Optional[str],
        file,
        filename: str,
        user_id: str,
    ) -> Document:
        """Upload document with tenant isolation.

        Args:
            tenant_id: Tenant ID.
            folder_id: Optional folder ID.
            file: File object to upload.
            filename: Original filename.
            user_id: User ID who uploaded the file.

        Returns:
            Created Document instance.

        Raises:
            ValueError: If validation fails.
        """
        # Calculate file hash
        file.seek(0)
        file_content = file.read()
        file_hash = hashlib.sha256(file_content).hexdigest()
        file.seek(0)

        # Generate tenant-isolated storage path
        storage_path = f"tenants/{tenant_id}/documents/{file_hash[:2]}/{file_hash}"

        # Save file
        saved_path = default_storage.save(storage_path, file)

        # Get or create folder
        folder = None
        if folder_id:
            folder = Folder.objects.filter(id=folder_id, tenant_id=tenant_id).first()
            if not folder:
                raise ValueError(f"Folder {folder_id} not found for tenant {tenant_id}")

        # Get MIME type
        mime_type = getattr(file, "content_type", "application/octet-stream")

        with transaction.atomic():
            # Create document record
            document = Document.objects.create(
                tenant_id=tenant_id,
                name=filename,
                folder=folder,
                file_path=saved_path,
                mime_type=mime_type,
                size=len(file_content),
                checksum=file_hash,
                created_by=user_id,
            )

            # Create initial version
            DocumentVersion.objects.create(
                document=document,
                version_number=1,
                file_path=saved_path,
                created_by=user_id,
            )

            logger.info(f"Uploaded document {document.id} for tenant {tenant_id}")
            return document

    def download_document(
        self,
        tenant_id: str,
        document_id: str,
    ) -> Tuple[Any, str, str]:
        """Download document with tenant verification.

        Args:
            tenant_id: Tenant ID.
            document_id: Document ID.

        Returns:
            Tuple of (file, filename, mime_type).

        Raises:
            Document.DoesNotExist: If document not found.
            ValueError: If tenant mismatch.
        """
        document = Document.objects.get(id=document_id, tenant_id=tenant_id)

        file = default_storage.open(document.file_path)
        return file, document.name, document.mime_type

    def create_version(
        self,
        document_id: str,
        tenant_id: str,
        file,
        user_id: str,
    ) -> DocumentVersion:
        """Create a new version of a document.

        Args:
            document_id: Document ID.
            tenant_id: Tenant ID.
            file: New file object.
            user_id: User ID who created the version.

        Returns:
            Created DocumentVersion instance.

        Raises:
            Document.DoesNotExist: If document not found.
            ValueError: If tenant mismatch.
        """
        document = Document.objects.get(id=document_id, tenant_id=tenant_id)

        # Calculate file hash
        file.seek(0)
        file_content = file.read()
        file_hash = hashlib.sha256(file_content).hexdigest()
        file.seek(0)

        # Generate storage path
        storage_path = f"tenants/{tenant_id}/documents/{file_hash[:2]}/{file_hash}"

        # Save file
        saved_path = default_storage.save(storage_path, file)

        # Get next version number
        latest_version = (
            DocumentVersion.objects.filter(document=document)
            .order_by("-version_number")
            .first()
        )
        next_version = (latest_version.version_number + 1) if latest_version else 1

        with transaction.atomic():
            # Update document with new file
            document.file_path = saved_path
            document.checksum = file_hash
            document.size = len(file_content)
            document.mime_type = getattr(file, "content_type", "application/octet-stream")
            document.save()

            # Create new version
            version = DocumentVersion.objects.create(
                document=document,
                version_number=next_version,
                file_path=saved_path,
                created_by=user_id,
            )

            logger.info(f"Created version {next_version} for document {document_id}")
            return version


class DmsService:
    """Service for managing Dms resources (legacy scaffold - kept for compatibility)."""

    def create_resource(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        config: Optional[Dict[str, Any]] = None,
        created_by: str = "",
    ):
        """Create a new resource (legacy method)."""
        logger.warning("DmsService.create_resource is deprecated. Use DocumentStorageService instead.")
        # This method is kept for backward compatibility but should not be used
        raise NotImplementedError("Use DocumentStorageService.upload_document instead")
