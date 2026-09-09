"""
Service Unit Tests for Localization module.

Tests business logic in services layer.
"""

import uuid

import pytest

from django.core.cache import cache

from src.modules.localization.models import (
    Language,
    LocaleConfig,
    TenantBaseModel,
    Translation,
)
from src.modules.localization.services import LocalizationService, TranslationService


@pytest.mark.django_db
class TestLocalizationService:
    """Test LocalizationService business logic."""

    def test_create_resource(self, db):
        """Test creating a resource via service."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            description="Test description",
            created_by="user-123",
        )
        assert resource.id is not None
        assert resource.name == "Test Resource"
        assert resource.tenant_id == "tenant-123"

    def test_get_resource(self, db):
        """Test getting a resource by ID."""
        service = LocalizationService()
        created = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )

        retrieved = service.get_resource(created.id, "tenant-123")
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test Resource"

    def test_get_resource_wrong_tenant(self, db):
        """Test that getting resource from wrong tenant returns None."""
        service = LocalizationService()
        created = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )

        retrieved = service.get_resource(created.id, "tenant-456")
        assert retrieved is None

    def test_list_resources(self, db):
        """Test listing resources for tenant."""
        service = LocalizationService()
        service.create_resource(
            tenant_id="tenant-123",
            name="Resource 1",
            created_by="user-123",
        )
        service.create_resource(
            tenant_id="tenant-123",
            name="Resource 2",
            created_by="user-123",
        )
        service.create_resource(
            tenant_id="tenant-456",
            name="Resource 3",
            created_by="user-456",
        )

        resources = service.list_resources("tenant-123")
        assert len(resources) == 2
        assert all(r.tenant_id == "tenant-123" for r in resources)

    def test_update_resource(self, db):
        """Test updating a resource."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Original Name",
            created_by="user-123",
        )

        updated = service.update_resource(
            resource.id,
            "tenant-123",
            name="Updated Name",
            description="Updated description",
        )
        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.description == "Updated description"

    def test_delete_resource(self, db):
        """Test deleting a resource."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="To Delete",
            created_by="user-123",
        )

        result = service.delete_resource(resource.id, "tenant-123")
        assert result is True
        assert not TenantBaseModel.objects.filter(id=resource.id).exists()

    def test_activate_resource(self, db):
        """Test activating a resource."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )
        resource.is_active = False
        resource.save()

        activated = service.activate_resource(resource.id, "tenant-123")
        assert activated is not None
        assert activated.is_active is True

    def test_deactivate_resource(self, db):
        """Test deactivating a resource."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )

        deactivated = service.deactivate_resource(resource.id, "tenant-123")
        assert deactivated is not None
        assert deactivated.is_active is False

    def test_create_resource_default_config_and_created_by(self, db):
        """Omitted config defaults to an empty dict; created_by defaults to empty string."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Bare Resource",
        )
        assert resource.config == {}
        assert resource.created_by == ""
        assert resource.description == ""

    def test_create_resource_with_explicit_config(self, db):
        """An explicitly supplied config dict is persisted verbatim, not replaced by {}."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Configured Resource",
            config={"locale": "en-US"},
        )
        assert resource.config == {"locale": "en-US"}

    def test_get_resource_not_found(self, db):
        """A non-existent resource id returns None rather than raising."""
        service = LocalizationService()
        assert service.get_resource("does-not-exist", "tenant-123") is None

    def test_list_resources_no_results(self, db):
        """A tenant with no resources gets an empty list, not None."""
        service = LocalizationService()
        assert service.list_resources("tenant-empty") == []

    def test_list_resources_filters_by_is_active_true(self, db):
        """Passing is_active=True excludes inactive resources."""
        service = LocalizationService()
        active = service.create_resource(
            tenant_id="tenant-123",
            name="Active",
            created_by="user-123",
        )
        inactive = service.create_resource(
            tenant_id="tenant-123",
            name="Inactive",
            created_by="user-123",
        )
        service.deactivate_resource(inactive.id, "tenant-123")

        resources = service.list_resources("tenant-123", is_active=True)
        ids = {r.id for r in resources}
        assert active.id in ids
        assert inactive.id not in ids

    def test_list_resources_filters_by_is_active_false(self, db):
        """Passing is_active=False returns only inactive resources."""
        service = LocalizationService()
        active = service.create_resource(
            tenant_id="tenant-123",
            name="Active",
            created_by="user-123",
        )
        inactive = service.create_resource(
            tenant_id="tenant-123",
            name="Inactive",
            created_by="user-123",
        )
        service.deactivate_resource(inactive.id, "tenant-123")

        resources = service.list_resources("tenant-123", is_active=False)
        ids = {r.id for r in resources}
        assert inactive.id in ids
        assert active.id not in ids

    def test_list_resources_is_active_none_returns_all(self, db):
        """is_active left as None (the default) applies no activity filter at all."""
        service = LocalizationService()
        active = service.create_resource(
            tenant_id="tenant-123",
            name="Active",
            created_by="user-123",
        )
        inactive = service.create_resource(
            tenant_id="tenant-123",
            name="Inactive",
            created_by="user-123",
        )
        service.deactivate_resource(inactive.id, "tenant-123")

        resources = service.list_resources("tenant-123")
        ids = {r.id for r in resources}
        assert {active.id, inactive.id} <= ids

    def test_update_resource_wrong_tenant_returns_none(self, db):
        """Updating with a mismatched tenant_id must not find or mutate the resource."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Original Name",
            created_by="user-123",
        )

        result = service.update_resource(resource.id, "tenant-456", name="Hijacked")
        assert result is None

        untouched = service.get_resource(resource.id, "tenant-123")
        assert untouched.name == "Original Name"

    def test_update_resource_not_found(self, db):
        """Updating a non-existent resource id returns None."""
        service = LocalizationService()
        assert service.update_resource("missing-id", "tenant-123", name="X") is None

    def test_update_resource_ignores_unknown_fields(self, db):
        """Fields outside _UPDATABLE_FIELDS (e.g. created_by, id) are silently dropped."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Original Name",
            created_by="user-123",
        )

        updated = service.update_resource(
            resource.id,
            "tenant-123",
            created_by="someone-else",
            id="different-id",
            name="Allowed Update",
        )
        assert updated is not None
        assert updated.tenant_id == "tenant-123"
        assert updated.created_by == "user-123"
        assert updated.id == resource.id
        assert updated.name == "Allowed Update"

    def test_update_resource_updates_config_field(self, db):
        """The config field is itself updatable."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Original Name",
            created_by="user-123",
        )

        updated = service.update_resource(
            resource.id,
            "tenant-123",
            config={"k": "v"},
        )
        assert updated.config == {"k": "v"}

    def test_update_resource_empty_updates_leaves_resource_unchanged(self, db):
        """Calling update_resource with no recognized fields still returns the (unchanged) resource."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Original Name",
            created_by="user-123",
        )

        updated = service.update_resource(resource.id, "tenant-123")
        assert updated is not None
        assert updated.id == resource.id
        assert updated.name == "Original Name"

    def test_delete_resource_wrong_tenant_returns_false(self, db):
        """Deleting with a mismatched tenant_id must not delete the resource."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Should Survive",
            created_by="user-123",
        )

        result = service.delete_resource(resource.id, "tenant-456")
        assert result is False
        assert TenantBaseModel.objects.filter(id=resource.id).exists()

    def test_delete_resource_not_found_returns_false(self, db):
        """Deleting a non-existent resource id returns False, not True."""
        service = LocalizationService()
        assert service.delete_resource("missing-id", "tenant-123") is False

    def test_activate_resource_wrong_tenant_returns_none(self, db):
        """activate_resource must not leak across tenants."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )
        resource.is_active = False
        resource.save()

        result = service.activate_resource(resource.id, "tenant-456")
        assert result is None
        still_inactive = service.get_resource(resource.id, "tenant-123")
        assert still_inactive.is_active is False

    def test_deactivate_resource_wrong_tenant_returns_none(self, db):
        """deactivate_resource must not leak across tenants."""
        service = LocalizationService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )

        result = service.deactivate_resource(resource.id, "tenant-456")
        assert result is None
        still_active = service.get_resource(resource.id, "tenant-123")
        assert still_active.is_active is True


@pytest.mark.django_db
class TestTranslationService:
    """Test TranslationService business logic, including caching behavior."""

    TENANT = str(uuid.uuid4())
    TENANT_OTHER = str(uuid.uuid4())
    TENANT_A = str(uuid.uuid4())
    TENANT_B = str(uuid.uuid4())
    TENANT_NONE = str(uuid.uuid4())

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        cache.clear()
        yield
        cache.clear()

    @pytest.fixture
    def language(self, db):
        return Language.objects.create(
            code="fr",
            name="French",
            native_name="Français",
            is_active=True,
        )

    @pytest.fixture
    def inactive_language(self, db):
        return Language.objects.create(
            code="xx",
            name="Inactive Lang",
            native_name="Inactive",
            is_active=False,
        )

    def test_translate_returns_stored_translation(self, db, language):
        """A matching Translation row's value is returned verbatim."""
        Translation.objects.create(
            tenant_id=self.TENANT,
            language=language,
            key="greeting.hello",
            value="Bonjour",
            context="",
        )
        service = TranslationService()
        result = service.translate("greeting.hello", "fr", self.TENANT)
        assert result == "Bonjour"

    def test_translate_missing_language_returns_default(self, db):
        """When the language code has no matching active Language, the default is returned."""
        service = TranslationService()
        result = service.translate("greeting.hello", "zz", self.TENANT, default="Hello")
        assert result == "Hello"

    def test_translate_missing_language_no_default_returns_key(self, db):
        """When there is no language and no default, the key itself is the fallback."""
        service = TranslationService()
        result = service.translate("greeting.hello", "zz", self.TENANT)
        assert result == "greeting.hello"

    def test_translate_inactive_language_treated_as_missing(self, db, inactive_language):
        """An inactive language must not be matched — is_active=True is required."""
        Translation.objects.create(
            tenant_id=self.TENANT,
            language=inactive_language,
            key="greeting.hello",
            value="Should Not Be Found",
            context="",
        )
        service = TranslationService()
        result = service.translate("greeting.hello", "xx", self.TENANT, default="Fallback")
        assert result == "Fallback"

    def test_translate_missing_translation_returns_default(self, db, language):
        """Language exists but no Translation row matches: default wins."""
        service = TranslationService()
        result = service.translate("no.such.key", "fr", self.TENANT, default="Missing")
        assert result == "Missing"

    def test_translate_missing_translation_no_default_returns_key(self, db, language):
        """Language exists, no Translation row, no default: the key is returned."""
        service = TranslationService()
        result = service.translate("no.such.key", "fr", self.TENANT)
        assert result == "no.such.key"

    def test_translate_uses_context_when_provided(self, db, language):
        """A context-specific translation is only matched when the same context is requested."""
        Translation.objects.create(
            tenant_id=self.TENANT,
            language=language,
            key="save",
            value="Enregistrer",
            context="button",
        )
        Translation.objects.create(
            tenant_id=self.TENANT,
            language=language,
            key="save",
            value="Sauvegarder",
            context="",
        )
        service = TranslationService()
        with_context = service.translate("save", "fr", self.TENANT, context="button")
        without_context = service.translate("save", "fr", self.TENANT)
        assert with_context == "Enregistrer"
        assert without_context == "Sauvegarder"

    def test_translate_context_translation_not_matched_without_context(self, db, language):
        """A translation stored under a non-empty context is not returned for a contextless lookup."""
        Translation.objects.create(
            tenant_id=self.TENANT,
            language=language,
            key="save",
            value="Enregistrer",
            context="button",
        )
        service = TranslationService()
        result = service.translate("save", "fr", self.TENANT, default="fallback")
        assert result == "fallback"

    def test_translate_scopes_by_tenant(self, db, language):
        """A translation belonging to a different tenant must never be returned."""
        Translation.objects.create(
            tenant_id=self.TENANT_OTHER,
            language=language,
            key="greeting.hello",
            value="Bonjour (other tenant)",
            context="",
        )
        service = TranslationService()
        result = service.translate("greeting.hello", "fr", self.TENANT, default="Hello")
        assert result == "Hello"

    def test_translate_caches_result(self, db, language):
        """A second call for the same key/tenant/language hits the cache, not the DB."""
        translation = Translation.objects.create(
            tenant_id=self.TENANT,
            language=language,
            key="greeting.hello",
            value="Bonjour",
            context="",
        )
        service = TranslationService()
        first = service.translate("greeting.hello", "fr", self.TENANT)
        assert first == "Bonjour"

        translation.value = "Changed After Cache"
        translation.save()

        second = service.translate("greeting.hello", "fr", self.TENANT)
        assert second == "Bonjour"

    def test_translate_cache_key_is_isolated_by_context(self, db, language):
        """Different context values must not collide in the cache key."""
        Translation.objects.create(
            tenant_id=self.TENANT,
            language=language,
            key="save",
            value="Enregistrer",
            context="button",
        )
        Translation.objects.create(
            tenant_id=self.TENANT,
            language=language,
            key="save",
            value="Sauvegarder",
            context="",
        )
        service = TranslationService()
        assert service.translate("save", "fr", self.TENANT, context="button") == "Enregistrer"
        assert service.translate("save", "fr", self.TENANT) == "Sauvegarder"

    def test_translate_cache_key_is_isolated_by_tenant(self, db, language):
        """Two tenants requesting the same key/language must not share a cache entry."""
        Translation.objects.create(
            tenant_id=self.TENANT_A,
            language=language,
            key="greeting.hello",
            value="Bonjour A",
            context="",
        )
        Translation.objects.create(
            tenant_id=self.TENANT_B,
            language=language,
            key="greeting.hello",
            value="Bonjour B",
            context="",
        )
        service = TranslationService()
        assert service.translate("greeting.hello", "fr", self.TENANT_A) == "Bonjour A"
        assert service.translate("greeting.hello", "fr", self.TENANT_B) == "Bonjour B"

    def test_get_tenant_locale_found(self, db, language):
        """get_tenant_locale returns the LocaleConfig for a matching tenant."""
        locale_config = LocaleConfig.objects.create(
            tenant_id=self.TENANT,
            default_language=language,
            timezone="Europe/Paris",
        )
        service = TranslationService()
        result = service.get_tenant_locale(self.TENANT)
        assert result is not None
        assert result.id == locale_config.id
        assert result.timezone == "Europe/Paris"

    def test_get_tenant_locale_not_found(self, db):
        """get_tenant_locale returns None when no LocaleConfig exists for the tenant."""
        service = TranslationService()
        assert service.get_tenant_locale(self.TENANT_NONE) is None

    def test_get_tenant_locale_scoped_by_tenant(self, db, language):
        """A LocaleConfig for one tenant must not be returned for a different tenant."""
        LocaleConfig.objects.create(
            tenant_id=self.TENANT_A,
            default_language=language,
        )
        service = TranslationService()
        assert service.get_tenant_locale(self.TENANT_B) is None

    def test_invalidate_cache_logs_with_language_code(self, db, caplog):
        """invalidate_cache logs an info message including tenant and language when given both."""
        service = TranslationService()
        with caplog.at_level("INFO"):
            result = service.invalidate_cache(self.TENANT, "fr")
        assert result is None
        assert any(
            self.TENANT in record.message and "fr" in record.message for record in caplog.records
        )

    def test_invalidate_cache_logs_without_language_code(self, db, caplog):
        """invalidate_cache logs an info message with 'None' as language when omitted."""
        service = TranslationService()
        with caplog.at_level("INFO"):
            result = service.invalidate_cache(self.TENANT)
        assert result is None
        assert any(
            self.TENANT in record.message and "None" in record.message for record in caplog.records
        )

    def test_cache_timeout_constant(self):
        """CACHE_TIMEOUT is exactly one hour in seconds, as documented."""
        assert TranslationService.CACHE_TIMEOUT == 3600
