"""Truthful, sanitized MDM liveness and readiness tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from django.db import DatabaseError
from rest_framework.test import APIRequestFactory

from src.modules.master_data_management import health


def test_liveness_does_not_probe_database(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = Mock(side_effect=AssertionError("liveness must not query storage"))
    monkeypatch.setattr(health.connection, "cursor", cursor)

    response = health.live(APIRequestFactory().get("/health/live/"))

    assert response.status_code == 200
    assert response.data == {"module": "master_data_management", "status": "live"}
    cursor.assert_not_called()


def test_readiness_declares_every_domain_and_durability_table() -> None:
    assert set(health.DOMAIN_TABLES) == {
        "mdm_entity_types",
        "mdm_entities",
        "mdm_entity_versions",
        "mdm_quality_rules",
        "mdm_quality_issues",
        "mdm_matching_rules",
        "mdm_match_candidates",
        "mdm_merge_history",
        "mdm_merge_participants",
    }
    assert set(health.DURABILITY_TABLES) == {"async_jobs", "async_job_outbox_events"}


def test_sqlite_readiness_is_truthful_about_rls(db: object) -> None:
    del db
    if health.connection.vendor == "postgresql":
        pytest.skip("This assertion covers the explicitly non-production backend")
    components = health._readiness_components()
    assert components["database"] == {"ready": True, "code": "DATABASE_READY"}
    assert components["row_level_security"] == {
        "ready": True,
        "code": "RLS_NOT_APPLICABLE",
    }
    assert "missing" in components["domain_schema"]
    assert "missing" in components["durable_execution"]


def test_readiness_failure_is_503_and_does_not_leak_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "postgres://admin:secret-password@db.example.test/mdm"
    monkeypatch.setattr(health, "_readiness_components", Mock(side_effect=DatabaseError(secret)))

    response = health.ready(APIRequestFactory().get("/health/ready/"))

    assert response.status_code == 503
    serialized = str(response.data)
    assert secret not in serialized
    assert "secret-password" not in serialized
    assert response.data == {
        "module": "master_data_management",
        "status": "not_ready",
        "components": {"probe": {"ready": False, "code": "READINESS_PROBE_FAILED"}},
    }


@pytest.mark.parametrize("ready", [True, False])
def test_readiness_status_reflects_all_components(
    monkeypatch: pytest.MonkeyPatch,
    ready: bool,
) -> None:
    components = {
        "database": {"ready": True, "code": "DATABASE_READY"},
        "domain_schema": {
            "ready": ready,
            "code": "DOMAIN_SCHEMA_READY" if ready else "DOMAIN_SCHEMA_INCOMPLETE",
        },
        "durable_execution": {"ready": True, "code": "DURABLE_EXECUTION_READY"},
        "row_level_security": {"ready": True, "code": "RLS_NOT_APPLICABLE"},
    }
    monkeypatch.setattr(health, "_readiness_components", lambda: components)

    response = health.ready(APIRequestFactory().get("/health/ready/"))

    assert response.status_code == (200 if ready else 503)
    assert response.data["status"] == ("ready" if ready else "not_ready")
    assert response.data["components"] == components
