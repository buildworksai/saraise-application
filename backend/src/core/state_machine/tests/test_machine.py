"""Transactional behavior tests for :mod:`src.core.state_machine.machine`."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import pytest
from django.db import connection, models

from src.core.state_machine import (
    GuardFailedError,
    IdempotencyConflictError,
    IllegalTransitionError,
    StateMachine,
    StateMachineConfigurationError,
    TerminalStateError,
    Transition,
    TransitionRecord,
    UnknownCommandError,
)


class StateMachineOrder(models.Model):
    """Private real aggregate used to exercise locking and JSON persistence."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    status = models.CharField(max_length=24, default="draft")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transition_history = models.JSONField(default=list)

    class Meta:
        app_label = "core"
        db_table = "test_state_machine_orders"


@pytest.fixture(scope="module", autouse=True)
def order_table(django_db_setup: Any, django_db_blocker: Any) -> Any:
    """Create the private model without adding a production migration."""
    del django_db_setup
    with django_db_blocker.unblock():
        with connection.schema_editor() as editor:
            editor.create_model(StateMachineOrder)
    yield
    with django_db_blocker.unblock():
        with connection.schema_editor() as editor:
            editor.delete_model(StateMachineOrder)


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def order(tenant_id: uuid.UUID) -> StateMachineOrder:
    return StateMachineOrder.objects.create(tenant_id=tenant_id, total="100.00")


@pytest.fixture
def machine() -> StateMachine[StateMachineOrder]:
    def positive_total(aggregate: StateMachineOrder, context: Mapping[str, Any]) -> bool:
        return aggregate.total > 0 and context.get("approved") is True

    return StateMachine(
        name="order",
        model=StateMachineOrder,
        states=("draft", "confirmed", "fulfilled", "cancelled"),
        terminal_states=("fulfilled", "cancelled"),
        transitions=(
            Transition("confirm", "draft", "confirmed", (positive_total,)),
            Transition("fulfil", "confirmed", "fulfilled"),
            Transition("cancel", "draft", "cancelled"),
            Transition("cancel", "confirmed", "cancelled"),
        ),
    )


