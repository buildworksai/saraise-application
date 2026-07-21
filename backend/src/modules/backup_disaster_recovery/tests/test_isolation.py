from __future__ import annotations

import uuid

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.testing.tenant_contract import TenantIsolationContract

from ..models import DRRunbook, RunbookStep, ScopeType
from .factories import recovery_point_factory, runbook_factory, runbook_step_factory

pytest_plugins = ["src.core.testing"]

PREFIX = "/api/v2/backup-disaster-recovery"


@pytest.fixture(autouse=True)
def allow_access(monkeypatch):
    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(True, AccessReasonCode.ALLOW, "allowed", tenant_id=uuid.UUID(str(tenant_id)))

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


class V2IsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response):
        return response.json()["data"]


@pytest.mark.django_db
class TestDRRunbookIsolation(V2IsolationContract):
    model = DRRunbook
    list_url = f"{PREFIX}/runbooks/"
    detail_url_template = f"{PREFIX}/runbooks/{{pk}}/"
    update_payload = {"name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = runbook_factory(tenant_id=tenant_a.id, slug="tenant-a")
        self.tenant_b_row = runbook_factory(tenant_id=tenant_b.id, slug="tenant-b")
        self.create_payload = {
            "name": "Spoof attempt",
            "slug": f"spoof-{uuid.uuid4().hex[:8]}",
            "description": "must bind to authenticated tenant",
            "scope_type": ScopeType.TENANT,
            "scope_ref": "primary",
            "adapter_key": "local-filesystem",
            "rpo_target_seconds": 3600,
            "rto_target_seconds": 7200,
            "owner_id": str(uuid.uuid4()),
        }


@pytest.mark.django_db
class TestRunbookStepIsolation(V2IsolationContract):
    model = RunbookStep
    detail_url_template = f"{PREFIX}/runbook-steps/{{pk}}/"
    update_payload = {"name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        runbook_a = runbook_factory(tenant_id=tenant_a.id, slug="steps-a")
        runbook_b = runbook_factory(tenant_id=tenant_b.id, slug="steps-b")
        self.tenant_a_row = runbook_step_factory(runbook_a, step_key="validate-a")
        self.tenant_b_row = runbook_step_factory(runbook_b, step_key="validate-b")
        self.list_url = f"{PREFIX}/runbook-steps/?runbook_id={runbook_a.id}"
        self.create_payload = {
            "runbook_id": str(runbook_a.id),
            "step_key": f"step-{uuid.uuid4().hex[:8]}",
            "position": 2,
            "name": "Validate artifact",
            "action_type": "validate_recovery_point",
            "parameters": {"require_checksum": True, "require_encryption": True},
            "timeout_seconds": 300,
            "retry_limit": 0,
            "on_failure": "stop",
        }


@pytest.mark.django_db
def test_recovery_point_list_and_detail_isolation(
    authenticated_tenant_a_client, tenant_a, tenant_b
):
    own = recovery_point_factory(tenant_id=tenant_a.id, scope_ref="own")
    other = recovery_point_factory(tenant_id=tenant_b.id, scope_ref="other")
    body = authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/").json()
    identities = {row["id"] for row in body["data"]}
    assert str(own.id) in identities
    assert str(other.id) not in identities
    assert authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/{other.id}/").status_code == 404


@pytest.mark.django_db
def test_spoofed_tenant_filter_is_rejected_without_mutation(authenticated_tenant_a_client, tenant_b):
    other = recovery_point_factory(tenant_id=tenant_b.id)
    before = DRRunbook.objects.count()
    response = authenticated_tenant_a_client.get(
        f"{PREFIX}/recovery-points/?tenant_id={tenant_b.id}"
    )
    assert response.status_code == 400
    assert DRRunbook.objects.count() == before
    other.refresh_from_db()
