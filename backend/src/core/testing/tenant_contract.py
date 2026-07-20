"""Reusable black-box contract for tenant-scoped DRF endpoints.

Modules consume :class:`TenantIsolationContract` by supplying a model, URLs,
valid create/update payloads, two persisted rows, and a tenant-A API client.
The client must use real session authentication; the fixtures in
``src.core.testing.factories`` provide a CSRF-enforcing client for that purpose.
For example::

    pytest_plugins = ["src.core.testing.factories"]

    @pytest.mark.django_db
    class TestWidgetIsolation(TenantIsolationContract):
        model = Widget
        list_url = "/api/v1/widgets/"
        detail_url_template = "/api/v1/widgets/{pk}/"
        create_payload = {"name": "Attempted tenant spoof"}
        update_payload = {"name": "Attempted cross-tenant update"}

        @pytest.fixture(autouse=True)
        def isolation_context(
            self,
            authenticated_tenant_a_client,
            tenant_a_widget,
            tenant_b_widget,
        ):
            self.client = authenticated_tenant_a_client
            self.tenant_a_row = tenant_a_widget
            self.tenant_b_row = tenant_b_widget

Tests using ``unittest`` can assign the same attributes in ``setUp``.  Override
the ``get_*`` hooks when an endpoint uses dynamic URLs, non-standard response
envelopes, or payloads that cannot be expressed as class attributes.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping

from django.db.models import Model
from rest_framework import status
from rest_framework.test import APIClient


class TenantIsolationContract:
    """Assert the complete CRUD isolation boundary for one tenant model.

    The class deliberately does not start with ``Test`` so test runners do not
    collect it on its own.  Concrete subclasses inherit five ``test_*`` methods
    covering list, detail, spoofed create, cross-tenant update, and delete.

    ``create_payload`` must be otherwise valid for the endpoint.  A server may
    either reject an explicit tenant override or ignore it and create the row
    for tenant A; both behaviours enforce isolation and are verified without
    treating an arbitrary error as success.
    """

    model: type[Model] | None = None
    list_url: str | None = None
    detail_url_template: str | None = None
    create_payload: Mapping[str, Any] | None = None
    update_payload: Mapping[str, Any] | None = None

    tenant_field = "tenant_id"
    tenant_payload_field = "tenant_id"
    response_identity_field = "id"
    row_identity_attribute = "pk"
    request_format: str | None = "json"
    update_method = "patch"

    read_denial_statuses = frozenset({status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND})
    write_denial_statuses = frozenset(
        {
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        }
    )
    create_success_statuses = frozenset({status.HTTP_200_OK, status.HTTP_201_CREATED})

    def get_client(self) -> APIClient:
        """Return the session-authenticated tenant-A client."""

        client = getattr(self, "client", None)
        if client is None:
            raise AssertionError(
                "TenantIsolationContract requires self.client to be a " "session-authenticated tenant-A APIClient"
            )
        return client

    def get_tenant_a_row(self) -> Model:
        """Return a persisted row owned by tenant A."""

        return self._required_row("tenant_a_row")

    def get_tenant_b_row(self) -> Model:
        """Return a persisted row owned by tenant B."""

        return self._required_row("tenant_b_row")

    def get_model(self) -> type[Model]:
        """Return the concrete tenant-scoped model under test."""

        if self.model is not None:
            return self.model
        return type(self.get_tenant_a_row())

    def get_list_url(self) -> str:
        """Return the collection endpoint URL."""

        if self.list_url is None:
            raise AssertionError("TenantIsolationContract requires list_url or a get_list_url() override")
        return self.list_url

    def get_detail_url(self, row: Model) -> str:
        """Return the detail endpoint URL for ``row``."""

        if self.detail_url_template is None:
            raise AssertionError(
                "TenantIsolationContract requires detail_url_template or a " "get_detail_url() override"
            )
        return self.detail_url_template.format(pk=getattr(row, self.row_identity_attribute))

    def get_create_payload(self) -> MutableMapping[str, Any]:
        """Return an otherwise-valid payload for a create request."""

        if self.create_payload is None:
            raise AssertionError(
                "TenantIsolationContract requires create_payload or a " "get_create_payload() override"
            )
        return dict(deepcopy(self.create_payload))

    def get_update_payload(self) -> MutableMapping[str, Any]:
        """Return a valid partial-update payload."""

        if self.update_payload is None:
            raise AssertionError(
                "TenantIsolationContract requires update_payload or a " "get_update_payload() override"
            )
        return dict(deepcopy(self.update_payload))

    def get_list_items(self, response: Any) -> list[Mapping[str, Any]]:
        """Extract rows from an unpaginated or standard paginated DRF response."""

        payload = self._response_payload(response)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, Mapping) and isinstance(payload.get("results"), list):
            return payload["results"]
        raise AssertionError(
            "List response must be a JSON list or a mapping with a list-valued "
            "'results' key; override get_list_items() for a custom envelope"
        )

    def get_response_identity(self, item: Mapping[str, Any]) -> Any:
        """Extract a model identity from one serialized list row."""

        if self.response_identity_field not in item:
            raise AssertionError(f"Serialized row has no {self.response_identity_field!r} identity: {item!r}")
        return item[self.response_identity_field]

    def test_tenant_list_is_isolated(self) -> None:
        """Tenant A sees its row and cannot enumerate tenant B's row."""

        tenant_a_row, tenant_b_row = self._validated_rows()
        response = self.get_client().get(self.get_list_url())

        assert response.status_code == status.HTTP_200_OK, self._status_failure("list tenant-scoped rows", response)
        identities = {
            self._normalise_identity(self.get_response_identity(item)) for item in self.get_list_items(response)
        }
        tenant_a_identity = self._normalise_identity(getattr(tenant_a_row, self.row_identity_attribute))
        tenant_b_identity = self._normalise_identity(getattr(tenant_b_row, self.row_identity_attribute))
        assert tenant_a_identity in identities, (
            "The tenant-A control row was not visible in the list response; "
            "the endpoint or test context is not exercising a usable list path"
        )
        assert (
            tenant_b_identity not in identities
        ), f"Tenant-B row {tenant_b_identity} leaked into tenant A's list response"

    def test_cross_tenant_detail_is_invisible(self) -> None:
        """Tenant A cannot retrieve tenant B's row by a known identifier."""

        _, tenant_b_row = self._validated_rows()
        response = self.get_client().get(self.get_detail_url(tenant_b_row))

        assert response.status_code in self.read_denial_statuses, self._status_failure(
            "retrieve a tenant-B row", response
        )

    def test_spoofed_tenant_create_is_denied(self) -> None:
        """A client-supplied tenant B identifier can never create a tenant-B row."""

        tenant_a_row, tenant_b_row = self._validated_rows()
        model = self.get_model()
        tenant_a_id = self._row_tenant_id(tenant_a_row)
        tenant_b_id = self._row_tenant_id(tenant_b_row)
        all_rows_before = self._all_rows_snapshot(model)
        tenant_b_before = self._tenant_rows_snapshot(model, tenant_b_id)

        payload = self.get_create_payload()
        payload[self.tenant_payload_field] = tenant_b_id
        response = self._request("post", self.get_list_url(), payload)

        if response.status_code in self.write_denial_statuses:
            assert (
                self._all_rows_snapshot(model) == all_rows_before
            ), "A rejected spoofed-tenant create changed the model's database rows"
            return

        assert response.status_code in self.create_success_statuses, self._status_failure(
            "create with a spoofed tenant identifier", response
        )
        tenant_b_after = self._tenant_rows_snapshot(model, tenant_b_id)
        assert tenant_b_after == tenant_b_before, "The spoofed create inserted or changed a row belonging to tenant B"

        all_rows_after = self._all_rows_snapshot(model)
        new_identities = set(all_rows_after).difference(all_rows_before)
        assert len(new_identities) == 1, (
            "A successful create must add exactly one model row so its tenant "
            f"assignment can be proven; observed new identities: {new_identities!r}"
        )
        created_identity = new_identities.pop()
        created = model._base_manager.get(pk=created_identity)
        assert self._same_tenant(self._row_tenant_id(created), tenant_a_id), (
            "The server accepted the spoofed tenant identifier instead of binding "
            "the new row to the authenticated tenant A"
        )

    def test_cross_tenant_update_is_denied_and_unchanged(self) -> None:
        """Tenant A cannot update tenant B, and the target remains byte-for-byte stable."""

        _, tenant_b_row = self._validated_rows()
        before = self._row_snapshot(tenant_b_row)
        response = self._request(
            self.update_method,
            self.get_detail_url(tenant_b_row),
            self.get_update_payload(),
        )

        assert response.status_code in self.read_denial_statuses, self._status_failure(
            "update a tenant-B row", response
        )
        assert (
            self._row_snapshot(tenant_b_row) == before
        ), "The tenant-B row changed after the denied cross-tenant update"

    def test_cross_tenant_delete_is_denied_and_unchanged(self) -> None:
        """Tenant A cannot delete tenant B, and the target row remains unchanged."""

        _, tenant_b_row = self._validated_rows()
        before = self._row_snapshot(tenant_b_row)
        response = self._request("delete", self.get_detail_url(tenant_b_row), data=None)

        assert response.status_code in self.read_denial_statuses, self._status_failure(
            "delete a tenant-B row", response
        )
        assert (
            self._row_snapshot(tenant_b_row) == before
        ), "The tenant-B row was deleted or changed after the denied delete"

    def _validated_rows(self) -> tuple[Model, Model]:
        tenant_a_row = self.get_tenant_a_row()
        tenant_b_row = self.get_tenant_b_row()
        model = self.get_model()
        assert isinstance(
            tenant_a_row, model
        ), f"tenant_a_row must be a {model.__name__}, got {type(tenant_a_row).__name__}"
        assert isinstance(
            tenant_b_row, model
        ), f"tenant_b_row must be a {model.__name__}, got {type(tenant_b_row).__name__}"
        tenant_a_id = self._row_tenant_id(tenant_a_row)
        tenant_b_id = self._row_tenant_id(tenant_b_row)
        assert (
            tenant_a_id is not None and tenant_b_id is not None
        ), f"Both test rows must have a non-null {self.tenant_field}"
        assert not self._same_tenant(
            tenant_a_id, tenant_b_id
        ), "tenant_a_row and tenant_b_row must belong to different tenants"
        return tenant_a_row, tenant_b_row

    def _required_row(self, attribute: str) -> Model:
        row = getattr(self, attribute, None)
        if row is None:
            raise AssertionError(
                f"TenantIsolationContract requires self.{attribute} to be a " "persisted tenant-scoped model instance"
            )
        if not isinstance(row, Model):
            raise AssertionError(f"self.{attribute} must be a Django model instance, " f"got {type(row).__name__}")
        if row.pk is None:
            raise AssertionError(f"self.{attribute} must already be persisted")
        return row

    def _row_tenant_id(self, row: Model) -> Any:
        if not hasattr(row, self.tenant_field):
            raise AssertionError(f"{type(row).__name__} has no {self.tenant_field!r} tenant field")
        return getattr(row, self.tenant_field)

    def _request(
        self,
        method: str,
        url: str,
        data: MutableMapping[str, Any] | None,
    ) -> Any:
        request_method = getattr(self.get_client(), method.lower(), None)
        if request_method is None:
            raise AssertionError(f"API client does not support HTTP {method.upper()}")
        kwargs: dict[str, Any] = {"data": data}
        if self.request_format is not None:
            kwargs["format"] = self.request_format
        return request_method(url, **kwargs)

    def _row_snapshot(self, row: Model) -> tuple[tuple[str, Any], ...]:
        fresh = type(row)._base_manager.get(pk=row.pk)
        return tuple((field.attname, getattr(fresh, field.attname)) for field in fresh._meta.concrete_fields)

    def _all_rows_snapshot(self, model: type[Model]) -> dict[Any, tuple[tuple[str, Any], ...]]:
        return {row.pk: self._row_snapshot(row) for row in model._base_manager.all().iterator()}

    def _tenant_rows_snapshot(self, model: type[Model], tenant_id: Any) -> dict[Any, tuple[tuple[str, Any], ...]]:
        rows = model._base_manager.filter(**{self.tenant_field: tenant_id})
        return {row.pk: self._row_snapshot(row) for row in rows.iterator()}

    @staticmethod
    def _response_payload(response: Any) -> Any:
        if hasattr(response, "data"):
            return response.data
        try:
            return response.json()
        except (AttributeError, TypeError, ValueError) as exc:
            raise AssertionError("API response does not contain valid JSON data") from exc

    @classmethod
    def _status_failure(cls, action: str, response: Any) -> str:
        try:
            payload = cls._response_payload(response)
        except AssertionError:
            payload = "<non-JSON response>"
        return (
            f"Unexpected HTTP {getattr(response, 'status_code', '<missing>')} while "
            f"attempting to {action}; response={payload!r}"
        )

    @staticmethod
    def _normalise_identity(value: Any) -> str:
        return str(value)

    @classmethod
    def _same_tenant(cls, left: Any, right: Any) -> bool:
        return cls._normalise_identity(left) == cls._normalise_identity(right)
