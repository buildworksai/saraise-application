"""Black-box governed v2 API contract tests."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from src.core.access.permissions import RequiresAccess
from src.modules.dms import api
from src.modules.dms.services import (
    DEFAULT_DMS_CONFIGURATION,
    DocumentService,
    PermissionService,
    ShareService,
    VersionService,
)
from src.modules.dms.tests.test_services import AllowQuota, Directory, MemoryStorage

pytest_plugins = ["src.core.testing"]


def actor_id(user) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.id}")


def data(response):
    return response.json()["data"]


@pytest.fixture(autouse=True)
def allow_module_access(monkeypatch):
    """API tests isolate transport; protected access branches have their own suite."""

    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


@pytest.fixture
def api_services(monkeypatch, tenant_a_user):
    storage = MemoryStorage()
    principal = uuid.uuid4()
    permission_service = PermissionService(Directory(principal))
    documents = DocumentService(storage=storage, permission_service=permission_service, quota_service=AllowQuota())
    versions = VersionService(documents)
    shares = ShareService(documents)
    monkeypatch.setattr(api.DocumentViewSet, "service_class", staticmethod(lambda: documents))
    monkeypatch.setattr(api.DocumentVersionViewSet, "service_class", staticmethod(lambda: versions))
    monkeypatch.setattr(api.DocumentPermissionViewSet, "service_class", staticmethod(lambda: permission_service))
    monkeypatch.setattr(api.DocumentShareViewSet, "service_class", staticmethod(lambda: shares))
    monkeypatch.setattr(api, "ShareService", lambda: shares)
    return documents, versions, permission_service, shares, storage, principal


@pytest.mark.django_db
def test_authentication_and_csrf_are_enforced(api_client, tenant_a_user, allow_module_access) -> None:
    anonymous = api_client.get("/api/v2/dms/folders/")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    csrf_missing = APIClient(enforce_csrf_checks=True)
    assert csrf_missing.login(username=tenant_a_user.username, password="saraise-test-password")
    rejected = csrf_missing.post("/api/v2/dms/folders/", {"name": "Rejected"}, format="json")
    assert rejected.status_code == 403


@pytest.mark.django_db
def test_folder_endpoint_matrix_envelopes_pagination_and_put_rejection(
    authenticated_tenant_a_client,
    api_services,
) -> None:
    client = authenticated_tenant_a_client
    created = client.post("/api/v2/dms/folders/", {"name": "Finance", "tenant_id": str(uuid.uuid4())}, format="json")
    assert created.status_code == 201
    folder = data(created)
    assert "tenant_id" not in folder
    assert created.json()["meta"]["correlation_id"]

    listed = client.get("/api/v2/dms/folders/?parent_id=root&page_size=100&ordering=name")
    assert listed.status_code == 200
    assert listed.json()["meta"]["pagination"]["page_size"] == 100
    assert [item["id"] for item in data(listed)] == [folder["id"]]

    detail = client.get(f"/api/v2/dms/folders/{folder['id']}/")
    assert detail.status_code == 200
    updated = client.patch(f"/api/v2/dms/folders/{folder['id']}/", {"description": "Records"}, format="json")
    assert data(updated)["description"] == "Records"
    assert client.put(f"/api/v2/dms/folders/{folder['id']}/", {"name": "Forbidden"}, format="json").status_code == 405
    moved = client.post(f"/api/v2/dms/folders/{folder['id']}/move/", {"parent_id": None}, format="json")
    assert moved.status_code == 200
    contents = client.get(f"/api/v2/dms/folders/{folder['id']}/contents/")
    assert data(contents)["folder"]["id"] == folder["id"]
    assert client.delete(f"/api/v2/dms/folders/{folder['id']}/").status_code == 204


@pytest.mark.django_db
def test_configuration_api_is_versioned_reversible_and_cross_tenant_isolated(
    authenticated_tenant_a_client,
    authenticated_tenant_b_client,
) -> None:
    tenant_a = authenticated_tenant_a_client
    tenant_b = authenticated_tenant_b_client
    endpoint = "/api/v2/dms/configuration"

    initial_a = data(tenant_a.get(f"{endpoint}/current/?environment=staging"))
    assert initial_a["environment"] == "staging"
    assert initial_a["values"] == DEFAULT_DMS_CONFIGURATION

    changed = dict(initial_a["values"])
    changed["max_document_tags"] = 75
    preview = tenant_a.post(
        f"{endpoint}/preview/",
        {"environment": "staging", "values": changed},
        format="json",
    )
    assert preview.status_code == 200
    assert data(preview)["changes"] == [{"field": "max_document_tags", "before": 50, "after": 75}]
    updated = tenant_a.put(
        f"{endpoint}/current/",
        {"environment": "staging", "values": changed},
        format="json",
    )
    assert updated.status_code == 200
    assert data(updated)["version"] == 2

    isolated_b = data(tenant_b.get(f"{endpoint}/current/?environment=staging"))
    assert isolated_b["version"] == 1
    assert isolated_b["values"]["max_document_tags"] == 50

    history = tenant_a.get(f"{endpoint}/history/?environment=staging")
    audit = tenant_a.get(f"{endpoint}/audit/?environment=staging")
    assert [row["version"] for row in data(history)] == [2, 1]
    assert all(row["correlation_id"] for row in data(history))
    assert [row["action"] for row in data(audit)] == ["updated", "created"]
    assert all(row["correlation_id"] for row in data(audit))

    rolled_back = tenant_a.post(
        f"{endpoint}/rollback/",
        {"environment": "staging", "version": 1},
        format="json",
    )
    assert rolled_back.status_code == 200
    assert data(rolled_back)["version"] == 3
    assert data(rolled_back)["values"]["max_document_tags"] == 50

    exported = tenant_a.get(f"{endpoint}/export/?environment=staging")
    assert data(exported)["environment"] == "staging"
    assert data(exported)["version"] == 3


@pytest.mark.django_db
def test_document_upload_filter_detail_update_move_download_delete(
    authenticated_tenant_a_client,
    tenant_a_user,
    api_services,
) -> None:
    client = authenticated_tenant_a_client
    folder = data(client.post("/api/v2/dms/folders/", {"name": "Legal"}, format="json"))
    upload = client.post(
        "/api/v2/dms/documents/",
        {
            "file": SimpleUploadedFile("proof.txt", b"proof", content_type="text/plain"),
            "name": "Proof",
            "folder_id": folder["id"],
            "description": "Source evidence",
        },
        format="multipart",
    )
    assert upload.status_code == 201, upload.content
    document = data(upload)
    assert document["current_version"]["size_bytes"] == 5
    assert "storage_key" not in document["current_version"]

    listed = client.get(f"/api/v2/dms/documents/?folder={folder['id']}&search=Proof&ordering=-updated_at")
    assert [row["id"] for row in data(listed)] == [document["id"]]
    detail = data(client.get(f"/api/v2/dms/documents/{document['id']}/"))
    patched = client.patch(
        f"/api/v2/dms/documents/{document['id']}/",
        {"name": "Updated proof", "expected_updated_at": detail["updated_at"]},
        format="json",
    )
    assert data(patched)["name"] == "Updated proof"
    stale = client.patch(
        f"/api/v2/dms/documents/{document['id']}/",
        {"name": "Lost", "expected_updated_at": detail["updated_at"]},
        format="json",
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT"

    moved = client.post(f"/api/v2/dms/documents/{document['id']}/move/", {"folder_id": None}, format="json")
    assert data(moved)["folder_id"] is None
    download = client.get(f"/api/v2/dms/documents/{document['id']}/download/")
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == b"proof"
    assert "filename=" in download["Content-Disposition"]
    assert client.put(f"/api/v2/dms/documents/{document['id']}/", {}, format="json").status_code == 405
    assert client.delete(f"/api/v2/dms/documents/{document['id']}/").status_code == 204


@pytest.mark.django_db
def test_version_permission_and_share_endpoint_matrix(
    authenticated_tenant_a_client,
    tenant_a_user,
    api_services,
) -> None:
    client = authenticated_tenant_a_client
    _documents, _versions, _permissions, _shares, _storage, principal = api_services
    uploaded = data(
        client.post(
            "/api/v2/dms/documents/",
            {"file": SimpleUploadedFile("v1.txt", b"one", content_type="text/plain"), "name": "Versioned"},
            format="multipart",
        )
    )
    document_id = uploaded["id"]
    first_id = uploaded["current_version"]["id"]
    created_version = client.post(
        "/api/v2/dms/document-versions/",
        {
            "document_id": document_id,
            "file": SimpleUploadedFile("v2.txt", b"two", content_type="text/plain"),
            "change_note": "Second",
        },
        format="multipart",
    )
    assert created_version.status_code == 201
    assert data(created_version)["version_number"] == 2
    versions = client.get(f"/api/v2/dms/document-versions/?document_id={document_id}")
    assert [item["version_number"] for item in data(versions)] == [2, 1]
    assert client.get("/api/v2/dms/document-versions/").status_code == 400
    assert client.get(f"/api/v2/dms/document-versions/{first_id}/").status_code == 200
    restored = client.post(
        f"/api/v2/dms/document-versions/{first_id}/restore/",
        {"change_note": "Restore"},
        format="json",
    )
    assert data(restored)["version_number"] == 3
    assert data(restored)["source_version_id"] == first_id

    grant = client.post(
        "/api/v2/dms/document-permissions/",
        {
            "document_id": document_id,
            "principal_type": "user",
            "principal_id": str(principal),
            "permission": "read",
        },
        format="json",
    )
    assert grant.status_code == 201, grant.content
    grant_id = data(grant)["id"]
    assert client.get(f"/api/v2/dms/document-permissions/?document_id={document_id}").status_code == 200
    assert client.get(f"/api/v2/dms/document-permissions/{grant_id}/").status_code == 200
    assert (
        data(client.patch(f"/api/v2/dms/document-permissions/{grant_id}/", {"permission": "write"}, format="json"))[
            "permission"
        ]
        == "write"
    )
    assert client.delete(f"/api/v2/dms/document-permissions/{grant_id}/").status_code == 204

    share = client.post(
        "/api/v2/dms/document-shares/",
        {
            "document_id": document_id,
            "version_id": first_id,
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            "max_access_count": 1,
        },
        format="json",
    )
    assert share.status_code == 201
    created_share = data(share)
    assert created_share["share_url"]
    assert "token_digest" not in created_share["share"]
    share_id = created_share["share"]["id"]
    token = created_share["share_url"].split("/")[-3]
    ordinary = data(client.get(f"/api/v2/dms/document-shares/{share_id}/"))
    assert "share_url" not in ordinary
    assert client.get(f"/api/v2/dms/document-shares/?document_id={document_id}").status_code == 200
    public = client.get(f"/api/v2/dms/public/shares/{token}/download/")
    assert b"".join(public.streaming_content) == b"one"
    assert client.get(f"/api/v2/dms/public/shares/{token}/download/").status_code == 404
    revoked = client.post(f"/api/v2/dms/document-shares/{share_id}/revoke/", {}, format="json")
    assert data(revoked)["state"] == "revoked"


@pytest.mark.django_db
def test_validation_filter_and_ordering_errors_use_stable_envelope(
    authenticated_tenant_a_client,
    api_services,
) -> None:
    client = authenticated_tenant_a_client
    invalid = client.get("/api/v2/dms/documents/?search=" + "x" * 201)
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    forbidden_order = client.get("/api/v2/dms/documents/?ordering=tenant_id")
    assert forbidden_order.status_code == 400
    excessive_page = client.get("/api/v2/dms/folders/?page_size=1000")
    assert excessive_page.status_code == 200
    assert excessive_page.json()["meta"]["pagination"]["page_size"] == 100
