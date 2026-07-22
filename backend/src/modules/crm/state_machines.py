"""Guarded CRM state machines and a non-bypassable extension surface."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol, cast
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.state_machine import (
    GuardFailedError,
    IdempotencyConflictError,
    IllegalTransitionError,
    StateMachine,
    StateMachineError,
    TerminalStateError,
    Transition,
    TransitionRecord,
    UnknownCommandError,
    registry,
)

from .models import Lead, LeadStatus, Opportunity, OpportunityStage, OpportunityStatus


def _positive_amount(value: object) -> bool:
    try:
        return value is not None and Decimal(str(value)) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def conversion_ready(lead: Lead, context: Mapping[str, object]) -> bool:
    """Require complete deterministic conversion input before terminal state."""

    has_identity = bool(str(getattr(lead, "email", "") or "").strip()) or bool(
        str(getattr(lead, "company", "") or "").strip()
    )
    account_resolved = bool(context.get("account_id") or context.get("account_created"))
    return has_identity and account_resolved and _positive_amount(context.get("opportunity_amount"))


def confirmed_close(_opportunity: Opportunity, context: Mapping[str, object]) -> bool:
    """Terminal wins require an explicit confirmation from the command DTO."""

    return context.get("confirmed") is True


def has_loss_reason(_opportunity: Opportunity, context: Mapping[str, object]) -> bool:
    """A loss is auditable only when the caller supplies a meaningful reason."""

    return bool(str(context.get("reason") or "").strip())


def allow_backward(_opportunity: Opportunity, context: Mapping[str, object]) -> bool:
    """Backward movement can only become stricter through extensions."""

    return context.get("allow_backward") is True and bool(str(context.get("reason") or "").strip())


LEAD_MACHINE: Final[StateMachine[Lead]] = StateMachine(
    name="crm.lead",
    model=Lead,
    states=tuple(LeadStatus.values),
    terminal_states=(LeadStatus.CONVERTED, LeadStatus.LOST),
    state_field="status",
    history_field="transition_history",
    guards={"conversion_ready": conversion_ready},
    transitions=(
        {"command": "contact", "from": LeadStatus.NEW, "to": LeadStatus.CONTACTED},
        {
            "command": "qualify",
            "from": (LeadStatus.NEW, LeadStatus.CONTACTED),
            "to": LeadStatus.QUALIFIED,
        },
        {
            "command": "disqualify",
            "from": (LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.QUALIFIED),
            "to": LeadStatus.LOST,
        },
        {
            "command": "convert",
            "from": LeadStatus.QUALIFIED,
            "to": LeadStatus.CONVERTED,
            "guards": "conversion_ready",
        },
    ),
)

_OPEN_STAGES: Final = (
    OpportunityStage.PROSPECTING,
    OpportunityStage.QUALIFICATION,
    OpportunityStage.NEEDS_ANALYSIS,
    OpportunityStage.PROPOSAL,
    OpportunityStage.NEGOTIATION,
)

_opportunity_transitions: list[Mapping[str, object]] = [
    {
        "command": "advance_to_qualification",
        "from": OpportunityStage.PROSPECTING,
        "to": OpportunityStage.QUALIFICATION,
    },
    {
        "command": "advance_to_needs_analysis",
        "from": OpportunityStage.QUALIFICATION,
        "to": OpportunityStage.NEEDS_ANALYSIS,
    },
    {
        "command": "advance_to_proposal",
        "from": OpportunityStage.NEEDS_ANALYSIS,
        "to": OpportunityStage.PROPOSAL,
    },
    {
        "command": "advance_to_negotiation",
        "from": OpportunityStage.PROPOSAL,
        "to": OpportunityStage.NEGOTIATION,
    },
    {
        "command": "close_won",
        "from": _OPEN_STAGES,
        "to": OpportunityStage.CLOSED_WON,
        "guards": "confirmed_close",
    },
    {
        "command": "close_lost",
        "from": _OPEN_STAGES,
        "to": OpportunityStage.CLOSED_LOST,
        "guards": "has_loss_reason",
    },
]
for target_index, target in enumerate(_OPEN_STAGES[:-1]):
    _opportunity_transitions.append(
        {
            "command": f"reopen_to_{target}",
            "from": _OPEN_STAGES[target_index + 1 :],
            "to": target,
            "guards": "allow_backward",
        }
    )

OPPORTUNITY_MACHINE: Final[StateMachine[Opportunity]] = StateMachine(
    name="crm.opportunity",
    model=Opportunity,
    states=tuple(OpportunityStage.values),
    terminal_states=(OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST),
    state_field="stage",
    history_field="transition_history",
    guards={
        "allow_backward": allow_backward,
        "confirmed_close": confirmed_close,
        "has_loss_reason": has_loss_reason,
    },
    transitions=tuple(_opportunity_transitions),
)


@dataclass(frozen=True, slots=True)
class TransitionExtensionContext:
    """PII-free input delivered to paid-module transition contributions."""

    tenant_id: str
    machine: str
    aggregate_id: str
    command: str
    source: str
    target: str
    actor_id: str | None
    correlation_id: str
    transition_key: str


@dataclass(frozen=True, slots=True)
class ExtensionGuardDecision:
    """Extensions may veto a core-approved transition, never grant one."""

    allowed: bool
    code: str = "allowed"


class TransitionGuardExtension(Protocol):
    schema_version: str

    def evaluate(self, context: TransitionExtensionContext) -> ExtensionGuardDecision: ...


@dataclass(frozen=True, slots=True)
class ExtensionEffectRequest:
    """Declarative post-transition request persisted through the outbox."""

    event_type: str
    payload: Mapping[str, object]
    idempotency_key: str


class TransitionEffectExtension(Protocol):
    schema_version: str

    def build(self, context: TransitionExtensionContext) -> ExtensionEffectRequest | None: ...


class CRMStateMachineExtensionRegistry:
    """Versioned, ordered registrations that cannot replace core machines."""

    def __init__(self) -> None:
        self._guards: dict[tuple[str, str], tuple[int, TransitionGuardExtension]] = {}
        self._effects: dict[tuple[str, str], tuple[int, TransitionEffectExtension]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _validate(machine: str, provider: str, extension: object, priority: int) -> None:
        if machine not in {"crm.lead", "crm.opportunity"}:
            raise ValueError("extensions may target crm.lead or crm.opportunity")
        if not provider or len(provider) > 160:
            raise ValueError("provider must be a bounded non-empty identifier")
        if getattr(extension, "schema_version", None) != "1.0":
            raise ValueError("CRM transition extension schema_version must be 1.0")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 10_000:
            raise ValueError("priority must be an integer from 0 to 10000")

    def register_guard(
        self,
        machine: str,
        provider: str,
        extension: TransitionGuardExtension,
        *,
        priority: int = 100,
    ) -> None:
        self._validate(machine, provider, extension, priority)
        key = (machine, provider)
        with self._lock:
            if key in self._guards:
                raise ValueError(f"guard contribution {provider!r} is already registered for {machine}")
            self._guards[key] = (priority, extension)

    def register_effect(
        self,
        machine: str,
        provider: str,
        extension: TransitionEffectExtension,
        *,
        priority: int = 100,
    ) -> None:
        self._validate(machine, provider, extension, priority)
        key = (machine, provider)
        with self._lock:
            if key in self._effects:
                raise ValueError(f"effect contribution {provider!r} is already registered for {machine}")
            self._effects[key] = (priority, extension)

    def guards(self, machine: str) -> tuple[TransitionGuardExtension, ...]:
        with self._lock:
            values = [
                (priority, provider, extension)
                for (registered_machine, provider), (priority, extension) in self._guards.items()
                if registered_machine == machine
            ]
        return tuple(extension for _, _, extension in sorted(values, key=lambda item: (item[0], item[1])))

    def effects(self, machine: str) -> tuple[TransitionEffectExtension, ...]:
        with self._lock:
            values = [
                (priority, provider, extension)
                for (registered_machine, provider), (priority, extension) in self._effects.items()
                if registered_machine == machine
            ]
        return tuple(extension for _, _, extension in sorted(values, key=lambda item: (item[0], item[1])))

    def unregister(self, machine: str, provider: str) -> None:
        with self._lock:
            self._guards.pop((machine, provider), None)
            self._effects.pop((machine, provider), None)


extension_registry: Final = CRMStateMachineExtensionRegistry()


class StaleTransitionVersionError(StateMachineError):
    """Raised when a transition is based on an obsolete aggregate version."""


def _required_transition_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 255:
        raise ValueError("transition_key must be a bounded non-empty string")
    return value.strip()


def _actor(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or len(normalized) > 255:
        raise ValueError("actor_id must be a bounded non-empty identifier")
    return normalized


def _edge(machine: StateMachine[Lead] | StateMachine[Opportunity], command: str, source: str) -> Transition:
    if source in machine.terminal_states:
        raise TerminalStateError(f"{machine.name} is immutable in terminal state {source!r}")
    commands = {candidate.command for candidate in machine.transitions}
    if command not in commands:
        raise UnknownCommandError(f"Machine {machine.name!r} has no command {command!r}")
    candidate = next(
        (item for item in machine.transitions if item.command == command and item.source == source),
        None,
    )
    if candidate is None:
        raise IllegalTransitionError(f"Command {command!r} cannot transition {machine.name} from {source!r}")
    return candidate


def _run_core_guards(edge: Transition, aggregate: Lead | Opportunity, context: Mapping[str, object]) -> None:
    for guard in edge.guards:
        try:
            accepted = guard(aggregate, context)
        except GuardFailedError:
            raise
        except Exception as exc:
            raise GuardFailedError(f"Guard {getattr(guard, '__name__', type(guard).__name__)!r} errored") from exc
        if accepted is not True:
            raise GuardFailedError(
                f"Guard {getattr(guard, '__name__', type(guard).__name__)!r} rejected the transition"
            )


def _extension_context(
    *,
    machine: str,
    aggregate: Lead | Opportunity,
    command: str,
    source: str,
    target: str,
    actor_id: str | None,
    correlation_id: str,
    transition_key: str,
) -> TransitionExtensionContext:
    return TransitionExtensionContext(
        tenant_id=str(aggregate.tenant_id),
        machine=machine,
        aggregate_id=str(aggregate.id),
        command=command,
        source=source,
        target=target,
        actor_id=actor_id,
        correlation_id=correlation_id,
        transition_key=transition_key,
    )


def _run_extension_guards(context: TransitionExtensionContext) -> None:
    for guard in extension_registry.guards(context.machine):
        decision = guard.evaluate(context)
        if not isinstance(decision, ExtensionGuardDecision):
            raise GuardFailedError("CRM extension guard returned an invalid decision")
        if not decision.allowed:
            raise GuardFailedError(f"CRM extension rejected transition with code {decision.code!r}")


def transition_extension_effects(context: TransitionExtensionContext) -> tuple[ExtensionEffectRequest, ...]:
    """Build deterministic declarative effects after core persistence succeeds."""

    effects: list[ExtensionEffectRequest] = []
    for extension in extension_registry.effects(context.machine):
        effect = extension.build(context)
        if effect is not None:
            if not effect.event_type or not effect.idempotency_key:
                raise ValueError("extension effects require event_type and idempotency_key")
            effects.append(effect)
    return tuple(effects)


def apply_lead_command(
    tenant_id: object,
    *,
    lead_id: object,
    command: str,
    transition_key: str,
    actor_id: str | None,
    correlation_id: str,
    expected_version: int | None = None,
    context: Mapping[str, object] | None = None,
    opportunity_id: object | None = None,
) -> Lead:
    """Persist lead state and conversion effects in one validated save."""

    key = _required_transition_key(transition_key)
    actor = _actor(actor_id)
    guard_context = dict(context or {})
    if command == "convert" and opportunity_id is None:
        opportunity_id = guard_context.get("opportunity_id")
    with transaction.atomic():
        lead = cast(
            Lead,
            Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False),
        )
        existing = LEAD_MACHINE.recorder.find(lead, key)
        if existing is not None:
            if existing.command != command:
                raise IdempotencyConflictError(
                    f"Transition key {key!r} already belongs to command {existing.command!r}"
                )
            return lead
        if expected_version is not None and lead.version != expected_version:
            raise StaleTransitionVersionError(
                f"Expected lead version {expected_version}, current version is {lead.version}"
            )
        source = str(lead.status)
        edge = _edge(LEAD_MACHINE, command, source)
        _run_core_guards(edge, lead, guard_context)
        extension_context = _extension_context(
            machine="crm.lead",
            aggregate=lead,
            command=command,
            source=source,
            target=edge.target,
            actor_id=actor,
            correlation_id=correlation_id,
            transition_key=key,
        )
        _run_extension_guards(extension_context)

        occurred_at = timezone.now()
        record = TransitionRecord(
            transition_key=key,
            command=command,
            from_state=source,
            to_state=edge.target,
            occurred_at=occurred_at.astimezone(datetime_timezone.utc).isoformat(),
            metadata={
                "actor_id": actor,
                "correlation_id": correlation_id,
            },
        )
        lead.status = edge.target
        if command == "convert":
            if opportunity_id is None:
                raise GuardFailedError("Conversion requires a persisted opportunity identifier")
            lead.converted_at = occurred_at
            try:
                lead.converted_to_opportunity_id = (
                    opportunity_id if isinstance(opportunity_id, UUID) else UUID(str(opportunity_id))
                )
            except (TypeError, ValueError, AttributeError) as exc:
                raise GuardFailedError("Conversion requires a valid opportunity identifier") from exc
        LEAD_MACHINE.recorder.record(lead, record)
        lead.updated_by = actor
        lead.version += 1
        lead.save(
            update_fields={
                "status",
                "converted_at",
                "converted_to_opportunity_id",
                "transition_history",
                "updated_by",
                "version",
                "updated_at",
            }
        )
        return lead


_STAGE_PROBABILITY: Final[Mapping[str, int]] = {
    OpportunityStage.PROSPECTING: 10,
    OpportunityStage.QUALIFICATION: 20,
    OpportunityStage.NEEDS_ANALYSIS: 40,
    OpportunityStage.PROPOSAL: 60,
    OpportunityStage.NEGOTIATION: 80,
    OpportunityStage.CLOSED_WON: 100,
    OpportunityStage.CLOSED_LOST: 0,
}


def apply_opportunity_command(
    tenant_id: object,
    *,
    opportunity_id: object,
    command: str,
    transition_key: str,
    actor_id: str | None,
    correlation_id: str,
    expected_version: int | None,
    reason: str | None = None,
    allow_backward_transition: bool = False,
    confirmed: bool = False,
) -> Opportunity:
    """Persist stage, derived status, probability, and close fields atomically."""

    key = _required_transition_key(transition_key)
    actor = _actor(actor_id)
    normalized_reason = str(reason or "").strip()
    context: dict[str, object] = {
        "reason": normalized_reason,
        "allow_backward": allow_backward_transition,
        "confirmed": confirmed,
    }
    with transaction.atomic():
        opportunity = cast(
            Opportunity,
            Opportunity.objects.select_for_update().get(id=opportunity_id, tenant_id=tenant_id, is_deleted=False),
        )
        existing = OPPORTUNITY_MACHINE.recorder.find(opportunity, key)
        if existing is not None:
            if existing.command != command:
                raise IdempotencyConflictError(
                    f"Transition key {key!r} already belongs to command {existing.command!r}"
                )
            return opportunity
        if expected_version is not None and opportunity.version != expected_version:
            raise StaleTransitionVersionError(
                f"Expected opportunity version {expected_version}, current version is {opportunity.version}"
            )
        source = str(opportunity.stage)
        edge = _edge(OPPORTUNITY_MACHINE, command, source)
        _run_core_guards(edge, opportunity, context)
        extension_context = _extension_context(
            machine="crm.opportunity",
            aggregate=opportunity,
            command=command,
            source=source,
            target=edge.target,
            actor_id=actor,
            correlation_id=correlation_id,
            transition_key=key,
        )
        _run_extension_guards(extension_context)

        occurred_at = timezone.now()
        record = TransitionRecord(
            transition_key=key,
            command=command,
            from_state=source,
            to_state=edge.target,
            occurred_at=occurred_at.astimezone(datetime_timezone.utc).isoformat(),
            metadata={
                "actor_id": actor,
                "correlation_id": correlation_id,
                "reason_supplied": bool(normalized_reason),
            },
        )
        opportunity.stage = edge.target
        opportunity.probability = _STAGE_PROBABILITY[edge.target]
        if edge.target == OpportunityStage.CLOSED_WON:
            opportunity.status = OpportunityStatus.WON
            opportunity.closed_at = occurred_at
            opportunity.loss_reason = ""
        elif edge.target == OpportunityStage.CLOSED_LOST:
            opportunity.status = OpportunityStatus.LOST
            opportunity.closed_at = occurred_at
            opportunity.loss_reason = normalized_reason
        else:
            opportunity.status = OpportunityStatus.OPEN
            opportunity.closed_at = None
            opportunity.loss_reason = ""
        OPPORTUNITY_MACHINE.recorder.record(opportunity, record)
        opportunity.updated_by = actor
        opportunity.version += 1
        opportunity.save(
            update_fields={
                "stage",
                "probability",
                "status",
                "closed_at",
                "loss_reason",
                "transition_history",
                "updated_by",
                "version",
                "updated_at",
            }
        )
        return opportunity


def register_state_machines() -> None:
    """Install CRM machines without permitting implicit replacement."""

    for name, machine in (("crm.lead", LEAD_MACHINE), ("crm.opportunity", OPPORTUNITY_MACHINE)):
        current = None
        try:
            current = registry.get(name)
        except LookupError:
            pass
        if current is None:
            registry.register(name, machine)
        elif current is not machine:
            raise RuntimeError(f"A different state machine is already registered as {name!r}")


__all__ = [
    "CRMStateMachineExtensionRegistry",
    "ExtensionEffectRequest",
    "ExtensionGuardDecision",
    "LEAD_MACHINE",
    "OPPORTUNITY_MACHINE",
    "TransitionEffectExtension",
    "TransitionExtensionContext",
    "TransitionGuardExtension",
    "allow_backward",
    "apply_lead_command",
    "apply_opportunity_command",
    "confirmed_close",
    "conversion_ready",
    "extension_registry",
    "has_loss_reason",
    "register_state_machines",
    "StaleTransitionVersionError",
    "transition_extension_effects",
]
