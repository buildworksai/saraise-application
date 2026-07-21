"""Extension-registry, honesty, and built-in issuer tests."""

from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace

import pytest

from src.core.async_jobs.services import HandlerAlreadyRegistered, register_handler, unregister_handler

from ..apps import BlockchainTraceabilityConfig
from ..hashing import canonical_json, sha256_hex
from ..providers import (
    AdapterNotRegisteredError,
    AdapterRegistrationError,
    AdapterRegistry,
    CapabilityMetadata,
    DjangoSigningCredentialIssuer,
    InvalidProviderResponseError,
    ProofResult,
    SubmissionReceipt,
    credential_issuer_registry,
    document_resolver_registry,
    inventory_resolver_registry,
    ledger_provider_registry,
    list_provider_capabilities,
    register_builtin_adapters,
)


class DescriptorAdapter:
    def capability_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(key="adapter", display_name="Adapter", capabilities=("proof.verify",))


def test_registry_rejects_missing_duplicate_and_exposes_stable_metadata() -> None:
    registry: AdapterRegistry[DescriptorAdapter] = AdapterRegistry("test")
    with pytest.raises(AdapterNotRegisteredError):
        registry.get("missing")
    adapter = registry.register("adapter", DescriptorAdapter())
    assert registry.get("ADAPTER") is adapter
    assert registry.keys() == ("adapter",)
    assert registry.descriptors()[0].capabilities == ("proof.verify",)
    with pytest.raises(AdapterRegistrationError):
        registry.register("adapter", DescriptorAdapter())
    assert registry.unregister("adapter") is adapter


def test_simulated_or_evidenceless_proof_can_never_be_verified() -> None:
    with pytest.raises(InvalidProviderResponseError, match="simulated"):
        ProofResult(verified=True, reason_code="SIMULATED_PROVIDER", evidence={"proof": "x"}, simulated=True)
    with pytest.raises(InvalidProviderResponseError, match="concrete evidence"):
        ProofResult(verified=True, reason_code="VERIFIED")
    with pytest.raises(InvalidProviderResponseError, match="transaction identity"):
        SubmissionReceipt(accepted=True)


@pytest.mark.django_db
def test_builtin_django_issuer_signs_and_verifies_real_tenant_salted_claims() -> None:
    issuer = DjangoSigningCredentialIssuer()
    tenant = uuid.uuid4()
    claims = {"asset_id": str(uuid.uuid4()), "public_id": str(uuid.uuid4()), "lot": 7}
    canonical = canonical_json(claims)
    result = issuer.sign_claims(tenant, issuer.issuer_key_ref, canonical)
    credential = SimpleNamespace(
        claims=claims,
        claims_hash=sha256_hex(canonical),
        issuer_key_ref=issuer.issuer_key_ref,
        signature=result.signature,
    )
    proof = issuer.verify_signature(tenant, credential)
    assert proof.verified and proof.reason_code == "SIGNATURE_VALID" and proof.simulated is False
    credential.signature = f"{result.signature}tampered"
    assert issuer.verify_signature(tenant, credential).verified is False
    other_tenant = uuid.uuid4()
    assert issuer.verify_signature(other_tenant, credential).verified is False


def test_builtin_registration_is_idempotent_but_rejects_competing_owner() -> None:
    original = credential_issuer_registry.unregister(DjangoSigningCredentialIssuer.issuer_type)
    try:
        register_builtin_adapters()
        register_builtin_adapters()
        credential_issuer_registry.unregister(DjangoSigningCredentialIssuer.issuer_type)
        credential_issuer_registry.register(DjangoSigningCredentialIssuer.issuer_type, DescriptorAdapter())  # type: ignore[arg-type]
        with pytest.raises(AdapterRegistrationError, match="competing"):
            register_builtin_adapters()
    finally:
        credential_issuer_registry.unregister(DjangoSigningCredentialIssuer.issuer_type)
        credential_issuer_registry.register(
            DjangoSigningCredentialIssuer.issuer_type,
            original if original is not None else DjangoSigningCredentialIssuer(),
        )


def test_capability_catalog_includes_all_paid_module_extension_surfaces() -> None:
    catalog = list_provider_capabilities()
    assert set(catalog) == {
        "ledger_providers",
        "credential_issuers",
        "inventory_resolvers",
        "document_resolvers",
    }
    assert isinstance(ledger_provider_registry.keys(), tuple)
    assert isinstance(inventory_resolver_registry.keys(), tuple)
    assert isinstance(document_resolver_registry.keys(), tuple)


def test_app_ready_does_not_mask_competing_async_handler() -> None:
    command = "blockchain_traceability.submit_anchor"

    def competing_handler(job: object) -> dict[str, bool]:
        return {"competing": True}

    unregister_handler(command)
    register_handler(command, competing_handler)
    module = importlib.import_module("src.modules.blockchain_traceability")
    config = BlockchainTraceabilityConfig("blockchain_traceability", module)
    try:
        with pytest.raises(HandlerAlreadyRegistered):
            config.ready()
    finally:
        unregister_handler(command)
        config.ready()
