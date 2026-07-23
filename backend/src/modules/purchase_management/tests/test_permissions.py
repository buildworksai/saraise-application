"""Fail-closed action metadata proofs."""

from src.modules.purchase_management.permissions import ACTION_ACCESS


def test_every_mutating_controller_action_has_access_metadata():
    required = {
        "create",
        "update",
        "partial_update",
        "destroy",
        "submit",
        "approve",
        "reject",
        "cancel",
        "publish",
        "award",
        "dispatch",
        "complete",
        "preview",
        "rollback",
    }
    assert required <= ACTION_ACCESS.keys()
    assert all(ACTION_ACCESS[action] for action in required)
