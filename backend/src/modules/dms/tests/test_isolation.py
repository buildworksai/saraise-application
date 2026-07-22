"""Black-box tenant-isolation proofs for the governed DMS v2 boundary.

These tests deliberately authenticate through Django sessions with CSRF
enforcement.  Module entitlement decisions are allowed so this suite can
exercise the next security boundary: tenant-qualified services, document ACLs,
opaque public shares, and PostgreSQL row-level security.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from src.core.access.permissions import RequiresAccess
from src.core.async_jobs.models import OutboxEvent
from src.core.tenancy import MissingTenantContext, get_current_tenant_id, tenant_context, tenant_context_worker
from src.core.testing.factories import TEST_PASSWORD
from src.core.testing.tenant_contract import TenantIsolationContract
from src.modules.dms import api
from src.modules.dms.events import FOLDER_CREATED, FolderEventData, publish_domain_event
from src.modules.dms.models import Document, DocumentPermission, DocumentShare, DocumentVersion, Folder
from src.modules.dms.services import DocumentService, PermissionService, ShareService, VersionService
from src.modules.dms.tests.factories import DocumentGraph, make_folder, make_share
from src.modules.dms.tests.test_services import AllowQuota, Directory, MemoryStorage

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db

BASE = "/api/v2/dms"
User = get_user_model()


def _uuid(value: object) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _actor_id(user: Any) -> uuid.UUID:
    """Mirror the API's stable UUID projection for integer Django user IDs."""

    value = user.pk
    return value if isinstance(value, uuid.UUID) else uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


def _snapshot(row: Any) -> tuple[tuple[str, object], ...]:
    row.refresh_from_db()
    return tuple((field.attname, getattr(row, field.attname)) for field in row._meta.concrete_fields)


class GovernedEnvelopeIsolationContract(TenantIsolationContract):
    """Adapt the shared CRUD proof to the governed ``{data, meta}`` shape."""

    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response: object) -> list[dict[str, object]]:
        payload = response.json()  # type: ignore[attr-defined]
        assert set(payload) == {"data", "meta"}
        assert isinstance(payload["data"], list)
        assert payload["meta"]["correlation_id"]
        return payload["data"]


@dataclass(frozen=True)
class IsolationServices:
    documents: DocumentService
    versions: VersionService
    permissions: PermissionService
    shares: ShareService
    storage: MemoryStorage
    verified_principal: uuid.UUID


