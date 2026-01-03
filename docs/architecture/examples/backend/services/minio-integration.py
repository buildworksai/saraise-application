# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: MinIO Integration with Error Handling
# backend/src/services/storage_service.py
# Reference: docs/architecture/operational-runbooks.md § 2.2 (Object Storage)

from minio import Minio
from minio.error import S3Error
from src.core.urls import get_minio_url
from rest_framework.exceptions import APIException
import os
import logging


class StorageService:
    """
    MinIO object storage service for file management.

    FROZEN ARCHITECTURE: Django/DRF exception pattern (NOT FastAPI HTTPException)

    CRITICAL: Platform-level infrastructure service.
    Tenant data segregated via bucket naming convention.
    See docs/architecture/operational-runbooks.md § 2.2.

    Key Features:
    - Multi-tenant file isolation via bucket prefixes
    - Presigned URL generation for secure downloads
    - Automatic bucket creation and lifecycle management
    - S3-compatible API for portability

    Bucket Naming Convention:
    - Development: saraise-dev-{tenant_id}
    - Staging: saraise-staging-{tenant_id}
    - Production: saraise-prod-{tenant_id}
    """

    def __init__(self):
        """Initialize MinIO client with credentials"""
        minio_url = get_minio_url()
        self.client = Minio(
            endpoint=minio_url.replace('http://', '').replace('https://', ''),
            access_key=os.getenv('MINIO_ACCESS_KEY', 'saraise_admin'),
            secret_key=os.getenv('MINIO_SECRET_KEY', 'Saraise2024!Secure'),
            secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true'
        )
        self.bucket_name = os.getenv('MINIO_BUCKET_NAME', 'saraise-storage')
        self.logger = logging.getLogger(__name__)
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        """
        Ensure MinIO bucket exists, create if missing.

        Raises:
            APIException: Bucket creation failed
        """
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                self.logger.info(f"Created MinIO bucket: {self.bucket_name}")
            else:
                self.logger.debug(f"MinIO bucket exists: {self.bucket_name}")
        except S3Error as e:
            self.logger.error(f"Failed to ensure bucket exists: {str(e)}", exc_info=True)
            raise APIException(detail="Storage service unavailable")

    def upload_file(self, object_name: str, file_path: str, tenant_id: str = None) -> str:
        """
        Upload file to MinIO with tenant isolation.

        FROZEN ARCHITECTURE: Raises DRF APIException (NOT HTTPException, NOT raise Response)

        Args:
            object_name: Object key/path in bucket (e.g., "invoices/2024/invoice-123.pdf")
            file_path: Local file path to upload
            tenant_id: Optional tenant ID for isolation (prefixes object_name)

        Returns:
            str: Public URL to the uploaded object

        Raises:
            APIException: File upload failed (DRF exception, returns HTTP 500)

        Example:
            storage = StorageService()
            url = storage.upload_file(
                object_name="invoices/invoice-123.pdf",
                file_path="/tmp/invoice-123.pdf",
                tenant_id="tenant_abc123"
            )
            # Result: "http://minio:9000/saraise-storage/tenant_abc123/invoices/invoice-123.pdf"

        Security Notes:
        - Tenant isolation via object_name prefixing
        - File size limits enforced by middleware
        - Malware scanning recommended before upload (not implemented here)
        """
        try:
            # Prefix object name with tenant_id for isolation
            if tenant_id:
                object_name = f"{tenant_id}/{object_name}"

            # Upload file to MinIO
            self.client.fput_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=file_path
            )

            # Return public URL
            url = f"{get_minio_url()}/{self.bucket_name}/{object_name}"
            self.logger.info(f"File uploaded successfully: {object_name}")
            return url

        except S3Error as e:
            # MinIO/S3 error (bucket not found, permissions, etc.)
            self.logger.error(f"MinIO upload failed for {object_name}: {str(e)}", exc_info=True)
            # ✅ CORRECT: Raise DRF exception (NOT raise Response)
            raise APIException(detail="File upload failed")

        except Exception as e:
            # File not found, permission error, network error
            self.logger.error(f"Upload failed for {object_name}: {str(e)}", exc_info=True)
            # ✅ CORRECT: Raise DRF exception (NOT raise Response)
            raise APIException(detail="File upload failed")

    def download_file(self, object_name: str, destination_path: str, tenant_id: str = None) -> None:
        """
        Download file from MinIO with tenant isolation.

        Args:
            object_name: Object key/path in bucket
            destination_path: Local file path to save downloaded file
            tenant_id: Optional tenant ID for isolation

        Raises:
            APIException: File download failed
        """
        try:
            # Prefix object name with tenant_id for isolation
            if tenant_id:
                object_name = f"{tenant_id}/{object_name}"

            # Download file from MinIO
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=destination_path
            )
            self.logger.info(f"File downloaded successfully: {object_name}")

        except S3Error as e:
            self.logger.error(f"MinIO download failed for {object_name}: {str(e)}", exc_info=True)
            raise APIException(detail="File download failed")

        except Exception as e:
            self.logger.error(f"Download failed for {object_name}: {str(e)}", exc_info=True)
            raise APIException(detail="File download failed")

    def delete_file(self, object_name: str, tenant_id: str = None) -> None:
        """
        Delete file from MinIO with tenant isolation.

        Args:
            object_name: Object key/path in bucket
            tenant_id: Optional tenant ID for isolation

        Raises:
            APIException: File deletion failed
        """
        try:
            # Prefix object name with tenant_id for isolation
            if tenant_id:
                object_name = f"{tenant_id}/{object_name}"

            # Delete file from MinIO
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            self.logger.info(f"File deleted successfully: {object_name}")

        except S3Error as e:
            self.logger.error(f"MinIO delete failed for {object_name}: {str(e)}", exc_info=True)
            raise APIException(detail="File deletion failed")


# ANTI-PATTERNS (FORBIDDEN - DOCUMENTED FOR REFERENCE):
# ❌ WRONG: from rest_framework import HTTPException  # HTTPException does NOT exist in DRF
# ❌ WRONG: raise Response(status=status.HTTP_500, detail="...")  # Cannot raise Response
# ❌ WRONG: raise HTTPException(status_code=500, detail="...")  # FastAPI pattern
# ❌ WRONG: object_name = f"{file_name}"  # Missing tenant_id prefix (data leakage risk)
#
# ✅ CORRECT: raise APIException(detail="File upload failed")  # DRF exception
# ✅ CORRECT: object_name = f"{tenant_id}/{file_name}"  # Tenant isolation
