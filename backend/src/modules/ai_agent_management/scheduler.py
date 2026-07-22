"""Compatibility import for durable outbox-backed scheduling."""
from .services import ScheduleService
AgentScheduler = ScheduleService
__all__ = ["AgentScheduler", "ScheduleService"]
