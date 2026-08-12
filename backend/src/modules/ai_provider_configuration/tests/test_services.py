"""Service tests for governed AI-provider configuration behavior."""

from __future__ import annotations

import uuid
from copy import deepcopy

import pytest
from cryptography.fernet import Fernet
from rest_framework.exceptions import ValidationError

from src.core.encryption import EncryptionService
from src.modules.ai_provider_configuration.models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    CredentialStatus,
    DeploymentStatus,
    ProviderType,
    TenantBaseModel,
)
from src.modules.ai_provider_configuration.services import (
    DEFAULT_RUNTIME_CONFIGURATION,
    AIProviderConfigurationService,
    AiProviderConfigurationService,
    AIProviderFactory,
    AIProviderRuntimeConfigurationService,
    AIUsageService,
    AnthropicProvider,
    AzureOpenAIProvider,
    CustomProvider,
    GoogleGeminiProvider,
    GroqProvider,
    HuggingFaceProvider,
    InvalidProviderResponse,
    MistralProvider,
    OpenAIProvider,
    ProviderUnavailable,
)


@pytest.mark.django_db
class TestAiProviderConfigurationService:
    def test_create_resource_requires_uuid_tenant_and_idempotency(self) -> None:
        service = AiProviderConfigurationService()
        with pytest.raises(ValidationError):
            service.create_resource(tenant_id="tenant-123", name="Test Resource", created_by=uuid.uuid4())
        with pytest.raises(ValidationError):
            service.create_resource(tenant_id=uuid.uuid4(), name="Test Resource", created_by=uuid.uuid4())

    def test_create_resource(self) -> None:
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        resource = AiProviderConfigurationService().create_resource(
            tenant_id=tenant_id,
            name="Test Resource",
            description="Test description",
            created_by=actor_id,
            idempotency_key="create-resource",
        )
        assert resource.id is not None
        assert resource.name == "Test Resource"
        assert resource.tenant_id == tenant_id
        assert resource.created_by == actor_id

    def test_create_resource_replays_same_idempotency_key(self) -> None:
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        service = AiProviderConfigurationService()
        first = service.create_resource(
            tenant_id=tenant_id,
            name="Test Resource",
            created_by=actor_id,
            idempotency_key="same-request",
        )
        second = service.create_resource(
            tenant_id=tenant_id,
            name="Test Resource",
            created_by=actor_id,
            idempotency_key="same-request",
        )
        assert second.id == first.id

    def test_get_resource_wrong_tenant(self) -> None:
        service = AiProviderConfigurationService()
        resource = service.create_resource(
            tenant_id=uuid.uuid4(),
            name="Test Resource",
            created_by=uuid.uuid4(),
            idempotency_key="tenant-a-create",
        )
        assert service.get_resource(resource.id, uuid.uuid4()) is None

    def test_update_resource_validates_allowed_config_keys(self) -> None:
        tenant_id = uuid.uuid4()
        service = AiProviderConfigurationService()
        resource = service.create_resource(
            tenant_id=tenant_id,
            name="Original Name",
            created_by=uuid.uuid4(),
            idempotency_key="update-create",
        )
        updated = service.update_resource(resource.id, tenant_id, name="Updated Name", config={"owner": "ops"})
        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.config == {"owner": "ops"}
        with pytest.raises(ValidationError):
            service.update_resource(resource.id, tenant_id, config={"unsupported": True})

    def test_delete_and_restore_resource_are_reversible(self) -> None:
        tenant_id = uuid.uuid4()
        service = AiProviderConfigurationService()
        resource = service.create_resource(
            tenant_id=tenant_id,
            name="To Archive",
            created_by=uuid.uuid4(),
            idempotency_key="delete-create",
        )
        assert service.delete_resource(resource.id, tenant_id) is True
        archived = TenantBaseModel.objects.get(id=resource.id)
        assert archived.is_deleted is True
        restored = service.restore_resource(resource.id, tenant_id)
        assert restored.is_deleted is False

    def test_activate_and_deactivate_resource(self) -> None:
        tenant_id = uuid.uuid4()
        service = AiProviderConfigurationService()
        resource = service.create_resource(
            tenant_id=tenant_id,
            name="Toggle Resource",
            created_by=uuid.uuid4(),
            idempotency_key="toggle-create",
        )
        assert service.deactivate_resource(resource.id, tenant_id).is_active is False
        assert service.activate_resource(resource.id, tenant_id).is_active is True


