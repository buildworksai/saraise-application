"""Operation-specific serializers for the governed DMS API.

Relationships are UUID values only.  Domain services resolve those values
inside the authenticated tenant boundary; serializers never own tenancy or
authorization decisions.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from .models import (
    DmsConfiguration,
    DmsConfigurationAudit,
    DmsConfigurationVersion,
    Document,
    DocumentPermission,
    DocumentShare,
    DocumentVersion,
    Folder,
)


class AllowedActionsField(serializers.Field):
    """Render the bounded capability projection attached by the service."""

    def to_representation(self, value: object) -> list[str]:
        actions = getattr(value, "allowed_actions", ())
        return sorted(str(action) for action in actions)

    def to_internal_value(self, data: object) -> object:
        raise serializers.ValidationError("This field is read-only.")


class FolderListSerializer(serializers.ModelSerializer[Folder]):
    parent_id = serializers.UUIDField(read_only=True, allow_null=True)
    children_count = serializers.IntegerField(read_only=True, default=0)
    documents_count = serializers.IntegerField(read_only=True, default=0)
    allowed_actions = AllowedActionsField(source="*", read_only=True)

    class Meta:
        model = Folder
        fields = (
            "id",
            "name",
            "description",
            "parent_id",
            "path",
            "depth",
            "sort_order",
            "children_count",
            "documents_count",
            "created_by",
            "created_at",
            "updated_at",
            "allowed_actions",
        )


class FolderDetailSerializer(FolderListSerializer):
    pass


class FolderCreateSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    parent_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class FolderUpdateSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if not attrs:
            raise serializers.ValidationError("At least one editable field is required.")
        return attrs


class FolderMoveSerializer(serializers.Serializer[dict[str, object]]):
    parent_id = serializers.UUIDField(required=True, allow_null=True)


class DocumentVersionSummarySerializer(serializers.ModelSerializer[DocumentVersion]):
    size_bytes = serializers.IntegerField(read_only=True)

    class Meta:
        model = DocumentVersion
        fields = (
            "id",
            "version_number",
            "original_filename",
            "mime_type",
            "size_bytes",
            "checksum_sha256",
            "created_at",
            "created_by",
        )


class DocumentListSerializer(serializers.ModelSerializer[Document]):
    folder_id = serializers.UUIDField(read_only=True, allow_null=True)
    folder_name = serializers.CharField(source="folder.name", read_only=True, allow_null=True)
    current_version = DocumentVersionSummarySerializer(read_only=True)
    allowed_actions = AllowedActionsField(source="*", read_only=True)

    class Meta:
        model = Document
        fields = (
            "id",
            "name",
            "description",
            "folder_id",
            "folder_name",
            "tags",
            "current_version",
            "version_count",
            "created_by",
            "created_at",
            "updated_at",
            "allowed_actions",
        )


class DocumentDetailSerializer(DocumentListSerializer):
    metadata = serializers.JSONField(read_only=True)

    class Meta(DocumentListSerializer.Meta):
        fields = DocumentListSerializer.Meta.fields + ("metadata",)


class DocumentUploadSerializer(serializers.Serializer[dict[str, object]]):
    file = serializers.FileField(allow_empty_file=False)
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    folder_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    tags = serializers.ListField(
        child=serializers.CharField(trim_whitespace=True),
        required=False,
        default=list,
    )
    metadata = serializers.JSONField(required=False, default=dict)


class DocumentUpdateSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.ListField(
        child=serializers.CharField(trim_whitespace=True),
        required=False,
    )
    metadata = serializers.JSONField(required=False)
    expected_updated_at = serializers.DateTimeField(required=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if len(attrs) == 1:
            raise serializers.ValidationError("At least one editable field is required.")
        return attrs


class DocumentMoveSerializer(serializers.Serializer[dict[str, object]]):
    folder_id = serializers.UUIDField(required=True, allow_null=True)
    expected_updated_at = serializers.DateTimeField(required=False)


class DocumentVersionListSerializer(serializers.ModelSerializer[DocumentVersion]):
    document_id = serializers.UUIDField(read_only=True)
    source_version_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = DocumentVersion
        fields = (
            "id",
            "document_id",
            "version_number",
            "original_filename",
            "mime_type",
            "size_bytes",
            "checksum_sha256",
            "change_note",
            "source_version_id",
            "created_by",
            "created_at",
        )


class DocumentVersionDetailSerializer(DocumentVersionListSerializer):
    pass


class DocumentVersionCreateSerializer(serializers.Serializer[dict[str, object]]):
    document_id = serializers.UUIDField()
    file = serializers.FileField(allow_empty_file=False)
    change_note = serializers.CharField(required=False, allow_blank=True, default="")


class DocumentVersionRestoreSerializer(serializers.Serializer[dict[str, object]]):
    change_note = serializers.CharField(required=False, allow_blank=True, default="")


class DocumentPermissionReadSerializer(serializers.ModelSerializer[DocumentPermission]):
    document_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = DocumentPermission
        fields = (
            "id",
            "document_id",
            "principal_type",
            "principal_id",
            "permission",
            "created_by",
            "created_at",
            "updated_at",
            "deleted_at",
        )


class DocumentPermissionCreateSerializer(serializers.Serializer[dict[str, object]]):
    document_id = serializers.UUIDField()
    principal_type = serializers.ChoiceField(choices=("user", "role", "group"))
    principal_id = serializers.UUIDField()
    permission = serializers.ChoiceField(choices=("read", "write", "delete", "share", "manage"))


class DocumentPermissionUpdateSerializer(serializers.Serializer[dict[str, object]]):
    permission = serializers.ChoiceField(choices=("read", "write", "delete", "share", "manage"))


class DocumentShareReadSerializer(serializers.ModelSerializer[DocumentShare]):
    document_id = serializers.UUIDField(read_only=True)
    version_id = serializers.UUIDField(read_only=True)
    state = serializers.SerializerMethodField()

    class Meta:
        model = DocumentShare
        fields = (
            "id",
            "document_id",
            "version_id",
            "token_prefix",
            "expires_at",
            "max_access_count",
            "access_count",
            "last_accessed_at",
            "revoked_at",
            "created_by",
            "created_at",
            "state",
        )

    def get_state(self, value: DocumentShare) -> str:
        if value.revoked_at is not None:
            return "revoked"
        if value.expires_at <= timezone.now():
            return "expired"
        if value.max_access_count is not None and value.access_count >= value.max_access_count:
            return "exhausted"
        return "active"


class DocumentShareCreateSerializer(serializers.Serializer[dict[str, object]]):
    document_id = serializers.UUIDField()
    version_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    expires_at = serializers.DateTimeField()
    max_access_count = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class ShareCreatedSerializer(serializers.Serializer[dict[str, object]]):
    share = DocumentShareReadSerializer(read_only=True)
    share_url = serializers.URLField(read_only=True)


class FolderContentsSerializer(serializers.Serializer[dict[str, object]]):
    folder = FolderDetailSerializer(read_only=True, allow_null=True)
    breadcrumbs = FolderListSerializer(read_only=True, many=True)
    folders = FolderListSerializer(read_only=True, many=True)
    documents = DocumentListSerializer(read_only=True, many=True)
    allowed_actions = serializers.ListField(child=serializers.CharField(), read_only=True)


class PrincipalSummarySerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField(read_only=True)
    type = serializers.ChoiceField(choices=("user", "role", "group"), read_only=True)
    display_name = serializers.CharField(read_only=True)
    secondary_text = serializers.CharField(read_only=True, allow_blank=True)


class DmsHealthSerializer(serializers.Serializer[dict[str, object]]):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unhealthy"), read_only=True)
    checks = serializers.DictField(child=serializers.DictField(), read_only=True)


class DmsConfigurationSerializer(serializers.ModelSerializer[DmsConfiguration]):
    class Meta:
        model = DmsConfiguration
        fields = (
            "id",
            "tenant_id",
            "environment",
            "version",
            "values",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DmsConfigurationWriteSerializer(serializers.Serializer[dict[str, object]]):
    environment = serializers.CharField(max_length=64, default="default")
    values = serializers.JSONField()


class DmsConfigurationRollbackSerializer(serializers.Serializer[dict[str, object]]):
    version = serializers.IntegerField(min_value=1)
    environment = serializers.CharField(max_length=64, default="default")


class DmsConfigurationVersionSerializer(serializers.ModelSerializer[DmsConfigurationVersion]):
    class Meta:
        model = DmsConfigurationVersion
        fields = (
            "id",
            "version",
            "environment",
            "values",
            "created_by",
            "correlation_id",
            "created_at",
        )
        read_only_fields = fields


class DmsConfigurationAuditSerializer(serializers.ModelSerializer[DmsConfigurationAudit]):
    class Meta:
        model = DmsConfigurationAudit
        fields = (
            "id",
            "action",
            "actor_id",
            "correlation_id",
            "from_version",
            "to_version",
            "before",
            "after",
            "created_at",
        )
        read_only_fields = fields


__all__ = [
    "DmsHealthSerializer",
    "DmsConfigurationAuditSerializer",
    "DmsConfigurationRollbackSerializer",
    "DmsConfigurationSerializer",
    "DmsConfigurationVersionSerializer",
    "DmsConfigurationWriteSerializer",
    "DocumentDetailSerializer",
    "DocumentListSerializer",
    "DocumentMoveSerializer",
    "DocumentPermissionCreateSerializer",
    "DocumentPermissionReadSerializer",
    "DocumentPermissionUpdateSerializer",
    "DocumentShareCreateSerializer",
    "DocumentShareReadSerializer",
    "DocumentUpdateSerializer",
    "DocumentUploadSerializer",
    "DocumentVersionCreateSerializer",
    "DocumentVersionDetailSerializer",
    "DocumentVersionListSerializer",
    "DocumentVersionRestoreSerializer",
    "FolderContentsSerializer",
    "FolderCreateSerializer",
    "FolderDetailSerializer",
    "FolderListSerializer",
    "FolderMoveSerializer",
    "FolderUpdateSerializer",
    "PrincipalSummarySerializer",
    "ShareCreatedSerializer",
]
