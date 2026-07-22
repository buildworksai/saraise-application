"""Static safety contracts for the reversible BI migration chain."""

from __future__ import annotations

import importlib


def test_all_domain_migrations_define_reverse_operations() -> None:
    for suffix in (
        "0002_domain_schema",
        "0003_migrate_legacy_definitions",
        "0004_domain_constraints",
        "0005_domain_rls",
    ):
        module = importlib.import_module(f"src.modules.business_intelligence.migrations.{suffix}")
        assert module.Migration.operations


def test_rls_migration_is_explicitly_reversible() -> None:
    module = importlib.import_module("src.modules.business_intelligence.migrations.0005_domain_rls")
    operation = module.Migration.operations[0]
    assert getattr(operation, "reverse_code", None) is not None