class ResponseStub:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> object:
        return self.body


class InvalidJsonResponseStub(ResponseStub):
    def json(self) -> object:
        raise ValueError("not json")


class HttpClientStub:
    def __init__(self, response: ResponseStub) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> ResponseStub:
        self.calls.append({"url": url, **kwargs})
        return self.response


def runtime_document(**overrides: object) -> dict[str, object]:
    document = deepcopy(DEFAULT_RUNTIME_CONFIGURATION)
    document.update(overrides)
    return document


def merge_runtime_patch(document: dict[str, object], patch: dict[str, object]) -> None:
    for section, values in patch.items():
        if isinstance(values, dict) and isinstance(document.get(section), dict):
            target = document[section]
            for key, value in values.items():
                if isinstance(value, dict) and isinstance(target.get(key), dict):  # type: ignore[attr-defined]
                    target[key].update(value)  # type: ignore[index, union-attr]
                else:
                    target[key] = value  # type: ignore[index]
        else:
            document[section] = values


def configure_encryption(settings) -> None:
    key = Fernet.generate_key().decode("ascii")
    settings.SARAISE_ENCRYPTION_KEYS = {"primary": key}
    settings.SARAISE_ACTIVE_ENCRYPTION_KEY_ID = "primary"
    settings.SARAISE_ENCRYPTION_KEY = None
    EncryptionService._fernet = None
    EncryptionService._cached_keys = None


@pytest.mark.django_db
def test_runtime_configuration_preview_update_rollback_and_import_validation() -> None:
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    proposed = runtime_document(pagination={"default_page_size": 50, "max_page_size": 100})

    preview = AIProviderRuntimeConfigurationService.preview(tenant_id, actor_id, proposed)
    assert preview["current_version"] == 1
    assert preview["would_create_version"] == 2
    assert preview["changes"]["pagination"]["after"]["default_page_size"] == 50

    updated = AIProviderRuntimeConfigurationService.update(tenant_id, actor_id, proposed)
    assert updated.version == 2
    assert updated.values["pagination"]["default_page_size"] == 50

    rolled_back = AIProviderRuntimeConfigurationService.rollback(tenant_id, actor_id, 1)
    assert rolled_back.version == 3
    assert rolled_back.values["pagination"]["default_page_size"] == 25

    with pytest.raises(ValidationError):
        AIProviderRuntimeConfigurationService.import_document(
            tenant_id,
            actor_id,
            {"module": "wrong", "environment": "default", "values": DEFAULT_RUNTIME_CONFIGURATION},
        )


def test_runtime_configuration_rejects_fail_open_or_inconsistent_policy() -> None:
    duplicate_types = runtime_document(provider_types=["openai", "openai"])
    with pytest.raises(ValidationError) as duplicate_error:
        AIProviderRuntimeConfigurationService.validate_values(duplicate_types)
    assert "provider_types" in duplicate_error.value.detail

    http_endpoint = runtime_document(provider_endpoints={"openai": "http://api.example.test"})
    with pytest.raises(ValidationError) as endpoint_error:
        AIProviderRuntimeConfigurationService.validate_values(http_endpoint)
    assert "provider_endpoints" in endpoint_error.value.detail

    token_limits = runtime_document()
    token_limits["deployment_policy"]["limits"]["max_tokens_min"] = 20  # type: ignore[index]
    token_limits["deployment_policy"]["defaults"]["max_tokens"] = 10  # type: ignore[index]
    with pytest.raises(ValidationError) as limits_error:
        AIProviderRuntimeConfigurationService.validate_values(token_limits)
    assert "deployment_policy.defaults.max_tokens" in limits_error.value.detail

    incomplete_deployment = runtime_document()
    del incomplete_deployment["deployment_policy"]["limits"]["temperature_max"]  # type: ignore[index]
    with pytest.raises(ValidationError) as incomplete_error:
        AIProviderRuntimeConfigurationService.validate_values(incomplete_deployment)
    assert "deployment_policy" in incomplete_error.value.detail


