"""Governed API v2 controllers for document intelligence."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db.models import Count, QuerySet
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api.profile import GovernedAPIViewMixin
from src.core.auth_utils import get_user_tenant_id

from .filters import (
    ClassifierModelVersionFilterSet,
    ClassifierTrainingJobFilterSet,
    DocumentClassificationFilterSet,
    DocumentExtractionFilterSet,
    ExtractionTemplateFilterSet,
    TemplateZoneFilterSet,
)
from .health import get_module_health
from .models import (
    ClassifierModelVersion,
    ClassifierTrainingJob,
    DocumentClassification,
    DocumentClassificationScore,
    DocumentExtraction,
    DocumentExtractionPage,
    DocumentIntelligenceConfiguration,
    ExtractionTemplate,
    ExtractionTemplateZone,
)
from .permissions import ActionAccessMixin, SessionAuthentication401
from .serializers import (
    ClassificationCancelSerializer,
    ClassificationRetrySerializer,
    ClassificationReviewSerializer,
    ClassifierModelVersionDetailSerializer,
    ClassifierModelVersionListSerializer,
    ClassifierTrainingJobCreateSerializer,
    ClassifierTrainingJobDetailSerializer,
    ClassifierTrainingJobListSerializer,
    CloneTemplateSerializer,
    ConfigurationAuditSerializer,
    ConfigurationImportSerializer,
    ConfigurationRollbackSerializer,
    ConfigurationSimulationSerializer,
    ConfigurationVersionSerializer,
    ConfigurationWriteSerializer,
    DocumentClassificationCreateSerializer,
    DocumentClassificationDetailSerializer,
    DocumentClassificationListSerializer,
    DocumentClassificationScoreSerializer,
    DocumentExtractionCreateSerializer,
    DocumentExtractionDetailSerializer,
    DocumentExtractionListSerializer,
    DocumentExtractionPageSerializer,
    DocumentIntelligenceConfigurationSerializer,
    ExtractionCancelSerializer,
    ExtractionRetrySerializer,
    ExtractionTemplateCreateSerializer,
    ExtractionTemplateDetailSerializer,
    ExtractionTemplateListSerializer,
    ExtractionTemplateUpdateSerializer,
    ExtractionTemplateZoneCreateSerializer,
    ExtractionTemplateZoneReadSerializer,
    ExtractionTemplateZoneUpdateSerializer,
    JobSummarySerializer,
    ModelActivateSerializer,
    ModelRollbackSerializer,
    TemplateActivateSerializer,
    TemplateDeactivateSerializer,
    TemplateMatchSerializer,
    TrainingCancelSerializer,
    TrainingRetrySerializer,
)
from .services import (
    ConfigurationService,
    DocumentClassificationService,
    DocumentExtractionService,
    DocumentIntelligenceError,
    TemplateMatchingService,
    default_configuration_document,
)


class TenantGovernedViewSet(GovernedAPIViewMixin, ActionAccessMixin, viewsets.GenericViewSet):
    """Resolve canonical identity and provide uniform filter/pagination helpers."""

    filterset_class: type | None = None

    def resolved_tenant_id(self) -> UUID | None:
        value = get_user_tenant_id(self.request.user)
        try:
            tenant_id = UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return None
        self.request.tenant_id = tenant_id
        return tenant_id

    def tenant_id(self) -> UUID:
        """Return a valid tenant for commands, failing closed when absent."""

        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            raise PermissionDenied("Authenticated identity has no valid tenant.")
        return tenant_id

    def actor_id(self) -> UUID:
        identifier = getattr(self.request.user, "id", None)
        if identifier is None:
            raise PermissionDenied("Authenticated identity has no valid actor identifier.")
        try:
            return UUID(str(identifier))
        except (TypeError, ValueError, AttributeError):
            # Django's built-in user model uses integer primary keys while the
            # domain audit contract is UUID.  UUIDv5 provides a stable,
            # non-secret identity projection without accepting client input.
            return uuid5(NAMESPACE_URL, f"saraise:user:{identifier}")

    def filtered_queryset(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if self.filterset_class is None:
            return queryset
        search_max_length = int(ConfigurationService().get_value(self.tenant_id(), "limits.search_max_length"))
        filters = self.filterset_class(
            self.request.query_params,
            queryset=queryset,
            search_max_length=search_max_length,
        )
        if not filters.is_valid():
            raise ValidationError(filters.errors)
        return filters.qs

    def paginated(self, queryset: QuerySet[Any], serializer_class: type, **context: object) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination must be configured for collection endpoints")
        return self.get_paginated_response(serializer_class(page, many=True, context=context).data)


class DocumentExtractionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TenantGovernedViewSet,
):
    service_class = DocumentExtractionService
    filterset_class = DocumentExtractionFilterSet
    action_permissions = {
        "list": "document_intelligence.extraction:read",
        "retrieve": "document_intelligence.extraction:read",
        "pages": "document_intelligence.extraction:read",
        "create": "document_intelligence.extraction:create",
        "retry": "document_intelligence.extraction:retry",
        "cancel": "document_intelligence.extraction:cancel",
        "destroy": "document_intelligence.extraction:delete",
    }
    action_quotas = {"create": "document_intelligence.processing_requests"}

    def get_queryset(self) -> QuerySet[DocumentExtraction]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return DocumentExtraction.objects.none()
        return DocumentExtraction.objects.for_tenant(tenant_id).filter(is_deleted=False).select_related("template")

    def get_serializer_class(self) -> type:
        return {
            "list": DocumentExtractionListSerializer,
            "create": DocumentExtractionCreateSerializer,
            "retry": ExtractionRetrySerializer,
            "cancel": ExtractionCancelSerializer,
        }.get(self.action, DocumentExtractionDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered_queryset(self.get_queryset()), DocumentExtractionListSerializer)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del args, kwargs
        serializer = DocumentExtractionCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        key = data.pop("idempotency_key")
        accepted = self.service_class().request_extraction(self.tenant_id(), self.actor_id(), data, key)
        return Response(
            {
                "extraction": DocumentExtractionDetailSerializer(accepted.record).data,
                "job": JobSummarySerializer(accepted.job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.service_class().get_extraction(self.tenant_id(), self.kwargs["pk"])
        return Response(DocumentExtractionDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        self.service_class().archive_extraction(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def pages(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        extraction = self.get_object()
        queryset = (
            DocumentExtractionPage.objects.for_tenant(self.tenant_id())
            .filter(extraction=extraction)
            .order_by("page_number")
        )
        return self.paginated(queryset, DocumentExtractionPageSerializer)

    @action(detail=True, methods=["post"], serializer_class=ExtractionRetrySerializer)
    def retry(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = ExtractionRetrySerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        accepted = self.service_class().retry_extraction(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["idempotency_key"]
        )
        return Response(
            {
                "extraction": DocumentExtractionDetailSerializer(accepted.record).data,
                "job": JobSummarySerializer(accepted.job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], serializer_class=ExtractionCancelSerializer)
    def cancel(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = ExtractionCancelSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().cancel_extraction(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(DocumentExtractionDetailSerializer(value).data)


class DocumentExtractionPageViewSet(mixins.RetrieveModelMixin, TenantGovernedViewSet):
    serializer_class = DocumentExtractionPageSerializer
    action_permissions = {"retrieve": "document_intelligence.extraction:read"}

    def get_queryset(self) -> QuerySet[DocumentExtractionPage]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return DocumentExtractionPage.objects.none()
        return DocumentExtractionPage.objects.for_tenant(tenant_id).select_related("extraction")


class DocumentClassificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantGovernedViewSet):
    service_class = DocumentClassificationService
    filterset_class = DocumentClassificationFilterSet
    action_permissions = {
        "list": "document_intelligence.classification:read",
        "retrieve": "document_intelligence.classification:read",
        "scores": "document_intelligence.classification:read",
        "create": "document_intelligence.classification:create",
        "review": "document_intelligence.classification:review",
        "retry": "document_intelligence.classification:retry",
        "cancel": "document_intelligence.classification:cancel",
        "destroy": "document_intelligence.classification:delete",
    }
    action_quotas = {"create": "document_intelligence.processing_requests"}

    def get_queryset(self) -> QuerySet[DocumentClassification]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return DocumentClassification.objects.none()
        return (
            DocumentClassification.objects.for_tenant(tenant_id)
            .filter(is_deleted=False)
            .select_related("model_version")
        )

    def get_serializer_class(self) -> type:
        return {
            "list": DocumentClassificationListSerializer,
            "create": DocumentClassificationCreateSerializer,
            "review": ClassificationReviewSerializer,
            "retry": ClassificationRetrySerializer,
            "cancel": ClassificationCancelSerializer,
        }.get(self.action, DocumentClassificationDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered_queryset(self.get_queryset()), DocumentClassificationListSerializer)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = DocumentClassificationCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        accepted = self.service_class().request_classification(
            self.tenant_id(), self.actor_id(), data["document_id"], data["document_version_id"], data["idempotency_key"]
        )
        return Response(
            {
                "classification": DocumentClassificationDetailSerializer(accepted.record).data,
                "job": JobSummarySerializer(accepted.job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.service_class().get_classification(self.tenant_id(), self.kwargs["pk"])
        return Response(DocumentClassificationDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        self.service_class().archive_classification(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def scores(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        queryset = self.service_class().get_confidence_distribution(self.tenant_id(), self.kwargs["pk"])
        return self.paginated(queryset, DocumentClassificationScoreSerializer)

    @action(detail=True, methods=["post"], serializer_class=ClassificationReviewSerializer)
    def review(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = ClassificationReviewSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().review_classification(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["category"],
            serializer.validated_data.get("note", ""),
        )
        return Response(DocumentClassificationDetailSerializer(value).data)

    @action(detail=True, methods=["post"], serializer_class=ClassificationRetrySerializer)
    def retry(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = ClassificationRetrySerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        accepted = self.service_class().retry_classification(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["idempotency_key"]
        )
        return Response(
            {
                "classification": DocumentClassificationDetailSerializer(accepted.record).data,
                "job": JobSummarySerializer(accepted.job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], serializer_class=ClassificationCancelSerializer)
    def cancel(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = ClassificationCancelSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().cancel_classification(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(DocumentClassificationDetailSerializer(value).data)


class DocumentClassificationScoreViewSet(mixins.RetrieveModelMixin, TenantGovernedViewSet):
    serializer_class = DocumentClassificationScoreSerializer
    action_permissions = {"retrieve": "document_intelligence.classification:read"}

    def get_queryset(self) -> QuerySet[DocumentClassificationScore]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return DocumentClassificationScore.objects.none()
        return DocumentClassificationScore.objects.for_tenant(tenant_id).select_related("classification")


class ExtractionTemplateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantGovernedViewSet):
    service_class = TemplateMatchingService
    filterset_class = ExtractionTemplateFilterSet
    action_permissions = {
        "list": "document_intelligence.template:read",
        "retrieve": "document_intelligence.template:read",
        "create": "document_intelligence.template:create",
        "partial_update": "document_intelligence.template:update",
        "destroy": "document_intelligence.template:delete",
        "activate": "document_intelligence.template:activate",
        "deactivate": "document_intelligence.template:activate",
        "clone": "document_intelligence.template:create",
        "match": "document_intelligence.template:read",
    }
    action_quotas = {"match": "document_intelligence.processing_requests"}

    def get_queryset(self) -> QuerySet[ExtractionTemplate]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return ExtractionTemplate.objects.none()
        return (
            ExtractionTemplate.objects.for_tenant(tenant_id)
            .filter(is_deleted=False)
            .annotate(zone_count=Count("zones"))
            .prefetch_related("zones")
        )

    def get_serializer_class(self) -> type:
        return {
            "list": ExtractionTemplateListSerializer,
            "create": ExtractionTemplateCreateSerializer,
            "partial_update": ExtractionTemplateUpdateSerializer,
            "activate": TemplateActivateSerializer,
            "deactivate": TemplateDeactivateSerializer,
            "clone": CloneTemplateSerializer,
            "match": TemplateMatchSerializer,
        }.get(self.action, ExtractionTemplateDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered_queryset(self.get_queryset()), ExtractionTemplateListSerializer)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ExtractionTemplateCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        zones = data.pop("zones", [])
        value = self.service_class().create_template(self.tenant_id(), self.actor_id(), data, zones)
        return Response(ExtractionTemplateDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.service_class().get_template(self.tenant_id(), self.kwargs["pk"])
        return Response(ExtractionTemplateDetailSerializer(value).data)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        serializer = ExtractionTemplateUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().update_template(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data
        )
        return Response(ExtractionTemplateDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        self.service_class().archive_template(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], serializer_class=TemplateActivateSerializer)
    def activate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = TemplateActivateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().activate_template(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["transition_key"]
        )
        return Response(ExtractionTemplateDetailSerializer(value).data)

    @action(detail=True, methods=["post"], serializer_class=TemplateDeactivateSerializer)
    def deactivate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = TemplateDeactivateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().deactivate_template(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["transition_key"]
        )
        return Response(ExtractionTemplateDetailSerializer(value).data)

    @action(detail=True, methods=["post"], serializer_class=CloneTemplateSerializer)
    def clone(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = CloneTemplateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().clone_template_revision(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["name"]
        )
        return Response(ExtractionTemplateDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], serializer_class=TemplateMatchSerializer)
    def match(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = TemplateMatchSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        result = self.service_class().match_template(
            self.tenant_id(),
            serializer.validated_data["document_id"],
            serializer.validated_data["document_version_id"],
            self.kwargs["pk"],
        )
        return Response(
            {
                "matched": result.template_id is not None,
                "template_id": str(result.template_id) if result.template_id else None,
                "confidence": result.confidence,
                "processing_time_ms": result.processing_time_ms,
                "evidence": {"threshold_met": result.template_id is not None},
            }
        )


class ExtractionTemplateZoneViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantGovernedViewSet):
    service_class = TemplateMatchingService
    filterset_class = TemplateZoneFilterSet
    action_permissions = {
        "list": "document_intelligence.template:read",
        "retrieve": "document_intelligence.template:read",
        "create": "document_intelligence.template:update",
        "partial_update": "document_intelligence.template:update",
        "destroy": "document_intelligence.template:update",
    }

    def get_queryset(self) -> QuerySet[ExtractionTemplateZone]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return ExtractionTemplateZone.objects.none()
        return ExtractionTemplateZone.objects.for_tenant(tenant_id).filter(is_deleted=False).select_related("template")

    def get_serializer_class(self) -> type:
        return {
            "create": ExtractionTemplateZoneCreateSerializer,
            "partial_update": ExtractionTemplateZoneUpdateSerializer,
        }.get(self.action, ExtractionTemplateZoneReadSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered_queryset(self.get_queryset()), ExtractionTemplateZoneReadSerializer)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ExtractionTemplateZoneCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        template_id = data.pop("template_id", None)
        if template_id is None:
            raise ValidationError({"template_id": "This field is required."})
        value = self.service_class().create_zone(self.tenant_id(), template_id, self.actor_id(), data)
        return Response(ExtractionTemplateZoneReadSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        serializer = ExtractionTemplateZoneUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().update_zone(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data
        )
        return Response(ExtractionTemplateZoneReadSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        self.service_class().archive_zone(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClassifierTrainingJobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantGovernedViewSet):
    service_class = DocumentClassificationService
    filterset_class = ClassifierTrainingJobFilterSet
    action_permissions = {
        "list": "document_intelligence.training:read",
        "retrieve": "document_intelligence.training:read",
        "create": "document_intelligence.training:create",
        "retry": "document_intelligence.training:retry",
        "cancel": "document_intelligence.training:cancel",
    }
    action_quotas = {"create": "document_intelligence.processing_requests"}

    def get_queryset(self) -> QuerySet[ClassifierTrainingJob]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return ClassifierTrainingJob.objects.none()
        return ClassifierTrainingJob.objects.for_tenant(tenant_id).all()

    def get_serializer_class(self) -> type:
        return {
            "list": ClassifierTrainingJobListSerializer,
            "create": ClassifierTrainingJobCreateSerializer,
            "retry": TrainingRetrySerializer,
            "cancel": TrainingCancelSerializer,
        }.get(self.action, ClassifierTrainingJobDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered_queryset(self.get_queryset()), ClassifierTrainingJobListSerializer)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ClassifierTrainingJobCreateSerializer(
            data=self.request.data,
            context={"tenant_id": self.tenant_id()},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        accepted = self.service_class().train_classifier(
            self.tenant_id(),
            self.actor_id(),
            data["name"],
            data["items"],
            data["requested_version"],
            data["idempotency_key"],
        )
        return Response(
            {
                "training_job": ClassifierTrainingJobDetailSerializer(accepted.record).data,
                "job": JobSummarySerializer(accepted.job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], serializer_class=TrainingRetrySerializer)
    def retry(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = TrainingRetrySerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        accepted = self.service_class().retry_training(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["idempotency_key"]
        )
        return Response(
            {
                "training_job": ClassifierTrainingJobDetailSerializer(accepted.record).data,
                "job": JobSummarySerializer(accepted.job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], serializer_class=TrainingCancelSerializer)
    def cancel(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = TrainingCancelSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().cancel_training(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(ClassifierTrainingJobDetailSerializer(value).data)


class ClassifierModelVersionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantGovernedViewSet):
    service_class = DocumentClassificationService
    filterset_class = ClassifierModelVersionFilterSet
    action_permissions = {
        "list": "document_intelligence.model:read",
        "retrieve": "document_intelligence.model:read",
        "activate": "document_intelligence.model:activate",
        "rollback": "document_intelligence.model:rollback",
    }

    def get_queryset(self) -> QuerySet[ClassifierModelVersion]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return ClassifierModelVersion.objects.none()
        return ClassifierModelVersion.objects.for_tenant(tenant_id).select_related("training_job")

    def get_serializer_class(self) -> type:
        return {
            "list": ClassifierModelVersionListSerializer,
            "activate": ModelActivateSerializer,
            "rollback": ModelRollbackSerializer,
        }.get(self.action, ClassifierModelVersionDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered_queryset(self.get_queryset()), ClassifierModelVersionListSerializer)

    @action(detail=True, methods=["post"], serializer_class=ModelActivateSerializer)
    def activate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = ModelActivateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().activate_model_version(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["transition_key"]
        )
        return Response(ClassifierModelVersionDetailSerializer(value).data)

    @action(detail=True, methods=["post"], serializer_class=ModelRollbackSerializer)
    def rollback(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = ModelRollbackSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class().rollback_model_version(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["transition_key"]
        )
        return Response(ClassifierModelVersionDetailSerializer(value).data)


class DocumentIntelligenceConfigurationViewSet(TenantGovernedViewSet):
    """RBAC-gated client surface for the complete configuration lifecycle."""

    service_class = ConfigurationService
    action_permissions = {
        "current": "document_intelligence.configuration:read",
        "defaults": "document_intelligence.configuration:read",
        "versions": "document_intelligence.configuration:read",
        "audit": "document_intelligence.configuration:read",
        "export_configuration": "document_intelligence.configuration:read",
        "rollback": "document_intelligence.configuration:update",
        "import_configuration": "document_intelligence.configuration:update",
        "simulate": "document_intelligence.configuration:update",
    }

    def get_permissions(self) -> list[object]:
        if getattr(self, "action", "") == "current" and self.request.method != "GET":
            self.action_permissions = {
                **self.action_permissions,
                "current": "document_intelligence.configuration:update",
            }
        return super().get_permissions()

    def get_queryset(self) -> QuerySet[DocumentIntelligenceConfiguration]:
        tenant_id = self.resolved_tenant_id()
        if tenant_id is None:
            return DocumentIntelligenceConfiguration.objects.none()
        return DocumentIntelligenceConfiguration.objects.for_tenant(tenant_id)

    def _environment(self) -> str | None:
        value = self.request.query_params.get("environment")
        return str(value) if value else None

    def _correlation_id(self) -> str | None:
        value = getattr(self.request, "correlation_id", None)
        return str(value) if value else None

    @action(detail=False, methods=["get", "put", "patch"])
    def current(self, request: object) -> Response:
        del request
        service = self.service_class()
        if self.request.method == "GET":
            try:
                record = service.get_record(self.tenant_id(), self._environment())
            except DocumentIntelligenceError as exc:
                if exc.error_code != "configuration_unavailable":
                    raise
                record = service.save(
                    self.tenant_id(),
                    self.actor_id(),
                    default_configuration_document(),
                    environment=self._environment(),
                    change_reason="Initialize validated tenant defaults",
                    correlation_id=self._correlation_id(),
                )
            return Response(DocumentIntelligenceConfigurationSerializer(record).data)
        serializer = ConfigurationWriteSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        record = service.save(
            self.tenant_id(),
            self.actor_id(),
            data["document"],
            environment=data.get("environment"),
            change_reason=data["change_reason"],
            correlation_id=self._correlation_id(),
            partial=self.request.method == "PATCH",
        )
        return Response(DocumentIntelligenceConfigurationSerializer(record).data)

    @action(detail=False, methods=["get"])
    def defaults(self, request: object) -> Response:
        del request
        return Response(default_configuration_document())

    @action(detail=False, methods=["get"])
    def versions(self, request: object) -> Response:
        del request
        values = self.service_class().versions(self.tenant_id(), self._environment())
        return Response(ConfigurationVersionSerializer(values, many=True).data)

    @action(detail=False, methods=["get"])
    def audit(self, request: object) -> Response:
        del request
        values = self.service_class().audits(self.tenant_id(), self._environment())
        return Response(ConfigurationAuditSerializer(values, many=True).data)

    @action(detail=False, methods=["post"])
    def rollback(self, request: object) -> Response:
        del request
        serializer = ConfigurationRollbackSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        record = self.service_class().rollback(
            self.tenant_id(),
            self.actor_id(),
            data["version"],
            environment=data.get("environment"),
            change_reason=data["change_reason"],
            correlation_id=self._correlation_id(),
        )
        return Response(DocumentIntelligenceConfigurationSerializer(record).data)

    @action(detail=False, methods=["post"], url_path="import")
    def import_configuration(self, request: object) -> Response:
        del request
        serializer = ConfigurationImportSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        reason = payload.pop("change_reason", "Import configuration document")
        if "exported_at" in payload:
            payload["exported_at"] = payload["exported_at"].isoformat()
        record = self.service_class().import_document(
            self.tenant_id(),
            self.actor_id(),
            payload,
            change_reason=reason,
            correlation_id=self._correlation_id(),
        )
        return Response(DocumentIntelligenceConfigurationSerializer(record).data)

    @action(detail=False, methods=["get"], url_path="export")
    def export_configuration(self, request: object) -> Response:
        del request
        return Response(self.service_class().export_document(self.tenant_id(), self._environment()))

    @action(detail=False, methods=["post"])
    def simulate(self, request: object) -> Response:
        del request
        serializer = ConfigurationSimulationSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = self.service_class().simulate(self.tenant_id(), data["document"], environment=data.get("environment"))
        return Response(result)


class ModuleHealthAPIView(GovernedAPIViewMixin, APIView):
    authentication_classes = (SessionAuthentication401,)
    permission_classes = ()

    def get_permissions(self) -> list[object]:
        from rest_framework.permissions import IsAuthenticated

        from src.core.access.permissions import RequiresAccess

        tenant_id = get_user_tenant_id(getattr(self.request, "user", None))
        if tenant_id is not None:
            try:
                self.request.tenant_id = UUID(str(tenant_id))
            except (TypeError, ValueError, AttributeError):
                self.request.tenant_id = None
        self.required_permission = "document_intelligence.health:read"
        self.required_entitlement = self.required_permission
        self.quota_resource = "document_intelligence.api_reads"
        return [IsAuthenticated(), RequiresAccess()]

    def get(self, request: object) -> Response:
        del request
        tenant_value = get_user_tenant_id(self.request.user)
        try:
            tenant_id = UUID(str(tenant_value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("Authenticated identity has no valid tenant.") from exc
        stale_after = int(ConfigurationService().get_value(tenant_id, "health.stale_after_seconds"))
        report = get_module_health(stale_after)
        return Response(report.payload, status=report.status_code)


__all__ = [name for name in globals() if name.endswith("ViewSet") or name.endswith("APIView")]
