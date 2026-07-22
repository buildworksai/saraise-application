"""Mandatory black-box tenant isolation contracts for compliance API v2."""

from __future__ import annotations

import pytest
from rest_framework import status

from src.core.access.permissions import RequiresAccess
from src.core.testing.tenant_contract import TenantIsolationContract

from ..models import (
    ComplianceConfigurationRevision, ComplianceEvidence, ComplianceFramework,
    CompliancePolicy, ComplianceRequirement, RequirementPolicyMapping,
)
from .factories import (
    ComplianceConfigurationRevisionFactory, ComplianceEvidenceFactory,
    ComplianceFrameworkFactory, CompliancePolicyFactory,
    ComplianceRequirementFactory, RequirementPolicyMappingFactory,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/compliance-management"


@pytest.fixture(autouse=True)
def allow_manifest_access(monkeypatch):
    """Grant declared access so this suite isolates the tenant boundary itself."""
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


class GovernedIsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response):
        body = response.json()
        assert set(body) == {"data", "meta"}
        assert body["meta"]["correlation_id"]
        return body["data"]


class TestFrameworkIsolation(GovernedIsolationContract):
    model = ComplianceFramework
    list_url = f"{BASE}/frameworks/"
    detail_url_template = f"{BASE}/frameworks/{{pk}}/"
    create_payload = {"code": "NEW", "name": "New", "version": "1", "category": "General", "source_kind": "custom"}
    update_payload = {"name": "Cross-tenant change"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ComplianceFrameworkFactory(tenant_id=tenant_a.id)
        self.tenant_b_row = ComplianceFrameworkFactory(tenant_id=tenant_b.id)


class TestRequirementIsolation(GovernedIsolationContract):
    model = ComplianceRequirement
    list_url = f"{BASE}/requirements/"
    detail_url_template = f"{BASE}/requirements/{{pk}}/"
    update_payload = {"title": "Cross-tenant change"}

    def get_create_payload(self):
        return {"framework_id": str(self.tenant_a_row.framework_id), "code": "NEW", "title": "New", "description": "Normative text"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ComplianceRequirementFactory(tenant_id=tenant_a.id)
        self.tenant_b_row = ComplianceRequirementFactory(tenant_id=tenant_b.id)


class TestPolicyIsolation(GovernedIsolationContract):
    model = CompliancePolicy
    list_url = f"{BASE}/policies/"
    detail_url_template = f"{BASE}/policies/{{pk}}/"
    create_payload = {"code": "NEW", "title": "New policy", "category": "General"}
    update_payload = {"title": "Cross-tenant change"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = CompliancePolicyFactory(tenant_id=tenant_a.id)
        self.tenant_b_row = CompliancePolicyFactory(tenant_id=tenant_b.id)


class TestMappingIsolation(GovernedIsolationContract):
    model = RequirementPolicyMapping
    list_url = f"{BASE}/mappings/"
    detail_url_template = f"{BASE}/mappings/{{pk}}/"
    update_payload = {"coverage": "partial", "rationale": "Partial coverage remains."}

    def get_create_payload(self):
        return {"requirement_id": str(self.tenant_a_row.requirement_id), "policy_id": str(self.tenant_a_row.policy_id), "coverage": "full", "rationale": "Covered"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = RequirementPolicyMappingFactory(tenant_id=tenant_a.id)
        self.tenant_b_row = RequirementPolicyMappingFactory(tenant_id=tenant_b.id)


class TestEvidenceIsolation(GovernedIsolationContract):
    model = ComplianceEvidence
    list_url = f"{BASE}/evidence/"
    detail_url_template = f"{BASE}/evidence/{{pk}}/"
    create_payload = {"name": "New evidence", "evidence_type": "attestation", "reference_kind": "text_reference", "text_reference": "Reference", "classification": "internal"}
    update_payload = {"name": "Cross-tenant change"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ComplianceEvidenceFactory(tenant_id=tenant_a.id)
        self.tenant_b_row = ComplianceEvidenceFactory(tenant_id=tenant_b.id)


class TestConfigurationIsolation(GovernedIsolationContract):
    model = ComplianceConfigurationRevision
    list_url = f"{BASE}/configuration/?environment=development"
    detail_url_template = f"{BASE}/configuration/{{pk}}/"
    create_payload = {"environment": "development", "expiry_warning_days": 45}
    update_payload = {"expiry_warning_days": 60}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ComplianceConfigurationRevisionFactory(tenant_id=tenant_a.id)
        self.tenant_b_row = ComplianceConfigurationRevisionFactory(tenant_id=tenant_b.id)

    def test_cross_tenant_delete_is_denied_and_unchanged(self):
        before = self._row_snapshot(self.tenant_b_row)
        response = self.client.delete(self.get_detail_url(self.tenant_b_row))
        assert response.status_code in {status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED}
        assert self._row_snapshot(self.tenant_b_row) == before