def test_runtime_configuration_rejects_schema_and_control_boundary_drift() -> None:
    with pytest.raises(ValidationError) as non_object:
        AIProviderRuntimeConfigurationService.validate_values([])  # type: ignore[arg-type]
    assert "values" in non_object.value.detail

    unknown = runtime_document(extra_section=True)
    with pytest.raises(ValidationError) as unknown_error:
        AIProviderRuntimeConfigurationService.validate_values(unknown)
    assert "unknown_fields" in unknown_error.value.detail

    missing = runtime_document()
    del missing["field_limits"]
    with pytest.raises(ValidationError) as missing_error:
        AIProviderRuntimeConfigurationService.validate_values(missing)
    assert "missing_fields" in missing_error.value.detail

    invalid_cases = [
        ("provider_types", {"provider_types": []}),
        ("provider_endpoints", {"provider_endpoints": []}),
        ("field_limits.prompt_max", {"field_limits": {"prompt_max": True}}),
        ("resilience.connect_timeout_seconds", {"resilience": {"connect_timeout_seconds": 0}}),
        ("resilience.max_retries", {"resilience": {"max_retries": True}}),
        ("resilience.failure_threshold", {"resilience": {"failure_threshold": 0}}),
        (
            "deployment_policy.limits",
            {"deployment_policy": {"limits": {"max_tokens_min": 100, "max_tokens_max": 10}}},
        ),
        (
            "deployment_policy.defaults.temperature",
            {"deployment_policy": {"defaults": {"temperature": 99}}},
        ),
        (
            "deployment_policy.editable_config_fields",
            {"deployment_policy": {"editable_config_fields": ["temperature", "unsafe"]}},
        ),
        ("deployment_policy.default_status", {"deployment_policy": {"default_status": "unknown"}}),
        (
            "credential_policy.permitted_deployment_statuses",
            {"credential_policy": {"permitted_deployment_statuses": ["root"]}},
        ),
        ("metering.currency_allowlist", {"metering": {"currency_allowlist": ["usd"]}}),
        ("metering.default_currency", {"metering": {"currency_allowlist": ["USD"], "default_currency": "EUR"}}),
        ("feature_flags", {"feature_flags": {"configuration_ui": "yes"}}),
        ("rollout", {"rollout": []}),
    ]
    for field, patch in invalid_cases:
        document = runtime_document()
        merge_runtime_patch(document, patch)
        with pytest.raises(ValidationError) as caught:
            AIProviderRuntimeConfigurationService.validate_values(document)
        assert field in caught.value.detail


def test_openai_provider_maps_success_and_rejects_bad_provider_evidence() -> None:
    http = HttpClientStub(ResponseStub(200, {"choices": [{"message": {"content": "accepted"}}]}))
    provider = OpenAIProvider("secret-key", http_client=http)

    assert provider.complete("hello", "gpt-test", max_tokens=12, temperature=0.2) == "accepted"
    assert http.calls[0]["dependency"] == "ai-provider-openai"
    assert http.calls[0]["json"]["messages"][0]["content"] == "hello"  # type: ignore[index]

    bad_shape = OpenAIProvider("secret-key", http_client=HttpClientStub(ResponseStub(200, {"choices": []})))
    with pytest.raises(InvalidProviderResponse):
        bad_shape.complete("hello", "gpt-test")

    rejected = OpenAIProvider("secret-key", http_client=HttpClientStub(ResponseStub(429, {"error": "rate"})))
    with pytest.raises(ProviderUnavailable):
        rejected.complete("hello", "gpt-test")

    with pytest.raises(ValidationError):
        provider.complete("", "gpt-test")


