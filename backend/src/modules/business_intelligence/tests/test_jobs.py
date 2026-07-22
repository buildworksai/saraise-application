"""Durable worker registration and tenant-context tests."""

from __future__ import annotations

import pytest

from src.modules.business_intelligence.jobs import execute_query_job


def test_worker_rejects_missing_tenant_payload() -> None:
    job = type("Job", (), {"payload": {}, "tenant_id": "not-a-tenant"})()
    with pytest.raises(ValueError, match="missing a valid tenant"):
        execute_query_job(job)
