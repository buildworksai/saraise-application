"""Backup recovery access metadata contract tests."""

from __future__ import annotations

from src.modules.backup_recovery.permissions import ACCESS_MAP


def test_access_rules_have_positive_quota_costs() -> None:
    for action_map in ACCESS_MAP.values():
        for rule in action_map.values():
            assert rule.quota_cost >= 1