def test_provider_adapters_reject_invalid_runtime_requests_and_transport_failures() -> None:
    with pytest.raises(ProviderUnavailable):
        OpenAIProvider("")
    with pytest.raises(ProviderUnavailable):
        OpenAIProvider("secret-key", base_url="not-a-url")

    provider = OpenAIProvider(
        "secret-key",
        http_client=HttpClientStub(ResponseStub(200, {"choices": [{"message": {"content": "accepted"}}]})),
    )
    with pytest.raises(ValidationError) as token_error:
        provider.complete("hello", "gpt-test", max_tokens=True)
    assert "max_tokens" in token_error.value.detail
    with pytest.raises(ValidationError) as temperature_error:
        provider.complete("hello", "gpt-test", temperature=True)
    assert "temperature" in temperature_error.value.detail

    invalid_json = OpenAIProvider("secret-key", http_client=HttpClientStub(InvalidJsonResponseStub(200, {})))
    with pytest.raises(InvalidProviderResponse):
        invalid_json.complete("hello", "gpt-test")

    empty_text = OpenAIProvider(
        "secret-key",
        http_client=HttpClientStub(ResponseStub(200, {"choices": [{"message": {"content": ""}}]})),
    )
    with pytest.raises(InvalidProviderResponse):
        empty_text.complete("hello", "gpt-test")


def test_provider_adapters_map_vendor_payloads_and_fail_closed() -> None:
    adapters = [
        (
            AnthropicProvider,
            ResponseStub(200, {"content": [{"text": "anthropic-ok"}]}),
            "anthropic-ok",
            "messages",
        ),
        (
            GoogleGeminiProvider,
            ResponseStub(200, {"candidates": [{"content": {"parts": [{"text": "gemini-ok"}]}}]}),
            "gemini-ok",
            "models/gemini-test:generateContent",
        ),
        (
            HuggingFaceProvider,
            ResponseStub(200, [{"generated_text": "hf-ok"}]),
            "hf-ok",
            "models/hf-test",
        ),
        (
            GroqProvider,
            ResponseStub(200, {"choices": [{"message": {"content": "groq-ok"}}]}),
            "groq-ok",
            "chat/completions",
        ),
        (
            MistralProvider,
            ResponseStub(200, {"choices": [{"message": {"content": "mistral-ok"}}]}),
            "mistral-ok",
            "chat/completions",
        ),
    ]
    for adapter_type, response, expected, path in adapters:
        http = HttpClientStub(response)
        provider = adapter_type("secret-key", http_client=http)
        model = "gemini-test" if adapter_type is GoogleGeminiProvider else "hf-test"

        assert provider.complete("hello", model) == expected
        assert http.calls[0]["url"].endswith(path)

    azure_http = HttpClientStub(ResponseStub(200, {"choices": [{"message": {"content": "azure-ok"}}]}))
    azure = AzureOpenAIProvider("secret-key", "https://azure.example.test", http_client=azure_http)
    assert azure.complete("hello", "deployment-one") == "azure-ok"
    assert "api-version=2024-10-21" in azure_http.calls[0]["url"]

    custom_http = HttpClientStub(ResponseStub(200, {"choices": [{"message": {"content": "custom-ok"}}]}))
    custom = CustomProvider("secret-key", "https://custom.example.test/v1", http_client=custom_http)
    assert custom.complete("hello", "custom-model") == "custom-ok"

    with pytest.raises(ProviderUnavailable):
        CustomProvider("secret-key")
    with pytest.raises(ProviderUnavailable):
        AzureOpenAIProvider("secret-key")
    with pytest.raises(InvalidProviderResponse):
        AnthropicProvider("secret-key", http_client=HttpClientStub(ResponseStub(200, {"content": []}))).complete(
            "hello", "claude-test"
        )
    with pytest.raises(InvalidProviderResponse):
        GoogleGeminiProvider("secret-key", http_client=HttpClientStub(ResponseStub(200, {"candidates": []}))).complete(
            "hello", "gemini-test"
        )
    with pytest.raises(InvalidProviderResponse):
        HuggingFaceProvider("secret-key", http_client=HttpClientStub(ResponseStub(200, {}))).complete(
            "hello", "hf-test"
        )
    with pytest.raises(InvalidProviderResponse):
        AzureOpenAIProvider(
            "secret-key",
            "https://azure.example.test",
            http_client=HttpClientStub(ResponseStub(200, {"choices": [{"message": {"content": ""}}]})),
        ).complete("hello", "deployment-one")
    with pytest.raises(ProviderUnavailable):
        AnthropicProvider(
            "secret-key", policy=runtime_document(provider_defaults={"api_version_by_type": {}})
        ).complete("hello", "claude-test")
    with pytest.raises(InvalidProviderResponse):
        GoogleGeminiProvider(
            "secret-key",
            http_client=HttpClientStub(ResponseStub(200, {"candidates": [{"content": {"parts": [{"text": ""}]}}]})),
        ).complete("hello", "gemini-test")
    with pytest.raises(InvalidProviderResponse):
        HuggingFaceProvider(
            "secret-key", http_client=HttpClientStub(ResponseStub(200, [{"generated_text": ""}]))
        ).complete("hello", "hf-test")


