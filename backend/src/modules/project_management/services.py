"""Transactional project-management application services.

All public mutations are tenant-first, validate relationships under that tenant,
lock mutable rows, enforce optimistic concurrency, and append immutable activity.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from src.core.middleware.correlation import get_correlation_id
from src.core.async_jobs.models import OutboxEvent

from .models import (
    ConfigurationEnvironment, ConfigurationState, Project, ProjectActivity,
    ProjectManagementConfiguration, ProjectManagementConfigurationVersion,
    ProjectMember, ProjectMilestone, ProjectStatus, Task, TaskStatus, TimeEntry,
)


class ProjectManagementError(ValidationError):
    def __init__(self, message: str, code: str = "INVALID_OPERATION"):
        self.code = code
        super().__init__(message, code=code)


class StaleVersionError(ProjectManagementError):
    def __init__(self): super().__init__("The record changed since it was loaded.", "STALE_VERSION")


class IdempotencyConflictError(ProjectManagementError):
    def __init__(self): super().__init__("The idempotency key was already used for a different command.", "IDEMPOTENCY_CONFLICT")


def _uuid(value, field="identifier"):
    try: return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc: raise ProjectManagementError(f"{field} must be a valid UUID.", "INVALID_UUID") from exc


def _actor(value): return _uuid(value, "actor_id")
def _tenant(value): return _uuid(value, "tenant_id")


def _required(value, field, maximum=255):
    result = str(value or "").strip()
    if not result or len(result) > maximum: raise ProjectManagementError(f"{field} must be a bounded non-empty string.", "INVALID_INPUT")
    return result


def _correlation(seed):
    current = get_correlation_id().strip()
    return current[:64] if current else f"cmd-{hashlib.sha256(seed.encode()).hexdigest()[:40]}"


def _snapshot(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in {"tenant_id", "description"}: continue
        value = getattr(instance, field.attname)
        if isinstance(value, (uuid.UUID, Decimal, date)) or hasattr(value, "isoformat"): value = str(value)
        values[field.name] = value
    return values


def _fingerprint(action, data):
    def canonical(value):
        if isinstance(value, Mapping): return {str(k): canonical(v) for k, v in sorted(value.items())}
        if isinstance(value, (list, tuple)): return [canonical(v) for v in value]
        if isinstance(value, (uuid.UUID, Decimal, date)): return str(value)
        return value
    return hashlib.sha256(json.dumps({"action": action, "data": canonical(data)}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ActivityService:
    @staticmethod
    def record(tenant_id, actor_id, entity_type, entity_id, action, *, project=None, before=None, after=None, idempotency_key="", fingerprint="", metadata=None, correlation_id=None):
        meta = dict(metadata or {})
        if idempotency_key: meta.update({"idempotency_key": idempotency_key, "fingerprint": fingerprint})
        activity = ProjectActivity.objects.create(
            tenant_id=_tenant(tenant_id), actor_id=_actor(actor_id), project=project,
            entity_type=entity_type, entity_id=_uuid(entity_id), action=action,
            correlation_id=(correlation_id or _correlation(f"{action}:{entity_id}"))[:64],
            before=before or {}, after=after or {}, metadata=meta,
        )
        emitted = {
            "project.created", "project.transitioned", "project.archived",
            "task.created", "task.transitioned", "member.changed",
            "time_entry.changed", "milestone.changed", "configuration.published",
        }
        if action in emitted:
            event_type = f"project_management.{action}"
            event = OutboxEvent(
                tenant_id=_tenant(tenant_id), aggregate_type="project_management",
                aggregate_id=_uuid(entity_id), event_type=event_type,
                payload={"schema_version": "1.0", "event_id": "", "event_type": event_type,
                         "tenant_id": str(_tenant(tenant_id)), "aggregate_id": str(entity_id),
                         "actor_id": str(_actor(actor_id)), "correlation_id": activity.correlation_id,
                         "action": action},
            )
            event.payload["event_id"] = str(event.id); event.save()
        return activity

    @staticmethod
    def replay(tenant_id, action, idempotency_key, fingerprint, model):
        if not idempotency_key: raise ProjectManagementError("idempotency_key is required.", "IDEMPOTENCY_REQUIRED")
        activity = ProjectActivity.objects.for_tenant(_tenant(tenant_id)).filter(action=action, metadata__idempotency_key=idempotency_key).first()
        if not activity: return None
        if activity.metadata.get("fingerprint") != fingerprint: raise IdempotencyConflictError()
        try: return model.objects.for_tenant(_tenant(tenant_id)).get(pk=activity.entity_id)
        except model.DoesNotExist: raise IdempotencyConflictError()

    @staticmethod
    def list_for_project(tenant_id, project_id, filters=None):
        queryset = ProjectActivity.objects.for_tenant(_tenant(tenant_id)).filter(project_id=_uuid(project_id))
        for key in ("entity_type", "entity_id", "action"):
            value = (filters or {}).get(key)
            if value: queryset = queryset.filter(**{key: value})
        return queryset.order_by("-created_at")


def _version(instance, expected):
    if isinstance(expected, bool) or int(expected) != instance.version: raise StaleVersionError()


def _active_configuration(tenant_id):
    return ConfigurationService.get_active(tenant_id, ConfigurationService.runtime_environment())


def _project(tenant_id, project_id, include_archived=False, lock=False):
    qs = (Project.all_objects if include_archived else Project.objects).for_tenant(_tenant(tenant_id))
    if lock: qs = qs.select_for_update()
    try: return qs.get(pk=_uuid(project_id, "project_id"))
    except Project.DoesNotExist as exc: raise ProjectManagementError("Project was not found.", "NOT_FOUND") from exc


class ProjectService:
    MUTABLE = {"project_code", "project_name", "description", "start_date", "end_date", "project_manager_id", "budget", "currency"}

    @staticmethod
    @transaction.atomic
    def create_project(tenant_id, actor_id=None, data=None, idempotency_key=None, **legacy):
        # Backwards compatible invocation for the original public service API.
        if data is None:
            data = legacy
            if actor_id is not None and not legacy and isinstance(actor_id, Mapping): data, actor_id = actor_id, None
        actor_id = actor_id or uuid.UUID(int=0)
        key = idempotency_key or f"legacy-{uuid.uuid4()}"
        payload = {k: v for k, v in dict(data).items() if k in ProjectService.MUTABLE}
        payload["project_code"] = _required(payload.get("project_code"), "project_code", 50).upper()
        payload["project_name"] = _required(payload.get("project_name"), "project_name", 255)
        config = _active_configuration(tenant_id)
        payload["currency"] = str(payload.get("currency") or config.default_currency).upper()
        if not re.fullmatch(config.project_code_pattern, payload["project_code"]): raise ProjectManagementError("project_code does not match tenant configuration.", "INVALID_PROJECT_CODE")
        fp = _fingerprint("project.create", payload)
        replay = ActivityService.replay(tenant_id, "project.created", key, fp, Project)
        if replay: return replay
        project = Project(tenant_id=_tenant(tenant_id), **payload); project.save()
        ActivityService.record(tenant_id, actor_id, "project", project.id, "project.created", project=project, after=_snapshot(project), idempotency_key=key, fingerprint=fp)
        return project

    @staticmethod
    @transaction.atomic
    def update_project(tenant_id, actor_id, project_id, data, expected_version, idempotency_key):
        project = _project(tenant_id, project_id, lock=True); _version(project, expected_version)
        payload = {k: v for k, v in dict(data).items() if k in ProjectService.MUTABLE}
        fp = _fingerprint("project.update", {"id": project_id, "version": expected_version, **payload})
        replay = ActivityService.replay(tenant_id, "project.updated", idempotency_key, fp, Project)
        if replay: return replay
        before = _snapshot(project)
        if "project_code" in payload:
            payload["project_code"] = _required(payload["project_code"], "project_code", 50).upper()
            if not re.fullmatch(_active_configuration(tenant_id).project_code_pattern, payload["project_code"]): raise ProjectManagementError("project_code does not match tenant configuration.", "INVALID_PROJECT_CODE")
        for field, value in payload.items(): setattr(project, field, value)
        project.version += 1; project.save()
        ActivityService.record(tenant_id, actor_id, "project", project.id, "project.updated", project=project, before=before, after=_snapshot(project), idempotency_key=idempotency_key, fingerprint=fp)
        return project

    @staticmethod
    @transaction.atomic
    def transition_project(tenant_id, actor_id, project_id, command, transition_key, reason=""):
        project = _project(tenant_id, project_id, lock=True)
        fp = _fingerprint("project.transition", {"id": project_id, "command": command, "reason": reason})
        replay = ActivityService.replay(tenant_id, "project.transitioned", transition_key, fp, Project)
        if replay: return replay
        transitions = {"activate": ({ProjectStatus.PLANNING}, ProjectStatus.ACTIVE), "hold": ({ProjectStatus.ACTIVE}, ProjectStatus.ON_HOLD), "resume": ({ProjectStatus.ON_HOLD}, ProjectStatus.ACTIVE), "complete": ({ProjectStatus.ACTIVE, ProjectStatus.ON_HOLD}, ProjectStatus.COMPLETED), "cancel": ({ProjectStatus.PLANNING, ProjectStatus.ACTIVE, ProjectStatus.ON_HOLD}, ProjectStatus.CANCELLED)}
        if command not in transitions: raise ProjectManagementError("Unknown project transition.", "UNKNOWN_COMMAND")
        sources, target = transitions[command]
        if project.status in {ProjectStatus.COMPLETED, ProjectStatus.CANCELLED} or project.status not in sources: raise ProjectManagementError(f"{command} is not allowed from {project.status}.", "ILLEGAL_TRANSITION")
        if command == "activate" and (not project.start_date or not project.project_manager_id): raise ProjectManagementError("Activation requires a start date and project manager.", "ACTIVATION_GUARD")
        if command == "complete":
            if Task.objects.for_tenant(_tenant(tenant_id)).filter(project=project, archived_at__isnull=True).exclude(status__in=[TaskStatus.DONE, TaskStatus.CANCELLED]).exists(): raise ProjectManagementError("Complete or cancel all active tasks first.", "INCOMPLETE_TASKS")
            if ProjectMilestone.objects.for_tenant(_tenant(tenant_id)).filter(project=project, archived_at__isnull=True, achieved_date__isnull=True, cancelled_at__isnull=True).exists(): raise ProjectManagementError("Achieve or cancel all active milestones first.", "INCOMPLETE_MILESTONES")
        before = _snapshot(project); prior = project.status; project.status = target; project.version += 1
        project.transition_history = [*project.transition_history, {"transition_key": transition_key, "command": command, "from": prior, "to": target, "reason": reason, "actor_id": str(_actor(actor_id)), "correlation_id": _correlation(transition_key), "at": timezone.now().isoformat()}]
        project.save()
        ActivityService.record(tenant_id, actor_id, "project", project.id, "project.transitioned", project=project, before=before, after=_snapshot(project), idempotency_key=transition_key, fingerprint=fp, metadata={"command": command})
        return project

    @staticmethod
    @transaction.atomic
    def archive_project(tenant_id, actor_id, project_id, expected_version, idempotency_key):
        project = _project(tenant_id, project_id, lock=True); _version(project, expected_version)
        return ProjectService._archive(tenant_id, actor_id, project, True, idempotency_key)

    @staticmethod
    @transaction.atomic
    def restore_project(tenant_id, actor_id, project_id, expected_version, idempotency_key):
        project = _project(tenant_id, project_id, include_archived=True, lock=True); _version(project, expected_version)
        return ProjectService._archive(tenant_id, actor_id, project, False, idempotency_key)

    @staticmethod
    def _archive(tenant_id, actor_id, project, archive, key):
        action = "project.archived" if archive else "project.restored"; fp = _fingerprint(action, {"id": project.id, "version": project.version})
        replay = ActivityService.replay(tenant_id, action, key, fp, Project)
        if replay: return replay
        before = _snapshot(project); project.archived_at = timezone.now() if archive else None; project.archived_by_id = _actor(actor_id) if archive else None; project.version += 1; project.save()
        ActivityService.record(tenant_id, actor_id, "project", project.id, action, project=project, before=before, after=_snapshot(project), idempotency_key=key, fingerprint=fp)
        return project

    @staticmethod
    @transaction.atomic
    def duplicate_project(tenant_id, actor_id, project_id, project_code, project_name, idempotency_key):
        source = _project(tenant_id, project_id)
        clone = ProjectService.create_project(tenant_id, actor_id, {"project_code": project_code, "project_name": project_name, "description": source.description, "start_date": source.start_date, "end_date": source.end_date, "project_manager_id": source.project_manager_id, "budget": source.budget, "currency": source.currency}, idempotency_key)
        if clone.tasks.exists(): return clone
        task_map = {}
        for task in Task.objects.for_tenant(_tenant(tenant_id)).filter(project=source, archived_at__isnull=True).order_by("position"):
            parent = task_map.get(task.parent_task_id)
            copy = TaskService.create_task(tenant_id, actor_id, {"project": clone.id, "task_code": task.task_code, "task_name": task.task_name, "description": task.description, "assigned_to_id": task.assigned_to_id, "parent_task": parent.id if parent else None, "start_date": task.start_date, "due_date": task.due_date, "priority": task.priority, "estimated_hours": task.estimated_hours, "position": task.position}, f"{idempotency_key}:task:{task.id}")
            task_map[task.id] = copy
        for member in ProjectMember.objects.for_tenant(_tenant(tenant_id)).filter(project=source, archived_at__isnull=True): ProjectMemberService.add_member(tenant_id, actor_id, {"project": clone.id, "employee_id": member.employee_id, "role": member.role, "allocation_percentage": member.allocation_percentage, "joined_at": member.joined_at, "left_at": member.left_at}, f"{idempotency_key}:member:{member.id}")
        for milestone in ProjectMilestone.objects.for_tenant(_tenant(tenant_id)).filter(project=source, archived_at__isnull=True): MilestoneService.create_milestone(tenant_id, actor_id, {"project": clone.id, "milestone_name": milestone.milestone_name, "target_date": milestone.target_date, "description": milestone.description}, f"{idempotency_key}:milestone:{milestone.id}")
        return clone

    @staticmethod
    def get_project_summary(tenant_id, project_id):
        project = _project(tenant_id, project_id)
        tasks = Task.objects.for_tenant(_tenant(tenant_id)).filter(project=project, archived_at__isnull=True)
        milestones = ProjectMilestone.objects.for_tenant(_tenant(tenant_id)).filter(project=project, archived_at__isnull=True)
        time_total = TimeEntry.objects.for_tenant(_tenant(tenant_id)).filter(project=project, archived_at__isnull=True).aggregate(v=models.Sum("hours_worked"))["v"] or Decimal("0")
        total = tasks.count(); done = tasks.filter(status=TaskStatus.DONE).count()
        return {"project_id": project.id, "task_count": total, "completed_task_count": done, "blocked_task_count": tasks.filter(status=TaskStatus.BLOCKED).count(), "progress_percentage": Decimal(done * 100 / total).quantize(Decimal("0.01")) if total else Decimal("0.00"), "milestone_count": milestones.count(), "achieved_milestone_count": milestones.filter(achieved_date__isnull=False).count(), "time_hours": time_total, "next_due_date": tasks.filter(due_date__isnull=False).order_by("due_date").values_list("due_date", flat=True).first()}

    @staticmethod
    def get_portfolio_summary(tenant_id):
        tenant = _tenant(tenant_id); today = timezone.localdate()
        projects = Project.objects.for_tenant(tenant)
        tasks = Task.objects.for_tenant(tenant)
        milestones = ProjectMilestone.objects.for_tenant(tenant)
        budget_rows = projects.exclude(budget__isnull=True).values("currency").annotate(total=models.Sum("budget")).order_by("currency")
        return {
            "project_count": projects.count(), "active_project_count": projects.filter(status=ProjectStatus.ACTIVE).count(),
            "task_count": tasks.count(), "overdue_task_count": tasks.filter(due_date__lt=today).exclude(status__in=[TaskStatus.DONE, TaskStatus.CANCELLED]).count(),
            "blocked_task_count": tasks.filter(status=TaskStatus.BLOCKED).count(),
            "upcoming_milestone_count": milestones.filter(target_date__gte=today, achieved_date__isnull=True, cancelled_at__isnull=True).count(),
            "budget_by_currency": [{"currency": row["currency"], "amount": row["total"]} for row in budget_rows],
        }


class TaskService:
    MUTABLE = {"project", "task_code", "task_name", "description", "assigned_to_id", "parent_task", "start_date", "due_date", "priority", "estimated_hours", "position"}
    @staticmethod
    def _payload(tenant_id, data, instance=None):
        payload = {k: v for k, v in dict(data).items() if k in TaskService.MUTABLE}
        project_id = payload.pop("project", instance.project_id if instance else None); payload["project"] = _project(tenant_id, project_id)
        parent_id = payload.pop("parent_task", None)
        if parent_id: payload["parent_task"] = Task.objects.for_tenant(_tenant(tenant_id)).filter(pk=_uuid(parent_id), archived_at__isnull=True).first()
        if parent_id and not payload["parent_task"]: raise ProjectManagementError("Parent task was not found.", "NOT_FOUND")
        if "task_code" in payload: payload["task_code"] = _required(payload["task_code"], "task_code", 50).upper()
        return payload

    @staticmethod
    @transaction.atomic
    def create_task(tenant_id, actor_id, data, idempotency_key):
        payload = TaskService._payload(tenant_id, data); config = _active_configuration(tenant_id)
        if not re.fullmatch(config.task_code_pattern, payload.get("task_code", "")): raise ProjectManagementError("task_code does not match tenant configuration.", "INVALID_TASK_CODE")
        fp = _fingerprint("task.create", data); replay = ActivityService.replay(tenant_id, "task.created", idempotency_key, fp, Task)
        if replay: return replay
        task = Task(tenant_id=_tenant(tenant_id), **payload); task.save()
        ActivityService.record(tenant_id, actor_id, "task", task.id, "task.created", project=task.project, after=_snapshot(task), idempotency_key=idempotency_key, fingerprint=fp); return task

    @staticmethod
    @transaction.atomic
    def update_task(tenant_id, actor_id, task_id, data, expected_version, idempotency_key):
        try: task = Task.objects.for_tenant(_tenant(tenant_id)).select_for_update().get(pk=_uuid(task_id), archived_at__isnull=True)
        except Task.DoesNotExist as exc: raise ProjectManagementError("Task was not found.", "NOT_FOUND") from exc
        _version(task, expected_version); payload = TaskService._payload(tenant_id, data, task); before = _snapshot(task)
        for k, v in payload.items(): setattr(task, k, v)
        task.version += 1; task.save(); fp = _fingerprint("task.update", {"id": task_id, **data})
        ActivityService.record(tenant_id, actor_id, "task", task.id, "task.updated", project=task.project, before=before, after=_snapshot(task), idempotency_key=idempotency_key, fingerprint=fp); return task

    @staticmethod
    @transaction.atomic
    def transition_task(tenant_id, actor_id, task_id, command, transition_key, reason="", target_state=None):
        try: task = Task.objects.for_tenant(_tenant(tenant_id)).select_for_update().get(pk=_uuid(task_id), archived_at__isnull=True)
        except Task.DoesNotExist as exc: raise ProjectManagementError("Task was not found.", "NOT_FOUND") from exc
        fp = _fingerprint("task.transition", {"id": task_id, "command": command, "reason": reason, "target": target_state}); replay = ActivityService.replay(tenant_id, "task.transitioned", transition_key, fp, Task)
        if replay: return replay
        target = {"start": TaskStatus.IN_PROGRESS, "submit_review": TaskStatus.REVIEW, "request_changes": TaskStatus.IN_PROGRESS, "complete": TaskStatus.DONE, "block": TaskStatus.BLOCKED, "cancel": TaskStatus.CANCELLED}.get(command)
        allowed = {"start": {TaskStatus.TODO}, "submit_review": {TaskStatus.IN_PROGRESS}, "request_changes": {TaskStatus.REVIEW}, "complete": {TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}, "block": {TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}, "cancel": {TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.BLOCKED}}
        if command == "unblock":
            if target_state not in {TaskStatus.TODO, TaskStatus.IN_PROGRESS}: raise ProjectManagementError("Unblock target must be todo or in_progress.", "INVALID_TARGET_STATE")
            target, allowed[command] = target_state, {TaskStatus.BLOCKED}
        if command not in allowed or task.status not in allowed[command]: raise ProjectManagementError(f"{command} is not allowed from {task.status}.", "ILLEGAL_TRANSITION")
        if command == "block" and not str(reason).strip(): raise ProjectManagementError("A block reason is required.", "BLOCK_REASON_REQUIRED")
        prior = task.status; before = _snapshot(task); task.status = target
        if target == TaskStatus.DONE: task.percent_complete = Decimal("100.00")
        task.version += 1; task.transition_history = [*task.transition_history, {"transition_key": transition_key, "command": command, "from": prior, "to": target, "reason": reason, "actor_id": str(_actor(actor_id)), "at": timezone.now().isoformat()}]; task.save()
        ActivityService.record(tenant_id, actor_id, "task", task.id, "task.transitioned", project=task.project, before=before, after=_snapshot(task), idempotency_key=transition_key, fingerprint=fp, metadata={"command": command}); return task

    @staticmethod
    def reorder_task(tenant_id, actor_id, task_id, position, expected_version, idempotency_key): return TaskService.update_task(tenant_id, actor_id, task_id, {"position": position}, expected_version, idempotency_key)

    @staticmethod
    def _archive(tenant_id, actor_id, task_id, expected_version, key, restore):
        try: task = Task.all_objects.for_tenant(_tenant(tenant_id)).select_for_update().get(pk=_uuid(task_id))
        except Task.DoesNotExist as exc: raise ProjectManagementError("Task was not found.", "NOT_FOUND") from exc
        _version(task, expected_version); task.archived_at = None if restore else timezone.now(); task.archived_by_id = None if restore else _actor(actor_id); task.version += 1; task.save()
        action = "task.restored" if restore else "task.archived"; ActivityService.record(tenant_id, actor_id, "task", task.id, action, project=task.project, after=_snapshot(task), idempotency_key=key, fingerprint=_fingerprint(action, {"id": task_id})); return task
    archive_task = staticmethod(transaction.atomic(lambda tenant_id, actor_id, task_id, expected_version, idempotency_key: TaskService._archive(tenant_id, actor_id, task_id, expected_version, idempotency_key, False)))
    restore_task = staticmethod(transaction.atomic(lambda tenant_id, actor_id, task_id, expected_version, idempotency_key: TaskService._archive(tenant_id, actor_id, task_id, expected_version, idempotency_key, True)))

    @staticmethod
    @transaction.atomic
    def recalculate_actual_hours(tenant_id, task_id):
        try: task = Task.objects.for_tenant(_tenant(tenant_id)).select_for_update().get(pk=_uuid(task_id))
        except Task.DoesNotExist as exc: raise ProjectManagementError("Task was not found.", "NOT_FOUND") from exc
        task.actual_hours = TimeEntry.objects.for_tenant(_tenant(tenant_id)).filter(task=task, archived_at__isnull=True).aggregate(total=models.Sum("hours_worked"))["total"] or Decimal("0.00"); task.save(update_fields=["actual_hours", "updated_at"]); return task

    @staticmethod
    def update_task_hours(task): return TaskService.recalculate_actual_hours(task.tenant_id, task.id)


class ProjectMemberService:
    @staticmethod
    @transaction.atomic
    def add_member(tenant_id, actor_id, data, idempotency_key):
        payload = dict(data); payload["project"] = _project(tenant_id, payload["project"]); allocation = Decimal(str(payload.get("allocation_percentage", 100)))
        if allocation > _active_configuration(tenant_id).max_allocation_percentage or allocation <= 0: raise ProjectManagementError("Allocation exceeds the configured safe limit.", "ALLOCATION_LIMIT")
        member = ProjectMember(tenant_id=_tenant(tenant_id), **payload); member.save(); ActivityService.record(tenant_id, actor_id, "member", member.id, "member.changed", project=member.project, after=_snapshot(member), idempotency_key=idempotency_key, fingerprint=_fingerprint("member.create", data)); return member
    @staticmethod
    @transaction.atomic
    def update_member(tenant_id, actor_id, member_id, data, idempotency_key):
        try: member = ProjectMember.objects.for_tenant(_tenant(tenant_id)).select_for_update().get(pk=_uuid(member_id), archived_at__isnull=True)
        except ProjectMember.DoesNotExist as exc: raise ProjectManagementError("Member was not found.", "NOT_FOUND") from exc
        for field in {"role", "allocation_percentage", "joined_at", "left_at"} & data.keys(): setattr(member, field, data[field])
        if member.allocation_percentage > _active_configuration(tenant_id).max_allocation_percentage: raise ProjectManagementError("Allocation exceeds the configured safe limit.", "ALLOCATION_LIMIT")
        member.save(); ActivityService.record(tenant_id, actor_id, "member", member.id, "member.changed", project=member.project, after=_snapshot(member), idempotency_key=idempotency_key, fingerprint=_fingerprint("member.update", data)); return member
    @staticmethod
    def _archive(tenant_id, actor_id, member_id, key, restore):
        try: member = ProjectMember.all_objects.for_tenant(_tenant(tenant_id)).get(pk=_uuid(member_id))
        except ProjectMember.DoesNotExist as exc: raise ProjectManagementError("Member was not found.", "NOT_FOUND") from exc
        member.archived_at = None if restore else timezone.now(); member.archived_by_id = None if restore else _actor(actor_id); member.save(); ActivityService.record(tenant_id, actor_id, "member", member.id, "member.changed", project=member.project, after=_snapshot(member), idempotency_key=key, fingerprint=_fingerprint("member.archive", {"id": member_id, "restore": restore})); return member
    archive_member = staticmethod(transaction.atomic(lambda tenant_id, actor_id, member_id, idempotency_key: ProjectMemberService._archive(tenant_id, actor_id, member_id, idempotency_key, False)))
    restore_member = staticmethod(transaction.atomic(lambda tenant_id, actor_id, member_id, idempotency_key: ProjectMemberService._archive(tenant_id, actor_id, member_id, idempotency_key, True)))


class TimeEntryService:
    @staticmethod
    def _payload(tenant_id, data):
        payload = dict(data); payload["project"] = _project(tenant_id, payload["project"]); task_id = payload.get("task")
        if task_id:
            try: payload["task"] = Task.objects.for_tenant(_tenant(tenant_id)).get(pk=_uuid(task_id), project=payload["project"], archived_at__isnull=True)
            except Task.DoesNotExist as exc: raise ProjectManagementError("Task must belong to the selected project.", "TASK_PROJECT_MISMATCH") from exc
        return payload
    @staticmethod
    def _validate(tenant_id, payload, exclude=None):
        config = _active_configuration(tenant_id); entry_date = payload["entry_date"]
        if isinstance(entry_date, str): entry_date = date.fromisoformat(entry_date); payload["entry_date"] = entry_date
        if entry_date > timezone.localdate() and not config.allow_future_time_entries: raise ProjectManagementError("Future time entries are disabled.", "FUTURE_TIME_DISABLED")
        if config.require_time_description and not str(payload.get("description", "")).strip(): raise ProjectManagementError("A time description is required.", "DESCRIPTION_REQUIRED")
        hours = Decimal(str(payload["hours_worked"])); qs = TimeEntry.objects.for_tenant(_tenant(tenant_id)).select_for_update().filter(employee_id=payload["employee_id"], entry_date=entry_date, archived_at__isnull=True)
        if exclude: qs = qs.exclude(pk=exclude)
        total = qs.aggregate(v=models.Sum("hours_worked"))["v"] or Decimal("0")
        if hours <= 0 or hours > 24 or total + hours > config.max_daily_hours: raise ProjectManagementError("Hours exceed the configured daily limit.", "DAILY_HOURS_LIMIT")
        payload.setdefault("billable", config.default_billable)
    @staticmethod
    @transaction.atomic
    def create_time_entry(tenant_id, actor_id=None, data=None, idempotency_key=None, **legacy):
        if data is None:
            data = legacy; actor_id = actor_id or uuid.UUID(int=0)
        key = idempotency_key or f"legacy-{uuid.uuid4()}"; fp = _fingerprint("time.create", data)
        replay = ActivityService.replay(tenant_id, "time_entry.changed", key, fp, TimeEntry)
        if replay: return replay
        payload = TimeEntryService._payload(tenant_id, data); TimeEntryService._validate(tenant_id, payload); payload["idempotency_key"] = key
        try: entry = TimeEntry(tenant_id=_tenant(tenant_id), **payload); entry.save()
        except ValidationError: raise
        ActivityService.record(tenant_id, actor_id or uuid.UUID(int=0), "time_entry", entry.id, "time_entry.changed", project=entry.project, after=_snapshot(entry), idempotency_key=key, fingerprint=fp)
        if entry.task_id: TaskService.recalculate_actual_hours(tenant_id, entry.task_id)
        return entry
    @staticmethod
    @transaction.atomic
    def update_time_entry(tenant_id, actor_id, entry_id, data, expected_version, idempotency_key):
        try: entry = TimeEntry.objects.for_tenant(_tenant(tenant_id)).select_for_update().get(pk=_uuid(entry_id), archived_at__isnull=True)
        except TimeEntry.DoesNotExist as exc: raise ProjectManagementError("Time entry was not found.", "NOT_FOUND") from exc
        _version(entry, expected_version); old_task = entry.task_id; merged = {"project": data.get("project", entry.project_id), "task": data.get("task", entry.task_id), "employee_id": data.get("employee_id", entry.employee_id), "entry_date": data.get("entry_date", entry.entry_date), "hours_worked": data.get("hours_worked", entry.hours_worked), "description": data.get("description", entry.description), "billable": data.get("billable", entry.billable)}; payload = TimeEntryService._payload(tenant_id, merged); TimeEntryService._validate(tenant_id, payload, entry.id)
        for k, v in payload.items(): setattr(entry, k, v)
        entry.version += 1; entry.save(); ActivityService.record(tenant_id, actor_id, "time_entry", entry.id, "time_entry.changed", project=entry.project, after=_snapshot(entry), idempotency_key=idempotency_key, fingerprint=_fingerprint("time.update", data))
        if old_task: TaskService.recalculate_actual_hours(tenant_id, old_task)
        if entry.task_id and entry.task_id != old_task: TaskService.recalculate_actual_hours(tenant_id, entry.task_id)
        return entry
    @staticmethod
    def _archive(tenant_id, actor_id, entry_id, expected_version, key, restore):
        try: entry = TimeEntry.all_objects.for_tenant(_tenant(tenant_id)).select_for_update().get(pk=_uuid(entry_id))
        except TimeEntry.DoesNotExist as exc: raise ProjectManagementError("Time entry was not found.", "NOT_FOUND") from exc
        _version(entry, expected_version); entry.archived_at = None if restore else timezone.now(); entry.archived_by_id = None if restore else _actor(actor_id); entry.version += 1; entry.save(); ActivityService.record(tenant_id, actor_id, "time_entry", entry.id, "time_entry.changed", project=entry.project, after=_snapshot(entry), idempotency_key=key, fingerprint=_fingerprint("time.archive", {"id": entry_id, "restore": restore}));
        if entry.task_id: TaskService.recalculate_actual_hours(tenant_id, entry.task_id)
        return entry
    archive_time_entry = staticmethod(transaction.atomic(lambda tenant_id, actor_id, entry_id, expected_version, idempotency_key: TimeEntryService._archive(tenant_id, actor_id, entry_id, expected_version, idempotency_key, False)))
    restore_time_entry = staticmethod(transaction.atomic(lambda tenant_id, actor_id, entry_id, expected_version, idempotency_key: TimeEntryService._archive(tenant_id, actor_id, entry_id, expected_version, idempotency_key, True)))


class MilestoneService:
    @staticmethod
    @transaction.atomic
    def create_milestone(tenant_id, actor_id, data, idempotency_key):
        payload = dict(data); payload["project"] = _project(tenant_id, payload["project"]); milestone = ProjectMilestone(tenant_id=_tenant(tenant_id), **payload); milestone.save(); ActivityService.record(tenant_id, actor_id, "milestone", milestone.id, "milestone.changed", project=milestone.project, after=_snapshot(milestone), idempotency_key=idempotency_key, fingerprint=_fingerprint("milestone.create", data)); return milestone
    @staticmethod
    @transaction.atomic
    def update_milestone(tenant_id, actor_id, milestone_id, data, expected_version, idempotency_key):
        milestone = MilestoneService._get(tenant_id, milestone_id, True); _version(milestone, expected_version)
        for k in {"milestone_name", "target_date", "description"} & data.keys(): setattr(milestone, k, data[k])
        milestone.version += 1; milestone.save(); ActivityService.record(tenant_id, actor_id, "milestone", milestone.id, "milestone.changed", project=milestone.project, after=_snapshot(milestone), idempotency_key=idempotency_key, fingerprint=_fingerprint("milestone.update", data)); return milestone
    @staticmethod
    def _get(tenant_id, milestone_id, lock=False):
        qs = ProjectMilestone.all_objects.for_tenant(_tenant(tenant_id)); qs = qs.select_for_update() if lock else qs
        try: return qs.get(pk=_uuid(milestone_id))
        except ProjectMilestone.DoesNotExist as exc: raise ProjectManagementError("Milestone was not found.", "NOT_FOUND") from exc
    @staticmethod
    def _lifecycle(tenant_id, actor_id, milestone_id, action, key, achieved_date=None):
        milestone = MilestoneService._get(tenant_id, milestone_id, True)
        if action == "achieve":
            achieved = achieved_date if isinstance(achieved_date, date) else date.fromisoformat(str(achieved_date));
            if milestone.project.start_date and achieved < milestone.project.start_date: raise ProjectManagementError("Achieved date cannot precede project start.", "INVALID_DATE")
            milestone.achieved_date, milestone.cancelled_at = achieved, None
        elif action == "reopen": milestone.achieved_date = None; milestone.cancelled_at = None
        elif action == "cancel": milestone.achieved_date = None; milestone.cancelled_at = timezone.now()
        milestone.version += 1; milestone.save(); ActivityService.record(tenant_id, actor_id, "milestone", milestone.id, "milestone.changed", project=milestone.project, after=_snapshot(milestone), idempotency_key=key, fingerprint=_fingerprint(f"milestone.{action}", {"id": milestone_id, "date": achieved_date})); return milestone
    achieve_milestone = staticmethod(transaction.atomic(lambda tenant_id, actor_id, milestone_id, achieved_date, idempotency_key: MilestoneService._lifecycle(tenant_id, actor_id, milestone_id, "achieve", idempotency_key, achieved_date)))
    reopen_milestone = staticmethod(transaction.atomic(lambda tenant_id, actor_id, milestone_id, idempotency_key: MilestoneService._lifecycle(tenant_id, actor_id, milestone_id, "reopen", idempotency_key)))
    cancel_milestone = staticmethod(transaction.atomic(lambda tenant_id, actor_id, milestone_id, idempotency_key: MilestoneService._lifecycle(tenant_id, actor_id, milestone_id, "cancel", idempotency_key)))
    @staticmethod
    def _archive(tenant_id, actor_id, milestone_id, expected_version, key, restore):
        milestone = MilestoneService._get(tenant_id, milestone_id, True); _version(milestone, expected_version); milestone.archived_at = None if restore else timezone.now(); milestone.archived_by_id = None if restore else _actor(actor_id); milestone.version += 1; milestone.save(); ActivityService.record(tenant_id, actor_id, "milestone", milestone.id, "milestone.changed", project=milestone.project, after=_snapshot(milestone), idempotency_key=key, fingerprint=_fingerprint("milestone.archive", {"id": milestone_id, "restore": restore})); return milestone
    archive_milestone = staticmethod(transaction.atomic(lambda tenant_id, actor_id, milestone_id, expected_version, idempotency_key: MilestoneService._archive(tenant_id, actor_id, milestone_id, expected_version, idempotency_key, False)))
    restore_milestone = staticmethod(transaction.atomic(lambda tenant_id, actor_id, milestone_id, expected_version, idempotency_key: MilestoneService._archive(tenant_id, actor_id, milestone_id, expected_version, idempotency_key, True)))


class ConfigurationService:
    FIELDS = {"default_currency", "project_code_pattern", "task_code_pattern", "max_daily_hours", "max_allocation_percentage", "enforce_project_date_bounds", "allow_future_time_entries", "require_time_description", "default_billable", "enabled_views", "paid_extension_rollout"}
    DEFAULTS = {"default_currency": "USD", "project_code_pattern": r"^[A-Z][A-Z0-9-]{0,49}$", "task_code_pattern": r"^[A-Z][A-Z0-9-]{0,49}$", "max_daily_hours": Decimal("12.00"), "max_allocation_percentage": Decimal("100.00"), "enforce_project_date_bounds": True, "allow_future_time_entries": False, "require_time_description": True, "default_billable": False, "enabled_views": ["list"], "paid_extension_rollout": {}}
    @staticmethod
    def runtime_environment():
        from django.conf import settings
        value = str(getattr(settings, "SARAISE_MODE", "development")); return value if value in ConfigurationEnvironment.values else ConfigurationEnvironment.DEVELOPMENT
    @staticmethod
    def _validate(values):
        unknown = set(values) - ConfigurationService.FIELDS
        if unknown: raise ProjectManagementError(f"Unknown configuration fields: {', '.join(sorted(unknown))}.", "UNKNOWN_FIELD")
        merged = {**ConfigurationService.DEFAULTS, **values}; currency = str(merged["default_currency"]).upper()
        if len(currency) != 3 or not currency.isalpha(): raise ProjectManagementError("default_currency must be a three-letter code.", "INVALID_CURRENCY")
        merged["default_currency"] = currency
        for name in ("project_code_pattern", "task_code_pattern"):
            pattern = str(merged[name]);
            if len(pattern) > 255 or not pattern.startswith("^") or not pattern.endswith("$") or "(?" in pattern or re.search(r"([+*}])\s*[+*{]", pattern): raise ProjectManagementError(f"{name} must be a safe anchored regular expression.", "UNSAFE_REGEX")
            try: re.compile(pattern)
            except re.error as exc: raise ProjectManagementError(f"{name} is invalid.", "UNSAFE_REGEX") from exc
        merged["max_daily_hours"] = Decimal(str(merged["max_daily_hours"])); merged["max_allocation_percentage"] = Decimal(str(merged["max_allocation_percentage"]))
        if not Decimal("0") < merged["max_daily_hours"] <= Decimal("24"): raise ProjectManagementError("max_daily_hours must be between 0 and 24.", "SAFE_LIMIT")
        if not Decimal("0") < merged["max_allocation_percentage"] <= Decimal("100"): raise ProjectManagementError("max_allocation_percentage must be between 0 and 100.", "SAFE_LIMIT")
        views = merged["enabled_views"]
        if not isinstance(views, list) or len(views) != len(set(views)) or not set(views) <= {"list", "board", "calendar", "timeline"}: raise ProjectManagementError("enabled_views contains unsupported or duplicate values.", "INVALID_JSON_SCHEMA")
        rollout = merged["paid_extension_rollout"]
        if not isinstance(rollout, dict) or any(not isinstance(k, str) or not isinstance(v, (bool, list, str)) for k, v in rollout.items()): raise ProjectManagementError("paid_extension_rollout has an invalid schema.", "INVALID_JSON_SCHEMA")
        return merged
    @staticmethod
    @transaction.atomic
    def get_active(tenant_id, environment):
        tenant = _tenant(tenant_id)
        if environment not in ConfigurationEnvironment.values: raise ProjectManagementError("Unknown environment.", "INVALID_ENVIRONMENT")
        config, _ = ProjectManagementConfiguration.objects.get_or_create(tenant_id=tenant, environment=environment)
        if config.active_version_id: return ProjectManagementConfigurationVersion.objects.for_tenant(tenant).get(pk=config.active_version_id)
        system = uuid.UUID(int=0); version = ProjectManagementConfigurationVersion(tenant_id=tenant, configuration=config, version=1, state=ConfigurationState.ACTIVE, change_summary="Initial safe defaults", created_by_id=system, **ConfigurationService.DEFAULTS); version.save(); config.active_version = version; config.save(update_fields=["active_version", "updated_at"]); return version
    @staticmethod
    @transaction.atomic
    def create_draft(tenant_id, actor_id, environment, values, change_summary):
        active = ConfigurationService.get_active(tenant_id, environment); merged = ConfigurationService._validate({**{f: getattr(active, f) for f in ConfigurationService.FIELDS}, **values}); version = ProjectManagementConfigurationVersion.objects.filter(configuration=active.configuration).aggregate(v=models.Max("version"))["v"] + 1; draft = ProjectManagementConfigurationVersion(tenant_id=_tenant(tenant_id), configuration=active.configuration, version=version, state=ConfigurationState.DRAFT, change_summary=_required(change_summary, "change_summary", 500), created_by_id=_actor(actor_id), **merged); draft.save(); return draft
    @staticmethod
    def simulate(tenant_id, draft_id):
        try: draft = ProjectManagementConfigurationVersion.objects.for_tenant(_tenant(tenant_id)).get(pk=_uuid(draft_id), state=ConfigurationState.DRAFT)
        except ProjectManagementConfigurationVersion.DoesNotExist as exc: raise ProjectManagementError("Draft was not found.", "NOT_FOUND") from exc
        config = ConfigurationService._validate({f: getattr(draft, f) for f in ConfigurationService.FIELDS}); invalid_projects = Project.objects.for_tenant(_tenant(tenant_id)).filter(archived_at__isnull=True).exclude(project_code__regex=config["project_code_pattern"]).count(); invalid_tasks = Task.objects.for_tenant(_tenant(tenant_id)).filter(archived_at__isnull=True).exclude(task_code__regex=config["task_code_pattern"]).count(); over_allocated = ProjectMember.objects.for_tenant(_tenant(tenant_id)).filter(archived_at__isnull=True, allocation_percentage__gt=config["max_allocation_percentage"]).count(); return {"valid": not any([invalid_projects, invalid_tasks, over_allocated]), "errors": [], "affected_records": {"invalid_project_codes": invalid_projects, "invalid_task_codes": invalid_tasks, "over_allocated_members": over_allocated}}
    @staticmethod
    @transaction.atomic
    def publish(tenant_id, actor_id, draft_id, idempotency_key):
        try: draft = ProjectManagementConfigurationVersion.objects.for_tenant(_tenant(tenant_id)).select_for_update().get(pk=_uuid(draft_id), state=ConfigurationState.DRAFT)
        except ProjectManagementConfigurationVersion.DoesNotExist as exc: raise ProjectManagementError("Draft was not found.", "NOT_FOUND") from exc
        result = ConfigurationService.simulate(tenant_id, draft.id)
        if not result["valid"]: raise ProjectManagementError("Configuration would invalidate existing records.", "SIMULATION_FAILED")
        ProjectManagementConfigurationVersion.objects.filter(pk=draft.configuration.active_version_id)._service_update(state=ConfigurationState.SUPERSEDED)
        ProjectManagementConfigurationVersion.objects.filter(pk=draft.pk)._service_update(state=ConfigurationState.ACTIVE)
        draft.configuration.active_version_id = draft.id; draft.configuration.save(update_fields=["active_version", "updated_at"]); draft.refresh_from_db()
        ActivityService.record(tenant_id, actor_id, "configuration", draft.id, "configuration.published", after={"version": draft.version}, idempotency_key=idempotency_key, fingerprint=_fingerprint("configuration.publish", {"id": draft.id})); return draft
    @staticmethod
    def export_document(tenant_id, environment):
        active = ConfigurationService.get_active(tenant_id, environment); return {"schema_version": "1.0", "environment": environment, "configuration_version": active.version, "values": {f: str(getattr(active, f)) if isinstance(getattr(active, f), Decimal) else getattr(active, f) for f in ConfigurationService.FIELDS}}
    @staticmethod
    def import_document(tenant_id, actor_id, document):
        if not isinstance(document, dict) or document.get("schema_version") != "1.0" or not isinstance(document.get("values"), dict): raise ProjectManagementError("Unsupported configuration document.", "INVALID_DOCUMENT")
        return ConfigurationService.create_draft(tenant_id, actor_id, document.get("environment", ConfigurationService.runtime_environment()), document["values"], "Imported configuration")
    @staticmethod
    @transaction.atomic
    def rollback(tenant_id, actor_id, target_version, idempotency_key):
        tenant = _tenant(tenant_id)
        try: target = ProjectManagementConfigurationVersion.objects.for_tenant(tenant).get(version=int(target_version))
        except ProjectManagementConfigurationVersion.DoesNotExist as exc: raise ProjectManagementError("Configuration version was not found.", "NOT_FOUND") from exc
        values = {f: getattr(target, f) for f in ConfigurationService.FIELDS}; draft = ConfigurationService.create_draft(tenant, actor_id, target.configuration.environment, values, f"Rollback to version {target.version}"); return ConfigurationService.publish(tenant, actor_id, draft.id, idempotency_key)
