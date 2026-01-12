"""
DRF ViewSets for Dms module.
Provides REST API endpoints for all models.
"""

import uuid

from django.core.files.storage import default_storage
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import Document, DocumentPermission, DocumentShare, DocumentVersion, Folder
from .serializers import (
    DocumentPermissionSerializer,
    DocumentSerializer,
    DocumentShareSerializer,
    DocumentVersionSerializer,
    FolderSerializer,
)
from .services import DocumentStorageService


class FolderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Folder CRUD operations.

    Endpoints:
    - GET /api/v1/dms/folders/ - List all folders
    - POST /api/v1/dms/folders/ - Create folder
    - GET /api/v1/dms/folders/{id}/ - Get folder detail
    - PUT /api/v1/dms/folders/{id}/ - Update folder
    - PATCH /api/v1/dms/folders/{id}/ - Partial update folder
    - DELETE /api/v1/dms/folders/{id}/ - Delete folder
    - POST /api/v1/dms/folders/{id}/move/ - Move folder
    """

    serializer_class = FolderSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter folders by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Folder.objects.none()
        queryset = Folder.objects.filter(tenant_id=tenant_id)

        # Filter by parent
        parent_id = self.request.query_params.get("parent_id")
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        elif parent_id == "":
            queryset = queryset.filter(parent__isnull=True)

        return queryset.order_by("name")

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id, created_by=str(self.request.user.id))

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        """Move folder to a different parent."""
        folder = self.get_object()
        new_parent_id = request.data.get("parent_id")

        tenant_id = get_user_tenant_id(request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")

        new_parent = None
        if new_parent_id:
            new_parent = Folder.objects.filter(id=new_parent_id, tenant_id=tenant_id).first()
            if not new_parent:
                raise NotFound("Parent folder not found")

        folder.parent = new_parent
        folder.save()

        serializer = self.get_serializer(folder)
        return Response(serializer.data)


class DocumentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Document CRUD operations.

    Endpoints:
    - GET /api/v1/dms/documents/ - List all documents
    - POST /api/v1/dms/documents/ - Create document
    - GET /api/v1/dms/documents/{id}/ - Get document detail
    - PUT /api/v1/dms/documents/{id}/ - Update document
    - PATCH /api/v1/dms/documents/{id}/ - Partial update document
    - DELETE /api/v1/dms/documents/{id}/ - Delete document
    - POST /api/v1/dms/documents/{id}/upload/ - Upload new version
    - GET /api/v1/dms/documents/{id}/download/ - Download document
    """

    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter documents by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Document.objects.none()
        queryset = Document.objects.filter(tenant_id=tenant_id)

        # Filter by folder
        folder_id = self.request.query_params.get("folder_id")
        if folder_id:
            queryset = queryset.filter(folder_id=folder_id)
        elif folder_id == "":
            queryset = queryset.filter(folder__isnull=True)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id, created_by=str(self.request.user.id))

    @action(detail=True, methods=["post"])
    def upload(self, request, pk=None):
        """Upload a new version of the document."""
        document = self.get_object()
        tenant_id = get_user_tenant_id(request.user)

        if "file" not in request.FILES:
            return Response({"error": "File is required"}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES["file"]
        service = DocumentStorageService()
        version = service.create_version(document.id, tenant_id, file, str(request.user.id))

        serializer = DocumentVersionSerializer(version)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Download document file."""
        from django.http import FileResponse

        document = self.get_object()
        tenant_id = get_user_tenant_id(request.user)

        service = DocumentStorageService()
        file, filename, mime_type = service.download_document(tenant_id, document.id)

        response = FileResponse(file, content_type=mime_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class DocumentVersionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for DocumentVersion read operations.

    Endpoints:
    - GET /api/v1/dms/document-versions/ - List all versions
    - GET /api/v1/dms/document-versions/{id}/ - Get version detail
    """

    serializer_class = DocumentVersionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter versions by document tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return DocumentVersion.objects.none()

        queryset = DocumentVersion.objects.filter(document__tenant_id=tenant_id)

        # Filter by document
        document_id = self.request.query_params.get("document_id")
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        return queryset.order_by("-version_number")


class DocumentPermissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for DocumentPermission CRUD operations.

    Endpoints:
    - GET /api/v1/dms/document-permissions/ - List all permissions
    - POST /api/v1/dms/document-permissions/ - Create permission
    - GET /api/v1/dms/document-permissions/{id}/ - Get permission detail
    - PUT /api/v1/dms/document-permissions/{id}/ - Update permission
    - DELETE /api/v1/dms/document-permissions/{id}/ - Delete permission
    """

    serializer_class = DocumentPermissionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter permissions by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return DocumentPermission.objects.none()

        queryset = DocumentPermission.objects.filter(tenant_id=tenant_id)

        # Filter by document
        document_id = self.request.query_params.get("document_id")
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)


class DocumentShareViewSet(viewsets.ModelViewSet):
    """
    ViewSet for DocumentShare CRUD operations.

    Endpoints:
    - GET /api/v1/dms/document-shares/ - List all shares
    - POST /api/v1/dms/document-shares/ - Create share link
    - GET /api/v1/dms/document-shares/{id}/ - Get share detail
    - DELETE /api/v1/dms/document-shares/{id}/ - Delete share
    """

    serializer_class = DocumentShareSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter shares by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return DocumentShare.objects.none()

        queryset = DocumentShare.objects.filter(tenant_id=tenant_id)

        # Filter by document
        document_id = self.request.query_params.get("document_id")
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id, created_by, and generate share_token."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")

        import secrets

        share_token = secrets.token_urlsafe(32)
        serializer.save(
            tenant_id=tenant_id,
            created_by=str(self.request.user.id),
            share_token=share_token,
        )
