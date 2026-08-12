"""
Service tests for Project Management module.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.modules.project_management.models import ProjectActivity, ProjectStatus, TaskStatus
from src.modules.project_management.services import (
    ActivityService,
    ConfigurationService,
    IdempotencyConflictError,
    MilestoneService,
    ProjectManagementError,
    ProjectMemberService,
    ProjectService,
    TaskService,
    TimeEntryService,
)


@pytest.mark.django_db
class TestProjectService:
    """Test ProjectService."""

    def test_create_project(self):
        """Test creating a project via service."""
        tenant_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id=str(tenant_id),
            project_code="PROJ-001",
            project_name="Test Project",
        )

        assert project.project_code == "PROJ-001"
        assert project.project_name == "Test Project"
        assert str(project.tenant_id) == str(tenant_id)

    def test_create_project_replays_matching_idempotency_and_rejects_conflict(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        first = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-100", "project_name": "Original"},
            "create-project-once",
        )
        replay = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-100", "project_name": "Original"},
            "create-project-once",
        )

        assert replay.id == first.id
        assert (
            ProjectActivity.objects.for_tenant(tenant_id)
            .filter(
                action="project.created",
                metadata__idempotency_key="create-project-once",
            )
            .count()
            == 1
        )

        with pytest.raises(IdempotencyConflictError):
            ProjectService.create_project(
                tenant_id,
                actor_id,
                {"project_code": "PROJ-101", "project_name": "Different"},
                "create-project-once",
            )

    def test_project_transition_guards_emit_outbox_and_replay(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {
                "project_code": "PROJ-200",
                "project_name": "Launch",
                "start_date": timezone.localdate(),
                "project_manager_id": actor_id,
            },
            "create-transition-project",
        )

        active = ProjectService.transition_project(tenant_id, actor_id, project.id, "activate", "activate-once")
        replay = ProjectService.transition_project(tenant_id, actor_id, project.id, "activate", "activate-once")

        assert active.status == ProjectStatus.ACTIVE
        assert replay.id == active.id
        assert active.transition_history[-1]["command"] == "activate"
        assert OutboxEvent.objects.filter(
            tenant_id=tenant_id,
            aggregate_id=project.id,
            event_type="project_management.project.transitioned",
        ).exists()

        with pytest.raises(ProjectManagementError) as exc:
            ProjectService.transition_project(tenant_id, actor_id, project.id, "activate", "activate-again")
        assert exc.value.code == "ILLEGAL_TRANSITION"

    def test_project_completion_requires_terminal_children(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {
                "project_code": "PROJ-300",
                "project_name": "Delivery",
                "start_date": timezone.localdate(),
                "project_manager_id": actor_id,
            },
            "create-completion-project",
        )
        active = ProjectService.transition_project(tenant_id, actor_id, project.id, "activate", "activate-completion")
        task = TaskService.create_task(
            tenant_id,
            actor_id,
            {"project": active.id, "task_code": "TASK-1", "task_name": "Build"},
            "create-open-task",
        )

        with pytest.raises(ProjectManagementError) as exc:
            ProjectService.transition_project(tenant_id, actor_id, project.id, "complete", "complete-blocked")
        assert exc.value.code == "INCOMPLETE_TASKS"

        started = TaskService.transition_task(tenant_id, actor_id, task.id, "start", "task-start")
        TaskService.transition_task(tenant_id, actor_id, started.id, "complete", "task-complete")
        completed = ProjectService.transition_project(tenant_id, actor_id, project.id, "complete", "complete-open")
        assert completed.status == ProjectStatus.COMPLETED

    def test_task_block_requires_reason_and_unblock_target_is_validated(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-400", "project_name": "Tasks"},
            "create-task-project",
        )
        task = TaskService.create_task(
            tenant_id,
            actor_id,
            {"project": project.id, "task_code": "TASK-2", "task_name": "Investigate"},
            "create-task-2",
        )

        with pytest.raises(ProjectManagementError) as exc:
            TaskService.transition_task(tenant_id, actor_id, task.id, "block", "block-without-reason")
        assert exc.value.code == "BLOCK_REASON_REQUIRED"

        blocked = TaskService.transition_task(tenant_id, actor_id, task.id, "block", "block-with-reason", "Waiting")
        assert blocked.status == TaskStatus.BLOCKED

        with pytest.raises(ProjectManagementError) as exc:
            TaskService.transition_task(
                tenant_id,
                actor_id,
                task.id,
                "unblock",
                "unblock-invalid",
                target_state=TaskStatus.DONE,
            )
        assert exc.value.code == "INVALID_TARGET_STATE"

        unblocked = TaskService.transition_task(
            tenant_id,
            actor_id,
            task.id,
            "unblock",
            "unblock-valid",
            target_state=TaskStatus.TODO,
        )
        assert unblocked.status == TaskStatus.TODO

    def test_time_entry_enforces_daily_limit_and_recalculates_task_actual_hours(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-500", "project_name": "Timesheets"},
            "create-time-project",
        )
        task = TaskService.create_task(
            tenant_id,
            actor_id,
            {"project": project.id, "task_code": "TASK-3", "task_name": "Implement"},
            "create-time-task",
        )
        entry = TimeEntryService.create_time_entry(
            tenant_id,
            actor_id,
            {
                "project": project.id,
                "task": task.id,
                "employee_id": employee_id,
                "entry_date": timezone.localdate(),
                "hours_worked": Decimal("8.00"),
                "description": "Implementation work",
            },
            "time-entry-once",
        )

        task.refresh_from_db()
        assert entry.billable is False
        assert task.actual_hours == Decimal("8.00")

        with pytest.raises(ProjectManagementError) as exc:
            TimeEntryService.create_time_entry(
                tenant_id,
                actor_id,
                {
                    "project": project.id,
                    "task": task.id,
                    "employee_id": employee_id,
                    "entry_date": timezone.localdate(),
                    "hours_worked": Decimal("5.00"),
                    "description": "Exceeds configured day",
                },
                "time-entry-over-limit",
            )
        assert exc.value.code == "DAILY_HOURS_LIMIT"

        with pytest.raises(ProjectManagementError) as exc:
            TimeEntryService.create_time_entry(
                tenant_id,
                actor_id,
                {
                    "project": project.id,
                    "employee_id": uuid.uuid4(),
                    "entry_date": timezone.localdate() + timedelta(days=1),
                    "hours_worked": Decimal("1.00"),
                    "description": "Future work",
                },
                "time-entry-future",
            )
        assert exc.value.code == "FUTURE_TIME_DISABLED"

    def test_activity_replay_requires_key_and_tenant_scoped_entity(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-600", "project_name": "Replay"},
            "create-replay-project",
        )

        with pytest.raises(ProjectManagementError) as exc:
            ActivityService.replay(tenant_id, "project.created", "", "fingerprint", type(project))
        assert exc.value.code == "IDEMPOTENCY_REQUIRED"

        assert (
            ActivityService.replay(
                uuid.uuid4(), "project.created", "create-replay-project", "fingerprint", type(project)
            )
            is None
        )

    def test_member_milestone_archive_restore_and_configuration_simulation_paths(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {
                "project_code": "PROJ-700",
                "project_name": "Configuration",
                "start_date": timezone.localdate(),
            },
            "create-config-project",
        )
        member = ProjectMemberService.add_member(
            tenant_id,
            actor_id,
            {
                "project": project.id,
                "employee_id": uuid.uuid4(),
                "role": "member",
                "allocation_percentage": Decimal("100.00"),
            },
            "member-add",
        )
        updated_member = ProjectMemberService.update_member(
            tenant_id,
            actor_id,
            member.id,
            {"role": "team_lead", "allocation_percentage": Decimal("90.00")},
            "member-update",
        )
        archived_member = ProjectMemberService.archive_member(tenant_id, actor_id, member.id, "member-archive")
        restored_member = ProjectMemberService.restore_member(tenant_id, actor_id, member.id, "member-restore")
        milestone = MilestoneService.create_milestone(
            tenant_id,
            actor_id,
            {
                "project": project.id,
                "milestone_name": "Launch",
                "target_date": timezone.localdate() + timedelta(days=5),
            },
            "milestone-add",
        )
        achieved = MilestoneService.achieve_milestone(
            tenant_id,
            actor_id,
            milestone.id,
            timezone.localdate() + timedelta(days=2),
            "milestone-achieve",
        )
        reopened = MilestoneService.reopen_milestone(tenant_id, actor_id, milestone.id, "milestone-reopen")
        cancelled = MilestoneService.cancel_milestone(tenant_id, actor_id, milestone.id, "milestone-cancel")
        archived_milestone = MilestoneService.archive_milestone(
            tenant_id, actor_id, milestone.id, cancelled.version, "milestone-archive"
        )
        restored_milestone = MilestoneService.restore_milestone(
            tenant_id, actor_id, milestone.id, archived_milestone.version, "milestone-restore"
        )
        draft = ConfigurationService.create_draft(
            tenant_id,
            actor_id,
            ConfigurationService.runtime_environment(),
            {"enabled_views": ["list", "board"], "default_currency": "usd"},
            "Enable board view",
        )
        simulation = ConfigurationService.simulate(tenant_id, draft.id)
        published = ConfigurationService.publish(tenant_id, actor_id, draft.id, "publish-config")
        exported = ConfigurationService.export_document(tenant_id, ConfigurationService.runtime_environment())
        imported = ConfigurationService.import_document(tenant_id, actor_id, exported)
        rolled_back = ConfigurationService.rollback(tenant_id, actor_id, 1, "rollback-config")

        assert updated_member.role == "team_lead"
        assert archived_member.archived_at is not None
        assert restored_member.archived_at is None
        assert achieved.achieved_date is not None
        assert reopened.achieved_date is None
        assert cancelled.cancelled_at is not None
        assert restored_milestone.archived_at is None
        assert simulation["valid"] is True
        assert published.state == "active"
        assert exported["values"]["default_currency"] == "USD"
        assert imported.state == "draft"
        assert rolled_back.version > published.version

    def test_configuration_and_member_fail_closed_validation_paths(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-800", "project_name": "Invalid config"},
            "create-invalid-config-project",
        )

        with pytest.raises(ProjectManagementError) as exc:
            ProjectMemberService.add_member(
                tenant_id,
                actor_id,
                {
                    "project": project.id,
                    "employee_id": uuid.uuid4(),
                    "role": "member",
                    "allocation_percentage": Decimal("101.00"),
                },
                "member-overallocated",
            )
        assert exc.value.code == "ALLOCATION_LIMIT"
        with pytest.raises(ProjectManagementError) as exc:
            ConfigurationService.create_draft(
                tenant_id,
                actor_id,
                ConfigurationService.runtime_environment(),
                {"project_code_pattern": ".*"},
                "Unsafe pattern",
            )
        assert exc.value.code == "UNSAFE_REGEX"
        with pytest.raises(ProjectManagementError) as exc:
            ConfigurationService.import_document(tenant_id, actor_id, {"schema_version": "0"})
        assert exc.value.code == "INVALID_DOCUMENT"

    def test_duplicate_project_copies_active_children_once_and_skips_archived_rows(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-900", "project_name": "Source"},
            "create-dup-source",
        )
        parent = TaskService.create_task(
            tenant_id,
            actor_id,
            {"project": project.id, "task_code": "TASK-10", "task_name": "Parent", "position": 1},
            "create-parent-task",
        )
        child = TaskService.create_task(
            tenant_id,
            actor_id,
            {
                "project": project.id,
                "parent_task": parent.id,
                "task_code": "TASK-11",
                "task_name": "Child",
                "position": 2,
            },
            "create-child-task",
        )
        archived = TaskService.create_task(
            tenant_id,
            actor_id,
            {"project": project.id, "task_code": "TASK-12", "task_name": "Archived"},
            "create-archived-task",
        )
        TaskService.archive_task(tenant_id, actor_id, archived.id, archived.version, "archive-before-duplicate")
        member = ProjectMemberService.add_member(
            tenant_id,
            actor_id,
            {"project": project.id, "employee_id": uuid.uuid4(), "role": "stakeholder"},
            "add-dup-member",
        )
        milestone = MilestoneService.create_milestone(
            tenant_id,
            actor_id,
            {
                "project": project.id,
                "milestone_name": "Launch",
                "target_date": timezone.localdate() + timedelta(days=10),
            },
            "add-dup-milestone",
        )

        clone = ProjectService.duplicate_project(
            tenant_id, actor_id, project.id, "PROJ-901", "Clone", "duplicate-project-once"
        )
        replay = ProjectService.duplicate_project(
            tenant_id, actor_id, project.id, "PROJ-901", "Clone", "duplicate-project-once"
        )

        assert replay.id == clone.id
        assert list(clone.tasks.order_by("position").values_list("task_code", flat=True)) == ["TASK-10", "TASK-11"]
        cloned_child = clone.tasks.get(task_code=child.task_code)
        assert cloned_child.parent_task is not None
        assert cloned_child.parent_task.task_code == parent.task_code
        assert clone.members.get(employee_id=member.employee_id).role == member.role
        assert clone.milestones.get(milestone_name=milestone.milestone_name).target_date == milestone.target_date

    def test_project_completion_requires_terminal_milestones(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {
                "project_code": "PROJ-910",
                "project_name": "Milestone gated",
                "start_date": timezone.localdate(),
                "project_manager_id": actor_id,
            },
            "create-milestone-gated-project",
        )
        ProjectService.transition_project(tenant_id, actor_id, project.id, "activate", "activate-milestone-gated")
        milestone = MilestoneService.create_milestone(
            tenant_id,
            actor_id,
            {
                "project": project.id,
                "milestone_name": "Approval",
                "target_date": timezone.localdate() + timedelta(days=1),
            },
            "create-open-milestone",
        )

        with pytest.raises(ProjectManagementError) as exc:
            ProjectService.transition_project(tenant_id, actor_id, project.id, "complete", "complete-with-open-mile")
        assert exc.value.code == "INCOMPLETE_MILESTONES"

        MilestoneService.cancel_milestone(tenant_id, actor_id, milestone.id, "cancel-open-mile")
        completed = ProjectService.transition_project(
            tenant_id, actor_id, project.id, "complete", "complete-after-mile"
        )
        assert completed.status == ProjectStatus.COMPLETED

    def test_task_member_and_time_entry_fail_closed_relationship_guards(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-920", "project_name": "Guards"},
            "create-guard-project",
        )
        other_project = ProjectService.create_project(
            other_tenant_id,
            actor_id,
            {"project_code": "PROJ-920", "project_name": "Other tenant"},
            "create-other-guard-project",
        )
        other_task = TaskService.create_task(
            other_tenant_id,
            actor_id,
            {"project": other_project.id, "task_code": "TASK-90", "task_name": "Foreign"},
            "create-foreign-task",
        )

        with pytest.raises(ProjectManagementError) as exc:
            TaskService.create_task(
                tenant_id,
                actor_id,
                {
                    "project": project.id,
                    "parent_task": other_task.id,
                    "task_code": "TASK-91",
                    "task_name": "Bad parent",
                },
                "create-cross-parent-task",
            )
        assert exc.value.code == "NOT_FOUND"

        with pytest.raises(ProjectManagementError) as exc:
            TaskService.create_task(
                tenant_id,
                actor_id,
                {"project": project.id, "task_code": "", "task_name": "Bad code"},
                "create-bad-code-task",
            )
        assert exc.value.code == "INVALID_INPUT"

        with pytest.raises(ProjectManagementError) as exc:
            TimeEntryService.create_time_entry(
                tenant_id,
                actor_id,
                {
                    "project": project.id,
                    "task": other_task.id,
                    "employee_id": uuid.uuid4(),
                    "entry_date": timezone.localdate(),
                    "hours_worked": Decimal("1.00"),
                    "description": "Cross project",
                },
                "create-cross-task-time",
            )
        assert exc.value.code == "TASK_PROJECT_MISMATCH"

        member = ProjectMemberService.add_member(
            tenant_id,
            actor_id,
            {"project": project.id, "employee_id": uuid.uuid4(), "role": "member"},
            "add-guard-member",
        )
        with pytest.raises(ProjectManagementError) as exc:
            ProjectMemberService.update_member(
                tenant_id,
                actor_id,
                member.id,
                {"allocation_percentage": Decimal("101.00")},
                "overallocate-existing-member",
            )
        assert exc.value.code == "ALLOCATION_LIMIT"

    def test_update_archive_restore_and_activity_listing_are_version_and_idempotency_guarded(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {"project_code": "PROJ-930", "project_name": "Mutable"},
            "create-mutable-project",
        )

        with pytest.raises(ProjectManagementError) as exc:
            ProjectService.update_project(
                tenant_id,
                actor_id,
                project.id,
                {"project_name": "Wrong version"},
                True,
                "update-bool-version",
            )
        assert exc.value.code == "STALE_VERSION"

        updated = ProjectService.update_project(
            tenant_id,
            actor_id,
            project.id,
            {"project_code": "proj-931", "project_name": "Renamed", "unknown": "ignored"},
            project.version,
            "update-project-once",
        )
        replay = ProjectService.update_project(
            tenant_id,
            actor_id,
            project.id,
            {"project_code": "proj-931", "project_name": "Renamed", "unknown": "ignored"},
            project.version,
            "update-project-once",
        )

        assert updated.project_code == "PROJ-931"
        assert replay.id == updated.id

        archived = ProjectService.archive_project(
            tenant_id, actor_id, updated.id, updated.version, "archive-project-once"
        )
        restored = ProjectService.restore_project(
            tenant_id, actor_id, archived.id, archived.version, "restore-project-once"
        )
        activities = list(
            ActivityService.list_for_project(
                tenant_id,
                restored.id,
                {"entity_type": "project", "entity_id": restored.id, "action": "project.updated"},
            )
        )

        assert archived.archived_at is not None
        assert restored.archived_at is None
        assert [activity.action for activity in activities] == ["project.updated"]

        with pytest.raises(IdempotencyConflictError):
            ProjectService.update_project(
                tenant_id,
                actor_id,
                project.id,
                {"project_name": "Conflicting replay"},
                project.version,
                "update-project-once",
            )

    def test_summaries_and_time_entry_updates_recalculate_old_and_new_tasks(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        today = timezone.localdate()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {
                "project_code": "PROJ-940",
                "project_name": "Summaries",
                "budget": Decimal("1000.00"),
                "start_date": today,
                "project_manager_id": actor_id,
            },
            "create-summary-project",
        )
        first_task = TaskService.create_task(
            tenant_id,
            actor_id,
            {"project": project.id, "task_code": "TASK-940", "task_name": "First", "due_date": today},
            "create-first-summary-task",
        )
        second_task = TaskService.create_task(
            tenant_id,
            actor_id,
            {"project": project.id, "task_code": "TASK-941", "task_name": "Second"},
            "create-second-summary-task",
        )
        TaskService.transition_task(tenant_id, actor_id, first_task.id, "start", "summary-task-start")
        TaskService.transition_task(tenant_id, actor_id, first_task.id, "complete", "summary-task-complete")
        entry = TimeEntryService.create_time_entry(
            tenant_id,
            actor_id,
            {
                "project": project.id,
                "task": first_task.id,
                "employee_id": employee_id,
                "entry_date": today,
                "hours_worked": Decimal("2.00"),
                "description": "Initial work",
            },
            "create-summary-entry",
        )

        moved = TimeEntryService.update_time_entry(
            tenant_id,
            actor_id,
            entry.id,
            {"task": second_task.id, "hours_worked": Decimal("3.00"), "description": "Moved work"},
            entry.version,
            "move-summary-entry",
        )
        archived = TimeEntryService.archive_time_entry(
            tenant_id, actor_id, moved.id, moved.version, "archive-summary-entry"
        )
        TimeEntryService.restore_time_entry(tenant_id, actor_id, archived.id, archived.version, "restore-summary-entry")

        first_task.refresh_from_db()
        second_task.refresh_from_db()
        project_summary = ProjectService.get_project_summary(tenant_id, project.id)
        portfolio_summary = ProjectService.get_portfolio_summary(tenant_id)

        assert first_task.actual_hours == Decimal("0.00")
        assert second_task.actual_hours == Decimal("3.00")
        assert project_summary["completed_task_count"] == 1
        assert project_summary["progress_percentage"] == Decimal("50.00")
        assert project_summary["time_hours"] == Decimal("3")
        assert project_summary["next_due_date"] == today
        assert portfolio_summary["budget_by_currency"] == [{"currency": "USD", "amount": Decimal("1000")}]

    def test_configuration_validation_rejects_bad_bounds_schema_and_missing_versions(settings):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        settings.SARAISE_MODE = "not-a-real-mode"
        assert ConfigurationService.runtime_environment() == "development"

        invalid_cases = [
            ({"unknown": True}, "UNKNOWN_FIELD"),
            ({"default_currency": "US1"}, "INVALID_CURRENCY"),
            ({"max_daily_hours": "0"}, "SAFE_LIMIT"),
            ({"max_allocation_percentage": "101"}, "SAFE_LIMIT"),
            ({"enabled_views": ["list", "list"]}, "INVALID_JSON_SCHEMA"),
            ({"paid_extension_rollout": {"bad": {"nested": True}}}, "INVALID_JSON_SCHEMA"),
        ]
        for patch, code in invalid_cases:
            with pytest.raises(ProjectManagementError) as exc:
                ConfigurationService.create_draft(
                    tenant_id,
                    actor_id,
                    ConfigurationService.runtime_environment(),
                    patch,
                    f"invalid {code}",
                )
            assert exc.value.code == code

        with pytest.raises(ProjectManagementError) as exc:
            ConfigurationService.get_active(tenant_id, "invalid-env")
        assert exc.value.code == "INVALID_ENVIRONMENT"

        with pytest.raises(ProjectManagementError) as exc:
            ConfigurationService.rollback(tenant_id, actor_id, 404, "rollback-missing-version")
        assert exc.value.code == "NOT_FOUND"

    def test_milestone_update_and_invalid_lifecycle_dates_fail_closed(self):
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id,
            actor_id,
            {
                "project_code": "PROJ-950",
                "project_name": "Milestone lifecycle",
                "start_date": timezone.localdate(),
            },
            "create-milestone-lifecycle-project",
        )
        milestone = MilestoneService.create_milestone(
            tenant_id,
            actor_id,
            {
                "project": project.id,
                "milestone_name": "Original",
                "target_date": timezone.localdate() + timedelta(days=10),
            },
            "create-lifecycle-milestone",
        )

        updated = MilestoneService.update_milestone(
            tenant_id,
            actor_id,
            milestone.id,
            {"milestone_name": "Updated", "description": "Reviewed"},
            milestone.version,
            "update-lifecycle-milestone",
        )

        assert updated.milestone_name == "Updated"

        with pytest.raises(ProjectManagementError) as exc:
            MilestoneService.achieve_milestone(
                tenant_id,
                actor_id,
                milestone.id,
                timezone.localdate() - timedelta(days=1),
                "achieve-before-project-start",
            )
        assert exc.value.code == "INVALID_DATE"
