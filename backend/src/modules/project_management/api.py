"""Governed v2 controllers; every mutation delegates to a domain service."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from src.core.access import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

from src.core.api import GovernedAPIViewMixin, OperationFailed

from .models import Project, ProjectActivity, ProjectManagementConfigurationVersion, ProjectMember, ProjectMilestone, Task, TimeEntry
from .permissions import ActionAccessMixin
from .serializers import *
from .services import ConfigurationService, IdempotencyConflictError, MilestoneService, ProjectManagementError, ProjectMemberService, ProjectService, StaleVersionError, TaskService, TimeEntryService


def _bool(value, field):
    normalized = str(value).lower()
    if normalized in {"true", "1"}: return True
    if normalized in {"false", "0"}: return False
    raise ValidationError({field: "Use true or false."})


def _date(value, field):
    try: return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc: raise ValidationError({field: "Use YYYY-MM-DD."}) from exc


class TenantGovernedViewSet(GovernedAPIViewMixin, ActionAccessMixin, viewsets.GenericViewSet):
    http_method_names = ("get", "post", "patch", "delete", "head", "options")
    list_serializer_class = None; detail_serializer_class = None
    def tenant_id(self):
        value = getattr(self.request, "tenant_id", None)
        if value is None: raise PermissionDenied("Authenticated identity has no valid tenant.")
        return value
    def actor_id(self):
        try: return uuid.UUID(str(self.request.user.pk))
        except (ValueError, TypeError, AttributeError): return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{self.request.user.pk}")
    def idempotency_key(self, payload=None):
        key = str(self.request.headers.get("Idempotency-Key") or (payload or {}).get("idempotency_key") or "").strip()
        if not key and self.request.path.startswith("/api/v1/"): key = f"legacy-{uuid.uuid4()}"
        if not key or len(key) > 255: raise ValidationError({"idempotency_key": "A bounded Idempotency-Key header or field is required."})
        return key
    def get_serializer_class(self):
        if self.action == "list": return self.list_serializer_class
        if self.action in {"retrieve"}: return self.detail_serializer_class
        return super().get_serializer_class()
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        if page is None: raise RuntimeError("Governed pagination is required.")
        return self.get_paginated_response(self.list_serializer_class(page, many=True).data)
    def retrieve(self, request, pk=None): return Response(self.detail_serializer_class(self.get_object()).data)
    def handle_exception(self, exc):
        if isinstance(exc, StaleVersionError): exc = OperationFailed(error_code="STALE_VERSION", message="The record changed since it was loaded.", http_status=status.HTTP_409_CONFLICT)
        elif isinstance(exc, IdempotencyConflictError): exc = OperationFailed(error_code="IDEMPOTENCY_CONFLICT", message="The idempotency key conflicts with a prior command.", http_status=status.HTTP_409_CONFLICT)
        elif isinstance(exc, ProjectManagementError):
            if exc.code == "NOT_FOUND": exc = NotFound()
            else: exc = ValidationError({"code": exc.code, "message": exc.messages[0]})
        elif isinstance(exc, DjangoValidationError): exc = ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages}))
        return super().handle_exception(exc)


class CrudViewSet(TenantGovernedViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin):
    def destroy(self, request, *args, **kwargs):
        payload = request.data if isinstance(request.data, dict) else {}; instance = self.get_object(); self.archive_service(self.tenant_id(), self.actor_id(), instance.id, int(payload.get("version", getattr(instance, "version", 1))), self.idempotency_key(payload)); return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectViewSet(CrudViewSet):
    archived_permission = "project_management.project:restore"
    queryset = Project.objects.none(); list_serializer_class = ProjectListSerializer; detail_serializer_class = ProjectDetailSerializer; serializer_class = ProjectCreateSerializer
    action_permissions = {"list":"project_management.project:read", "retrieve":"project_management.project:read", "summary":"project_management.project:read", "create":"project_management.project:create", "partial_update":"project_management.project:update", "destroy":"project_management.project:archive", "restore":"project_management.project:restore", "duplicate":"project_management.project:duplicate", **{x:"project_management.project:transition" for x in ("activate","hold","resume","complete","cancel")}}
    action_quotas = {"create":"project_management.project_writes", "partial_update":"project_management.project_writes", "destroy":"project_management.project_writes"}
    archive_service = staticmethod(ProjectService.archive_project)
    def get_queryset(self):
        include = self.request.query_params.get("include_archived")
        include_archived = bool(include and _bool(include, "include_archived"))
        qs = (Project.all_objects if include_archived else Project.objects).for_tenant(self.tenant_id()).select_related()
        p = self.request.query_params
        if p.get("search"): qs = qs.filter(Q(project_code__icontains=p["search"][:100]) | Q(project_name__icontains=p["search"][:100]))
        if p.get("status"): qs = qs.filter(status=p["status"])
        if p.get("manager_id"): qs = qs.filter(project_manager_id=p["manager_id"])
        if p.get("start_from"): qs = qs.filter(start_date__gte=_date(p["start_from"], "start_from"))
        if p.get("start_to"): qs = qs.filter(start_date__lte=_date(p["start_to"], "start_to"))
        ordering = p.get("ordering", "-updated_at"); allowed = {"project_code","project_name","start_date","updated_at"}
        if ordering.lstrip("-") not in allowed: raise ValidationError({"ordering":"Unsupported ordering field."})
        return qs.order_by(ordering, "id")
    def create(self, request):
        serializer = ProjectCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); project = ProjectService.create_project(self.tenant_id(), self.actor_id(), serializer.validated_data, self.idempotency_key(request.data)); return Response(ProjectDetailSerializer(project).data, status=201)
    def partial_update(self, request, pk=None):
        self.get_object(); serializer = ProjectUpdateSerializer(data=request.data, partial=False); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data); version=data.pop("version"); key=data.pop("idempotency_key"); project=ProjectService.update_project(self.tenant_id(),self.actor_id(),pk,data,version,self.idempotency_key({"idempotency_key":key})); return Response(ProjectDetailSerializer(project).data)
    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None): self.get_object(); return Response(ProjectSummarySerializer(ProjectService.get_project_summary(self.tenant_id(), pk)).data)
    def _transition(self, request, pk, command):
        self.get_object(); serializer=ProjectTransitionSerializer(data=request.data); serializer.is_valid(raise_exception=True); project=ProjectService.transition_project(self.tenant_id(),self.actor_id(),pk,command,serializer.validated_data["transition_key"],serializer.validated_data.get("reason", "")); return Response(ProjectDetailSerializer(project).data)
    @action(detail=True,methods=["post"])
    def activate(self,r,pk=None): return self._transition(r,pk,"activate")
    @action(detail=True,methods=["post"])
    def hold(self,r,pk=None): return self._transition(r,pk,"hold")
    @action(detail=True,methods=["post"])
    def resume(self,r,pk=None): return self._transition(r,pk,"resume")
    @action(detail=True,methods=["post"])
    def complete(self,r,pk=None): return self._transition(r,pk,"complete")
    @action(detail=True,methods=["post"])
    def cancel(self,r,pk=None): return self._transition(r,pk,"cancel")
    @action(detail=True,methods=["post"])
    def restore(self,request,pk=None):
        serializer=ArchiveRestoreSerializer(data=request.data);serializer.is_valid(raise_exception=True); project=ProjectService.restore_project(self.tenant_id(),self.actor_id(),pk,serializer.validated_data["version"],self.idempotency_key(serializer.validated_data));return Response(ProjectDetailSerializer(project).data)
    @action(detail=True,methods=["post"])
    def duplicate(self,request,pk=None):
        self.get_object(); serializer=DuplicateProjectSerializer(data=request.data);serializer.is_valid(raise_exception=True); project=ProjectService.duplicate_project(self.tenant_id(),self.actor_id(),pk,serializer.validated_data["project_code"],serializer.validated_data["project_name"],self.idempotency_key(serializer.validated_data));return Response(ProjectDetailSerializer(project).data,status=201)


class TaskViewSet(CrudViewSet):
    archived_permission = "project_management.task:restore"
    queryset=Task.objects.none();list_serializer_class=TaskListSerializer;detail_serializer_class=TaskDetailSerializer;serializer_class=TaskCreateSerializer;archive_service=staticmethod(TaskService.archive_task)
    action_permissions={"list":"project_management.task:read","retrieve":"project_management.task:read","create":"project_management.task:create","partial_update":"project_management.task:update","destroy":"project_management.task:archive","restore":"project_management.task:restore","reorder":"project_management.task:reorder",**{x:"project_management.task:transition" for x in ("start","submit_review","request_changes","complete","block","unblock","cancel")}}
    def get_queryset(self):
        p=self.request.query_params;include=bool(p.get("include_archived") and _bool(p["include_archived"],"include_archived"));qs=(Task.all_objects if include else Task.objects).for_tenant(self.tenant_id()).select_related("project","parent_task")
        for key in ("project_id","status","priority","assigned_to_id"):
            if p.get(key): qs=qs.filter(**{key:p[key]})
        if p.get("search"): qs=qs.filter(Q(task_code__icontains=p["search"][:100])|Q(task_name__icontains=p["search"][:100]))
        if p.get("due_from"): qs=qs.filter(due_date__gte=_date(p["due_from"],"due_from"))
        if p.get("due_to"): qs=qs.filter(due_date__lte=_date(p["due_to"],"due_to"))
        if p.get("overdue") and _bool(p["overdue"],"overdue"): qs=qs.filter(due_date__lt=timezone.localdate()).exclude(status__in=["done","cancelled"])
        ordering=p.get("ordering","position");allowed={"position","due_date","priority","updated_at"}
        if ordering.lstrip("-") not in allowed: raise ValidationError({"ordering":"Unsupported ordering field."})
        return qs.order_by(ordering,"id")
    def create(self,request):
        s=TaskCreateSerializer(data=request.data);s.is_valid(raise_exception=True);obj=TaskService.create_task(self.tenant_id(),self.actor_id(),s.validated_data,self.idempotency_key(request.data));return Response(TaskDetailSerializer(obj).data,status=201)
    def partial_update(self,request,pk=None):
        self.get_object();s=TaskUpdateSerializer(data=request.data);s.is_valid(raise_exception=True);d=dict(s.validated_data);v=d.pop("version");k=d.pop("idempotency_key");obj=TaskService.update_task(self.tenant_id(),self.actor_id(),pk,d,v,self.idempotency_key({"idempotency_key":k}));return Response(TaskDetailSerializer(obj).data)
    def _transition(self,r,pk,command):
        self.get_object();s=TaskTransitionSerializer(data=r.data);s.is_valid(raise_exception=True);obj=TaskService.transition_task(self.tenant_id(),self.actor_id(),pk,command,s.validated_data["transition_key"],s.validated_data.get("reason",""),s.validated_data.get("target_state"));return Response(TaskDetailSerializer(obj).data)
    @action(detail=True,methods=["post"])
    def start(self,r,pk=None):return self._transition(r,pk,"start")
    @action(detail=True,methods=["post"],url_path="submit-review")
    def submit_review(self,r,pk=None):return self._transition(r,pk,"submit_review")
    @action(detail=True,methods=["post"],url_path="request-changes")
    def request_changes(self,r,pk=None):return self._transition(r,pk,"request_changes")
    @action(detail=True,methods=["post"])
    def complete(self,r,pk=None):return self._transition(r,pk,"complete")
    @action(detail=True,methods=["post"])
    def block(self,r,pk=None):return self._transition(r,pk,"block")
    @action(detail=True,methods=["post"])
    def unblock(self,r,pk=None):return self._transition(r,pk,"unblock")
    @action(detail=True,methods=["post"])
    def cancel(self,r,pk=None):return self._transition(r,pk,"cancel")
    @action(detail=True,methods=["post"])
    def reorder(self,r,pk=None):
        s=ReorderTaskSerializer(data=r.data);s.is_valid(raise_exception=True);obj=TaskService.reorder_task(self.tenant_id(),self.actor_id(),pk,s.validated_data["position"],s.validated_data["version"],self.idempotency_key(s.validated_data));return Response(TaskDetailSerializer(obj).data)
    @action(detail=True,methods=["post"])
    def restore(self,r,pk=None):
        s=ArchiveRestoreSerializer(data=r.data);s.is_valid(raise_exception=True);obj=TaskService.restore_task(self.tenant_id(),self.actor_id(),pk,s.validated_data["version"],self.idempotency_key(s.validated_data));return Response(TaskDetailSerializer(obj).data)


class ProjectMemberViewSet(CrudViewSet):
    archived_permission = "project_management.member:restore"
    queryset=ProjectMember.objects.none();list_serializer_class=ProjectMemberListSerializer;detail_serializer_class=ProjectMemberDetailSerializer;serializer_class=ProjectMemberCreateSerializer
    action_permissions={"list":"project_management.member:read","retrieve":"project_management.member:read","create":"project_management.member:create","partial_update":"project_management.member:update","destroy":"project_management.member:archive","restore":"project_management.member:restore"}
    def get_queryset(self):
        p=self.request.query_params;include=bool(p.get("include_archived") and _bool(p["include_archived"],"include_archived"));qs=(ProjectMember.all_objects if include else ProjectMember.objects).for_tenant(self.tenant_id()).select_related("project")
        for k in ("project_id","employee_id","role"):
            if p.get(k):qs=qs.filter(**{k:p[k]})
        ordering=p.get("ordering","joined_at");
        if ordering.lstrip("-") not in {"joined_at","role","updated_at"}:raise ValidationError({"ordering":"Unsupported ordering field."})
        return qs.order_by(ordering,"id")
    def create(self,r):s=ProjectMemberCreateSerializer(data=r.data);s.is_valid(raise_exception=True);o=ProjectMemberService.add_member(self.tenant_id(),self.actor_id(),s.validated_data,self.idempotency_key(r.data));return Response(ProjectMemberDetailSerializer(o).data,status=201)
    def partial_update(self,r,pk=None):self.get_object();s=ProjectMemberUpdateSerializer(data=r.data);s.is_valid(raise_exception=True);d=dict(s.validated_data);k=d.pop("idempotency_key");o=ProjectMemberService.update_member(self.tenant_id(),self.actor_id(),pk,d,self.idempotency_key({"idempotency_key":k}));return Response(ProjectMemberDetailSerializer(o).data)
    def archive_service(self,*args):return ProjectMemberService.archive_member(args[0],args[1],args[2],args[4])
    @action(detail=True,methods=["post"])
    def restore(self,r,pk=None):s=IdempotencySerializer(data=r.data);s.is_valid(raise_exception=True);o=ProjectMemberService.restore_member(self.tenant_id(),self.actor_id(),pk,self.idempotency_key(s.validated_data));return Response(ProjectMemberDetailSerializer(o).data)


class TimeEntryViewSet(CrudViewSet):
    archived_permission = "project_management.time_entry:restore"
    queryset=TimeEntry.objects.none();list_serializer_class=TimeEntryListSerializer;detail_serializer_class=TimeEntryDetailSerializer;serializer_class=TimeEntryCreateSerializer;archive_service=staticmethod(TimeEntryService.archive_time_entry)
    action_permissions={"list":"project_management.time_entry:read","retrieve":"project_management.time_entry:read","create":"project_management.time_entry:create","partial_update":"project_management.time_entry:update","destroy":"project_management.time_entry:archive","restore":"project_management.time_entry:restore"}
    def get_queryset(self):
        p=self.request.query_params;include=bool(p.get("include_archived") and _bool(p["include_archived"],"include_archived"));qs=(TimeEntry.all_objects if include else TimeEntry.objects).for_tenant(self.tenant_id()).select_related("project","task")
        for k in ("project_id","task_id","employee_id","billable"):
            if p.get(k) is not None and p.get(k)!="":qs=qs.filter(**{k:_bool(p[k],k) if k=="billable" else p[k]})
        if p.get("entry_from"):qs=qs.filter(entry_date__gte=_date(p["entry_from"],"entry_from"))
        if p.get("entry_to"):qs=qs.filter(entry_date__lte=_date(p["entry_to"],"entry_to"))
        ordering=p.get("ordering","-entry_date");
        if ordering.lstrip("-") not in {"entry_date","created_at"}:raise ValidationError({"ordering":"Unsupported ordering field."})
        return qs.order_by(ordering,"id")
    def create(self,r):s=TimeEntryCreateSerializer(data=r.data);s.is_valid(raise_exception=True);o=TimeEntryService.create_time_entry(self.tenant_id(),self.actor_id(),s.validated_data,self.idempotency_key(r.data));return Response(TimeEntryDetailSerializer(o).data,status=201)
    def partial_update(self,r,pk=None):self.get_object();s=TimeEntryUpdateSerializer(data=r.data);s.is_valid(raise_exception=True);d=dict(s.validated_data);v=d.pop("version");k=d.pop("idempotency_key");o=TimeEntryService.update_time_entry(self.tenant_id(),self.actor_id(),pk,d,v,self.idempotency_key({"idempotency_key":k}));return Response(TimeEntryDetailSerializer(o).data)
    @action(detail=True,methods=["post"])
    def restore(self,r,pk=None):s=ArchiveRestoreSerializer(data=r.data);s.is_valid(raise_exception=True);o=TimeEntryService.restore_time_entry(self.tenant_id(),self.actor_id(),pk,s.validated_data["version"],self.idempotency_key(s.validated_data));return Response(TimeEntryDetailSerializer(o).data)


class ProjectMilestoneViewSet(CrudViewSet):
    archived_permission = "project_management.milestone:restore"
    queryset=ProjectMilestone.objects.none();list_serializer_class=ProjectMilestoneListSerializer;detail_serializer_class=ProjectMilestoneDetailSerializer;serializer_class=ProjectMilestoneCreateSerializer;archive_service=staticmethod(MilestoneService.archive_milestone)
    action_permissions={"list":"project_management.milestone:read","retrieve":"project_management.milestone:read","create":"project_management.milestone:create","partial_update":"project_management.milestone:update","destroy":"project_management.milestone:archive","restore":"project_management.milestone:restore",**{x:"project_management.milestone:transition" for x in ("achieve","reopen","cancel")}}
    def get_queryset(self):
        p=self.request.query_params;include=bool(p.get("include_archived") and _bool(p["include_archived"],"include_archived"));qs=(ProjectMilestone.all_objects if include else ProjectMilestone.objects).for_tenant(self.tenant_id()).select_related("project")
        if p.get("project_id"):qs=qs.filter(project_id=p["project_id"])
        if p.get("search"):qs=qs.filter(milestone_name__icontains=p["search"][:100])
        if p.get("achieved"):qs=qs.filter(achieved_date__isnull=not _bool(p["achieved"],"achieved"))
        if p.get("overdue") and _bool(p["overdue"],"overdue"):qs=qs.filter(target_date__lt=timezone.localdate(),achieved_date__isnull=True,cancelled_at__isnull=True)
        if p.get("target_from"):qs=qs.filter(target_date__gte=_date(p["target_from"],"target_from"))
        if p.get("target_to"):qs=qs.filter(target_date__lte=_date(p["target_to"],"target_to"))
        ordering=p.get("ordering","target_date");
        if ordering.lstrip("-") not in {"target_date","milestone_name"}:raise ValidationError({"ordering":"Unsupported ordering field."})
        return qs.order_by(ordering,"id")
    def create(self,r):s=ProjectMilestoneCreateSerializer(data=r.data);s.is_valid(raise_exception=True);o=MilestoneService.create_milestone(self.tenant_id(),self.actor_id(),s.validated_data,self.idempotency_key(r.data));return Response(ProjectMilestoneDetailSerializer(o).data,status=201)
    def partial_update(self,r,pk=None):self.get_object();s=ProjectMilestoneUpdateSerializer(data=r.data);s.is_valid(raise_exception=True);d=dict(s.validated_data);v=d.pop("version");k=d.pop("idempotency_key");o=MilestoneService.update_milestone(self.tenant_id(),self.actor_id(),pk,d,v,self.idempotency_key({"idempotency_key":k}));return Response(ProjectMilestoneDetailSerializer(o).data)
    @action(detail=True,methods=["post"])
    def achieve(self,r,pk=None):s=MilestoneAchieveSerializer(data=r.data);s.is_valid(raise_exception=True);o=MilestoneService.achieve_milestone(self.tenant_id(),self.actor_id(),pk,s.validated_data["achieved_date"],self.idempotency_key(s.validated_data));return Response(ProjectMilestoneDetailSerializer(o).data)
    @action(detail=True,methods=["post"])
    def reopen(self,r,pk=None):s=IdempotencySerializer(data=r.data);s.is_valid(raise_exception=True);o=MilestoneService.reopen_milestone(self.tenant_id(),self.actor_id(),pk,self.idempotency_key(s.validated_data));return Response(ProjectMilestoneDetailSerializer(o).data)
    @action(detail=True,methods=["post"])
    def cancel(self,r,pk=None):s=IdempotencySerializer(data=r.data);s.is_valid(raise_exception=True);o=MilestoneService.cancel_milestone(self.tenant_id(),self.actor_id(),pk,self.idempotency_key(s.validated_data));return Response(ProjectMilestoneDetailSerializer(o).data)
    @action(detail=True,methods=["post"])
    def restore(self,r,pk=None):s=ArchiveRestoreSerializer(data=r.data);s.is_valid(raise_exception=True);o=MilestoneService.restore_milestone(self.tenant_id(),self.actor_id(),pk,s.validated_data["version"],self.idempotency_key(s.validated_data));return Response(ProjectMilestoneDetailSerializer(o).data)


class ProjectActivityViewSet(TenantGovernedViewSet,mixins.ListModelMixin,mixins.RetrieveModelMixin):
    queryset=ProjectActivity.objects.none();list_serializer_class=ProjectActivitySerializer;detail_serializer_class=ProjectActivitySerializer;serializer_class=ProjectActivitySerializer;action_permissions={"list":"project_management.activity:read","retrieve":"project_management.activity:read"}
    def get_queryset(self):
        project_id=self.request.query_params.get("project_id");
        if self.action == "list" and not project_id:raise ValidationError({"project_id":"This filter is required."})
        qs=ProjectActivity.objects.for_tenant(self.tenant_id())
        if project_id: qs=qs.filter(project_id=project_id)
        for k in ("entity_type","entity_id","action"):
            if self.request.query_params.get(k):qs=qs.filter(**{k:self.request.query_params[k]})
        return qs.order_by("-created_at")


class ConfigurationVersionViewSet(TenantGovernedViewSet,mixins.ListModelMixin,mixins.RetrieveModelMixin):
    queryset=ProjectManagementConfigurationVersion.objects.none();list_serializer_class=ConfigurationVersionSerializer;detail_serializer_class=ConfigurationVersionSerializer;serializer_class=ConfigurationVersionSerializer;action_permissions={"list":"project_management.configuration:read","retrieve":"project_management.configuration:read"}
    def get_queryset(self):
        qs=ProjectManagementConfigurationVersion.objects.for_tenant(self.tenant_id()).select_related("configuration");p=self.request.query_params
        if p.get("environment"):qs=qs.filter(configuration__environment=p["environment"])
        if p.get("state"):qs=qs.filter(state=p["state"])
        return qs.order_by("-version","-created_at")


class ConfigurationViewSet(TenantGovernedViewSet):
    queryset=ProjectManagementConfigurationVersion.objects.none();serializer_class=ConfigurationVersionSerializer
    action_permissions={"list":"project_management.configuration:read","drafts":"project_management.configuration:write","simulate":"project_management.configuration:simulate","publish":"project_management.configuration:publish","rollback":"project_management.configuration:rollback","export":"project_management.configuration:export","import_document":"project_management.configuration:import"}
    def list(self,r):return Response(ConfigurationVersionSerializer(ConfigurationService.get_active(self.tenant_id(),r.query_params.get("environment",ConfigurationService.runtime_environment()))).data)
    @action(detail=False,methods=["post"],url_path="drafts")
    def drafts(self,r):s=ConfigurationDraftSerializer(data=r.data);s.is_valid(raise_exception=True);o=ConfigurationService.create_draft(self.tenant_id(),self.actor_id(),**s.validated_data);return Response(ConfigurationVersionSerializer(o).data,status=201)
    @action(detail=False,methods=["post"],url_path=r"drafts/(?P<draft_id>[^/.]+)/simulate")
    def simulate(self,r,draft_id=None):return Response(ConfigurationService.simulate(self.tenant_id(),draft_id))
    @action(detail=False,methods=["post"],url_path=r"drafts/(?P<draft_id>[^/.]+)/publish")
    def publish(self,r,draft_id=None):s=ConfigurationPublishSerializer(data=r.data);s.is_valid(raise_exception=True);o=ConfigurationService.publish(self.tenant_id(),self.actor_id(),draft_id,self.idempotency_key(s.validated_data));return Response(ConfigurationVersionSerializer(o).data)
    @action(detail=False,methods=["post"])
    def rollback(self,r):s=ConfigurationRollbackSerializer(data=r.data);s.is_valid(raise_exception=True);o=ConfigurationService.rollback(self.tenant_id(),self.actor_id(),s.validated_data["target_version"],self.idempotency_key(s.validated_data));return Response(ConfigurationVersionSerializer(o).data)
    @action(detail=False,methods=["get"])
    def export(self,r):return Response(ConfigurationService.export_document(self.tenant_id(),r.query_params.get("environment",ConfigurationService.runtime_environment())))
    @action(detail=False,methods=["post"],url_path="import")
    def import_document(self,r):s=ConfigurationImportSerializer(data=r.data);s.is_valid(raise_exception=True);o=ConfigurationService.import_document(self.tenant_id(),self.actor_id(),s.validated_data["document"]);return Response(ConfigurationVersionSerializer(o).data,status=201)

class PortfolioDashboardView(GovernedAPIViewMixin, APIView):
    permission_classes=(IsAuthenticated,RequiresAccess("project_management.project:read"));required_entitlement="project_management.core"
    def get(self,request):
        tenant=get_user_tenant_id(request.user)
        if not tenant:raise PermissionDenied("Authenticated identity has no tenant.")
        return Response(PortfolioSummarySerializer(ProjectService.get_portfolio_summary(tenant)).data)

class MyWorkView(GovernedAPIViewMixin, APIView):
    permission_classes=(IsAuthenticated,RequiresAccess("project_management.task:read"));required_entitlement="project_management.core"
    def get(self,request):
        raise OperationFailed(error_code="EMPLOYEE_LINK_UNAVAILABLE",message="My Work requires a tenant-safe employee identity provider.",http_status=status.HTTP_503_SERVICE_UNAVAILABLE)
