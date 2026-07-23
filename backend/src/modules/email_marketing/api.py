"""Governed API v2 controllers; all mutations delegate to domain services."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from django.core import signing
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from src.core.api import GovernedAPIViewMixin
from src.core.auth_utils import get_user_tenant_id

from .adapters import AdapterNotRegistered, get_provider_event_verifier
from .filters import (
    CampaignFilterSet,
    ConsentFilterSet,
    DeliveryFilterSet,
    RecipientFilterSet,
    SuppressionFilterSet,
    TemplateFilterSet,
)
from .models import (
    CampaignRecipient,
    ConsentRecord,
    DeliveryAttempt,
    EmailCampaign,
    EmailMarketingConfiguration,
    EmailTemplate,
    SuppressionEntry,
)
from .permissions import EmailMarketingAccessMixin, ProviderWebhookPermission
from .serializers import (
    AsyncJobSummarySerializer,
    CampaignAnalyticsSerializer,
    CampaignAudienceResolutionSerializer,
    CampaignCreateSerializer,
    CampaignDetailSerializer,
    CampaignListSerializer,
    CampaignScheduleSerializer,
    CampaignSendSerializer,
    CampaignTransitionSerializer,
    CampaignUpdateSerializer,
    ConfigurationPreviewSerializer,
    ConfigurationRollbackSerializer,
    ConfigurationSerializer,
    ConfigurationUpdateSerializer,
    ConfigurationVersionSerializer,
    ConsentCreateSerializer,
    ConsentDetailSerializer,
    ConsentListSerializer,
    ConsentRevokeSerializer,
    DeliveryAttemptDetailSerializer,
    DeliveryAttemptListSerializer,
    PublicUnsubscribeResponseSerializer,
    RecipientDetailSerializer,
    RecipientListSerializer,
    RecipientRetrySerializer,
    RenderedEmailSerializer,
    SuppressionCreateSerializer,
    SuppressionDeactivateSerializer,
    SuppressionDetailSerializer,
    SuppressionListSerializer,
    TemplateCloneSerializer,
    TemplateCreateSerializer,
    TemplateDetailSerializer,
    TemplateListSerializer,
    TemplatePreviewSerializer,
    TemplateUpdateSerializer,
)
from .services import (
    CampaignService,
    ComplianceService,
    ConfigurationService,
    DeliveryService,
    TemplateService,
    get_runtime_configuration,
)


class PublicEmailThrottle(SimpleRateThrottle):
    scope = "email_marketing_public"

    def allow_request(self, request: object, view: object) -> bool:
        tenant_id = getattr(request, "tenant_id", None)
        if tenant_id is None:
            return False
        per_minute = get_runtime_configuration(tenant_id).document["rate_limits"]["public_per_minute"]
        self.rate = f"{per_minute}/min"
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request: object, view: object) -> str:
        del view
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class EmailMarketingViewSet(
    GovernedAPIViewMixin,
    EmailMarketingAccessMixin,
    viewsets.GenericViewSet[Any],
):
    """Canonical tenant identity and common governed pagination helpers."""

    filterset_class: type | None = None
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def resolved_tenant_id(self) -> UUID | None:
        value = get_user_tenant_id(self.request.user)
        try:
            tenant = UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
            return None
        self.request.tenant_id = tenant
        return tenant

    def tenant_id(self) -> UUID:
        tenant = self.resolved_tenant_id()
        if tenant is None:
            raise PermissionDenied("Authenticated identity has no valid tenant.")
        return tenant

    def actor_id(self) -> UUID:
        value = getattr(self.request.user, "id", None)
        if value is None:
            raise PermissionDenied("Authenticated identity has no valid actor.")
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return uuid5(NAMESPACE_URL, f"saraise:user:{value}")

    def mutation_idempotency_key(self) -> str:
        value = str(self.request.headers.get("Idempotency-Key", "")).strip()
        if not value:
            canonical = json.dumps(
                self.request.data,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            value = f"request:{hashlib.sha256(canonical.encode()).hexdigest()}"
        if len(value) > 255:
            raise ValidationError({"Idempotency-Key": "Must not exceed 255 characters."})
        return value

    def filtered(self, queryset: Any) -> Any:
        if self.filterset_class is None:
            return queryset
        filters = self.filterset_class(
            self.request.query_params,
            queryset=queryset,
            tenant_id=self.tenant_id(),
        )
        if not filters.is_valid():
            raise ValidationError(filters.errors)
        return filters.qs

    def paginated(self, queryset: Any, serializer_class: type) -> Response:
        pagination = get_runtime_configuration(self.tenant_id()).document["pagination"]
        paginator = self.paginator
        if paginator is None:
            raise RuntimeError("Governed pagination is required.")
        paginator.page_size = pagination["default_page_size"]
        paginator.max_page_size = pagination["max_page_size"]
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required.")
        return self.get_paginated_response(serializer_class(page, many=True).data)


class EmailCampaignViewSet(EmailMarketingViewSet):
    service_class = CampaignService
    filterset_class = CampaignFilterSet
    action_permissions = {
        "list": "email_marketing.campaign:read",
        "retrieve": "email_marketing.campaign:read",
        "create": "email_marketing.campaign:create",
        "partial_update": "email_marketing.campaign:update",
        "destroy": "email_marketing.campaign:delete",
        "resolve_audience": "email_marketing.campaign:resolve_audience",
        "schedule": "email_marketing.campaign:schedule",
        "unschedule": "email_marketing.campaign:schedule",
        "send": "email_marketing.campaign:send",
        "pause": "email_marketing.campaign:pause",
        "resume": "email_marketing.campaign:send",
        "cancel": "email_marketing.campaign:cancel",
        "analytics": "email_marketing.analytics:read",
        "preflight": "email_marketing.campaign:read",
    }
    action_quotas = {"resolve_audience": "email_marketing.audience_resolutions"}

    def get_queryset(self) -> Any:
        tenant = self.resolved_tenant_id()
        if tenant is None:
            return EmailCampaign.objects.none()
        return EmailCampaign.objects.for_tenant(tenant).filter(is_deleted=False).select_related("template")

    def get_serializer_class(self) -> type:
        return {
            "list": CampaignListSerializer,
            "create": CampaignCreateSerializer,
            "partial_update": CampaignUpdateSerializer,
            "resolve_audience": CampaignAudienceResolutionSerializer,
            "schedule": CampaignScheduleSerializer,
            "unschedule": CampaignTransitionSerializer,
            "send": CampaignSendSerializer,
            "pause": CampaignTransitionSerializer,
            "resume": CampaignTransitionSerializer,
            "cancel": CampaignTransitionSerializer,
            "analytics": CampaignAnalyticsSerializer,
        }.get(self.action, CampaignDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered(self.get_queryset()), CampaignListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(CampaignDetailSerializer(self.get_object()).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = CampaignCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        campaign = self.service_class.create_campaign(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data,
            self.mutation_idempotency_key(),
        )
        return Response(
            CampaignDetailSerializer(campaign).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        serializer = CampaignUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        campaign = self.service_class.update_campaign(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data,
        )
        return Response(CampaignDetailSerializer(campaign).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        self.service_class.archive_campaign(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="resolve-audience")
    def resolve_audience(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = CampaignAudienceResolutionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        job = self.service_class.request_audience_resolution(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["idempotency_key"],
        )
        return Response(
            AsyncJobSummarySerializer(job).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def preflight(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        return Response(self.service_class.preflight(self.tenant_id(), self.kwargs["pk"]).as_dict())

    @action(detail=True, methods=["post"])
    def schedule(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        campaign = self.get_object()
        serializer = CampaignScheduleSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = self.service_class.set_schedule(
            self.tenant_id(),
            campaign.id,
            self.actor_id(),
            data["scheduled_at"],
            data["timezone"],
            data["idempotency_key"],
        )
        return Response(CampaignDetailSerializer(result).data)

    @action(detail=True, methods=["post"])
    def unschedule(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = CampaignTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        campaign = self.service_class.unschedule_campaign(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["idempotency_key"],
        )
        return Response(CampaignDetailSerializer(campaign).data)

    @action(detail=True, methods=["post"])
    def send(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = CampaignSendSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        job = self.service_class.request_send(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            data["idempotency_key"],
            data.get("preflight_receipt"),
        )
        return Response(
            AsyncJobSummarySerializer(job).data,
            status=status.HTTP_202_ACCEPTED,
        )

    def _transition_action(self, name: str) -> Response:
        self.get_object()
        serializer = CampaignTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = getattr(self.service_class, f"{name}_campaign")(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["idempotency_key"],
        )
        if isinstance(value, EmailCampaign):
            return Response(CampaignDetailSerializer(value).data)
        return Response(
            AsyncJobSummarySerializer(value).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def pause(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition_action("pause")

    @action(detail=True, methods=["post"])
    def resume(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition_action("resume")

    @action(detail=True, methods=["post"])
    def cancel(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition_action("cancel")

    @action(detail=True, methods=["get"])
    def analytics(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        campaign = self.get_object()
        analytics = self.service_class.get_campaign_analytics(self.tenant_id(), self.kwargs["pk"])
        preflight = self.service_class.preflight(self.tenant_id(), self.kwargs["pk"])
        data = analytics.as_dict()
        data.update(
            {
                "sent": data.pop("accepted"),
                "unique_open_rate": data.pop("open_rate"),
                "unique_click_rate": data.pop("click_rate"),
                "preflight": {
                    "content_valid": preflight.content_valid,
                    "receipt": preflight.receipt,
                    "rendered": preflight.content_valid,
                    "resolved_count": preflight.resolved_count,
                    "eligible_count": preflight.eligible_count,
                    "suppressed_count": preflight.suppressed_count,
                    "consent_failure_count": preflight.consent_failure_count,
                    "suppression_failure_count": preflight.suppression_failure_count,
                    "sender_healthy": preflight.sender_valid,
                    "sender_detail": (
                        "Sender is verified for this tenant."
                        if preflight.sender_valid
                        else "Sender verification is required before delivery."
                    ),
                    "quota_required": preflight.quota_required,
                    "quota_remaining": preflight.quota_remaining,
                    "scheduled_at": campaign.scheduled_at,
                    "timezone": campaign.timezone,
                    "blocking_reasons": [item["message"] for item in preflight.blockers],
                },
            }
        )
        return Response(CampaignAnalyticsSerializer(data).data)


class EmailTemplateViewSet(EmailMarketingViewSet):
    service_class = TemplateService
    filterset_class = TemplateFilterSet
    action_permissions = {
        "list": "email_marketing.template:read",
        "retrieve": "email_marketing.template:read",
        "create": "email_marketing.template:create",
        "partial_update": "email_marketing.template:update",
        "destroy": "email_marketing.template:delete",
        "activate": "email_marketing.template:activate",
        "archive": "email_marketing.template:activate",
        "clone": "email_marketing.template:create",
        "preview": "email_marketing.template:read",
    }

    def get_queryset(self) -> Any:
        tenant = self.resolved_tenant_id()
        if tenant is None:
            return EmailTemplate.objects.none()
        return EmailTemplate.objects.for_tenant(tenant).filter(is_deleted=False)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered(self.get_queryset()), TemplateListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(TemplateDetailSerializer(self.get_object()).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = TemplateCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class.create_template(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data,
            self.mutation_idempotency_key(),
        )
        return Response(
            TemplateDetailSerializer(value).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        serializer = TemplateUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = self.service_class.update_template(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data,
        )
        return Response(TemplateDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        self.service_class.archive_record(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _lifecycle(self, command: str) -> Response:
        self.get_object()
        serializer = CampaignTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = getattr(self.service_class, f"{command}_template")(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["idempotency_key"],
        )
        return Response(TemplateDetailSerializer(value).data)

    @action(detail=True, methods=["post"])
    def activate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._lifecycle("activate")

    @action(detail=True, methods=["post"])
    def archive(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._lifecycle("archive")

    @action(detail=True, methods=["post"])
    def clone(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = TemplateCloneSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = self.service_class.clone_template(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["new_code"],
        )
        return Response(
            TemplateDetailSerializer(value).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def preview(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = TemplatePreviewSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        rendered = self.service_class.render_preview(
            self.tenant_id(),
            self.kwargs["pk"],
            serializer.validated_data["sample_data"],
        )
        return Response(RenderedEmailSerializer(rendered).data)


class CampaignRecipientViewSet(EmailMarketingViewSet):
    filterset_class = RecipientFilterSet
    action_permissions = {
        "list": "email_marketing.recipient:read",
        "retrieve": "email_marketing.recipient:read",
        "retry": "email_marketing.recipient:retry",
    }

    def get_queryset(self) -> Any:
        tenant = self.resolved_tenant_id()
        if tenant is None:
            return CampaignRecipient.objects.none()
        return CampaignRecipient.objects.for_tenant(tenant).select_related("campaign", "consent_record")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered(self.get_queryset()), RecipientListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(RecipientDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def retry(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = RecipientRetrySerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        job = DeliveryService.retry_recipient(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["idempotency_key"],
        )
        return Response(
            AsyncJobSummarySerializer(job).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DeliveryAttemptViewSet(EmailMarketingViewSet):
    filterset_class = DeliveryFilterSet
    action_permissions = {
        "list": "email_marketing.delivery:read",
        "retrieve": "email_marketing.delivery:read",
    }

    def get_queryset(self) -> Any:
        tenant = self.resolved_tenant_id()
        if tenant is None:
            return DeliveryAttempt.objects.none()
        return DeliveryAttempt.objects.for_tenant(tenant).select_related("recipient", "recipient__campaign")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered(self.get_queryset()), DeliveryAttemptListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(DeliveryAttemptDetailSerializer(self.get_object()).data)


class SuppressionEntryViewSet(EmailMarketingViewSet):
    filterset_class = SuppressionFilterSet
    action_permissions = {
        "list": "email_marketing.suppression:read",
        "retrieve": "email_marketing.suppression:read",
        "create": "email_marketing.suppression:manage",
        "deactivate": "email_marketing.suppression:manage",
    }

    def get_queryset(self) -> Any:
        tenant = self.resolved_tenant_id()
        if tenant is None:
            return SuppressionEntry.objects.none()
        return SuppressionEntry.objects.for_tenant(tenant).select_related("evidence_event")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered(self.get_queryset()), SuppressionListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(SuppressionDetailSerializer(self.get_object()).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = SuppressionCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ComplianceService.suppress(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data,
            self.mutation_idempotency_key(),
        )
        return Response(
            SuppressionDetailSerializer(value).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = SuppressionDeactivateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ComplianceService.deactivate_suppression(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["reason"],
        )
        return Response(SuppressionDetailSerializer(value).data)


class ConsentRecordViewSet(EmailMarketingViewSet):
    filterset_class = ConsentFilterSet
    action_permissions = {
        "list": "email_marketing.consent:read",
        "retrieve": "email_marketing.consent:read",
        "create": "email_marketing.consent:record",
        "revoke": "email_marketing.consent:revoke",
    }

    def get_queryset(self) -> Any:
        tenant = self.resolved_tenant_id()
        if tenant is None:
            return ConsentRecord.objects.none()
        return ConsentRecord.objects.for_tenant(tenant).select_related("supersedes")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.filtered(self.get_queryset()), ConsentListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(ConsentDetailSerializer(self.get_object()).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ConsentCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ComplianceService.record_consent(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data,
            {
                "remote_addr": str(self.request.META.get("REMOTE_ADDR", "")),
                "user_agent": str(self.request.META.get("HTTP_USER_AGENT", "")),
            },
            self.mutation_idempotency_key(),
        )
        return Response(ConsentDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def revoke(self, request: object) -> Response:
        del request
        serializer = ConsentRevokeSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        value = ComplianceService.revoke_consent(
            self.tenant_id(),
            self.actor_id(),
            data["email"],
            data["purpose"],
            data["source"],
        )
        return Response(ConsentDetailSerializer(value).data, status=status.HTTP_201_CREATED)


class ConfigurationViewSet(EmailMarketingViewSet):
    """RBAC-gated singleton configuration and immutable history surface."""

    action_permissions = {
        "current": "email_marketing.configuration:read",
        "preview": "email_marketing.configuration:read",
        "history": "email_marketing.configuration:read",
        "export_document": "email_marketing.configuration:export",
        "rollback": "email_marketing.configuration:manage",
        "import_document": "email_marketing.configuration:manage",
    }

    def get_permissions(self) -> list:
        if self.action == "current" and self.request.method == "PUT":
            self.action_permissions = {
                **self.action_permissions,
                "current": "email_marketing.configuration:manage",
            }
        return super().get_permissions()

    def get_queryset(self) -> Any:
        tenant = self.resolved_tenant_id()
        if tenant is None:
            return EmailMarketingConfiguration.objects.none()
        return EmailMarketingConfiguration.objects.for_tenant(tenant)

    @action(detail=False, methods=["get", "put"])
    def current(self, request: object) -> Response:
        if self.request.method == "GET":
            return Response(ConfigurationSerializer(ConfigurationService.current(self.tenant_id())).data)
        serializer = ConfigurationUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ConfigurationService.update(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data["document"],
            serializer.validated_data["expected_version"],
        )
        return Response(ConfigurationSerializer(value).data)

    @action(detail=False, methods=["post"])
    def preview(self, request: object) -> Response:
        del request
        serializer = ConfigurationPreviewSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(ConfigurationService.preview(self.tenant_id(), serializer.validated_data["document"]))

    @action(detail=False, methods=["get"])
    def history(self, request: object) -> Response:
        del request
        versions = ConfigurationService.history(self.tenant_id())
        return Response(ConfigurationVersionSerializer(versions, many=True).data)

    @action(detail=False, methods=["post"])
    def rollback(self, request: object) -> Response:
        del request
        serializer = ConfigurationRollbackSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ConfigurationService.rollback(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data["target_version"],
            serializer.validated_data["expected_version"],
        )
        return Response(ConfigurationSerializer(value).data)

    @action(detail=False, methods=["post"], url_path="import-document")
    def import_document(self, request: object) -> Response:
        del request
        serializer = ConfigurationUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ConfigurationService.update(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data["document"],
            serializer.validated_data["expected_version"],
            change_type="imported",
        )
        return Response(ConfigurationSerializer(value).data)

    @action(detail=False, methods=["get"], url_path="export-document")
    def export_document(self, request: object) -> Response:
        del request
        value = ConfigurationService.current(self.tenant_id())
        return Response(ConfigurationSerializer(value).data)


class ProviderEventAPIView(GovernedAPIViewMixin, APIView):
    permission_classes = (ProviderWebhookPermission,)
    throttle_classes = (PublicEmailThrottle,)

    def post(self, request: object) -> Response:
        gateway_key = str(getattr(request, "gateway_key", ""))
        try:
            verifier = get_provider_event_verifier(gateway_key)
        except AdapterNotRegistered as exc:
            raise PermissionDenied("No verifier is registered for this provider account.") from exc
        verified = verifier.verify(dict(self.request.headers), bytes(self.request.body))
        job = DeliveryService.enqueue_verified_provider_event(
            self.request.tenant_id,
            gateway_key,
            verified,
        )
        return Response(
            AsyncJobSummarySerializer(job).data,
            status=status.HTTP_202_ACCEPTED,
        )


def _signed_tenant(token: str, salt: str, token_kind: str) -> UUID:
    try:
        unsigned_age_payload = signing.loads(token, salt=salt)
        tenant = UUID(str(unsigned_age_payload["tenant_id"]))
        token_config = get_runtime_configuration(tenant).document["tokens"]
        configured_age = (
            token_config["unsubscribe_token_days"]
            if token_kind == "unsubscribe"
            else token_config["tracking_token_days"]
        )
        payload = signing.loads(token, salt=salt, max_age=configured_age * 86_400)
        verified_tenant = UUID(str(payload["tenant_id"]))
        if verified_tenant != tenant:
            raise signing.BadSignature("Tenant mismatch.")
        return tenant
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise NotFound("The signed token is invalid or expired.") from exc


class PublicUnsubscribeAPIView(GovernedAPIViewMixin, APIView):
    authentication_classes: tuple = ()
    permission_classes: tuple = ()
    throttle_classes = (PublicEmailThrottle,)

    def initial(self, request: object, *args: object, **kwargs: object) -> None:
        token = str(getattr(request, "data", {}).get("token", ""))
        request.tenant_id = _signed_tenant(token, "email_marketing.unsubscribe", "unsubscribe")
        super().initial(request, *args, **kwargs)

    def post(self, request: object) -> Response:
        token = str(self.request.data.get("token", ""))
        tenant = _signed_tenant(token, "email_marketing.unsubscribe", "unsubscribe")
        value = DeliveryService.unsubscribe(tenant, token, timezone.now())
        response = PublicUnsubscribeResponseSerializer({"suppression_id": value.id, "status": "unsubscribed"})
        return Response(response.data)


class TrackingOpenAPIView(APIView):
    authentication_classes: tuple = ()
    permission_classes: tuple = ()
    throttle_classes = (PublicEmailThrottle,)
    renderer_classes: tuple = ()
    pixel = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
        b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
        b"\x00\x00\x02\x02D\x01\x00;"
    )

    def initial(self, request: object, *args: object, **kwargs: object) -> None:
        token = str(kwargs.get("token", ""))
        request.tenant_id = _signed_tenant(token, "email_marketing.tracking", "tracking")
        super().initial(request, *args, **kwargs)

    def get(self, request: object, token: str) -> HttpResponse:
        del request
        tenant = _signed_tenant(token, "email_marketing.tracking", "tracking")
        DeliveryService.record_open(tenant, token)
        response = HttpResponse(self.pixel, content_type="image/gif")
        response["Cache-Control"] = "no-store, private"
        return response


class TrackingClickAPIView(APIView):
    authentication_classes: tuple = ()
    permission_classes: tuple = ()
    throttle_classes = (PublicEmailThrottle,)

    def initial(self, request: object, *args: object, **kwargs: object) -> None:
        token = str(kwargs.get("token", ""))
        request.tenant_id = _signed_tenant(token, "email_marketing.tracking", "tracking")
        super().initial(request, *args, **kwargs)

    def get(self, request: object, token: str) -> HttpResponseRedirect:
        tenant = _signed_tenant(token, "email_marketing.tracking", "tracking")
        destination = str(self.request.query_params.get("destination", ""))
        _, url = DeliveryService.record_click(tenant, token, destination)
        return HttpResponseRedirect(url)


__all__ = [
    "CampaignRecipientViewSet",
    "ConfigurationViewSet",
    "ConsentRecordViewSet",
    "DeliveryAttemptViewSet",
    "EmailCampaignViewSet",
    "EmailTemplateViewSet",
    "ProviderEventAPIView",
    "PublicUnsubscribeAPIView",
    "SuppressionEntryViewSet",
    "TrackingClickAPIView",
    "TrackingOpenAPIView",
]
