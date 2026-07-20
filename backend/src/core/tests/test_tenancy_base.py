"""Tests for the canonical tenancy model, registry, and ViewSet boundary."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, models
from django.test.utils import isolate_apps
from rest_framework import serializers, status
from rest_framework.test import APIRequestFactory, force_authenticate

from src.core.tenancy.models import TenantQuerySet, TenantScopedModel, TimestampedModel
from src.core.tenancy.registry import (
    HYBRID,
    MODEL_SCOPE_REGISTRY,
    PLATFORM_GLOBAL,
    TENANT_SCOPED,
    TenantScope,
    check_model_tenancy_scopes,
    get_model_scope,
    register_model_scope,
    tenancy_scope,
)
from src.core.views.tenant_scoped import TenantScopedModelViewSet, TenantScopedReadOnlyModelViewSet


def _user(tenant_id=None, *, authenticated=True, direct_tenant_id=None):
    return SimpleNamespace(
        pk=uuid4(),
        is_authenticated=authenticated,
        profile=SimpleNamespace(tenant_id=tenant_id),
        tenant_id=direct_tenant_id,
    )


@pytest.fixture
def tenant_resource_bundle(transactional_db):
    """Create an isolated real table without adding a project migration."""
    del transactional_db
    with isolate_apps("src.core"):

        class TenantResource(TenantScopedModel, TimestampedModel):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "core"
                db_table = "test_tenancy_base_resource"

        class TenantResourceSerializer(serializers.ModelSerializer):
            class Meta:
                model = TenantResource
                fields = ("id", "tenant_id", "name", "created_at", "updated_at")
                read_only_fields = ("id", "tenant_id", "created_at", "updated_at")

        class TenantResourceViewSet(TenantScopedModelViewSet):
            queryset = TenantResource.objects.all()
            serializer_class = TenantResourceSerializer
            permission_classes = []

        class TenantResourceReadOnlyViewSet(TenantScopedReadOnlyModelViewSet):
            queryset = TenantResource.objects.all()
            serializer_class = TenantResourceSerializer
            permission_classes = []

        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(TenantResource)

        try:
            yield SimpleNamespace(
                model=TenantResource,
                serializer=TenantResourceSerializer,
                viewset=TenantResourceViewSet,
                readonly_viewset=TenantResourceReadOnlyViewSet,
            )
        finally:
            with connection.schema_editor() as schema_editor:
                schema_editor.delete_model(TenantResource)


def test_tenant_scoped_model_contract_is_minimal_and_typed():
    field = TenantScopedModel._meta.get_field("tenant_id")

    assert TenantScopedModel._meta.abstract is True
    assert isinstance(field, models.UUIDField)
    assert field.db_index is True
    assert field.null is False
    assert "created_at" not in {item.name for item in TenantScopedModel._meta.fields}
    assert isinstance(TenantScopedModel._meta.managers_map["objects"].get_queryset(), TenantQuerySet)


def test_timestamp_mixin_remains_separate():
    assert TimestampedModel._meta.abstract is True
    assert TimestampedModel._meta.get_field("created_at").auto_now_add is True
    assert TimestampedModel._meta.get_field("updated_at").auto_now is True
    assert "tenant_id" not in {item.name for item in TimestampedModel._meta.fields}


def test_for_tenant_filters_real_rows(tenant_resource_bundle):
    tenant_a = uuid4()
    tenant_b = uuid4()
    own = tenant_resource_bundle.model.objects.create(tenant_id=tenant_a, name="Own")
    tenant_resource_bundle.model.objects.create(tenant_id=tenant_b, name="Other")

    records = list(tenant_resource_bundle.model.objects.for_tenant(tenant_a))

    assert records == [own]


def test_viewset_rejects_x_tenant_id_spoof(tenant_resource_bundle):
    tenant_a = uuid4()
    tenant_b = uuid4()
    own = tenant_resource_bundle.model.objects.create(tenant_id=tenant_a, name="Own")
    tenant_resource_bundle.model.objects.create(tenant_id=tenant_b, name="Other")
    request = APIRequestFactory().get("/resources/", HTTP_X_TENANT_ID=str(tenant_b))
    force_authenticate(request, user=_user(tenant_a, direct_tenant_id=tenant_b))

    response = tenant_resource_bundle.viewset.as_view({"get": "list"})(request)

    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in response.data] == [own.id]


def test_read_without_tenant_returns_none(tenant_resource_bundle):
    tenant_resource_bundle.model.objects.create(tenant_id=uuid4(), name="Hidden")
    request = APIRequestFactory().get("/resources/", HTTP_X_TENANT_ID=str(uuid4()))
    force_authenticate(request, user=_user(None, direct_tenant_id=uuid4()))

    response = tenant_resource_bundle.viewset.as_view({"get": "list"})(request)

    assert response.status_code == status.HTTP_200_OK
    assert response.data == []


def test_unauthenticated_profile_cannot_supply_tenant(tenant_resource_bundle):
    tenant_id = uuid4()
    tenant_resource_bundle.model.objects.create(tenant_id=tenant_id, name="Hidden")
    request = APIRequestFactory().get("/resources/")
    request.tenant_id = tenant_id
    force_authenticate(request, user=_user(tenant_id, authenticated=False))

    response = tenant_resource_bundle.viewset.as_view({"get": "list"})(request)

    assert response.data == []


def test_invalid_profile_tenant_fails_closed(tenant_resource_bundle):
    tenant_resource_bundle.model.objects.create(tenant_id=uuid4(), name="Hidden")
    request = APIRequestFactory().get("/resources/")
    force_authenticate(request, user=_user("not-a-uuid"))

    response = tenant_resource_bundle.viewset.as_view({"get": "list"})(request)

    assert response.data == []


def test_missing_profile_fails_closed(tenant_resource_bundle):
    tenant_resource_bundle.model.objects.create(tenant_id=uuid4(), name="Hidden")
    request = APIRequestFactory().get("/resources/")
    user = SimpleNamespace(pk=uuid4(), is_authenticated=True)
    force_authenticate(request, user=user)

    response = tenant_resource_bundle.viewset.as_view({"get": "list"})(request)

    assert response.data == []


def test_missing_tenant_write_is_rejected(tenant_resource_bundle):
    request = APIRequestFactory().post("/resources/", {"name": "Denied"}, format="json")
    force_authenticate(request, user=_user(None))

    response = tenant_resource_bundle.viewset.as_view({"post": "create"})(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert tenant_resource_bundle.model.objects.count() == 0


def test_create_injects_authenticated_tenant_over_body_and_header(tenant_resource_bundle):
    tenant_a = uuid4()
    tenant_b = uuid4()
    request = APIRequestFactory().post(
        "/resources/",
        {"name": "Created", "tenant_id": str(tenant_b)},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_b),
    )
    force_authenticate(request, user=_user(tenant_a, direct_tenant_id=tenant_b))

    response = tenant_resource_bundle.viewset.as_view({"post": "create"})(request)

    assert response.status_code == status.HTTP_201_CREATED
    created = tenant_resource_bundle.model.objects.get()
    assert created.tenant_id == tenant_a


def test_update_cannot_move_record_to_submitted_tenant(tenant_resource_bundle):
    tenant_a = uuid4()
    tenant_b = uuid4()
    resource = tenant_resource_bundle.model.objects.create(tenant_id=tenant_a, name="Before")
    request = APIRequestFactory().patch(
        f"/resources/{resource.pk}/",
        {"name": "After", "tenant_id": str(tenant_b)},
        format="json",
    )
    force_authenticate(request, user=_user(tenant_a))

    response = tenant_resource_bundle.viewset.as_view({"patch": "partial_update"})(request, pk=resource.pk)

    assert response.status_code == status.HTTP_200_OK
    resource.refresh_from_db()
    assert resource.name == "After"
    assert resource.tenant_id == tenant_a


def test_readonly_viewset_uses_same_tenant_boundary(tenant_resource_bundle):
    tenant_a = uuid4()
    tenant_b = uuid4()
    own = tenant_resource_bundle.model.objects.create(tenant_id=tenant_a, name="Own")
    tenant_resource_bundle.model.objects.create(tenant_id=tenant_b, name="Other")
    request = APIRequestFactory().get("/resources/")
    force_authenticate(request, user=_user(tenant_a))

    response = tenant_resource_bundle.readonly_viewset.as_view({"get": "list"})(request)

    assert [item["id"] for item in response.data] == [own.id]


def test_non_tenant_model_viewset_raises_improperly_configured():
    with isolate_apps("src.core"):

        class GlobalRecord(models.Model):
            class Meta:
                app_label = "core"

        class GlobalSerializer(serializers.ModelSerializer):
            class Meta:
                model = GlobalRecord
                fields = ("id",)

        class InvalidViewSet(TenantScopedModelViewSet):
            queryset = GlobalRecord.objects.all()
            serializer_class = GlobalSerializer
            permission_classes = []

        request = APIRequestFactory().get("/global/")
        force_authenticate(request, user=_user(uuid4()))

        with pytest.raises(ImproperlyConfigured, match="must inherit TenantScopedModel"):
            InvalidViewSet.as_view({"get": "list"})(request)


def test_unclassified_model_system_check_fires():
    with isolate_apps("src.core") as isolated_apps:

        class UnclassifiedRecord(models.Model):
            class Meta:
                app_label = "core"

        errors = check_model_tenancy_scopes(app_configs=[isolated_apps.get_app_config("core")])

    matching = [error for error in errors if error.obj is UnclassifiedRecord]
    assert len(matching) == 1
    assert matching[0].id == "core.E005"
    assert "no tenancy scope classification" in matching[0].msg


def test_canonical_model_is_classified_without_registry_entry():
    with isolate_apps("src.core") as isolated_apps:

        class CanonicalRecord(TenantScopedModel):
            class Meta:
                app_label = "core"

        errors = check_model_tenancy_scopes(app_configs=[isolated_apps.get_app_config("core")])

    assert get_model_scope(CanonicalRecord) is TENANT_SCOPED
    assert all(error.obj is not CanonicalRecord for error in errors)


def test_contradictory_canonical_model_system_check_fires():
    with isolate_apps("src.core") as isolated_apps:

        class ContradictoryRecord(TenantScopedModel):
            class Meta:
                app_label = "core"

        label = ContradictoryRecord._meta.label_lower
        MODEL_SCOPE_REGISTRY[label] = HYBRID
        try:
            errors = check_model_tenancy_scopes(app_configs=[isolated_apps.get_app_config("core")])
        finally:
            MODEL_SCOPE_REGISTRY.pop(label, None)

    matching = [error for error in errors if error.obj is ContradictoryRecord]
    assert len(matching) == 1
    assert matching[0].id == "core.E005"
    assert "contradicts" in matching[0].msg


def test_proxy_model_does_not_require_independent_classification():
    with isolate_apps("src.core") as isolated_apps:

        @tenancy_scope(PLATFORM_GLOBAL)
        class GlobalBase(models.Model):
            class Meta:
                app_label = "core"

        class GlobalProxy(GlobalBase):
            class Meta:
                app_label = "core"
                proxy = True

        try:
            errors = check_model_tenancy_scopes(app_configs=[isolated_apps.get_app_config("core")])
        finally:
            MODEL_SCOPE_REGISTRY.pop(GlobalBase._meta.label_lower, None)

    assert all(error.obj is not GlobalProxy for error in errors)


def test_known_hybrid_and_global_models_are_explicitly_classified():
    assert get_model_scope("platform_management.PlatformSetting") is HYBRID
    assert get_model_scope("platform_management.FeatureFlag") is HYBRID
    assert get_model_scope("core.ComplianceCheck") is HYBRID
    assert get_model_scope("core.ResidencyRule") is HYBRID
    assert get_model_scope("platform_management.SystemHealth") is PLATFORM_GLOBAL


def test_registry_rejects_contradictory_classification():
    label = "test_scope.Contradiction"
    try:
        register_model_scope(label, TenantScope.PLATFORM_GLOBAL)
        with pytest.raises(ImproperlyConfigured, match="already classified"):
            register_model_scope(label, TenantScope.HYBRID)
    finally:
        MODEL_SCOPE_REGISTRY.pop(label.lower(), None)


def test_scope_decorator_registers_model():
    with isolate_apps("src.core"):

        @tenancy_scope(PLATFORM_GLOBAL)
        class DecoratedGlobal(models.Model):
            class Meta:
                app_label = "core"

        try:
            assert get_model_scope(DecoratedGlobal) is PLATFORM_GLOBAL
        finally:
            MODEL_SCOPE_REGISTRY.pop(DecoratedGlobal._meta.label_lower, None)


def test_project_model_inventory_is_fully_classified():
    assert check_model_tenancy_scopes() == []


def test_registry_rejects_malformed_model_label():
    with pytest.raises(ValueError, match="app_label.ModelName"):
        get_model_scope("MissingAppLabel")


def test_uuid_result_type_from_profile(tenant_resource_bundle):
    tenant_id = uuid4()
    request = APIRequestFactory().get("/resources/")
    request.user = _user(str(tenant_id))
    view = tenant_resource_bundle.viewset()
    view.request = request

    assert view._get_tenant_id() == tenant_id
    assert isinstance(view._get_tenant_id(), UUID)
