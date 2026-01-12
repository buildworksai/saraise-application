"""
DRF Serializers for Dms module.
Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import Document, DocumentPermission, DocumentShare, DocumentVersion, Folder


class FolderSerializer(serializers.ModelSerializer):
    """Serializer for Folder model."""

    children_count = serializers.IntegerField(source="children.count", read_only=True)
    documents_count = serializers.IntegerField(source="documents.count", read_only=True)

    class Meta:
        model = Folder
        fields = [
            "id",
            "tenant_id",
            "name",
            "parent",
            "path",
            "children_count",
            "documents_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "path", "created_by", "created_at", "updated_at"]

    def validate_name(self, value):
        """Validate name field."""
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value.strip()

    def validate_parent(self, value):
        """Validate parent folder belongs to same tenant."""
        if value and hasattr(self, "initial_data"):
            tenant_id = self.initial_data.get("tenant_id")
            if tenant_id and value.tenant_id != tenant_id:
                raise serializers.ValidationError("Parent folder must belong to the same tenant")
        return value


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer for Document model."""

    folder_name = serializers.CharField(source="folder.name", read_only=True)
    versions_count = serializers.IntegerField(source="versions.count", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "tenant_id",
            "name",
            "folder",
            "folder_name",
            "file_path",
            "mime_type",
            "size",
            "checksum",
            "versions_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "file_path",
            "mime_type",
            "size",
            "checksum",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        """Validate name field."""
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value.strip()

    def validate_folder(self, value):
        """Validate folder belongs to same tenant."""
        if value and hasattr(self, "initial_data"):
            tenant_id = self.initial_data.get("tenant_id")
            if tenant_id and value.tenant_id != tenant_id:
                raise serializers.ValidationError("Folder must belong to the same tenant")
        return value


class DocumentVersionSerializer(serializers.ModelSerializer):
    """Serializer for DocumentVersion model."""

    document_name = serializers.CharField(source="document.name", read_only=True)

    class Meta:
        model = DocumentVersion
        fields = [
            "id",
            "document",
            "document_name",
            "version_number",
            "file_path",
            "created_at",
            "created_by",
        ]
        read_only_fields = ["id", "file_path", "created_at"]


class DocumentPermissionSerializer(serializers.ModelSerializer):
    """Serializer for DocumentPermission model."""

    document_name = serializers.CharField(source="document.name", read_only=True)

    class Meta:
        model = DocumentPermission
        fields = [
            "id",
            "tenant_id",
            "document",
            "document_name",
            "principal_type",
            "principal_id",
            "permission",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def validate_document(self, value):
        """Validate document belongs to same tenant."""
        if value and hasattr(self, "initial_data"):
            tenant_id = self.initial_data.get("tenant_id")
            if tenant_id and value.tenant_id != tenant_id:
                raise serializers.ValidationError("Document must belong to the same tenant")
        return value


class DocumentShareSerializer(serializers.ModelSerializer):
    """Serializer for DocumentShare model."""

    document_name = serializers.CharField(source="document.name", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = DocumentShare
        fields = [
            "id",
            "tenant_id",
            "document",
            "document_name",
            "share_token",
            "expires_at",
            "permissions",
            "is_expired",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "share_token", "created_by", "created_at", "updated_at"]

    def validate_document(self, value):
        """Validate document belongs to same tenant."""
        if value and hasattr(self, "initial_data"):
            tenant_id = self.initial_data.get("tenant_id")
            if tenant_id and value.tenant_id != tenant_id:
                raise serializers.ValidationError("Document must belong to the same tenant")
        return value
