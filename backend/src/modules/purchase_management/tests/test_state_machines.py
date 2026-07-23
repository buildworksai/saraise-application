"""Lifecycle graph registration proofs."""

from src.core.state_machine import registry


def test_all_procurement_state_machines_registered_with_terminal_guards():
    expected = {f"purchase_management.{name}" for name in ("requisition", "rfq", "quote", "order", "receipt")}
    assert expected <= set(registry.names())
    assert registry.get("purchase_management.receipt").allowed_commands("completed") == ()
    assert registry.get("purchase_management.order").allowed_commands("approved") == ("cancel", "dispatch")