@pytest.mark.django_db
def test_provider_factory_requires_active_valid_tenant_credential(settings) -> None:
    configure_encryption(settings)
    tenant_id = uuid.uuid4()
    service = AIProviderConfigurationService()
    provider_catalog = AIProvider.objects.create(name="OpenAI", provider_type=ProviderType.OPENAI)

    with pytest.raises(ProviderUnavailable):
        AIProviderFactory.get_provider(ProviderType.OPENAI, tenant_id)

    credential = service.create_credential(
        tenant_id,
        provider_id=provider_catalog.id,
        api_key="sk-test-secret",  # pragma: allowlist secret
        idempotency_key="create-openai-credential",
    )
    credential.status = CredentialStatus.VALID
    credential.save(update_fields=("status", "updated_at"))

    resolved = AIProviderFactory.get_provider(
        ProviderType.OPENAI,
        tenant_id,
        http_client=HttpClientStub(ResponseStub(200, {"choices": [{"message": {"content": "ok"}}]})),
    )
    assert resolved.complete("hello", "gpt-test") == "ok"


@pytest.mark.django_db
def test_provider_factory_fails_closed_for_inactive_catalog_and_unreadable_secret(settings) -> None:
    configure_encryption(settings)
    tenant_id = uuid.uuid4()
    service = AIProviderConfigurationService()
    inactive = AIProvider.objects.create(name="Inactive", provider_type=ProviderType.OPENAI)
    inactive_credential = service.create_credential(
        tenant_id,
        provider_id=inactive.id,
        api_key="sk-inactive",  # pragma: allowlist secret
        idempotency_key="inactive-credential",
    )
    inactive_credential.status = CredentialStatus.VALID
    inactive_credential.save(update_fields=("status", "updated_at"))
    inactive.is_active = False
    inactive.save(update_fields=("is_active", "updated_at"))

    with pytest.raises(ProviderUnavailable):
        AIProviderFactory.get_provider(ProviderType.OPENAI, tenant_id)

    active = AIProvider.objects.create(name="Active", provider_type=ProviderType.OPENAI)
    broken = service.create_credential(
        tenant_id,
        provider_id=active.id,
        api_key="sk-active",  # pragma: allowlist secret
        idempotency_key="broken-credential",
    )
    broken.status = CredentialStatus.VALID
    broken.api_key_encrypted = "not-fernet-token"  # pragma: allowlist secret
    broken.save(update_fields=("status", "api_key_encrypted", "updated_at"))

    with pytest.raises(ProviderUnavailable):
        AIProviderFactory.get_provider(ProviderType.OPENAI, tenant_id)


