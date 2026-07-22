"""Authoritative migration aggregate state graphs."""
from src.core.state_machine import StateMachine, Transition
from .models import MigrationJob, MigrationRollback, MigrationRun

JOB_MACHINE = StateMachine(model=MigrationJob, name="data_migration.job", states=("draft", "ready", "archived"), transitions=(Transition("validate", "draft", "ready"), Transition("revise", "ready", "draft"), Transition("archive", "draft", "archived"), Transition("archive", "ready", "archived"), Transition("restore", "archived", "draft")))
RUN_MACHINE = StateMachine(model=MigrationRun, name="data_migration.run", states=("queued", "running", "succeeded", "partial", "failed", "cancelled", "rolled_back"), terminal_states=("failed", "cancelled", "rolled_back"), transitions=(Transition("start", "queued", "running"), Transition("succeed", "running", "succeeded"), Transition("partial", "running", "partial"), Transition("fail", "queued", "failed"), Transition("fail", "running", "failed"), Transition("cancel", "queued", "cancelled"), Transition("cancel", "running", "cancelled"), Transition("mark_rolled_back", "succeeded", "rolled_back"), Transition("mark_rolled_back", "partial", "rolled_back")))
ROLLBACK_MACHINE = StateMachine(model=MigrationRollback, name="data_migration.rollback", states=("queued", "running", "succeeded", "failed"), terminal_states=("succeeded", "failed"), transitions=(Transition("start", "queued", "running"), Transition("succeed", "running", "succeeded"), Transition("fail", "queued", "failed"), Transition("fail", "running", "failed")))

__all__ = ["JOB_MACHINE", "ROLLBACK_MACHINE", "RUN_MACHINE"]
