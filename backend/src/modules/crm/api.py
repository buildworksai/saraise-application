"""
DRF ViewSets for CRM module.

Provides REST API endpoints for all models.
"""

import uuid
from datetime import date, timedelta

from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_id, get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import (
    Account,
    Activity,
    Contact,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStatus,
)
from .serializers import (
    AccountCreateSerializer,
    AccountHierarchySerializer,
    AccountSerializer,
    AccountUpdateSerializer,
    ActivityCreateSerializer,
    ActivitySerializer,
    ActivityUpdateSerializer,
    AIPredictionSerializer,
    CloseLostRequestSerializer,
    CloseWonRequestSerializer,
    ContactCreateSerializer,
    ContactSerializer,
    ContactUpdateSerializer,
    ForecastSerializer,
    LeadCreateSerializer,
    LeadScoringResponseSerializer,
    LeadSerializer,
    LeadUpdateSerializer,
    OpportunityCreateFromLeadSerializer,
    OpportunityCreateSerializer,
    OpportunitySerializer,
    OpportunityUpdateSerializer,
    WinRateSerializer,
)
from .pagination import CRMResultsSetPagination
from .services import (
    AccountService,
    ActivityService,
    ContactService,
    ForecastingService,
    IntegrationService,
    LeadService,
    OpportunityService,
)


# ===== Lead ViewSet =====


class LeadViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Lead CRUD operations.

    Endpoints:
    - GET /api/v1/crm/leads/ - List all leads
    - POST /api/v1/crm/leads/ - Create lead
    - GET /api/v1/crm/leads/{id}/ - Get lead detail
    - PATCH /api/v1/crm/leads/{id}/ - Update lead
    - DELETE /api/v1/crm/leads/{id}/ - Soft delete lead
    - POST /api/v1/crm/leads/{id}/convert/ - Convert lead to opportunity
    - POST /api/v1/crm/leads/{id}/ai-score/ - Run AI scoring
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]
    pagination_class = CRMResultsSetPagination

    def get_queryset(self):
        """Filter leads by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Lead.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Lead.objects.none()

        queryset = Lead.objects.filter(tenant_id=tenant_id, is_deleted=False)

        # Filtering
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        owner_id_filter = self.request.query_params.get("owner_id")
        if owner_id_filter:
            try:
                owner_id = uuid.UUID(owner_id_filter)
                queryset = queryset.filter(owner_id=owner_id)
            except (ValueError, TypeError):
                pass

        score_min = self.request.query_params.get("score_min")
        if score_min:
            try:
                queryset = queryset.filter(score__gte=int(score_min))
            except ValueError:
                pass

        # Search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(first_name__icontains=search)
                | models.Q(last_name__icontains=search)
                | models.Q(company__icontains=search)
                | models.Q(email__icontains=search)
            )

        # Ordering (default: -created_at)
        ordering = self.request.query_params.get("ordering", "-created_at")
        # Validate ordering field to prevent SQL injection
        allowed_ordering_fields = [
            "created_at", "-created_at",
            "updated_at", "-updated_at",
            "score", "-score",
            "last_name", "-last_name",
            "company", "-company",
        ]
        if ordering in allowed_ordering_fields:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return LeadCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return LeadUpdateSerializer
        return LeadSerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        # Use service to create lead
        lead_service = LeadService()
        lead = lead_service.create_lead(
            tenant_id=tenant_id,
            data=serializer.validated_data,
            created_by=user_id_str,
        )

        # Return serialized lead
        serializer.instance = lead

    def perform_update(self, serializer):
        """Update lead using service."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        lead_service = LeadService()
        updated_lead = lead_service.update_lead(
            lead_id=self.get_object().id,
            tenant_id=tenant_id,
            data=serializer.validated_data,
        )
        serializer.instance = updated_lead

    def destroy(self, request, *args, **kwargs):
        """Soft delete lead."""
        tenant_id_str = get_user_tenant_id(request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        lead = self.get_object()
        LeadService().delete_lead(lead_id=lead.id, tenant_id=tenant_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        """Convert lead to opportunity."""
        lead = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)
        user_id_str = get_user_id(request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        serializer = OpportunityCreateFromLeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        integration_service = IntegrationService()
        result = integration_service.convert_lead_to_opportunity(
            lead_id=lead.id,
            tenant_id=tenant_id,
            opportunity_data=serializer.validated_data,
            user_id=user_id_str,
        )

        opportunity_serializer = OpportunitySerializer(result["opportunity"])
        return Response(opportunity_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="ai-score")
    def ai_score(self, request, pk=None):
        """Run AI scoring on lead."""
        lead = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        lead_service = LeadService()
        updated_lead = lead_service.score_lead(lead_id=lead.id, tenant_id=tenant_id)

        response_data = {
            "score": updated_lead.score,
            "grade": updated_lead.grade,
            "bant_qualification": updated_lead.metadata.get("bant_qualification", {}),
        }

        serializer = LeadScoringResponseSerializer(response_data)
        return Response(serializer.data)


# ===== Account ViewSet =====


class AccountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Account CRUD operations.

    Endpoints:
    - GET /api/v1/crm/accounts/ - List all accounts
    - POST /api/v1/crm/accounts/ - Create account
    - GET /api/v1/crm/accounts/{id}/ - Get account detail
    - PATCH /api/v1/crm/accounts/{id}/ - Update account
    - DELETE /api/v1/crm/accounts/{id}/ - Soft delete account
    - GET /api/v1/crm/accounts/{id}/hierarchy/ - Get account hierarchy
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]
    pagination_class = CRMResultsSetPagination

    def get_queryset(self):
        """Filter accounts by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Account.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Account.objects.none()

        queryset = Account.objects.filter(tenant_id=tenant_id, is_deleted=False)

        # Filtering
        account_type_filter = self.request.query_params.get("account_type")
        if account_type_filter:
            queryset = queryset.filter(account_type=account_type_filter)

        owner_id_filter = self.request.query_params.get("owner_id")
        if owner_id_filter:
            try:
                owner_id = uuid.UUID(owner_id_filter)
                queryset = queryset.filter(owner_id=owner_id)
            except (ValueError, TypeError):
                pass

        # Search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)

        # Ordering (default: -created_at)
        ordering = self.request.query_params.get("ordering", "-created_at")
        allowed_ordering_fields = [
            "created_at", "-created_at",
            "updated_at", "-updated_at",
            "name", "-name",
        ]
        if ordering in allowed_ordering_fields:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return AccountCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return AccountUpdateSerializer
        return AccountSerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        account_service = AccountService()
        account = account_service.create_account(
            tenant_id=tenant_id,
            data=serializer.validated_data,
            created_by=user_id_str,
        )
        serializer.instance = account

    def perform_update(self, serializer):
        """Update account using service."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        account_service = AccountService()
        updated_account = account_service.update_account(
            account_id=self.get_object().id,
            tenant_id=tenant_id,
            data=serializer.validated_data,
        )
        serializer.instance = updated_account

    def destroy(self, request, *args, **kwargs):
        """Soft delete account."""
        tenant_id_str = get_user_tenant_id(request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        account = self.get_object()
        AccountService().delete_account(account_id=account.id, tenant_id=tenant_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def hierarchy(self, request, pk=None):
        """Get account hierarchy tree."""
        account = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        account_service = AccountService()
        hierarchy = account_service.get_account_hierarchy(account_id=account.id, tenant_id=tenant_id)

        serializer = AccountHierarchySerializer(hierarchy)
        return Response(serializer.data)


# ===== Contact ViewSet =====


class ContactViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Contact CRUD operations.

    Endpoints:
    - GET /api/v1/crm/contacts/ - List all contacts
    - POST /api/v1/crm/contacts/ - Create contact
    - GET /api/v1/crm/contacts/{id}/ - Get contact detail
    - PATCH /api/v1/crm/contacts/{id}/ - Update contact
    - DELETE /api/v1/crm/contacts/{id}/ - Soft delete contact
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]
    pagination_class = CRMResultsSetPagination

    def get_queryset(self):
        """Filter contacts by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Contact.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Contact.objects.none()

        queryset = Contact.objects.filter(tenant_id=tenant_id, is_deleted=False)

        # Filtering
        account_id_filter = self.request.query_params.get("account_id")
        if account_id_filter:
            try:
                account_id = uuid.UUID(account_id_filter)
                queryset = queryset.filter(account_id=account_id)
            except (ValueError, TypeError):
                pass

        owner_id_filter = self.request.query_params.get("owner_id")
        if owner_id_filter:
            try:
                owner_id = uuid.UUID(owner_id_filter)
                queryset = queryset.filter(owner_id=owner_id)
            except (ValueError, TypeError):
                pass

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return ContactCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return ContactUpdateSerializer
        return ContactSerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        contact_service = ContactService()
        contact = contact_service.create_contact(
            tenant_id=tenant_id,
            data=serializer.validated_data,
            created_by=user_id_str,
        )
        serializer.instance = contact

    def perform_update(self, serializer):
        """Update contact using service."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        contact_service = ContactService()
        updated_contact = contact_service.update_contact(
            contact_id=self.get_object().id,
            tenant_id=tenant_id,
            data=serializer.validated_data,
        )
        serializer.instance = updated_contact

    def destroy(self, request, *args, **kwargs):
        """Soft delete contact."""
        tenant_id_str = get_user_tenant_id(request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        contact = self.get_object()
        ContactService().delete_contact(contact_id=contact.id, tenant_id=tenant_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ===== Opportunity ViewSet =====


class OpportunityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Opportunity CRUD operations.

    Endpoints:
    - GET /api/v1/crm/opportunities/ - List all opportunities
    - POST /api/v1/crm/opportunities/ - Create opportunity
    - GET /api/v1/crm/opportunities/{id}/ - Get opportunity detail
    - PATCH /api/v1/crm/opportunities/{id}/ - Update opportunity
    - DELETE /api/v1/crm/opportunities/{id}/ - Soft delete opportunity
    - POST /api/v1/crm/opportunities/{id}/close-won/ - Close as won
    - POST /api/v1/crm/opportunities/{id}/close-lost/ - Close as lost
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]
    pagination_class = CRMResultsSetPagination

    def get_queryset(self):
        """Filter opportunities by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Opportunity.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Opportunity.objects.none()

        queryset = Opportunity.objects.filter(tenant_id=tenant_id, is_deleted=False)

        # Filtering
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        stage_filter = self.request.query_params.get("stage")
        if stage_filter:
            queryset = queryset.filter(stage=stage_filter)

        owner_id_filter = self.request.query_params.get("owner_id")
        if owner_id_filter:
            try:
                owner_id = uuid.UUID(owner_id_filter)
                queryset = queryset.filter(owner_id=owner_id)
            except (ValueError, TypeError):
                pass

        account_id_filter = self.request.query_params.get("account_id")
        if account_id_filter:
            try:
                account_id = uuid.UUID(account_id_filter)
                queryset = queryset.filter(account_id=account_id)
            except (ValueError, TypeError):
                pass

        # Ordering (default: -created_at)
        ordering = self.request.query_params.get("ordering", "-created_at")
        allowed_ordering_fields = [
            "created_at", "-created_at",
            "updated_at", "-updated_at",
            "close_date", "-close_date",
            "amount", "-amount",
            "name", "-name",
        ]
        if ordering in allowed_ordering_fields:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return OpportunityCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return OpportunityUpdateSerializer
        return OpportunitySerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        opportunity_service = OpportunityService()
        opportunity = opportunity_service.create_opportunity(
            tenant_id=tenant_id,
            data=serializer.validated_data,
            created_by=user_id_str,
        )
        serializer.instance = opportunity

    def perform_update(self, serializer):
        """Update opportunity using service."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        opportunity_service = OpportunityService()
        updated_opportunity = opportunity_service.update_opportunity(
            opportunity_id=self.get_object().id,
            tenant_id=tenant_id,
            data=serializer.validated_data,
        )
        serializer.instance = updated_opportunity

    def destroy(self, request, *args, **kwargs):
        """Soft delete opportunity."""
        tenant_id_str = get_user_tenant_id(request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        opportunity = self.get_object()
        OpportunityService().delete_opportunity(opportunity_id=opportunity.id, tenant_id=tenant_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="close-won")
    def close_won(self, request, pk=None):
        """Close opportunity as won."""
        opportunity = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)
        user_id_str = get_user_id(request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        serializer = CloseWonRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        opportunity_service = OpportunityService()
        updated_opportunity = opportunity_service.close_won(
            opportunity_id=opportunity.id,
            tenant_id=tenant_id,
            user_id=user_id_str,
        )

        response_serializer = OpportunitySerializer(updated_opportunity)
        return Response(response_serializer.data)

    @action(detail=True, methods=["post"], url_path="close-lost")
    def close_lost(self, request, pk=None):
        """Close opportunity as lost."""
        opportunity = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)
        user_id_str = get_user_id(request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        serializer = CloseLostRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        opportunity_service = OpportunityService()
        updated_opportunity = opportunity_service.close_lost(
            opportunity_id=opportunity.id,
            tenant_id=tenant_id,
            loss_reason=serializer.validated_data["loss_reason"],
            user_id=user_id_str,
        )

        response_serializer = OpportunitySerializer(updated_opportunity)
        return Response(response_serializer.data)


# ===== Activity ViewSet =====


class ActivityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Activity CRUD operations.

    Endpoints:
    - GET /api/v1/crm/activities/ - List all activities
    - POST /api/v1/crm/activities/ - Create activity
    - GET /api/v1/crm/activities/{id}/ - Get activity detail
    - PATCH /api/v1/crm/activities/{id}/ - Update activity
    - DELETE /api/v1/crm/activities/{id}/ - Soft delete activity
    - POST /api/v1/crm/activities/{id}/complete/ - Mark as complete
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]
    pagination_class = CRMResultsSetPagination

    def get_queryset(self):
        """Filter activities by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Activity.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Activity.objects.none()

        queryset = Activity.objects.filter(tenant_id=tenant_id, is_deleted=False)

        # Filtering
        related_to_type = self.request.query_params.get("related_to_type")
        if related_to_type:
            queryset = queryset.filter(related_to_type=related_to_type)

        related_to_id = self.request.query_params.get("related_to_id")
        if related_to_id:
            try:
                related_id = uuid.UUID(related_to_id)
                queryset = queryset.filter(related_to_id=related_id)
            except (ValueError, TypeError):
                pass

        owner_id_filter = self.request.query_params.get("owner_id")
        if owner_id_filter:
            try:
                owner_id = uuid.UUID(owner_id_filter)
                queryset = queryset.filter(owner_id=owner_id)
            except (ValueError, TypeError):
                pass

        # Ordering (default: -created_at)
        ordering = self.request.query_params.get("ordering", "-created_at")
        allowed_ordering_fields = [
            "created_at", "-created_at",
            "updated_at", "-updated_at",
            "due_date", "-due_date",
        ]
        if ordering in allowed_ordering_fields:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return ActivityCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return ActivityUpdateSerializer
        return ActivitySerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)

        if not tenant_id_str:
            raise DRFValidationError("Tenant ID required")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        activity_service = ActivityService()
        activity = activity_service.create_activity(
            tenant_id=tenant_id,
            data=serializer.validated_data,
            created_by=user_id_str,
        )
        serializer.instance = activity

    def perform_update(self, serializer):
        """Update activity using service."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        activity_service = ActivityService()
        updated_activity = activity_service.update_activity(
            activity_id=self.get_object().id,
            tenant_id=tenant_id,
            data=serializer.validated_data,
        )
        serializer.instance = updated_activity

    def destroy(self, request, *args, **kwargs):
        """Soft delete activity."""
        tenant_id_str = get_user_tenant_id(request.user)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        activity = self.get_object()
        ActivityService().delete_activity(activity_id=activity.id, tenant_id=tenant_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Mark activity as complete."""
        activity = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise DRFValidationError("Invalid tenant ID")

        activity_service = ActivityService()
        updated_activity = activity_service.complete_activity(
            activity_id=activity.id, tenant_id=tenant_id
        )

        serializer = ActivitySerializer(updated_activity)
        return Response(serializer.data)


# ===== Forecasting ViewSet =====


class ForecastingViewSet(viewsets.ViewSet):
    """
    ViewSet for forecasting and analytics.

    Endpoints:
    - GET /api/v1/crm/forecasting/pipeline/ - Get weighted pipeline
    - GET /api/v1/crm/forecasting/win-rate/ - Get win rate
    - GET /api/v1/crm/forecasting/ai-predict/ - Get AI prediction
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    @action(detail=False, methods=["get"], url_path="pipeline")
    def pipeline(self, request):
        """Get weighted pipeline forecast."""
        tenant_id_str = get_user_tenant_id(request.user)
        if not tenant_id_str:
            return Response({"error": "Invalid tenant"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Response({"error": "Invalid tenant ID"}, status=status.HTTP_400_BAD_REQUEST)

        owner_id = request.query_params.get("owner_id")
        owner_uuid = None
        if owner_id:
            try:
                owner_uuid = uuid.UUID(owner_id)
            except (ValueError, TypeError):
                pass

        period_days = int(request.query_params.get("period", 90))

        forecasting_service = ForecastingService()
        result = forecasting_service.get_weighted_pipeline(
            tenant_id=tenant_id, owner_id=owner_uuid, period_days=period_days
        )

        serializer = ForecastSerializer(result)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="win-rate")
    def win_rate(self, request):
        """Get historical win rate."""
        tenant_id_str = get_user_tenant_id(request.user)
        if not tenant_id_str:
            return Response({"error": "Invalid tenant"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Response({"error": "Invalid tenant ID"}, status=status.HTTP_400_BAD_REQUEST)

        owner_id = request.query_params.get("owner_id")
        owner_uuid = None
        if owner_id:
            try:
                owner_uuid = uuid.UUID(owner_id)
            except (ValueError, TypeError):
                pass

        period_days = int(request.query_params.get("period", 90))

        forecasting_service = ForecastingService()
        result = forecasting_service.get_win_rate(
            tenant_id=tenant_id, owner_id=owner_uuid, period_days=period_days
        )

        serializer = WinRateSerializer(result)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="ai-predict")
    def ai_predict(self, request):
        """Get AI-predicted revenue."""
        tenant_id_str = get_user_tenant_id(request.user)
        if not tenant_id_str:
            return Response({"error": "Invalid tenant"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Response({"error": "Invalid tenant ID"}, status=status.HTTP_400_BAD_REQUEST)

        period_days = int(request.query_params.get("period", 90))

        forecasting_service = ForecastingService()
        result = forecasting_service.get_ai_prediction(tenant_id=tenant_id, period_days=period_days)

        serializer = AIPredictionSerializer(result)
        return Response(serializer.data)