@pytest.fixture(autouse=True)
def allow_manifest_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reach DMS tenancy/ACL checks without bypassing session authentication."""

    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


@pytest.fixture
def isolation_services(monkeypatch: pytest.MonkeyPatch) -> IsolationServices:
    storage = MemoryStorage()
    verified_principal = uuid.uuid4()
    permissions = PermissionService(Directory(verified_principal))
    documents = DocumentService(
        storage=storage,
        permission_service=permissions,
        quota_service=AllowQuota(),
    )
    versions = VersionService(documents)
    shares = ShareService(documents)

    monkeypatch.setattr(api.DocumentViewSet, "service_class", staticmethod(lambda: documents))
    monkeypatch.setattr(api.DocumentVersionViewSet, "service_class", staticmethod(lambda: versions))
    monkeypatch.setattr(api.DocumentPermissionViewSet, "service_class", staticmethod(lambda: permissions))
    monkeypatch.setattr(api.DocumentShareViewSet, "service_class", staticmethod(lambda: shares))
    monkeypatch.setattr(api, "ShareService", lambda: shares)
    return IsolationServices(documents, versions, permissions, shares, storage, verified_principal)


@pytest.fixture
def tenant_ids(tenant_a: object, tenant_b: object) -> tuple[uuid.UUID, uuid.UUID]:
    return _uuid(tenant_a.id), _uuid(tenant_b.id)  # type: ignore[attr-defined]


@pytest.fixture
def actor_ids(tenant_a_user: Any, tenant_b_user: Any) -> tuple[uuid.UUID, uuid.UUID]:
    return _actor_id(tenant_a_user), _actor_id(tenant_b_user)


@pytest.fixture
def folder_pair(
    tenant_ids: tuple[uuid.UUID, uuid.UUID],
    actor_ids: tuple[uuid.UUID, uuid.UUID],
) -> tuple[Folder, Folder]:
    tenant_a_id, tenant_b_id = tenant_ids
    actor_a, actor_b = actor_ids
    return (
        make_folder(tenant_id=tenant_a_id, actor_id=actor_a, name="Tenant A records"),
        make_folder(tenant_id=tenant_b_id, actor_id=actor_b, name="Tenant B records"),
    )


@pytest.fixture
def graph_pair(
    tenant_ids: tuple[uuid.UUID, uuid.UUID],
    actor_ids: tuple[uuid.UUID, uuid.UUID],
    isolation_services: IsolationServices,
) -> tuple[DocumentGraph, DocumentGraph]:
    tenant_a_id, tenant_b_id = tenant_ids
    actor_a, actor_b = actor_ids
    document_a = isolation_services.documents.upload_document(
        tenant_a_id,
        actor_a,
        file=SimpleUploadedFile("tenant-a.txt", b"tenant A evidence", content_type="text/plain"),
        name="Tenant A evidence",
    )
    document_b = isolation_services.documents.upload_document(
        tenant_b_id,
        actor_b,
        file=SimpleUploadedFile("tenant-b.txt", b"tenant B evidence", content_type="text/plain"),
        name="Tenant B evidence",
    )
    return (
        DocumentGraph(document_a, document_a.current_version),
        DocumentGraph(document_b, document_b.current_version),
    )


@pytest.fixture
def permission_pair(
    graph_pair: tuple[DocumentGraph, DocumentGraph],
    actor_ids: tuple[uuid.UUID, uuid.UUID],
) -> tuple[DocumentPermission, DocumentPermission]:
    graph_a, graph_b = graph_pair
    actor_a, actor_b = actor_ids
    return (
        DocumentPermission.objects.create(
            tenant_id=graph_a.document.tenant_id,
            document=graph_a.document,
            principal_type="user",
            principal_id=uuid.uuid4(),
            permission="read",
            created_by=actor_a,
        ),
        DocumentPermission.objects.create(
            tenant_id=graph_b.document.tenant_id,
            document=graph_b.document,
            principal_type="user",
            principal_id=uuid.uuid4(),
            permission="read",
            created_by=actor_b,
        ),
    )


@pytest.fixture
def share_pair(
    graph_pair: tuple[DocumentGraph, DocumentGraph],
    actor_ids: tuple[uuid.UUID, uuid.UUID],
) -> tuple[DocumentShare, DocumentShare]:
    graph_a, graph_b = graph_pair
    actor_a, actor_b = actor_ids
    return (
        make_share(graph=graph_a, actor_id=actor_a, token="tenant-a-share-token"),
        make_share(graph=graph_b, actor_id=actor_b, token="tenant-b-share-token"),
    )


class TestFolderIsolation(GovernedEnvelopeIsolationContract):
    model = Folder
    list_url = f"{BASE}/folders/"
    detail_url_template = f"{BASE}/folders/{{pk}}/"
    create_payload = {"name": "Spoof-resistant folder"}
    update_payload = {"name": "Cross-tenant rename"}

    @pytest.fixture(autouse=True)
    def isolation_context(
        self,
        authenticated_tenant_a_client: APIClient,
        folder_pair: tuple[Folder, Folder],
    ) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = folder_pair


class TestDocumentIsolation(GovernedEnvelopeIsolationContract):
    model = Document
    list_url = f"{BASE}/documents/"
    detail_url_template = f"{BASE}/documents/{{pk}}/"
    request_format = "multipart"

    @pytest.fixture(autouse=True)
    def isolation_context(
        self,
        authenticated_tenant_a_client: APIClient,
        graph_pair: tuple[DocumentGraph, DocumentGraph],
    ) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = graph_pair[0].document
        self.tenant_b_row = graph_pair[1].document

    def get_create_payload(self) -> dict[str, object]:
        return {
            "file": SimpleUploadedFile("spoof.txt", b"tenant-bound", content_type="text/plain"),
            "name": "Spoof-resistant document",
        }

    def get_update_payload(self) -> dict[str, object]:
        return {
            "name": "Cross-tenant rename",
            "expected_updated_at": self.tenant_b_row.updated_at.isoformat(),
        }


class TestDocumentPermissionIsolation(GovernedEnvelopeIsolationContract):
    model = DocumentPermission
    detail_url_template = f"{BASE}/document-permissions/{{pk}}/"
    update_payload = {"permission": "manage"}

    @pytest.fixture(autouse=True)
    def isolation_context(
        self,
        authenticated_tenant_a_client: APIClient,
        permission_pair: tuple[DocumentPermission, DocumentPermission],
        isolation_services: IsolationServices,
    ) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = permission_pair
        self.verified_principal = isolation_services.verified_principal

    def get_list_url(self) -> str:
        return f"{BASE}/document-permissions/?document_id={self.tenant_a_row.document_id}"

    def get_create_payload(self) -> dict[str, object]:
        return {
            "document_id": str(self.tenant_a_row.document_id),
            "principal_type": "user",
            "principal_id": str(self.verified_principal),
            "permission": "write",
        }


class TestDocumentShareIsolation(GovernedEnvelopeIsolationContract):
    model = DocumentShare
    detail_url_template = f"{BASE}/document-shares/{{pk}}/"

    @pytest.fixture(autouse=True)
    def isolation_context(
        self,
        authenticated_tenant_a_client: APIClient,
        share_pair: tuple[DocumentShare, DocumentShare],
    ) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = share_pair

    def get_list_url(self) -> str:
        return f"{BASE}/document-shares/?document_id={self.tenant_a_row.document_id}"

    def get_create_payload(self) -> dict[str, object]:
        return {
            "document_id": str(self.tenant_a_row.document_id),
            "version_id": str(self.tenant_a_row.version_id),
            "expires_at": (timezone.now() + timedelta(hours=4)).isoformat(),
            "max_access_count": 2,
        }

    def test_cross_tenant_update_is_denied_and_unchanged(self) -> None:
        """Shares have no PATCH surface; revoke is their only lifecycle update."""

        before = _snapshot(self.tenant_b_row)
        response = self.client.post(
            f"{BASE}/document-shares/{self.tenant_b_row.id}/revoke/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert _snapshot(self.tenant_b_row) == before

    def test_cross_tenant_delete_is_denied_and_unchanged(self) -> None:
        """The action endpoint cannot be used as a cross-tenant delete surrogate."""

        before = _snapshot(self.tenant_b_row)
        response = self.client.post(
            f"{BASE}/document-shares/{self.tenant_b_row.id}/revoke/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert _snapshot(self.tenant_b_row) == before


def test_session_csrf_is_enforced_without_force_authentication(
    tenant_a_user: Any,
) -> None:
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(username=tenant_a_user.username, password=TEST_PASSWORD)
    before = Folder.objects.count()
    response = client.post(f"{BASE}/folders/", {"name": "CSRF bypass"}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Folder.objects.count() == before


def test_authenticated_profile_overrides_spoofed_header_and_body_tenant(
    authenticated_tenant_a_client: APIClient,
    tenant_ids: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_a_id, tenant_b_id = tenant_ids
    response = authenticated_tenant_a_client.post(
        f"{BASE}/folders/",
        {"name": "Profile-bound", "tenant_id": str(tenant_b_id)},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_b_id),
    )
    assert response.status_code == status.HTTP_201_CREATED
    created = Folder.objects.get(id=response.json()["data"]["id"])
    assert created.tenant_id == tenant_a_id


def test_folder_foreign_parent_and_move_target_are_invisible(
    authenticated_tenant_a_client: APIClient,
    folder_pair: tuple[Folder, Folder],
) -> None:
    folder_a, folder_b = folder_pair
    count_before = Folder.objects.count()
    create = authenticated_tenant_a_client.post(
        f"{BASE}/folders/",
        {"name": "Foreign child", "parent_id": str(folder_b.id)},
        format="json",
    )
    assert create.status_code == status.HTTP_404_NOT_FOUND
    assert Folder.objects.count() == count_before

    before = _snapshot(folder_a)
    move = authenticated_tenant_a_client.post(
        f"{BASE}/folders/{folder_a.id}/move/",
        {"parent_id": str(folder_b.id)},
        format="json",
    )
    assert move.status_code == status.HTTP_404_NOT_FOUND
    assert _snapshot(folder_a) == before


def test_document_foreign_folder_and_move_target_are_invisible(
    authenticated_tenant_a_client: APIClient,
    graph_pair: tuple[DocumentGraph, DocumentGraph],
    folder_pair: tuple[Folder, Folder],
    isolation_services: IsolationServices,
) -> None:
    graph_a, _graph_b = graph_pair
    _folder_a, folder_b = folder_pair
    document_count = Document.objects.count()
    stored_keys = set(isolation_services.storage.objects)
    upload = authenticated_tenant_a_client.post(
        f"{BASE}/documents/",
        {
            "file": SimpleUploadedFile("foreign.txt", b"must not persist", content_type="text/plain"),
            "name": "Foreign folder attempt",
            "folder_id": str(folder_b.id),
        },
        format="multipart",
    )
    assert upload.status_code == status.HTTP_404_NOT_FOUND
    assert Document.objects.count() == document_count
    assert set(isolation_services.storage.objects) == stored_keys

    before = _snapshot(graph_a.document)
    move = authenticated_tenant_a_client.post(
        f"{BASE}/documents/{graph_a.document.id}/move/",
        {"folder_id": str(folder_b.id)},
        format="json",
    )
    assert move.status_code == status.HTTP_404_NOT_FOUND
    assert _snapshot(graph_a.document) == before


def test_version_list_detail_create_restore_and_download_are_tenant_scoped(
    authenticated_tenant_a_client: APIClient,
    graph_pair: tuple[DocumentGraph, DocumentGraph],
    isolation_services: IsolationServices,
) -> None:
    graph_a, graph_b = graph_pair
    foreign_version_before = _snapshot(graph_b.version)
    version_count = DocumentVersion.objects.count()
    stored_keys = set(isolation_services.storage.objects)

    assert (
        authenticated_tenant_a_client.get(f"{BASE}/document-versions/?document_id={graph_b.document.id}").status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert (
        authenticated_tenant_a_client.get(f"{BASE}/document-versions/{graph_b.version.id}/").status_code
        == status.HTTP_404_NOT_FOUND
    )
    create = authenticated_tenant_a_client.post(
        f"{BASE}/document-versions/",
        {
            "document_id": str(graph_b.document.id),
            "file": SimpleUploadedFile("foreign-v2.txt", b"forbidden", content_type="text/plain"),
            "change_note": "Cross-tenant replacement",
        },
        format="multipart",
    )
    assert create.status_code == status.HTTP_404_NOT_FOUND
    restore = authenticated_tenant_a_client.post(
        f"{BASE}/document-versions/{graph_b.version.id}/restore/",
        {"change_note": "Cross-tenant restore"},
        format="json",
    )
    assert restore.status_code == status.HTTP_404_NOT_FOUND
    assert DocumentVersion.objects.count() == version_count
    assert set(isolation_services.storage.objects) == stored_keys
    assert _snapshot(graph_b.version) == foreign_version_before

    foreign_document = authenticated_tenant_a_client.get(f"{BASE}/documents/{graph_b.document.id}/download/")
    assert foreign_document.status_code == status.HTTP_404_NOT_FOUND
    foreign_version = authenticated_tenant_a_client.get(
        f"{BASE}/documents/{graph_a.document.id}/download/?version_id={graph_b.version.id}"
    )
    assert foreign_version.status_code == status.HTTP_404_NOT_FOUND


def test_permission_grant_cannot_target_foreign_document(
    authenticated_tenant_a_client: APIClient,
    graph_pair: tuple[DocumentGraph, DocumentGraph],
    isolation_services: IsolationServices,
) -> None:
    _graph_a, graph_b = graph_pair
    before = DocumentPermission.objects.count()
    response = authenticated_tenant_a_client.post(
        f"{BASE}/document-permissions/",
        {
            "document_id": str(graph_b.document.id),
            "principal_type": "user",
            "principal_id": str(isolation_services.verified_principal),
            "permission": "read",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert DocumentPermission.objects.count() == before


def test_share_create_and_revoke_cannot_target_foreign_rows(
    authenticated_tenant_a_client: APIClient,
    graph_pair: tuple[DocumentGraph, DocumentGraph],
    share_pair: tuple[DocumentShare, DocumentShare],
) -> None:
    _graph_a, graph_b = graph_pair
    _share_a, share_b = share_pair
    count_before = DocumentShare.objects.count()
    create = authenticated_tenant_a_client.post(
        f"{BASE}/document-shares/",
        {
            "document_id": str(graph_b.document.id),
            "version_id": str(graph_b.version.id),
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            "max_access_count": 1,
        },
        format="json",
    )
    assert create.status_code == status.HTTP_404_NOT_FOUND
    assert DocumentShare.objects.count() == count_before

    before = _snapshot(share_b)
    revoke = authenticated_tenant_a_client.post(
        f"{BASE}/document-shares/{share_b.id}/revoke/",
        {},
        format="json",
    )
    assert revoke.status_code == status.HTTP_404_NOT_FOUND
    assert _snapshot(share_b) == before


def test_foreign_public_token_exposes_only_pinned_content_not_tenant_metadata(
    authenticated_tenant_a_client: APIClient,
    graph_pair: tuple[DocumentGraph, DocumentGraph],
    actor_ids: tuple[uuid.UUID, uuid.UUID],
    isolation_services: IsolationServices,
) -> None:
    _graph_a, graph_b = graph_pair
    _actor_a, actor_b = actor_ids
    created = isolation_services.shares.create_share(
        graph_b.document.tenant_id,
        actor_b,
        graph_b.document.id,
        version_id=graph_b.version.id,
        expires_at=timezone.now() + timedelta(hours=1),
        max_access_count=1,
    )

    response = authenticated_tenant_a_client.get(created.share_url)
    assert response.status_code == status.HTTP_200_OK
    assert b"".join(response.streaming_content) == b"tenant B evidence"
    assert response["Content-Type"] == "text/plain"
    assert "tenant" not in response.headers
    assert str(graph_b.document.tenant_id) not in str(response.headers)
    assert str(graph_b.document.id) not in str(response.headers)
    assert str(graph_b.version.id) not in str(response.headers)
    assert authenticated_tenant_a_client.get(created.share_url).status_code == status.HTTP_404_NOT_FOUND


def test_dms_outbox_worker_requires_and_filters_by_tenant(
    tenant_ids: tuple[uuid.UUID, uuid.UUID],
    actor_ids: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_a_id, tenant_b_id = tenant_ids
    actor_a, actor_b = actor_ids
    folder_a, folder_b = uuid.uuid4(), uuid.uuid4()
    publish_domain_event(
        tenant_a_id,
        FOLDER_CREATED,
        "folder",
        folder_a,
        actor_id=actor_a,
        payload=FolderEventData(folder_a),
    )
    publish_domain_event(
        tenant_b_id,
        FOLDER_CREATED,
        "folder",
        folder_b,
        actor_id=actor_b,
        payload=FolderEventData(folder_b),
    )

    @tenant_context_worker
    def load_dms_outbox(*, tenant_id: uuid.UUID) -> tuple[uuid.UUID, list[uuid.UUID]]:
        current = get_current_tenant_id()
        assert current is not None
        event_tenants = list(
            OutboxEvent.objects.for_tenant(tenant_id)
            .filter(event_type__startswith="dms.")
            .values_list("tenant_id", flat=True)
        )
        return current, event_tenants

    current, event_tenants = load_dms_outbox(tenant_id=tenant_a_id)
    assert current == tenant_a_id
    assert event_tenants == [tenant_a_id]
    with pytest.raises(MissingTenantContext):
        load_dms_outbox()  # type: ignore[call-arg]


@pytest.mark.postgresql
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="PostgreSQL RLS behavior requires the PostgreSQL test database",
)
@pytest.mark.django_db(transaction=True)
def test_postgresql_rls_blocks_unscoped_cross_tenant_reads_and_writes(
    tenant_ids: tuple[uuid.UUID, uuid.UUID],
    folder_pair: tuple[Folder, Folder],
    graph_pair: tuple[DocumentGraph, DocumentGraph],
    permission_pair: tuple[DocumentPermission, DocumentPermission],
    share_pair: tuple[DocumentShare, DocumentShare],
) -> None:
    """Prove FORCE RLS on all five canonical DMS tables as a non-owner."""

    tenant_a_id, _tenant_b_id = tenant_ids
    model_rows = (
        (Folder, folder_pair),
        (Document, (graph_pair[0].document, graph_pair[1].document)),
        (DocumentVersion, (graph_pair[0].version, graph_pair[1].version)),
        (DocumentPermission, permission_pair),
        (DocumentShare, share_pair),
    )
    role_name = f"saraise_dms_rls_{uuid.uuid4().hex}"
    table_names = [model._meta.db_table for model, _rows in model_rows]

    with connection.cursor() as cursor:
        cursor.execute(f'CREATE ROLE "{role_name}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
        cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{role_name}"')
        for table_name in table_names:
            cursor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table_name}" TO "{role_name}"')

    try:
        with tenant_context(tenant_a_id):
            with connection.cursor() as cursor:
                cursor.execute(f'SET LOCAL ROLE "{role_name}"')
                for model, (own, foreign) in model_rows:
                    table_name = model._meta.db_table
                    cursor.execute(f'SELECT id, tenant_id FROM "{table_name}" ORDER BY id')
                    visible = cursor.fetchall()
                    assert visible
                    assert {row[1] for row in visible} == {tenant_a_id}
                    assert own.id in {row[0] for row in visible}
                    assert foreign.id not in {row[0] for row in visible}

                    cursor.execute(
                        f'UPDATE "{table_name}" SET created_by = %s WHERE id = %s',
                        [uuid.uuid4(), foreign.id],
                    )
                    assert cursor.rowcount == 0
                    cursor.execute(f'DELETE FROM "{table_name}" WHERE id = %s', [foreign.id])
                    assert cursor.rowcount == 0
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP OWNED BY "{role_name}"')
            cursor.execute(f'DROP ROLE IF EXISTS "{role_name}"')