@pytest.mark.django_db
def test_legal_transition_is_applied_and_recorded(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    result = machine.apply(
        order,
        "confirm",
        transition_key="request-001",
        context={"approved": True},
        metadata={"actor": "buyer"},
    )

    order.refresh_from_db()
    assert result.pk == order.pk
    assert order.status == "confirmed"
    assert order.transition_history == [
        {
            "transition_key": "request-001",
            "command": "confirm",
            "from_state": "draft",
            "to_state": "confirmed",
            "occurred_at": order.transition_history[0]["occurred_at"],
            "metadata": {"actor": "buyer"},
        }
    ]
    assert order.transition_history[0]["occurred_at"].endswith("+00:00")


@pytest.mark.django_db
def test_illegal_transition_is_rejected_without_mutation(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    with pytest.raises(IllegalTransitionError, match="cannot transition"):
        machine.apply(order, "fulfil", transition_key="request-002")

    order.refresh_from_db()
    assert order.status == "draft"
    assert order.transition_history == []


@pytest.mark.django_db
def test_unknown_command_is_rejected(machine: StateMachine[StateMachineOrder], order: StateMachineOrder) -> None:
    with pytest.raises(UnknownCommandError, match="has no command"):
        machine.apply(order, "refund", transition_key="request-unknown")


@pytest.mark.django_db
def test_precondition_failure_rolls_back_state_and_history(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    with pytest.raises(GuardFailedError, match="rejected"):
        machine.apply(
            "confirm",
            aggregate=order,
            transition_key="request-003",
            context={"approved": False},
        )

    order.refresh_from_db()
    assert order.status == "draft"
    assert order.transition_history == []


@pytest.mark.django_db
def test_one_argument_guard_is_supported(tenant_id: uuid.UUID) -> None:
    order = StateMachineOrder.objects.create(tenant_id=tenant_id, total="25.00")
    machine = StateMachine(
        states=("draft", "confirmed"),
        transitions=(
            {
                "command": "confirm",
                "from": "draft",
                "to": "confirmed",
                "guards": lambda aggregate: aggregate.total > 0,
            },
        ),
    )

    machine.apply(order, "confirm", transition_key="one-argument-guard")
    order.refresh_from_db()
    assert order.status == "confirmed"


@pytest.mark.django_db
def test_guard_exception_blocks_and_is_chained(
    order: StateMachineOrder,
) -> None:
    def broken_guard(aggregate: StateMachineOrder) -> bool:
        del aggregate
        raise ValueError("payment service response is invalid")

    machine = StateMachine(
        states=("draft", "confirmed"),
        transitions=(Transition("confirm", "draft", "confirmed", (broken_guard,)),),
    )

    with pytest.raises(GuardFailedError, match="errored") as raised:
        machine.apply(order, "confirm", transition_key="broken-guard")
    assert isinstance(raised.value.__cause__, ValueError)


@pytest.mark.django_db
def test_terminal_state_is_immutable(machine: StateMachine[StateMachineOrder], order: StateMachineOrder) -> None:
    machine.apply(order, "cancel", transition_key="request-004")

    with pytest.raises(TerminalStateError, match="terminal state"):
        machine.apply(order, "confirm", transition_key="request-005", context={"approved": True})

    order.refresh_from_db()
    assert order.status == "cancelled"
    assert len(order.transition_history) == 1


@pytest.mark.django_db
def test_competing_stale_apply_is_serialized_and_idempotent(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    """A stale caller must re-read the row and observe the first caller's key."""
    first_caller = StateMachineOrder.objects.get(pk=order.pk)
    stale_competing_caller = StateMachineOrder.objects.get(pk=order.pk)

    first_result = machine.apply(
        first_caller,
        "confirm",
        transition_key="shared-command-key",
        context={"approved": True},
    )
    replay_result = machine.apply(
        stale_competing_caller,
        "confirm",
        transition_key="shared-command-key",
        context={"approved": True},
    )

    order.refresh_from_db()
    assert first_result.pk == replay_result.pk == order.pk
    assert stale_competing_caller.status == "confirmed"
    assert order.status == "confirmed"
    assert len(order.transition_history) == 1


@pytest.mark.django_db
def test_transition_key_cannot_be_reused_for_another_command(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    machine.apply(order, "cancel", transition_key="same-key")

    with pytest.raises(IdempotencyConflictError, match="already belongs"):
        machine.apply(order, "confirm", transition_key="same-key", context={"approved": True})


@pytest.mark.django_db
def test_bound_model_can_be_addressed_by_tenant_and_id(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    result = machine.apply(
        "confirm",
        aggregate_id=order.pk,
        tenant_id=order.tenant_id,
        transition_key="by-id",
        context={"approved": True},
    )
    assert result.status == "confirmed"


@pytest.mark.django_db
def test_uuid_identifiers_accept_their_canonical_string_form(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    result = machine.apply(
        order,
        "confirm",
        aggregate_id=str(order.pk),
        tenant_id=str(order.tenant_id),
        transition_key="string-identifiers",
        context={"approved": True},
    )
    assert result.status == "confirmed"


@pytest.mark.django_db
def test_tenant_identity_is_required_and_cannot_be_substituted(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    with pytest.raises(StateMachineConfigurationError, match="different tenants"):
        machine.apply(
            order,
            "confirm",
            tenant_id=uuid.uuid4(),
            transition_key="wrong-tenant",
            context={"approved": True},
        )
    with pytest.raises(StateMachineConfigurationError, match="tenant_id is required"):
        machine.apply(
            "confirm",
            aggregate_id=order.pk,
            transition_key="missing-tenant",
            context={"approved": True},
        )


@pytest.mark.django_db
def test_transition_uses_fresh_database_state(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    stale = StateMachineOrder.objects.get(pk=order.pk)
    StateMachineOrder.objects.filter(pk=order.pk).update(status="confirmed")

    result = machine.apply(stale, "fulfil", transition_key="fresh-read")

    assert result.status == "fulfilled"
    assert stale.status == "fulfilled"


def test_allowed_commands_are_sorted_and_unknown_state_fails(
    machine: StateMachine[StateMachineOrder],
) -> None:
    assert machine.allowed_commands("draft") == ("cancel", "confirm")
    assert machine.allowed_commands("fulfilled") == ()
    with pytest.raises(StateMachineConfigurationError, match="Unknown state"):
        machine.allowed_commands("missing")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"states": (), "transitions": (Transition("go", "a", "b"),)}, "at least one state"),
        (
            {
                "states": ("a", "a"),
                "transitions": (Transition("go", "a", "a"),),
            },
            "unique",
        ),
        (
            {
                "states": ("a", "b"),
                "terminal_states": ("missing",),
                "transitions": (Transition("go", "a", "b"),),
            },
            "not declared",
        ),
        (
            {
                "states": ("a", "b"),
                "terminal_states": ("b",),
                "transitions": (Transition("go", "b", "a"),),
            },
            "cannot have outgoing",
        ),
        (
            {
                "states": ("a", "b"),
                "transitions": (
                    Transition("go", "a", "b"),
                    Transition("go", "a", "a"),
                ),
            },
            "ambiguous",
        ),
        (
            {
                "states": ("a", "b"),
                "transitions": (Transition("go", "missing", "b"),),
            },
            "undeclared edge",
        ),
    ],
)
def test_invalid_graph_definitions_fail_fast(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(StateMachineConfigurationError, match=message):
        StateMachine(**kwargs)


def test_from_dict_and_mapping_transition_forms() -> None:
    machine = StateMachine.from_dict(
        {
            "name": "document",
            "states": ["draft", "review", "published"],
            "terminal_states": ["published"],
            "transitions": {
                "submit": {"draft": "review"},
                ("publish", "review"): "published",
            },
        }
    )
    assert machine.allowed_commands("draft") == ("submit",)
    assert machine.allowed_commands("review") == ("publish",)


@pytest.mark.django_db
def test_malformed_or_missing_history_fails_explicitly(
    order: StateMachineOrder,
) -> None:
    order.transition_history = {"not": "a list"}
    order.save(update_fields=["transition_history"])
    machine = StateMachine(
        states=("draft", "confirmed"),
        transitions=(Transition("confirm", "draft", "confirmed"),),
    )
    with pytest.raises(StateMachineConfigurationError, match="JSON list"):
        machine.apply(order, "confirm", transition_key="malformed-history")


@pytest.mark.django_db
def test_unsaved_aggregate_is_rejected(machine: StateMachine[StateMachineOrder], tenant_id: uuid.UUID) -> None:
    unsaved = StateMachineOrder(tenant_id=tenant_id)
    with pytest.raises(StateMachineConfigurationError, match="unsaved"):
        machine.apply(unsaved, "confirm", transition_key="unsaved", context={"approved": True})


@pytest.mark.django_db
def test_custom_transition_recorder_is_a_real_extension_surface(order: StateMachineOrder) -> None:
    class Recorder:
        def __init__(self) -> None:
            self.records: dict[tuple[Any, str], TransitionRecord] = {}

        def find(self, aggregate: StateMachineOrder, transition_key: str) -> TransitionRecord | None:
            return self.records.get((aggregate.pk, transition_key))

        def record(self, aggregate: StateMachineOrder, record: TransitionRecord) -> None:
            self.records[(aggregate.pk, record.transition_key)] = record

        def aggregate_update_fields(self) -> tuple[str, ...]:
            return ()

    recorder = Recorder()
    machine = StateMachine(
        states=("draft", "confirmed"),
        transitions=(Transition("confirm", "draft", "confirmed"),),
        recorder=recorder,
    )
    result = machine.apply(order, "confirm", transition_key="external-audit")
    replay = machine.apply(order, "confirm", transition_key="external-audit")

    assert result.status == replay.status == "confirmed"
    assert recorder.records[(order.pk, "external-audit")].to_state == "confirmed"
    assert order.transition_history == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("history", "message"),
    [
        (["not-an-object"], "non-object"),
        ([{"transition_key": "duplicate"}, {"transition_key": "duplicate"}], "Duplicate transition key"),
        (
            [
                {
                    "transition_key": "malformed",
                    "command": "confirm",
                    "from_state": "draft",
                    "to_state": "confirmed",
                    "occurred_at": "now",
                    "metadata": [],
                }
            ],
            "Malformed transition record",
        ),
        ([{"transition_key": "incomplete"}], "Malformed transition record"),
    ],
)
def test_corrupt_transition_audit_is_never_treated_as_success(
    order: StateMachineOrder, history: list[Any], message: str
) -> None:
    order.transition_history = history
    order.save(update_fields=["transition_history"])
    machine = StateMachine(
        states=("draft", "confirmed"),
        transitions=(Transition("confirm", "draft", "confirmed"),),
    )
    key = str(history[0].get("transition_key", "unused")) if isinstance(history[0], dict) else "unused"
    with pytest.raises(StateMachineConfigurationError, match=message):
        machine.apply(order, "confirm", transition_key=key)


@pytest.mark.django_db
def test_undeclared_persisted_state_is_rejected(order: StateMachineOrder) -> None:
    order.status = "legacy"
    order.save(update_fields=["status"])
    machine = StateMachine(
        states=("draft", "confirmed"),
        transitions=(Transition("confirm", "draft", "confirmed"),),
    )
    with pytest.raises(StateMachineConfigurationError, match="undeclared state"):
        machine.apply(order, "confirm", transition_key="legacy-state")


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        ("not-a-mapping", "must be a mapping"),
        ({"states": ["a"]}, "missing 'transitions'"),
        ({"states": "a", "transitions": []}, "states must be a sequence"),
        ({"states": ["a"], "transitions": "go"}, "transitions must be"),
        ({"states": ["a"], "transitions": [], "unsupported": True}, "Unknown machine definition keys"),
    ],
)
def test_from_dict_rejects_non_declarative_input(definition: Any, message: str) -> None:
    with pytest.raises(StateMachineConfigurationError, match=message):
        StateMachine.from_dict(definition)


@pytest.mark.parametrize(
    ("transitions", "message"),
    [
        ((), "at least one transition"),
        ("go", "must not be a string"),
        ((42,), "Every transition"),
        (({"command": "go", "from": "a"},), "missing required key"),
        ({42: {"a": "b"}}, "must use command names"),
        (({"command": "go", "from": "a", "to": "b", "guards": 42},), "guards must be"),
        (({"command": "go", "from": "a", "to": "b", "guards": [42]},), "must be callable"),
        ((Transition(" ", "a", "b"),), "must not be empty"),
        (({"command": "go", "from": "a", "to": "b", "typo": True},), "Unknown transition"),
    ],
)
def test_invalid_transition_shapes_fail_during_startup(transitions: Any, message: str) -> None:
    with pytest.raises(StateMachineConfigurationError, match=message):
        StateMachine(states=("a", "b"), transitions=transitions)


@pytest.mark.django_db
def test_apply_call_contract_rejects_ambiguous_or_invalid_identity(
    machine: StateMachine[StateMachineOrder], order: StateMachineOrder
) -> None:
    with pytest.raises(TypeError, match="second argument"):
        machine.apply("confirm", "also-a-string", transition_key="bad-call")
    with pytest.raises(TypeError, match="requires a command"):
        machine.apply(order, None, transition_key="bad-call")
    with pytest.raises(TypeError, match="more than once"):
        machine.apply(order, "confirm", aggregate=order, transition_key="bad-call")
    with pytest.raises(TypeError, match="Django model"):
        machine.apply("confirm", 42, transition_key="bad-call")
    with pytest.raises(StateMachineConfigurationError, match="different rows"):
        machine.apply(
            order,
            "confirm",
            aggregate_id=uuid.uuid4(),
            transition_key="bad-id",
            context={"approved": True},
        )
    with pytest.raises(StateMachineConfigurationError, match="aggregate_id is required"):
        machine.apply("confirm", tenant_id=order.tenant_id, transition_key="missing-id")


@pytest.mark.django_db
def test_unbound_and_wrong_model_fail_before_database_mutation(order: StateMachineOrder) -> None:
    unbound = StateMachine(
        states=("draft", "confirmed"),
        transitions=(Transition("confirm", "draft", "confirmed"),),
    )
    with pytest.raises(StateMachineConfigurationError, match="not bound"):
        unbound.apply("confirm", aggregate_id=order.pk, transition_key="unbound")

    class DifferentOrder(StateMachineOrder):
        class Meta:
            proxy = True
            app_label = "core"

    wrong = DifferentOrder.objects.get(pk=order.pk)
    bound = StateMachine(
        model=StateMachineOrder,
        states=("draft", "confirmed"),
        transitions=(Transition("confirm", "draft", "confirmed"),),
    )
    with pytest.raises(StateMachineConfigurationError, match="Machine expects"):
        bound.apply(wrong, "confirm", transition_key="wrong-model")


def test_names_context_and_state_inputs_are_strict(machine: StateMachine[StateMachineOrder]) -> None:
    with pytest.raises(StateMachineConfigurationError, match="must be a string"):
        machine.allowed_commands(42)  # type: ignore[arg-type]
    with pytest.raises(StateMachineConfigurationError, match="must not be empty"):
        machine.allowed_commands(" ")
    with pytest.raises(StateMachineConfigurationError, match="not a string"):
        StateMachine(states="draft", transitions=())