@pytest.mark.django_db
def test_delete_credential_fails_closed_when_active_deployment_depends_on_it(settings) -> None:
    configure_encryption(settings)
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = AIProviderConfigurationService()
    provider = AIProvider.objects.create(name="Anthropic", provider_type=ProviderType.ANTHROPIC)
    model = AIModel.objects.create(provider=provider, model_id="claude-test", display_name="Claude Test")
    credential = service.create_credential(
        tenant_id,
        provider_id=provider.id,
        api_key="anthropic-secret",  # pragma: allowlist secret
        idempotency_key="create-anthropic-credential",
    )
    deployment = AIModelDeployment.objects.create(
        tenant_id=tenant_id,
        model=model,
        credential=credential,
        deployment_name="production",
        status=DeploymentStatus.ACTIVE,
        created_by=str(actor_id),
    )

    with pytest.raises(ValidationError):
        service.delete_credential(tenant_id, credential.id)

    deployment.status = DeploymentStatus.INACTIVE
    deployment.save(update_fields=("status", "updated_at"))
    service.delete_credential(tenant_id, credential.id)
    credential.refresh_from_db()
    assert credential.is_deleted is True


@pytest.mark.django_db
def test_resource_idempotency_conflict_does_not_create_second_resource() -> None:
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = AIProviderConfigurationService()
    first = service.create_resource(
        tenant_id=tenant_id,
        name="Original",
        created_by=actor_id,
        idempotency_key="resource-conflict",
    )

    with pytest.raises(ValidationError) as conflict:
        service.create_resource(
            tenant_id=tenant_id,
            name="Different",
            created_by=actor_id,
            idempotency_key="resource-conflict",
        )

    assert "idempotency_key" in conflict.value.detail
    assert service.list_resources(tenant_id) == [first]


@pytest.mark.django_db
def test_deployment_config_and_status_policy_are_enforced(settings) -> None:
    configure_encryption(settings)
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = AIProviderConfigurationService()
    provider = AIProvider.objects.create(name="OpenAI", provider_type=ProviderType.OPENAI)
    model = AIModel.objects.create(provider=provider, model_id="gpt-test", display_name="GPT Test")
    credential = service.create_credential(
        tenant_id,
        provider_id=provider.id,
        api_key="sk-test-secret",  # pragma: allowlist secret
        idempotency_key="deploy-credential",
    )
    credential.status = CredentialStatus.VALID
    credential.save(update_fields=("status", "updated_at"))

    with pytest.raises(ValidationError) as bad_config:
        service.create_deployment(
            tenant_id,
            actor_id,
            model_id=model.id,
            credential_id=credential.id,
            deployment_name="prod",
            config={"max_tokens": 0},
            idempotency_key="bad-deployment",
        )
    assert "config.max_tokens" in bad_config.value.detail

    deployment = service.create_deployment(
        tenant_id,
        actor_id,
        model_id=model.id,
        credential_id=credential.id,
        deployment_name="prod",
        config={"max_tokens": 100, "temperature": 0.4},
        idempotency_key="good-deployment",
    )

    with pytest.raises(ValidationError) as bad_transition:
        service.update_deployment(tenant_id, deployment.id, status=DeploymentStatus.ERROR)
    deployment.refresh_from_db()
    assert "status" in bad_transition.value.detail
    assert deployment.status == DeploymentStatus.ACTIVE

    replay = service.create_deployment(
        tenant_id,
        actor_id,
        model_id=model.id,
        credential_id=credential.id,
        deployment_name="prod",
        config={"max_tokens": 100, "temperature": 0.4},
        idempotency_key="good-deployment",
    )
    assert replay.id == deployment.id

    updated = service.update_deployment(
        tenant_id,
        deployment.id,
        deployment_name="prod-v2",
        config={"max_tokens": 250, "temperature": 0.2, "top_p": 0.9, "timeout_seconds": 5},
        status=DeploymentStatus.INACTIVE,
    )
    assert updated.deployment_name == "prod-v2"
    assert updated.config["timeout_seconds"] == 5
    assert updated.status == DeploymentStatus.INACTIVE

    service.delete_deployment(tenant_id, deployment.id)
    deployment.refresh_from_db()
    assert deployment.is_deleted is True
    assert deployment.status == DeploymentStatus.INACTIVE


