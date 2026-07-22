"""Governed API v2 controllers for document management."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import StreamingHttpResponse
from django.utils.http import content_disposition_header
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api.profile import GovernedAPIViewMixin, GovernedMultipartAPIViewMixin
from src.core.api.results import OperationFailed
from src.core.auth_utils import get_user_tenant_id

from .filters import DocumentFilterSet, FolderFilterSet
from .health import get_module_health
from .models import DocumentPermission, DocumentShare, DocumentVersion
from .permissions import ActionAccessMixin
from .permissions import (
    DOCUMENT_ACTION_PERMISSIONS,
    DOCUMENT_PERMISSION_ACTION_PERMISSIONS,
    FOLDER_ACTION_PERMISSIONS,
    HEALTH_ACTION_PERMISSIONS,
    PRINCIPAL_ACTION_PERMISSIONS,
    SHARE_ACTION_PERMISSIONS,
    VERSION_ACTION_PERMISSIONS,
)
from .serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
    DocumentMoveSerializer,
    DocumentPermissionCreateSerializer,
    DocumentPermissionReadSerializer,
    DocumentPermissionUpdateSerializer,
    DocumentShareCreateSerializer,
    DocumentShareReadSerializer,
    DocumentUpdateSerializer,
    DocumentUploadSerializer,
    DocumentVersionCreateSerializer,
    DocumentVersionDetailSerializer,
    DocumentVersionListSerializer,
    DocumentVersionRestoreSerializer,
    FolderContentsSerializer,
    FolderCreateSerializer,
    FolderDetailSerializer,
    FolderListSerializer,
    FolderMoveSerializer,
    FolderUpdateSerializer,
    PrincipalSummarySerializer,
    ShareCreatedSerializer,
)
from .services import (
    DmsConflict,
    DmsDependencyUnavailable,
    DmsIntegrityFailure,
    DmsNotFound,
    DmsPermissionDenied,
    DmsValidationError,
    DocumentService,
    FolderService,
    PermissionService,
    ShareService,
    VersionService,
    get_identity_directory,
)
from .storage import StorageIntegrityError, StorageUnavailableError, StorageValidationError


def _tenant(request: Any) -> UUID:
    value = get_user_tenant_id(request.user)
    try:
        tenant_id = value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("Authenticated identity has no valid tenant.") from exc
    request.tenant_id = tenant_id
    return tenant_id


def _actor(request: Any) -> UUID:
    value = getattr(request.user, "id", None)
    if value is None:
        raise PermissionDenied("Authenticated identity has no actor identifier.")
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


def _translate_error(exc: Exception) -> Exception:
    if isinstance(exc, DmsNotFound):
        return NotFound()
    if isinstance(exc, DmsPermissionDenied):
        return PermissionDenied()
    if isinstance(exc, DmsConflict):
        return OperationFailed(error_code="CONFLICT", message=str(exc), http_status=409)
    if isinstance(exc, (DmsDependencyUnavailable, StorageUnavailableError)):
        return OperationFailed(
            error_code="DEPENDENCY_UNAVAILABLE",
            message="A required document dependency is unavailable.",
            http_status=503,
        )
    if isinstance(exc, (DmsIntegrityFailure, StorageIntegrityError)):
        return OperationFailed(
            error_code="STORAGE_INTEGRITY_FAILURE",
            message="Stored document integrity verification failed.",
            http_status=503,
        )
    if isinstance(exc, DmsValidationError):
        return ValidationError(exc.detail)
    if isinstance(exc, StorageValidationError):
        return ValidationError({"file": [str(exc)]})
    if isinstance(exc, DjangoValidationError):
        return ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages}))
    return exc


def _call(operation: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    try:
        return operation(*args, **kwargs)
    except Exception as exc:
        translated = _translate_error(exc)
        if translated is exc:
            raise
        raise translated from exc


class TenantGovernedViewSet(GovernedAPIViewMixin, ActionAccessMixin, viewsets.GenericViewSet[Any]):
    """Shared strict-session tenant context and mandatory pagination."""

    @property
    def tenant_id(self) -> UUID:
        return _tenant(self.request)

    @property
    def actor_id(self) -> UUID:
        return _actor(self.request)

    def paginated(self, queryset: Any, serializer_class: type, **context: object) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is mandatory for DMS collections")
        return self.get_paginated_response(serializer_class(page, many=True, context=context).data)

    def handle_exception(self, exc: Exception) -> Response:
        return super().handle_exception(_translate_error(exc))


class FolderViewSet(TenantGovernedViewSet):
    service_class = FolderService
    action_permissions = FOLDER_ACTION_PERMISSIONS

    def get_queryset(self):
        return self.service_class().list_folders(self.tenant_id, self.actor_id)

    def get_serializer_class(self) -> type:
        return {
            "list": FolderListSerializer,
            "create": FolderCreateSerializer,
            "partial_update": FolderUpdateSerializer,
            "move": FolderMoveSerializer,
            "contents": FolderContentsSerializer,
        }.get(self.action, FolderDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        filters = FolderFilterSet(self.request.query_params, queryset=self.get_queryset())
        if not filters.is_valid():
            raise ValidationError(filters.errors)
        page = self.paginate_queryset(filters.qs)
        if page is None:
            raise RuntimeError("Governed pagination is mandatory for DMS collections")
        for folder in page:
            folder.allowed_actions = frozenset({"read"})
        return self.get_paginated_response(FolderListSerializer(page, many=True).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = FolderCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        folder = _call(self.service_class().create_folder, self.tenant_id, self.actor_id, **serializer.validated_data)
        return Response(FolderDetailSerializer(folder).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        folder = _call(self.service_class().get_folder, self.tenant_id, self.actor_id, self.kwargs["pk"])
        folder.allowed_actions = frozenset({"read"})
        return Response(FolderDetailSerializer(folder).data)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = FolderUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        folder = _call(
            self.service_class().update_folder,
            self.tenant_id,
            self.actor_id,
            self.kwargs["pk"],
            **serializer.validated_data,
        )
        return Response(FolderDetailSerializer(folder).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        _call(self.service_class().delete_folder, self.tenant_id, self.actor_id, self.kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def move(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = FolderMoveSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        folder = _call(
            self.service_class().move_folder,
            self.tenant_id,
            self.actor_id,
            self.kwargs["pk"],
            **serializer.validated_data,
        )
        return Response(FolderDetailSerializer(folder).data)

    @action(detail=True, methods=("get",))
    def contents(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        result = _call(
            self.service_class().list_contents,
            self.tenant_id,
            self.actor_id,
            folder_id=self.kwargs["pk"],
        )
        result.allowed_actions = frozenset({"read"})
        if result.folder is not None:
            result.folder.allowed_actions = result.allowed_actions
        for folder in (*result.breadcrumbs, *result.folders):
            folder.allowed_actions = frozenset({"read"})
        return Response(FolderContentsSerializer(result).data)


class DocumentViewSet(GovernedMultipartAPIViewMixin, TenantGovernedViewSet):
    service_class = DocumentService
    action_permissions = DOCUMENT_ACTION_PERMISSIONS
    action_quotas = {"create": "dms.api_writes", "download": "dms.api_reads"}

    def get_queryset(self):
        return self.service_class().list_documents(
            self.tenant_id,
            self.actor_id,
            filters={},
            search="",
            ordering="-updated_at",
        )

    def get_serializer_class(self) -> type:
        return {
            "list": DocumentListSerializer,
            "create": DocumentUploadSerializer,
            "partial_update": DocumentUpdateSerializer,
            "move": DocumentMoveSerializer,
        }.get(self.action, DocumentDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        queryset = _call(
            self.service_class().list_documents,
            self.tenant_id,
            self.actor_id,
            filters={},
            search="",
            ordering="-updated_at",
        )
        filters = DocumentFilterSet(self.request.query_params, queryset=queryset)
        if not filters.is_valid():
            raise ValidationError(filters.errors)
        page = self.paginate_queryset(filters.qs)
        if page is None:
            raise RuntimeError("Governed pagination is mandatory for DMS collections")
        permissions = PermissionService()
        for document in page:
            document.allowed_actions = permissions.allowed_actions(self.tenant_id, self.actor_id, document)
        return self.get_paginated_response(DocumentListSerializer(page, many=True).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = DocumentUploadSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        document = _call(
            self.service_class().upload_document,
            self.tenant_id,
            self.actor_id,
            **serializer.validated_data,
        )
        document = _call(self.service_class().get_document, self.tenant_id, self.actor_id, document.id)
        return Response(DocumentDetailSerializer(document).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        document = _call(self.service_class().get_document, self.tenant_id, self.actor_id, self.kwargs["pk"])
        return Response(DocumentDetailSerializer(document).data)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = DocumentUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        document = _call(
            self.service_class().update_document,
            self.tenant_id,
            self.actor_id,
            self.kwargs["pk"],
            **serializer.validated_data,
        )
        return Response(DocumentDetailSerializer(document).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        _call(self.service_class().delete_document, self.tenant_id, self.actor_id, self.kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def move(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = DocumentMoveSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        document = _call(
            self.service_class().move_document,
            self.tenant_id,
            self.actor_id,
            self.kwargs["pk"],
            **serializer.validated_data,
        )
        return Response(DocumentDetailSerializer(document).data)

    @action(detail=True, methods=("get",))
    def download(self, request: object, pk: str | None = None) -> StreamingHttpResponse:
        del request, pk
        version_raw = self.request.query_params.get("version_id")
        try:
            version_id = UUID(version_raw) if version_raw else None
        except ValueError as exc:
            raise ValidationError({"version_id": ["Must be a valid UUID."]}) from exc
        artifact = _call(
            self.service_class().download_document,
            self.tenant_id,
            self.actor_id,
            self.kwargs["pk"],
            version_id=version_id,
        )
        return _download_response(artifact)


class DocumentVersionViewSet(GovernedMultipartAPIViewMixin, TenantGovernedViewSet):
    service_class = VersionService
    action_permissions = VERSION_ACTION_PERMISSIONS

    def get_queryset(self):
        document_id = self.request.query_params.get("document_id")
        if not document_id:
            return DocumentVersion.objects.none()
        return self.service_class().list_versions(self.tenant_id, self.actor_id, document_id)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        raw = self.request.query_params.get("document_id")
        if not raw:
            raise ValidationError({"document_id": ["This filter is required."]})
        try:
            document_id = UUID(raw)
        except ValueError as exc:
            raise ValidationError({"document_id": ["Must be a valid UUID."]}) from exc
        return self.paginated(
            _call(self.service_class().list_versions, self.tenant_id, self.actor_id, document_id),
            DocumentVersionListSerializer,
        )

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = DocumentVersionCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        document_id = data.pop("document_id")
        version = _call(self.service_class().create_version, self.tenant_id, self.actor_id, document_id, **data)
        return Response(DocumentVersionDetailSerializer(version).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        version = _call(self.service_class().get_version, self.tenant_id, self.actor_id, self.kwargs["pk"])
        return Response(DocumentVersionDetailSerializer(version).data)

    @action(detail=True, methods=("post",))
    def restore(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = DocumentVersionRestoreSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        version = _call(
            self.service_class().restore_version,
            self.tenant_id,
            self.actor_id,
            self.kwargs["pk"],
            **serializer.validated_data,
        )
        return Response(DocumentVersionDetailSerializer(version).data, status=status.HTTP_201_CREATED)


class DocumentPermissionViewSet(TenantGovernedViewSet):
    service_class = PermissionService
    action_permissions = DOCUMENT_PERMISSION_ACTION_PERMISSIONS

    def get_queryset(self):
        document_id = self.request.query_params.get("document_id")
        if not document_id:
            return DocumentPermission.objects.none()
        return self.service_class().list_permissions(self.tenant_id, self.actor_id, document_id)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        raw = self.request.query_params.get("document_id")
        if not raw:
            raise ValidationError({"document_id": ["This filter is required."]})
        return self.paginated(
            _call(self.service_class().list_permissions, self.tenant_id, self.actor_id, raw),
            DocumentPermissionReadSerializer,
        )

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = DocumentPermissionCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        document_id = data.pop("document_id")
        grant = _call(self.service_class().grant_permission, self.tenant_id, self.actor_id, document_id, **data)
        return Response(DocumentPermissionReadSerializer(grant).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        grant = _call(self.service_class().get_permission, self.tenant_id, self.actor_id, self.kwargs["pk"])
        return Response(DocumentPermissionReadSerializer(grant).data)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = DocumentPermissionUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        grant = _call(
            self.service_class().update_permission,
            self.tenant_id,
            self.actor_id,
            self.kwargs["pk"],
            **serializer.validated_data,
        )
        return Response(DocumentPermissionReadSerializer(grant).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        _call(self.service_class().revoke_permission, self.tenant_id, self.actor_id, self.kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentShareViewSet(TenantGovernedViewSet):
    service_class = ShareService
    action_permissions = SHARE_ACTION_PERMISSIONS

    def get_queryset(self):
        document_id = self.request.query_params.get("document_id")
        if not document_id:
            return DocumentShare.objects.none()
        return self.service_class().list_shares(self.tenant_id, self.actor_id, document_id)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        raw = self.request.query_params.get("document_id")
        if not raw:
            raise ValidationError({"document_id": ["This filter is required."]})
        return self.paginated(
            _call(self.service_class().list_shares, self.tenant_id, self.actor_id, raw),
            DocumentShareReadSerializer,
        )

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = DocumentShareCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        document_id = data.pop("document_id")
        created = _call(self.service_class().create_share, self.tenant_id, self.actor_id, document_id, **data)
        return Response(ShareCreatedSerializer(created).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        share = _call(self.service_class().get_share, self.tenant_id, self.actor_id, self.kwargs["pk"])
        return Response(DocumentShareReadSerializer(share).data)

    @action(detail=True, methods=("post",))
    def revoke(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        share = _call(self.service_class().revoke_share, self.tenant_id, self.actor_id, self.kwargs["pk"])
        return Response(DocumentShareReadSerializer(share).data)


def _download_response(artifact: Any) -> StreamingHttpResponse:
    response = StreamingHttpResponse(artifact.stream, content_type=artifact.mime_type)
    response["Content-Length"] = str(artifact.size_bytes)
    response["Content-Disposition"] = content_disposition_header(True, artifact.filename)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


class PublicShareDownloadAPIView(GovernedAPIViewMixin, APIView):
    authentication_classes: tuple[type, ...] = ()
    permission_classes = (AllowAny,)

    def get(self, request: object, token: str) -> StreamingHttpResponse:
        del request
        try:
            artifact = ShareService().consume_share(token)
        except Exception as exc:
            raise NotFound() from exc
        return _download_response(artifact)


class PrincipalSearchAPIView(GovernedAPIViewMixin, ActionAccessMixin, APIView):
    action = "search"
    action_permissions = PRINCIPAL_ACTION_PERMISSIONS

    def get(self, request: object) -> Response:
        query = self.request.query_params.get("search", "")
        principal_type = self.request.query_params.get("type") or None
        if principal_type not in (None, "user", "role", "group"):
            raise ValidationError({"type": ["Must be user, role, or group."]})
        try:
            limit = int(self.request.query_params.get("limit", "20"))
        except ValueError as exc:
            raise ValidationError({"limit": ["Must be an integer."]}) from exc
        values = _call(get_identity_directory().search, _tenant(self.request), query, principal_type, limit)
        return Response(PrincipalSummarySerializer(values, many=True).data)


class DmsHealthAPIView(GovernedAPIViewMixin, ActionAccessMixin, APIView):
    action = "health"
    action_permissions = HEALTH_ACTION_PERMISSIONS

    def get(self, request: object) -> Response:
        del request
        report = get_module_health()
        return Response(dict(report.payload), status=report.status_code)


__all__ = [
    "DmsHealthAPIView",
    "DocumentPermissionViewSet",
    "DocumentShareViewSet",
    "DocumentVersionViewSet",
    "DocumentViewSet",
    "FolderViewSet",
    "PrincipalSearchAPIView",
    "PublicShareDownloadAPIView",
]
