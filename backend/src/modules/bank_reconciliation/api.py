"""Governed v2 HTTP controllers for bank reconciliation."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db.models import Count, Max, Q, QuerySet
from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api.profile import GovernedAPIViewMixin
from src.core.auth_utils import get_user_tenant_id

from .health import get_module_health
from .models import (
    BankAccount,
    BankStatement,
    BankStatementImport,
    BankTransaction,
    MatchingRule,
    ReconciliationMatch,
    ReconciliationSession,
)
from .permissions import ActionAccessMixin
from .serializers import (
    AsyncJobSummarySerializer,
    BankAccountCreateSerializer,
    BankAccountDetailSerializer,
    BankAccountListSerializer,
    BankAccountUpdateSerializer,
    CandidateGenerationSerializer,
    ImportCancelSerializer,
    ImportRetrySerializer,
    ManualMatchCreateSerializer,
    ManualStatementCreateSerializer,
    ManualTransactionCreateSerializer,
    ManualTransactionUpdateSerializer,
    MatchConfirmSerializer,
    MatchingRuleCreateSerializer,
    MatchingRuleDetailSerializer,
    MatchingRuleListSerializer,
    MatchingRuleUpdateSerializer,
    MatchRejectSerializer,
    MatchReverseSerializer,
    ReconciliationCreateSerializer,
    ReconciliationDetailSerializer,
    ReconciliationFinalizeSerializer,
    ReconciliationListSerializer,
    ReconciliationMatchDetailSerializer,
    ReconciliationReturnToWorkSerializer,
    ReconciliationStartSerializer,
    ReconciliationSubmitReviewSerializer,
    ReconciliationVoidSerializer,
    StatementDetailSerializer,
    StatementImportCreateSerializer,
    StatementImportDetailSerializer,
    StatementImportListSerializer,
    StatementListSerializer,
    StatementVoidSerializer,
    TransactionDetailSerializer,
    TransactionExclusionSerializer,
    TransactionListSerializer,
)
from .services import (
    BankAccountService,
    MatchingRuleService,
    ReconciliationService,
    StatementImportService,
    StatementService,
)


class TenantGovernedViewSet(GovernedAPIViewMixin, ActionAccessMixin, viewsets.GenericViewSet):
    """Resolve the trusted tenant and actor projections once per request."""

    def tenant_id(self) -> UUID:
        raw = get_user_tenant_id(self.request.user)
        try:
            value = UUID(str(raw))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("Authenticated identity has no valid tenant.") from exc
        self.request.tenant_id = value
        return value

    def actor_id(self) -> UUID:
        raw = getattr(self.request.user, "id", None)
        if raw is None:
            raise PermissionDenied("Authenticated identity has no valid actor.")
        try:
            return UUID(str(raw))
        except (TypeError, ValueError, AttributeError):
            return uuid5(NAMESPACE_URL, f"saraise:user:{raw}")

    def paginated(self, queryset: QuerySet[Any], serializer: type, **context: object) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required for every collection.")
        return self.get_paginated_response(serializer(page, many=True, context=context).data)

    def object_or_404(self, queryset: QuerySet[Any]) -> Any:
        value = queryset.filter(pk=self.kwargs["pk"]).first()
        if value is None:
            raise NotFound()
        return value


def _ordering(request: Any, allowed: set[str], default: str) -> str:
    value = str(request.query_params.get("ordering") or default)
    if value.lstrip("-") not in allowed:
        raise ValidationError({"ordering": "Unsupported ordering field."})
    return value


class BankAccountViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "bank_reconciliation.account:read",
        "retrieve": "bank_reconciliation.account:read",
        "create": "bank_reconciliation.account:create",
        "partial_update": "bank_reconciliation.account:update",
        "destroy": "bank_reconciliation.account:archive",
    }

    def get_queryset(self) -> QuerySet[BankAccount]:
        qs = BankAccount.objects.for_tenant(self.tenant_id()).annotate(
            statement_count=Count("statements", distinct=True),
            reconciliation_count=Count("reconciliation_sessions", distinct=True),
            unreconciled_count=Count("statements", filter=Q(statements__is_reconciled=False), distinct=True),
            active_session_count=Count(
                "reconciliation_sessions",
                filter=Q(reconciliation_sessions__status__in=("draft", "in_progress", "review")),
                distinct=True,
            ),
            last_statement_date=Max("statements__period_end"),
        )
        for field in ("is_active", "account_type", "currency"):
            if self.request.query_params.get(field) not in (None, ""):
                qs = qs.filter(**{field: self.request.query_params[field]})
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(account_name__icontains=search)
                | Q(bank_name__icontains=search)
                | Q(account_number_last4__icontains=str(search)[-4:])
            )
        return qs.order_by(_ordering(self.request, {"bank_name", "account_name", "created_at"}, "bank_name"), "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), BankAccountListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(BankAccountDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = BankAccountCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = BankAccountService.create(self.tenant_id(), self.actor_id(), serializer.validated_data)
        return Response(BankAccountDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.object_or_404(self.get_queryset())
        serializer = BankAccountUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = BankAccountService.update(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data
        )
        return Response(BankAccountDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.object_or_404(self.get_queryset())
        BankAccountService.archive(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)


class BankStatementViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "bank_reconciliation.statement:read",
        "retrieve": "bank_reconciliation.statement:read",
        "create": "bank_reconciliation.statement:create",
        "void": "bank_reconciliation.statement:void",
        "transactions": "bank_reconciliation.transaction:read",
    }

    def get_queryset(self) -> QuerySet[BankStatement]:
        qs = (
            BankStatement.objects.for_tenant(self.tenant_id())
            .select_related("bank_account", "statement_import")
            .annotate(transaction_count=Count("transactions"))
        )
        account = self.request.query_params.get("account") or self.request.query_params.get("bank_account")
        if account:
            qs = qs.filter(bank_account_id=account)
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        period_from = self.request.query_params.get("period_from") or self.request.query_params.get(
            "period_start_after"
        )
        period_to = self.request.query_params.get("period_to") or self.request.query_params.get("period_end_before")
        if period_from:
            qs = qs.filter(period_end__gte=period_from)
        if period_to:
            qs = qs.filter(period_start__lte=period_to)
        variance = self.request.query_params.get("has_variance")
        if variance == "true":
            qs = qs.exclude(balance_variance=0)
        if variance == "false":
            qs = qs.filter(balance_variance=0)
        return qs.order_by(
            _ordering(self.request, {"period_end", "created_at"}, "-period_end"),
            "id",
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), StatementListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(StatementDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ManualStatementCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = StatementService.create_manual_statement(self.tenant_id(), self.actor_id(), serializer.validated_data)
        return Response(StatementDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="void")
    def void(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = StatementVoidSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = StatementService.void_statement(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            serializer.validated_data["reason"],
            serializer.validated_data["idempotency_key"],
        )
        return Response(StatementDetailSerializer(value).data)

    def get_permissions(self) -> list[object]:
        if getattr(self, "action", "") == "transactions" and self.request.method == "POST":
            self.action_permissions = {
                **type(self).action_permissions,
                "transactions": "bank_reconciliation.transaction:create",
            }
        return super().get_permissions()

    @action(detail=True, methods=["get", "post"], url_path="transactions")
    def transactions(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        if self.request.method == "POST":
            serializer = ManualTransactionCreateSerializer(data=self.request.data)
            serializer.is_valid(raise_exception=True)
            value = StatementService.add_manual_transaction(
                self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data
            )
            return Response(TransactionDetailSerializer(value).data, status=status.HTTP_201_CREATED)
        values = StatementService.list_transactions(self.tenant_id(), self.kwargs["pk"], self.request.query_params)
        return self.paginated(values.select_related("bank_statement"), TransactionListSerializer)


class BankTransactionViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "bank_reconciliation.transaction:read",
        "retrieve": "bank_reconciliation.transaction:read",
        "partial_update": "bank_reconciliation.transaction:update",
        "exclude": "bank_reconciliation.transaction:update",
        "restore": "bank_reconciliation.transaction:update",
    }

    def get_queryset(self) -> QuerySet[BankTransaction]:
        qs = BankTransaction.objects.for_tenant(self.tenant_id()).select_related(
            "bank_statement", "bank_statement__statement_import"
        )
        statement_id = self.request.query_params.get("statement") or self.request.query_params.get("bank_statement")
        if statement_id:
            qs = qs.filter(bank_statement_id=statement_id)
        account_id = self.request.query_params.get("account") or self.request.query_params.get("bank_account")
        if account_id:
            qs = qs.filter(bank_statement__bank_account_id=account_id)
        for param in ("match_status", "transaction_type"):
            if self.request.query_params.get(param):
                qs = qs.filter(**{param: self.request.query_params[param]})
        date_from = self.request.query_params.get("date_from") or self.request.query_params.get("date_after")
        date_to = self.request.query_params.get("date_to") or self.request.query_params.get("date_before")
        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(description__icontains=search)
                | Q(reference_number__icontains=search)
                | Q(counterparty_name__icontains=search)
            )
        return qs.order_by(
            _ordering(self.request, {"transaction_date", "amount"}, "-transaction_date"),
            "id",
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), TransactionListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(TransactionDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.object_or_404(self.get_queryset())
        serializer = ManualTransactionUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = StatementService.update_manual_transaction(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data
        )
        return Response(TransactionDetailSerializer(value).data)

    @action(detail=True, methods=["post"])
    def exclude(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = TransactionExclusionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            TransactionDetailSerializer(
                StatementService.exclude_transaction(
                    self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["reason"]
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def restore(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        return Response(
            TransactionDetailSerializer(
                StatementService.restore_transaction(self.tenant_id(), self.kwargs["pk"], self.actor_id())
            ).data
        )


class StatementImportViewSet(TenantGovernedViewSet):
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    action_permissions = {
        "list": "bank_reconciliation.import:read",
        "retrieve": "bank_reconciliation.import:read",
        "create": "bank_reconciliation.import:create",
        "retry": "bank_reconciliation.import:retry",
        "cancel": "bank_reconciliation.import:cancel",
    }
    action_quotas = {"create": "bank_reconciliation.imports", "retry": "bank_reconciliation.imports"}

    def get_queryset(self) -> QuerySet[BankStatementImport]:
        qs = BankStatementImport.objects.for_tenant(self.tenant_id()).select_related("bank_account")
        account_id = self.request.query_params.get("account") or self.request.query_params.get("bank_account")
        file_format = self.request.query_params.get("format") or self.request.query_params.get("file_format")
        if account_id:
            qs = qs.filter(bank_account_id=account_id)
        if file_format:
            qs = qs.filter(file_format=file_format)
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        created_from = self.request.query_params.get("created_from") or self.request.query_params.get("created_after")
        created_to = self.request.query_params.get("created_to") or self.request.query_params.get("created_before")
        if created_from:
            qs = qs.filter(created_at__gte=created_from)
        if created_to:
            qs = qs.filter(created_at__lte=created_to)
        return qs.order_by("-created_at", "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), StatementImportListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(StatementImportDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = StatementImportCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        key = data.pop("idempotency_key")
        accepted = StatementImportService.request_import(self.tenant_id(), self.actor_id(), data, key)
        return Response(
            {
                "import": StatementImportDetailSerializer(accepted.statement_import).data,
                "job": AsyncJobSummarySerializer(accepted.job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def retry(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = ImportRetrySerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        accepted = StatementImportService.retry_import(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["idempotency_key"]
        )
        return Response(
            {
                "import": StatementImportDetailSerializer(accepted.statement_import).data,
                "job": AsyncJobSummarySerializer(accepted.job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = ImportCancelSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            StatementImportDetailSerializer(
                StatementImportService.cancel_import(self.tenant_id(), self.kwargs["pk"], self.actor_id())
            ).data
        )


class MatchingRuleViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "bank_reconciliation.rule:read",
        "retrieve": "bank_reconciliation.rule:read",
        "create": "bank_reconciliation.rule:create",
        "partial_update": "bank_reconciliation.rule:update",
        "destroy": "bank_reconciliation.rule:delete",
        "activate": "bank_reconciliation.rule:update",
        "deactivate": "bank_reconciliation.rule:update",
    }

    def get_queryset(self) -> QuerySet[MatchingRule]:
        return (
            MatchingRule.objects.for_tenant(self.tenant_id())
            .annotate(usage_count=Count("matches"))
            .order_by("priority", "id")
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), MatchingRuleListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(MatchingRuleDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = MatchingRuleCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            MatchingRuleDetailSerializer(
                MatchingRuleService.create(self.tenant_id(), self.actor_id(), serializer.validated_data)
            ).data,
            status=201,
        )

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.object_or_404(self.get_queryset())
        serializer = MatchingRuleUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(
            MatchingRuleDetailSerializer(
                MatchingRuleService.update(
                    self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data
                )
            ).data
        )

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.object_or_404(self.get_queryset())
        MatchingRuleService.delete(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def activate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        return Response(
            MatchingRuleDetailSerializer(
                MatchingRuleService.activate(self.tenant_id(), self.kwargs["pk"], self.actor_id())
            ).data
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        return Response(
            MatchingRuleDetailSerializer(
                MatchingRuleService.deactivate(self.tenant_id(), self.kwargs["pk"], self.actor_id())
            ).data
        )


class ReconciliationViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "bank_reconciliation.reconciliation:read",
        "retrieve": "bank_reconciliation.reconciliation:read",
        "create": "bank_reconciliation.reconciliation:create",
        "start": "bank_reconciliation.reconciliation:update",
        "generate_candidates": "bank_reconciliation.match:create",
        "matches": "bank_reconciliation.match:create",
        "submit_review": "bank_reconciliation.reconciliation:review",
        "return_to_work": "bank_reconciliation.reconciliation:review",
        "finalize": "bank_reconciliation.reconciliation:finalize",
        "void": "bank_reconciliation.reconciliation:void",
        "report": "bank_reconciliation.reconciliation:export",
    }

    def get_queryset(self) -> QuerySet[ReconciliationSession]:
        qs = (
            ReconciliationSession.objects.for_tenant(self.tenant_id())
            .select_related("bank_account", "bank_statement")
            .annotate(match_count=Count("matches", distinct=True))
        )
        account_id = self.request.query_params.get("account") or self.request.query_params.get("bank_account")
        statement_id = self.request.query_params.get("statement") or self.request.query_params.get("bank_statement")
        if account_id:
            qs = qs.filter(bank_account_id=account_id)
        if statement_id:
            qs = qs.filter(bank_statement_id=statement_id)
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        date_from = self.request.query_params.get("date_from") or self.request.query_params.get("date_after")
        date_to = self.request.query_params.get("date_to") or self.request.query_params.get("date_before")
        if date_from:
            qs = qs.filter(reconciliation_date__gte=date_from)
        if date_to:
            qs = qs.filter(reconciliation_date__lte=date_to)
        if (
            self.request.query_params.get("non_zero_difference") or self.request.query_params.get("has_difference")
        ) == "true":
            qs = qs.exclude(difference=0)
        finalized = self.request.query_params.get("finalized")
        if finalized == "true":
            qs = qs.filter(status="finalized")
        elif finalized == "false":
            qs = qs.exclude(status="finalized")
        return qs.order_by("-reconciliation_date", "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), ReconciliationListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(ReconciliationDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ReconciliationCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        key = data.pop("idempotency_key")
        return Response(
            ReconciliationDetailSerializer(
                ReconciliationService.create(self.tenant_id(), self.actor_id(), data, key)
            ).data,
            status=201,
        )

    def _transition(self, serializer_class: type, service_method: Any) -> Response:
        self.object_or_404(self.get_queryset())
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        value = service_method(
            self.tenant_id(),
            self.kwargs["pk"],
            self.actor_id(),
            *([data["reason"]] if "reason" in data else []),
            data["idempotency_key"],
        )
        return Response(ReconciliationDetailSerializer(value).data)

    @action(detail=True, methods=["post"])
    def start(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(ReconciliationStartSerializer, ReconciliationService.start)

    @action(detail=True, methods=["post"], url_path="generate-candidates")
    def generate_candidates(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = CandidateGenerationSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        result = ReconciliationService.generate_candidates(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["idempotency_key"]
        )
        return Response(
            {
                "generated": len(result.proposals),
                "auto_confirmed": 0,
                "matches": ReconciliationMatchDetailSerializer(result.proposals, many=True).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="matches")
    def matches(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = ManualMatchCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ReconciliationService.create_manual_match(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data
        )
        return Response(ReconciliationMatchDetailSerializer(value).data, status=201)

    @action(detail=True, methods=["post"], url_path="submit-review")
    def submit_review(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(ReconciliationSubmitReviewSerializer, ReconciliationService.submit_review)

    @action(detail=True, methods=["post"], url_path="return-to-work")
    def return_to_work(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(ReconciliationReturnToWorkSerializer, ReconciliationService.return_to_work)

    @action(detail=True, methods=["post"])
    def finalize(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(ReconciliationFinalizeSerializer, ReconciliationService.finalize)

    @action(detail=True, methods=["post"])
    def void(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(ReconciliationVoidSerializer, ReconciliationService.void)

    @action(detail=True, methods=["get"])
    def report(self, request: object, pk: str | None = None) -> StreamingHttpResponse:
        del request, pk
        self.object_or_404(self.get_queryset())
        report_format = str(self.request.query_params.get("format") or "csv").lower()
        if report_format not in {"csv", "pdf"}:
            raise ValidationError({"format": "Supported values are csv and pdf."})
        content_type = "application/pdf" if report_format == "pdf" else "text/csv; charset=utf-8"
        response = StreamingHttpResponse(
            ReconciliationService.export_report(self.tenant_id(), self.kwargs["pk"], self.actor_id(), report_format),
            content_type=content_type,
        )
        response["Content-Disposition"] = f'attachment; filename="reconciliation-{self.kwargs["pk"]}.{report_format}"'
        return response


class ReconciliationMatchViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "bank_reconciliation.match:read",
        "retrieve": "bank_reconciliation.match:read",
        "confirm": "bank_reconciliation.match:confirm",
        "reject": "bank_reconciliation.match:confirm",
        "reverse": "bank_reconciliation.match:reverse",
    }

    def get_queryset(self) -> QuerySet[ReconciliationMatch]:
        return (
            ReconciliationMatch.objects.for_tenant(self.tenant_id())
            .prefetch_related("lines")
            .select_related("rule", "reconciliation")
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        queryset = self.get_queryset().order_by("-created_at", "id")
        return self.paginated(queryset, ReconciliationMatchDetailSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(ReconciliationMatchDetailSerializer(self.object_or_404(self.get_queryset())).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = MatchConfirmSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            ReconciliationMatchDetailSerializer(
                ReconciliationService.confirm_match(
                    self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["idempotency_key"]
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def reject(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = MatchRejectSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            ReconciliationMatchDetailSerializer(
                ReconciliationService.reject_match(
                    self.tenant_id(), self.kwargs["pk"], self.actor_id(), serializer.validated_data["reason"]
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def reverse(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.object_or_404(self.get_queryset())
        serializer = MatchReverseSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            ReconciliationMatchDetailSerializer(
                ReconciliationService.reverse_match(
                    self.tenant_id(),
                    self.kwargs["pk"],
                    self.actor_id(),
                    serializer.validated_data["reason"],
                    serializer.validated_data["idempotency_key"],
                )
            ).data
        )


class ModuleHealthAPIView(GovernedAPIViewMixin, ActionAccessMixin, APIView):
    action_permissions = {"health": "bank_reconciliation.health:read"}

    def get_permissions(self) -> list[object]:
        self.action = "health"
        return super().get_permissions()

    def get(self, request: object) -> Response:
        del request
        result = get_module_health()
        return Response(result.payload, status=result.status_code)


__all__ = [
    "BankAccountViewSet",
    "BankStatementViewSet",
    "BankTransactionViewSet",
    "MatchingRuleViewSet",
    "ModuleHealthAPIView",
    "ReconciliationMatchViewSet",
    "ReconciliationViewSet",
    "StatementImportViewSet",
]