@pytest.mark.django_db
def test_credential_update_rotation_and_deployment_policy_fail_closed(settings) -> None:
    configure_encryption(settings)
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = AIProviderConfigurationService()
    provider = AIProvider.objects.create(name="Mistral", provider_type=ProviderType.MISTRAL)
    other_provider = AIProvider.objects.create(name="OpenAI Other", provider_type=ProviderType.OPENAI)
    model = AIModel.objects.create(provider=provider, model_id="mistral-test", display_name="Mistral Test")
    credential = service.create_credential(
        tenant_id,
        provider_id=provider.id,
        api_key="first-secret",  # pragma: allowlist secret
        label="primary",
        idempotency_key="credential-update",
    )

    updated = service.update_credential(
        tenant_id,
        credential.id,
        api_key="second-secret",  # pragma: allowlist secret
        label="rotated",
    )
    assert updated.label == "rotated"
    assert updated.secret_hint == "cret"  # pragma: allowlist secret
    assert updated.status == CredentialStatus.UNVERIFIED
    assert updated.last_verified_at is None

    with pytest.raises(ValidationError):
        service.create_deployment(
            tenant_id,
            actor_id,
            model_id=model.id,
            credential_id=credential.id,
            deployment_name="blocked",
            idempotency_key="deployment-blocked-by-unverified-credential",
        )

    credential.status = CredentialStatus.VALID
    credential.save(update_fields=("status", "updated_at"))
    deployment = service.create_deployment(
        tenant_id,
        actor_id,
        model_id=model.id,
        credential_id=credential.id,
        deployment_name="active",
        idempotency_key="deployment-active-for-provider-lock",
    )
    with pytest.raises(ValidationError):
        service.update_credential(tenant_id, credential.id, provider_id=other_provider.id)

    service.delete_deployment(tenant_id, deployment.id)
    service.update_credential(tenant_id, credential.id, provider_id=other_provider.id)
    credential.refresh_from_db()
    assert credential.provider_id == other_provider.id


@pytest.mark.django_db
def test_usage_recording_is_tenant_scoped_and_validates_metering(settings) -> None:
    configure_encryption(settings)
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = AIProviderConfigurationService()
    provider = AIProvider.objects.create(name="Groq", provider_type=ProviderType.GROQ)
    model = AIModel.objects.create(provider=provider, model_id="llama-test", display_name="Llama Test")
    credential = service.create_credential(
        tenant_id,
        provider_id=provider.id,
        api_key="gsk-test-secret",  # pragma: allowlist secret
        idempotency_key="usage-credential",
    )
    credential.status = CredentialStatus.VALID
    credential.save(update_fields=("status", "updated_at"))
    deployment = service.create_deployment(
        tenant_id,
        actor_id,
        model_id=model.id,
        credential_id=credential.id,
        deployment_name="metered",
        idempotency_key="usage-deployment",
    )

    with pytest.raises(Exception):
        AIUsageService().record_usage(
            other_tenant_id,
            deployment_id=deployment.id,
            prompt_tokens=1,
            completion_tokens=1,
            cost="0.01",
        )
    with pytest.raises(ValidationError):
        AIUsageService().record_usage(
            tenant_id,
            deployment_id=deployment.id,
            prompt_tokens=-1,
            completion_tokens=1,
            cost="0.01",
        )
    with pytest.raises(ValidationError):
        AIUsageService().record_usage(
            tenant_id,
            deployment_id=deployment.id,
            prompt_tokens=True,
            completion_tokens=1,
            cost="0.01",
        )
    with pytest.raises(ValidationError):
        AIUsageService().record_usage(
            tenant_id,
            deployment_id=deployment.id,
            prompt_tokens=1,
            completion_tokens=1,
            cost="not-a-decimal",
        )
    with pytest.raises(ValidationError):
        AIUsageService().record_usage(
            tenant_id,
            deployment_id=deployment.id,
            prompt_tokens=1,
            completion_tokens=1,
            cost="0.01",
            currency="JPY",
        )

    usage = AIUsageService().record_usage(
        tenant_id,
        deployment_id=deployment.id,
        prompt_tokens=2,
        completion_tokens=3,
        cost="0.015",
        currency="USD",
        provider_request_id="provider-req-1",
    )
    assert usage.total_tokens == 5
    assert usage.tenant_id == tenant_id
