import uuid

from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication
from .models import EntityDefinition, DynamicResource
from .serializers import EntityDefinitionSerializer, DynamicResourceSerializer
from .services import MetadataService


class EntityDefinitionViewSet(viewsets.ModelViewSet):
    serializer_class = EntityDefinitionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return EntityDefinition.objects.none()
        # Convert string tenant_id to UUID for filtering
        # EntityDefinition.tenant_id is UUIDField, but get_user_tenant_id returns string (CharField)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return EntityDefinition.objects.none()
        return EntityDefinition.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise serializers.ValidationError("tenant_id is required")
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise serializers.ValidationError("Invalid tenant_id format")
        serializer.save(tenant_id=tenant_id)


class DynamicResourceViewSet(viewsets.ModelViewSet):
    serializer_class = DynamicResourceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return DynamicResource.objects.none()
        # Convert string tenant_id to UUID for filtering
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return DynamicResource.objects.none()
        qs = DynamicResource.objects.filter(tenant_id=tenant_id)

        # Filter by entity code if provided in query params
        entity_code = self.request.query_params.get("entity_code")
        if entity_code:
            qs = qs.filter(entity_definition__code=entity_code)

        return qs

    def create(self, request, *args, **kwargs):
        tenant_id_str = get_user_tenant_id(request.user)
        if not tenant_id_str:
            return Response({"error": "tenant_id is required."}, status=status.HTTP_403_FORBIDDEN)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Response({"error": "Invalid tenant_id format."}, status=status.HTTP_400_BAD_REQUEST)
        entity_id = request.data.get("entity_definition")
        data_payload = request.data.get("data", {})

        try:
            entity_def = EntityDefinition.objects.get(id=entity_id, tenant_id=tenant_id)
        except EntityDefinition.DoesNotExist:
            return Response({"error": "Entity Definition not found."}, status=status.HTTP_404_NOT_FOUND)

        # Validate Data
        service = MetadataService()
        try:
            cleaned_data = service.validate_data(entity_def, data_payload)
        except ValidationError as e:
            return Response(e.message_dict, status=status.HTTP_400_BAD_REQUEST)

        # Create
        resource = DynamicResource.objects.create(
            tenant_id=tenant_id, entity_definition=entity_def, data=cleaned_data, created_by=request.user
        )

        serializer = self.get_serializer(resource)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        kwargs.pop("partial", False)  # noqa: F841
        instance = self.get_object()
        get_user_tenant_id(request.user)  # Verify tenant exists

        # If updating data, merge and validate
        if "data" in request.data:
            entity_def = instance.entity_definition
            new_data = request.data["data"]

            # Merge logic for PATCH? For now, implementing full replace or explicit merge if needed.
            # Assuming full replace of provided keys for simplicity, or we can do deep merge.
            # Making it simple: Re-validate the merged result.

            current_data = instance.data.copy()
            current_data.update(new_data)

            service = MetadataService()
            try:
                # Validate FULL data (since required fields check needs full data)
                cleaned_data = service.validate_data(entity_def, current_data)
            except ValidationError as e:
                return Response(e.message_dict, status=status.HTTP_400_BAD_REQUEST)

            instance.data = cleaned_data
            instance.save()

            # Remove data from payload passing to super update to avoid conflict if any
            # Actually we handled saving data manually.

        return super().update(request, *args, **kwargs)
