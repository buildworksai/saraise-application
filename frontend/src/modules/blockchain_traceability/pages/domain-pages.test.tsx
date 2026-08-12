/* eslint-disable max-lines-per-function -- domain page mutation tests need shared builders and end-to-end page branches in one focused file. */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type {
  AssetHistory,
  AuthenticityCredential,
  AuthenticityCredentialListItem,
  ComplianceEvidence,
  LedgerAnchor,
  LedgerAnchorListItem,
  LedgerNetwork,
  LedgerNetworkListItem,
  TraceabilityAsset,
  TraceabilityEventListItem,
  TraceabilityCapabilities,
  TraceabilityEvent,
  VerificationAttempt,
  VerificationAttemptListItem,
} from "../contracts";
import { blockchainTraceabilityService } from "../services/blockchain_traceability-service";
import {
  CreateComplianceEvidencePage,
  CreateLedgerAnchorPage,
  CreateLedgerNetworkPage,
  CreateTraceabilityAssetPage,
  AuthenticityCredentialListPage,
  EditComplianceEvidencePage,
  EditLedgerNetworkPage,
  EditTraceabilityAssetPage,
  AppendTraceabilityEventPage,
  AuthenticityCredentialDetailPage,
  ComplianceEvidenceDetailPage,
  ComplianceEvidenceListPage,
  IssueAuthenticityCredentialPage,
  LedgerAnchorDetailPage,
  LedgerAnchorListPage,
  LedgerNetworkDetailPage,
  LedgerNetworkListPage,
  TraceabilityEventDetailPage,
  TraceabilityAssetDetailPage,
  TraceabilityAssetListPage,
  TraceabilityEventListPage,
  VerificationAttemptDetailPage,
  VerificationCenterPage,
  VerificationAttemptListPage,
} from "./domain-pages";

const capabilityState = vi.hoisted(() => ({
  value: null as TraceabilityCapabilities | null,
}));

vi.mock("../hooks/use-traceability-configuration", () => ({
  useTraceabilityCapabilities: () => ({
    data: capabilityState.value,
    error: null,
    isLoading: capabilityState.value === null,
    refetch: vi.fn(),
  }),
}));

const now = "2026-07-30T10:00:00.000Z";

const capabilities = {
  can_read: true,
  can_update: true,
  can_preview: true,
  can_rollback: true,
  can_import: true,
  can_export: true,
  can_mutate_resources: true,
  can_finalize_compliance_evidence: true,
  can_supersede_compliance_evidence: true,
  document: {
    validation: {
      max_json_bytes: 8192,
      max_json_depth: 8,
      max_json_keys: 64,
      gtin_lengths: [8, 12, 13, 14],
      max_revocation_reason_chars: 240,
      max_authenticity_token_chars: 128,
      max_actor_id_chars: 96,
      credential_type_max_chars: 80,
    },
    network_policy: { default_confirmation_depth: 2, max_confirmation_depth: 12 },
    schema_policy: { default_version: 1, allowed_versions: [1] },
    list_policy: {
      default_page_size: 25,
      max_page_size: 100,
      history_chunk_size: 50,
      verification_chunk_size: 20,
    },
    health_policy: {
      provider_probe_cache_ttl_seconds: 60,
      outbox_freshness_seconds: 120,
      cache_marker_ttl_seconds: 30,
    },
    inventory_policy: { validation_required: true },
    anchor_policy: { default_start_sequence: 1, use_current_head_default: false },
    credential_policy: { issuer_type: "ed25519", token_entropy_bytes: 32 },
    resilience: {
      timeout_seconds: 5,
      max_attempts: 3,
      base_backoff_seconds: 1,
      max_backoff_seconds: 10,
      circuit_failure_threshold: 3,
      circuit_recovery_seconds: 60,
    },
    workflow: {
      machines: {},
      network_deletable_statuses: ["draft", "disabled"],
      asset_deletable_statuses: ["draft", "retired"],
    },
    ui: {
      sidebar_order: 40,
      positive_statuses: ["active", "confirmed", "verified", "pass"],
      warning_statuses: ["draft", "queued", "inconclusive", "warning", "recalled"],
      default_recall_reason: "Configured recall reason",
      default_revocation_reason: "Configured revocation reason",
    },
    features: {
      enabled: true,
      roles: ["traceability-admin"],
      cohorts: ["default"],
      enable_supersede: true,
      enable_health: true,
    },
  },
} satisfies TraceabilityCapabilities;

function renderWithProviders(ui: ReactElement, initialEntry = "/") {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function pageResult<T>(items: readonly T[]) {
  return {
    items,
    correlationId: "corr-page",
    pagination: {
      page: 1,
      page_size: 25,
      total_pages: 1,
      count: items.length,
      has_next: false,
      has_previous: false,
    },
  };
}

function networkListItem(overrides: Partial<LedgerNetworkListItem> = {}): LedgerNetworkListItem {
  return {
    id: "network-1",
    tenant_id: "tenant-1",
    network_key: "ethereum-mainnet",
    name: "Ethereum mainnet",
    provider_type: "evm",
    network_namespace: "eip155:1",
    chain_id: "1",
    confirmation_depth: 12,
    supports_batch_anchors: true,
    supports_finality: true,
    status: "active",
    credential_configured: true,
    last_health_status: "healthy",
    last_health_code: "ok",
    last_health_checked_at: now,
    last_successful_anchor_at: now,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function network(overrides: Partial<LedgerNetwork> = {}): LedgerNetwork {
  return {
    ...networkListItem(),
    description: "Mainnet anchoring adapter",
    dependency_key: "ledger.ethereum",
    provider_options: { rpc_url: "redacted" },
    transition_history: [],
    is_deleted: false,
    deleted_at: null,
    deleted_by: "",
    created_by: "actor-1",
    updated_by: "actor-1",
    ...overrides,
  };
}

function asset(overrides: Partial<TraceabilityAsset> = {}): TraceabilityAsset {
  return {
    id: "asset-1",
    tenant_id: "tenant-1",
    asset_key: "asset-key-1",
    name: "Serialized Pump",
    description: "Pump with custody evidence",
    product_ref: "SKU-1",
    batch_ref: "",
    serial_number: "SN-1",
    gtin: "",
    asset_type: "serial",
    status: "active",
    attributes: { color: "blue" },
    head_sequence: 2,
    head_hash: "a".repeat(64),
    transition_history: [],
    activated_at: now,
    recalled_at: null,
    retired_at: null,
    created_at: now,
    updated_at: now,
    created_by: "actor-1",
    updated_by: "actor-1",
    is_deleted: false,
    deleted_at: null,
    deleted_by: "",
    ...overrides,
  };
}

function eventListItem(
  overrides: Partial<TraceabilityEventListItem> = {}
): TraceabilityEventListItem {
  return {
    id: "event-1",
    tenant_id: "tenant-1",
    asset_id: "asset-1",
    sequence: 2,
    event_type: "custody_transferred",
    schema_version: 1,
    occurred_at: now,
    recorded_at: now,
    actor_ref: "warehouse-1",
    previous_hash: "b".repeat(64),
    event_hash: "c".repeat(64),
    hash_algorithm: "sha256",
    correlation_id: "corr-event",
    ...overrides,
  };
}

function event(overrides: Partial<TraceabilityEvent> = {}): TraceabilityEvent {
  return {
    id: "event-1",
    tenant_id: "tenant-1",
    asset_id: "asset-1",
    sequence: 2,
    idempotency_key: "append:event-1",
    event_type: "custody_transferred",
    schema_version: 1,
    occurred_at: now,
    recorded_at: now,
    actor_ref: "warehouse-1",
    location: { city: "Dallas" },
    payload: { condition: "sealed" },
    previous_hash: "b".repeat(64),
    event_hash: "c".repeat(64),
    hash_algorithm: "sha256",
    created_by: "actor-1",
    correlation_id: "corr-event",
    anchor_state: "not_anchored",
    ...overrides,
  };
}

function history(overrides: Partial<AssetHistory> = {}): AssetHistory {
  return {
    asset: asset(),
    items: [{ kind: "event", occurred_at: now, sequence: 2, event: event() }],
    proof_status: "invalid",
    failing_sequence: 2,
    pagination: {
      page: 1,
      page_size: 50,
      total_pages: 1,
      count: 1,
      has_next: false,
      has_previous: false,
    },
    ...overrides,
  };
}

function verificationAttempt(overrides: Partial<VerificationAttempt> = {}): VerificationAttempt {
  return {
    id: "attempt-1",
    tenant_id: "tenant-1",
    verification_type: "chain",
    asset_id: "asset-1",
    anchor_id: null,
    credential_id: null,
    compliance_evidence_id: null,
    idempotency_key: "verify-chain:test",
    outcome: "verified",
    reason_code: "simulated_provider",
    chain_head_hash: "a".repeat(64),
    proof_evidence: {
      externally_anchored: true,
      simulated_provider: true,
      failing_sequence: null,
      explanation: "Provider is simulated.",
    },
    actor_id: "actor-1",
    source_fingerprint: "fingerprint",
    correlation_id: "corr-attempt",
    latency_ms: 25,
    created_at: now,
    ...overrides,
  };
}

function anchor(overrides: Partial<LedgerAnchor> = {}): LedgerAnchor {
  return {
    id: "anchor-1",
    tenant_id: "tenant-1",
    asset_id: "asset-1",
    network_id: "network-1",
    start_sequence: 1,
    end_sequence: 2,
    root_hash: "d".repeat(64),
    hash_algorithm: "sha256",
    idempotency_key: "anchor:key",
    status: "queued",
    transition_history: [],
    async_job_id: "job-1",
    provider_transaction_id: "",
    transaction_hash: "",
    block_number: null,
    block_hash: "",
    confirmations: 0,
    provider_receipt: {},
    failure_code: "",
    failure_message: "",
    submitted_at: null,
    confirmed_at: null,
    last_checked_at: null,
    created_by: "actor-1",
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function anchorListItem(overrides: Partial<LedgerAnchorListItem> = {}): LedgerAnchorListItem {
  const item = anchor(overrides);
  return {
    id: item.id,
    tenant_id: item.tenant_id,
    asset_id: item.asset_id,
    network_id: item.network_id,
    start_sequence: item.start_sequence,
    end_sequence: item.end_sequence,
    root_hash: item.root_hash,
    hash_algorithm: item.hash_algorithm,
    status: item.status,
    async_job_id: item.async_job_id,
    provider_transaction_id: item.provider_transaction_id,
    transaction_hash: item.transaction_hash,
    block_number: item.block_number,
    block_hash: item.block_hash,
    confirmations: item.confirmations,
    failure_code: item.failure_code,
    submitted_at: item.submitted_at,
    confirmed_at: item.confirmed_at,
    last_checked_at: item.last_checked_at,
    created_at: item.created_at,
    updated_at: item.updated_at,
  };
}

function credential(overrides: Partial<AuthenticityCredential> = {}): AuthenticityCredential {
  return {
    id: "credential-1",
    tenant_id: "tenant-1",
    asset_id: "asset-1",
    public_id: "credential-public-1",
    credential_type: "product_passport",
    claims: { model: "pump" },
    claims_hash: "e".repeat(64),
    signature_algorithm: "ed25519",
    signature: "signature",
    status: "active",
    transition_history: [],
    issued_at: now,
    expires_at: "2026-12-31T00:00:00.000Z",
    revoked_at: null,
    revocation_reason: "",
    created_by: "actor-1",
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function credentialListItem(
  overrides: Partial<AuthenticityCredentialListItem> = {}
): AuthenticityCredentialListItem {
  const item = credential(overrides);
  return {
    id: item.id,
    tenant_id: item.tenant_id,
    asset_id: item.asset_id,
    public_id: item.public_id,
    credential_type: item.credential_type,
    status: item.status,
    issued_at: item.issued_at,
    expires_at: item.expires_at,
    revoked_at: item.revoked_at,
    created_at: item.created_at,
    updated_at: item.updated_at,
    ...overrides,
  };
}

function complianceEvidence(overrides: Partial<ComplianceEvidence> = {}): ComplianceEvidence {
  return {
    id: "compliance-1",
    tenant_id: "tenant-1",
    asset_id: "asset-1",
    event_id: "event-1",
    evidence_key: "iso-evidence-1",
    evidence_type: "inspection",
    standard: "ISO-9001",
    jurisdiction: "",
    result: "pass",
    details: { inspector: "qa-1" },
    document_ref: null,
    content_hash: "",
    observed_at: now,
    valid_until: null,
    status: "draft",
    transition_history: [],
    supersedes_id: null,
    finalized_at: null,
    created_at: now,
    updated_at: now,
    created_by: "actor-1",
    updated_by: "actor-1",
    is_deleted: false,
    deleted_at: null,
    deleted_by: "",
    ...overrides,
  };
}

function verificationListItem(
  overrides: Partial<VerificationAttemptListItem> = {}
): VerificationAttemptListItem {
  const item = verificationAttempt(overrides);
  return {
    id: item.id,
    tenant_id: item.tenant_id,
    verification_type: item.verification_type,
    asset_id: item.asset_id,
    anchor_id: item.anchor_id,
    credential_id: item.credential_id,
    compliance_evidence_id: item.compliance_evidence_id,
    outcome: item.outcome,
    reason_code: item.reason_code,
    chain_head_hash: item.chain_head_hash,
    correlation_id: item.correlation_id,
    latency_ms: item.latency_ms,
    created_at: item.created_at,
    ...overrides,
  };
}

describe("blockchain traceability domain pages", () => {
  beforeEach(() => {
    capabilityState.value = capabilities;
    vi.spyOn(window, "alert").mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("sanitizes network list filters and applies governed page size", async () => {
    const listNetworks = vi
      .spyOn(blockchainTraceabilityService, "listNetworks")
      .mockResolvedValue(pageResult([networkListItem()]));

    renderWithProviders(<LedgerNetworkListPage />, "/?page=0&status=bogus&provider_type=besu");

    await waitFor(() =>
      expect(listNetworks).toHaveBeenCalledWith({
        page: 1,
        page_size: 25,
        search: undefined,
        ordering: "name",
        status: undefined,
        provider_type: "besu",
      })
    );
    expect(await screen.findByRole("heading", { name: "Ledger networks" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Ethereum mainnet" })).toHaveLength(2);

    fireEvent.change(screen.getByLabelText("Filter by status"), { target: { value: "degraded" } });

    await waitFor(() =>
      expect(listNetworks).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 25,
        search: undefined,
        ordering: "name",
        status: "degraded",
        provider_type: "besu",
      })
    );
  });

  it("renders asset chain failure state and never treats simulated verification as external proof", async () => {
    vi.spyOn(blockchainTraceabilityService, "getAsset").mockResolvedValue(asset());
    vi.spyOn(blockchainTraceabilityService, "getAssetHistory").mockResolvedValue(history());
    const verifyAssetChain = vi
      .spyOn(blockchainTraceabilityService, "verifyAssetChain")
      .mockResolvedValue(verificationAttempt());
    const recallAsset = vi
      .spyOn(blockchainTraceabilityService, "recallAsset")
      .mockResolvedValue(asset({ status: "recalled", recalled_at: now }));

    renderWithProviders(
      <Routes>
        <Route path="/assets/:id" element={<TraceabilityAssetDetailPage />} />
      </Routes>,
      "/assets/asset-1"
    );

    expect(await screen.findByRole("heading", { name: "Serialized Pump" })).toBeInTheDocument();
    expect(screen.getByText("Hash mismatch at this sequence")).toBeInTheDocument();
    expect(screen.getByText("Actor: warehouse-1 · Anchor: not anchored")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Verify chain" }));

    await waitFor(() => expect(verifyAssetChain).toHaveBeenCalled());
    expect(verifyAssetChain.mock.calls[0]?.[0]).toBe("asset-1");
    expect(verifyAssetChain.mock.calls[0]?.[1].idempotency_key).toMatch(/^verify-chain:/);
    expect(
      await screen.findByText("Simulated provider — verification unavailable")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Recall" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Recall" }));

    await waitFor(() => expect(recallAsset).toHaveBeenCalled());
    expect(recallAsset.mock.calls[0]?.[0]).toBe("asset-1");
    expect(recallAsset.mock.calls[0]?.[1]).toMatchObject({ reason: "Configured recall reason" });
    expect(recallAsset.mock.calls[0]?.[1].transition_key).toMatch(/^recall:/);
  });

  it("queues an anchor with numeric ranges and renders the durable queued state", async () => {
    const requestAnchor = vi
      .spyOn(blockchainTraceabilityService, "requestAnchor")
      .mockResolvedValue({
        anchor: anchor(),
        job: {
          id: "job-1",
          command: "blockchain_traceability.submit_anchor",
          status: "queued",
          correlation_id: "corr-job",
        },
        queued: true,
      });

    renderWithProviders(<CreateLedgerAnchorPage />);

    fireEvent.change(screen.getByLabelText("Asset ID"), { target: { value: " asset-1 " } });
    fireEvent.change(screen.getByLabelText("Network ID"), { target: { value: " network-1 " } });
    fireEvent.change(screen.getByLabelText("Start sequence"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("End sequence"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: " anchor-key " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue anchor request" }));

    await waitFor(() =>
      expect(requestAnchor).toHaveBeenCalledWith({
        asset_id: "asset-1",
        network_id: "network-1",
        start_sequence: 1,
        end_sequence: 2,
        idempotency_key: "anchor-key",
      })
    );
    expect(await screen.findByRole("heading", { name: "Anchor queued" })).toBeInTheDocument();
    expect(screen.getByText(/Anchor anchor-1 is queued through job job-1/)).toBeInTheDocument();
  });

  it("creates compliance evidence with validated result, ISO dates, optional nulls, and JSON details", async () => {
    const createComplianceEvidence = vi
      .spyOn(blockchainTraceabilityService, "createComplianceEvidence")
      .mockResolvedValue({
        id: "evidence-1",
        tenant_id: "tenant-1",
        asset_id: "asset-1",
        event_id: null,
        evidence_key: "evidence-key-1",
        evidence_type: "inspection",
        standard: "ISO-9001",
        jurisdiction: "",
        result: "warning",
        details: { inspector: "qa-1" },
        document_ref: null,
        content_hash: "",
        observed_at: now,
        valid_until: null,
        status: "draft",
        transition_history: [],
        supersedes_id: null,
        finalized_at: null,
        created_at: now,
        updated_at: now,
        created_by: "actor-1",
        updated_by: "actor-1",
        is_deleted: false,
        deleted_at: null,
        deleted_by: "",
      });

    renderWithProviders(<CreateComplianceEvidencePage />);

    fireEvent.change(screen.getByLabelText("Asset ID"), { target: { value: " asset-1 " } });
    fireEvent.change(screen.getByLabelText("Evidence key"), {
      target: { value: " evidence-key-1 " },
    });
    fireEvent.change(screen.getByLabelText("Evidence type"), { target: { value: " inspection " } });
    fireEvent.change(screen.getByLabelText("Standard"), { target: { value: " ISO-9001 " } });
    fireEvent.change(screen.getByLabelText("Result (pass, fail, warning, not_applicable)"), {
      target: { value: " warning " },
    });
    fireEvent.change(screen.getByLabelText("Observed at"), {
      target: { value: "2026-07-30T10:00" },
    });
    fireEvent.change(screen.getByLabelText("Details (JSON)"), {
      target: { value: '{"inspector":"qa-1","score":97}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save evidence draft" }));

    await waitFor(() =>
      expect(createComplianceEvidence).toHaveBeenCalledWith({
        asset_id: "asset-1",
        event_id: undefined,
        evidence_key: "evidence-key-1",
        evidence_type: "inspection",
        standard: "ISO-9001",
        jurisdiction: undefined,
        result: "warning",
        document_ref: undefined,
        observed_at: new Date("2026-07-30T10:00").toISOString(),
        valid_until: null,
        details: { inspector: "qa-1", score: 97 },
      })
    );
  });

  it("persists verification attempts for authenticity, chain, anchor, and compliance modes", async () => {
    const verifyAuthenticity = vi
      .spyOn(blockchainTraceabilityService, "verifyAuthenticity")
      .mockResolvedValue(verificationAttempt({ verification_type: "authenticity" }));
    const verifyAssetChain = vi
      .spyOn(blockchainTraceabilityService, "verifyAssetChain")
      .mockResolvedValue(verificationAttempt({ verification_type: "chain" }));
    const verifyAnchor = vi
      .spyOn(blockchainTraceabilityService, "verifyAnchor")
      .mockResolvedValue(verificationAttempt({ verification_type: "anchor" }));
    const verifyComplianceEvidence = vi
      .spyOn(blockchainTraceabilityService, "verifyComplianceEvidence")
      .mockResolvedValue(verificationAttempt({ verification_type: "compliance" }));

    renderWithProviders(<VerificationCenterPage />);

    expect(await screen.findByRole("heading", { name: "Verification center" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Credential public ID"), {
      target: { value: "public-1" },
    });
    fireEvent.change(screen.getByLabelText("Authenticity token"), {
      target: { value: "token-1" },
    });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: "verify-authenticity:test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify and persist attempt" }));

    await waitFor(() =>
      expect(verifyAuthenticity).toHaveBeenCalledWith({
        public_id: "public-1",
        token: "token-1",
        idempotency_key: "verify-authenticity:test",
      })
    );
    expect(
      await screen.findByText("Simulated provider — verification unavailable")
    ).toBeInTheDocument();
    expect(screen.getByText("Provider is simulated.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "chain" }));
    fireEvent.change(screen.getByLabelText("Asset ID"), { target: { value: "asset-1" } });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: "verify-chain:test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify and persist attempt" }));
    await waitFor(() =>
      expect(verifyAssetChain).toHaveBeenCalledWith("asset-1", {
        idempotency_key: "verify-chain:test",
      })
    );

    fireEvent.click(screen.getByRole("tab", { name: "anchor" }));
    fireEvent.change(screen.getByLabelText("Anchor ID"), { target: { value: "anchor-1" } });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: "verify-anchor:test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify and persist attempt" }));
    await waitFor(() =>
      expect(verifyAnchor).toHaveBeenCalledWith("anchor-1", {
        idempotency_key: "verify-anchor:test",
      })
    );

    fireEvent.click(screen.getByRole("tab", { name: "compliance" }));
    fireEvent.change(screen.getByLabelText("Compliance evidence ID"), {
      target: { value: "evidence-1" },
    });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: "verify-compliance:test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify and persist attempt" }));
    await waitFor(() =>
      expect(verifyComplianceEvidence).toHaveBeenCalledWith("evidence-1", {
        idempotency_key: "verify-compliance:test",
      })
    );
  });

  it("lists asset, event, anchor, compliance, and verification resources with sanitized governed filters", async () => {
    const listAssets = vi
      .spyOn(blockchainTraceabilityService, "listAssets")
      .mockResolvedValue(pageResult([asset()]));
    renderWithProviders(
      <TraceabilityAssetListPage />,
      "/?page=-3&status=unknown&product_ref=SKU-1"
    );
    await waitFor(() =>
      expect(listAssets).toHaveBeenCalledWith(
        expect.objectContaining({
          page: 1,
          page_size: 25,
          product_ref: "SKU-1",
          status: undefined,
        })
      )
    );
    expect(await screen.findByRole("heading", { name: "Traceability assets" })).toBeInTheDocument();
    cleanup();

    const listEvents = vi
      .spyOn(blockchainTraceabilityService, "listEvents")
      .mockResolvedValue(pageResult([eventListItem()]));
    renderWithProviders(<TraceabilityEventListPage />, "/?asset_id=asset-1&actor_ref=warehouse-1");
    await waitFor(() =>
      expect(listEvents).toHaveBeenCalledWith(
        expect.objectContaining({ asset_id: "asset-1", actor_ref: "warehouse-1" })
      )
    );
    expect(await screen.findAllByText("custody_transferred · #2")).toHaveLength(2);
    cleanup();

    const listAnchors = vi
      .spyOn(blockchainTraceabilityService, "listAnchors")
      .mockResolvedValue(
        pageResult([anchorListItem({ status: "failed", failure_code: "timeout" })])
      );
    renderWithProviders(<LedgerAnchorListPage />, "/?status=failed&network_id=network-1");
    await waitFor(() =>
      expect(listAnchors).toHaveBeenCalledWith(
        expect.objectContaining({ status: "failed", network_id: "network-1" })
      )
    );
    expect(await screen.findAllByText("Sequences 1–2")).toHaveLength(2);
    cleanup();

    const listCredentials = vi
      .spyOn(blockchainTraceabilityService, "listCredentials")
      .mockResolvedValue(pageResult([credentialListItem({ status: "expired" })]));
    renderWithProviders(
      <AuthenticityCredentialListPage />,
      "/?status=bogus&asset_id=asset-1&credential_type=passport"
    );
    await waitFor(() =>
      expect(listCredentials).toHaveBeenCalledWith(
        expect.objectContaining({
          status: undefined,
          asset_id: "asset-1",
          credential_type: "passport",
          ordering: "-issued_at",
        })
      )
    );
    expect(await screen.findAllByText("credential-public-1")).toHaveLength(2);
    expect(screen.getAllByText("expired")).toHaveLength(3);
    cleanup();

    const listCompliance = vi
      .spyOn(blockchainTraceabilityService, "listComplianceEvidence")
      .mockResolvedValue(pageResult([complianceEvidence({ status: "finalized" })]));
    renderWithProviders(<ComplianceEvidenceListPage />, "/?status=finalized&standard=ISO-9001");
    await waitFor(() =>
      expect(listCompliance).toHaveBeenCalledWith(
        expect.objectContaining({ status: "finalized", standard: "ISO-9001" })
      )
    );
    expect(await screen.findAllByText("iso-evidence-1")).toHaveLength(2);
    cleanup();

    const listAttempts = vi
      .spyOn(blockchainTraceabilityService, "listVerificationAttempts")
      .mockResolvedValue(pageResult([verificationListItem({ outcome: "invalid" })]));
    renderWithProviders(<VerificationAttemptListPage />, "/?status=invalid&reason_code=hash");
    await waitFor(() =>
      expect(listAttempts).toHaveBeenCalledWith(
        expect.objectContaining({ outcome: "invalid", reason_code: "hash" })
      )
    );
    expect(await screen.findAllByText("chain verification")).toHaveLength(2);
    expect(screen.getAllByText("invalid")).toHaveLength(3);
  });

  it("creates network, asset, event, credential, and compliance records with parsed JSON payloads", async () => {
    const createNetwork = vi
      .spyOn(blockchainTraceabilityService, "createNetwork")
      .mockResolvedValue(network());
    renderWithProviders(<CreateLedgerNetworkPage />);
    fireEvent.change(screen.getByLabelText("Network key"), { target: { value: "polygon-amoy" } });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Polygon Amoy" } });
    fireEvent.change(screen.getByLabelText("Provider adapter key"), { target: { value: "evm" } });
    fireEvent.change(screen.getByLabelText("Resilience dependency key"), {
      target: { value: "ledger.polygon" },
    });
    fireEvent.change(screen.getByLabelText("Network namespace"), {
      target: { value: "eip155:80002" },
    });
    fireEvent.change(screen.getByLabelText("Required confirmations"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Provider options (JSON)"), {
      target: { value: '{"batch":true}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save draft network" }));
    await waitFor(() =>
      expect(createNetwork).toHaveBeenCalledWith(
        expect.objectContaining({
          network_key: "polygon-amoy",
          confirmation_depth: 4,
          provider_options: { batch: true },
        })
      )
    );
    cleanup();

    const registerAsset = vi
      .spyOn(blockchainTraceabilityService, "registerAsset")
      .mockResolvedValue(asset());
    renderWithProviders(<CreateTraceabilityAssetPage />);
    fireEvent.change(screen.getByLabelText("Asset key"), { target: { value: "asset-key-1" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Serialized Pump" } });
    fireEvent.change(screen.getByLabelText("Asset type"), { target: { value: "serial" } });
    fireEvent.change(screen.getByLabelText("Product reference"), { target: { value: "SKU-1" } });
    fireEvent.change(screen.getByLabelText("Attributes (JSON)"), {
      target: { value: '{"temperature":"cold-chain"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Register asset" }));
    await waitFor(() =>
      expect(registerAsset).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_key: "asset-key-1",
          attributes: { temperature: "cold-chain" },
        })
      )
    );
    cleanup();

    const appendEvent = vi
      .spyOn(blockchainTraceabilityService, "appendEvent")
      .mockResolvedValue(event());
    renderWithProviders(<AppendTraceabilityEventPage />);
    fireEvent.change(screen.getByLabelText("Asset ID"), { target: { value: "asset-1" } });
    fireEvent.change(screen.getByLabelText("Event type"), {
      target: { value: "custody_transferred" },
    });
    fireEvent.change(screen.getByLabelText("Occurred at"), {
      target: { value: "2026-07-30T10:00" },
    });
    fireEvent.change(screen.getByLabelText("Actor reference"), {
      target: { value: "warehouse-1" },
    });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: "append:test" },
    });
    fireEvent.change(screen.getByLabelText("Location (JSON)"), {
      target: { value: '{"city":"Dallas"}' },
    });
    fireEvent.change(screen.getByLabelText("Event payload (JSON)"), {
      target: { value: '{"condition":"sealed"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Append immutable event" }));
    await waitFor(() =>
      expect(appendEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          occurred_at: new Date("2026-07-30T10:00").toISOString(),
          location: { city: "Dallas" },
          payload: { condition: "sealed" },
        })
      )
    );
    cleanup();

    const issueCredential = vi
      .spyOn(blockchainTraceabilityService, "issueCredential")
      .mockResolvedValue({
        credential: credential(),
        token: "one-time-token",
        token_recoverable: false,
      });
    renderWithProviders(<IssueAuthenticityCredentialPage />);
    fireEvent.change(screen.getByLabelText("Asset ID"), { target: { value: "asset-1" } });
    fireEvent.change(screen.getByLabelText("Expires at"), {
      target: { value: "2026-12-31T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Signed claims (JSON)"), {
      target: { value: '{"model":"pump","lot":7}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Issue and reveal token once" }));
    await waitFor(() =>
      expect(issueCredential).toHaveBeenCalledWith({
        asset_id: "asset-1",
        expires_at: new Date("2026-12-31T00:00").toISOString(),
        claims: { model: "pump", lot: 7 },
      })
    );
    expect(await screen.findByText("Secure one-time token handoff")).toBeInTheDocument();
  });

  it("updates mutable network and draft compliance evidence with parsed governed payloads", async () => {
    vi.spyOn(blockchainTraceabilityService, "getNetwork").mockResolvedValue(
      network({ provider_options: { rpc_url: "https://old.example.test" } })
    );
    const updateNetwork = vi
      .spyOn(blockchainTraceabilityService, "updateNetwork")
      .mockResolvedValue(network({ provider_options: { rpc_url: "https://new.example.test" } }));
    renderWithProviders(
      <Routes>
        <Route path="/networks/:id/edit" element={<EditLedgerNetworkPage />} />
      </Routes>,
      "/networks/network-1/edit"
    );

    await screen.findByRole("heading", { name: "Edit Ethereum mainnet" });
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Ethereum guarded" },
    });
    fireEvent.change(screen.getByLabelText("Required confirmations"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Provider options (JSON)"), {
      target: { value: '{"rpc_url":"https://new.example.test","batch":true}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save network" }));
    await waitFor(() =>
      expect(updateNetwork).toHaveBeenCalledWith("network-1", {
        name: "Ethereum guarded",
        provider_type: "evm",
        dependency_key: "ledger.ethereum",
        network_namespace: "eip155:1",
        description: "Mainnet anchoring adapter",
        chain_id: "1",
        secret_ref: undefined,
        confirmation_depth: 8,
        provider_options: { rpc_url: "https://new.example.test", batch: true },
      })
    );
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getComplianceEvidence").mockResolvedValue(
      complianceEvidence({
        status: "draft",
        result: "warning",
        details: { inspector: "qa-1" },
        valid_until: null,
      })
    );
    const updateComplianceEvidence = vi
      .spyOn(blockchainTraceabilityService, "updateComplianceEvidence")
      .mockResolvedValue(complianceEvidence({ result: "pass" }));
    renderWithProviders(
      <Routes>
        <Route path="/compliance/:id/edit" element={<EditComplianceEvidencePage />} />
      </Routes>,
      "/compliance/compliance-1/edit"
    );

    await screen.findByRole("heading", { name: "Edit iso-evidence-1" });
    fireEvent.change(screen.getByLabelText("Result (pass, fail, warning, not_applicable)"), {
      target: { value: " pass " },
    });
    fireEvent.change(screen.getByLabelText("Valid until"), {
      target: { value: "2026-12-31T23:59" },
    });
    fireEvent.change(screen.getByLabelText("Details (JSON)"), {
      target: { value: '{"inspector":"qa-2","score":99}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() =>
      expect(updateComplianceEvidence).toHaveBeenCalledWith("compliance-1", {
        event_id: "event-1",
        evidence_type: "inspection",
        standard: "ISO-9001",
        jurisdiction: undefined,
        result: "pass",
        document_ref: undefined,
        observed_at: new Date(now.slice(0, 16)).toISOString(),
        valid_until: new Date("2026-12-31T23:59").toISOString(),
        details: { inspector: "qa-2", score: 99 },
      })
    );
  });

  it("blocks immutable compliance edits and reports invalid JSON without mutating", async () => {
    vi.spyOn(blockchainTraceabilityService, "getComplianceEvidence").mockResolvedValue(
      complianceEvidence({ status: "finalized" })
    );
    renderWithProviders(
      <Routes>
        <Route path="/compliance/:id/edit" element={<EditComplianceEvidencePage />} />
      </Routes>,
      "/compliance/compliance-1/edit"
    );
    expect(
      await screen.findByRole("heading", { name: "Traceability request failed" })
    ).toBeInTheDocument();
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getNetwork").mockResolvedValue(network());
    const updateNetwork = vi
      .spyOn(blockchainTraceabilityService, "updateNetwork")
      .mockResolvedValue(network());
    renderWithProviders(
      <Routes>
        <Route path="/networks/:id/edit" element={<EditLedgerNetworkPage />} />
      </Routes>,
      "/networks/network-1/edit"
    );

    await screen.findByRole("heading", { name: "Edit Ethereum mainnet" });
    fireEvent.change(screen.getByLabelText("Provider options (JSON)"), {
      target: { value: "{invalid-json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save network" }));
    expect(
      await screen.findByRole("heading", { name: "Traceability request failed" })
    ).toBeInTheDocument();
    expect(updateNetwork).not.toHaveBeenCalled();
  });

  it("executes network, anchor, credential, and compliance detail actions with governed keys", async () => {
    vi.spyOn(blockchainTraceabilityService, "getNetwork").mockResolvedValue(
      network({ status: "draft" })
    );
    const activateNetwork = vi
      .spyOn(blockchainTraceabilityService, "activateNetwork")
      .mockResolvedValue(network({ status: "active" }));
    const probeNetwork = vi
      .spyOn(blockchainTraceabilityService, "probeNetwork")
      .mockResolvedValue({ ok: true, code: "healthy", message: "ok", value: null });
    renderWithProviders(
      <Routes>
        <Route path="/networks/:id" element={<LedgerNetworkDetailPage />} />
      </Routes>,
      "/networks/network-1"
    );
    expect(await screen.findByRole("heading", { name: "Ethereum mainnet" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Probe" }));
    await waitFor(() => expect(probeNetwork).toHaveBeenCalledWith("network-1"));
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Activate" })
    );
    await waitFor(() => expect(activateNetwork).toHaveBeenCalled());
    expect(activateNetwork.mock.calls[0]?.[1].transition_key).toMatch(/^activate:/);
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getAnchor").mockResolvedValue(
      anchor({ status: "failed", failure_code: "provider_timeout", failure_message: "Timed out" })
    );
    const retryAnchor = vi.spyOn(blockchainTraceabilityService, "retryAnchor").mockResolvedValue({
      anchor: anchor(),
      job: {
        id: "job-2",
        command: "blockchain_traceability.submit_anchor",
        status: "queued",
        correlation_id: "corr-job-2",
      },
      queued: true,
    });
    const verifyAnchor = vi
      .spyOn(blockchainTraceabilityService, "verifyAnchor")
      .mockResolvedValue(verificationAttempt({ verification_type: "anchor" }));
    renderWithProviders(
      <Routes>
        <Route path="/anchors/:id" element={<LedgerAnchorDetailPage />} />
      </Routes>,
      "/anchors/anchor-1"
    );
    expect(await screen.findByText("provider_timeout")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Queue retry" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Queue retry" })
    );
    await waitFor(() => expect(retryAnchor).toHaveBeenCalled());
    expect(retryAnchor.mock.calls[0]?.[1].transition_key).toMatch(/^retry-anchor:/);
    fireEvent.click(screen.getByRole("button", { name: "Verify proof" }));
    await waitFor(() => expect(verifyAnchor).toHaveBeenCalled());
    expect(verifyAnchor.mock.calls[0]?.[1].idempotency_key).toMatch(/^verify-anchor:/);
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getCredential").mockResolvedValue(credential());
    const revokeCredential = vi
      .spyOn(blockchainTraceabilityService, "revokeCredential")
      .mockResolvedValue(credential({ status: "revoked", revoked_at: now }));
    renderWithProviders(
      <Routes>
        <Route path="/credentials/:id" element={<AuthenticityCredentialDetailPage />} />
      </Routes>,
      "/credentials/credential-1"
    );
    expect(await screen.findAllByText("credential-public-1")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Revoke" })
    );
    await waitFor(() => expect(revokeCredential).toHaveBeenCalled());
    expect(revokeCredential.mock.calls[0]?.[1]).toMatchObject({
      reason: "Configured revocation reason",
    });
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getComplianceEvidence").mockResolvedValue(
      complianceEvidence()
    );
    const finalizeComplianceEvidence = vi
      .spyOn(blockchainTraceabilityService, "finalizeComplianceEvidence")
      .mockResolvedValue(complianceEvidence({ status: "finalized", content_hash: "f".repeat(64) }));
    const verifyComplianceEvidence = vi
      .spyOn(blockchainTraceabilityService, "verifyComplianceEvidence")
      .mockResolvedValue(verificationAttempt({ verification_type: "compliance" }));
    renderWithProviders(
      <Routes>
        <Route path="/compliance/:id" element={<ComplianceEvidenceDetailPage />} />
      </Routes>,
      "/compliance/compliance-1"
    );
    expect(await screen.findAllByText("iso-evidence-1")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Finalize" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Finalize" })
    );
    await waitFor(() => expect(finalizeComplianceEvidence).toHaveBeenCalled());
    expect(finalizeComplianceEvidence.mock.calls[0]?.[1].transition_key).toMatch(/^finalize:/);
    fireEvent.click(screen.getByRole("button", { name: "Verify evidence" }));
    await waitFor(() => expect(verifyComplianceEvidence).toHaveBeenCalled());
    expect(verifyComplianceEvidence.mock.calls[0]?.[1].idempotency_key).toMatch(
      /^verify-evidence:/
    );
  });

  it("fails closed when governed capabilities disable mutation actions", async () => {
    capabilityState.value = {
      ...capabilities,
      can_mutate_resources: false,
      document: {
        ...capabilities.document,
        features: { ...capabilities.document.features, enabled: false },
      },
    };
    vi.spyOn(blockchainTraceabilityService, "listNetworks").mockResolvedValue(
      pageResult([networkListItem()])
    );

    renderWithProviders(<LedgerNetworkListPage />);

    expect(await screen.findByRole("heading", { name: "Ledger networks" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Configure network" })).not.toBeInTheDocument();
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getAsset").mockResolvedValue(
      asset({ status: "draft" })
    );
    vi.spyOn(blockchainTraceabilityService, "getAssetHistory").mockResolvedValue(history());
    renderWithProviders(
      <Routes>
        <Route path="/assets/:id" element={<TraceabilityAssetDetailPage />} />
      </Routes>,
      "/assets/asset-1"
    );

    expect(await screen.findByRole("heading", { name: "Serialized Pump" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Activate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retire" })).not.toBeInTheDocument();
  });

  it("renders immutable detail branches and invalid verification evidence without terminal actions", async () => {
    vi.spyOn(blockchainTraceabilityService, "getEvent").mockResolvedValue(event());
    renderWithProviders(
      <Routes>
        <Route path="/events/:id" element={<TraceabilityEventDetailPage />} />
      </Routes>,
      "/events/event-1"
    );

    expect(
      await screen.findByRole("heading", { name: "custody_transferred · sequence 2" })
    ).toBeInTheDocument();
    expect(screen.getByText("Canonical schema v1 · SHA256 · correlation corr-event")).toBeVisible();
    expect(screen.getByText(/"condition": "sealed"/)).toBeInTheDocument();
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getVerificationAttempt").mockResolvedValue(
      verificationAttempt({
        outcome: "invalid",
        proof_evidence: {
          externally_anchored: false,
          simulated_provider: false,
          failing_sequence: 2,
          expected_hash: "f".repeat(64),
          actual_hash: "0".repeat(64),
        },
      })
    );
    renderWithProviders(
      <Routes>
        <Route path="/attempts/:id" element={<VerificationAttemptDetailPage />} />
      </Routes>,
      "/attempts/attempt-1"
    );

    expect(await screen.findByText("Chain failure at sequence 2")).toBeInTheDocument();
    expect(screen.getByText("Invalid proof")).toBeInTheDocument();
    expect(screen.getByTitle("f".repeat(64))).toBeInTheDocument();
    expect(screen.getByTitle("0".repeat(64))).toBeInTheDocument();
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getCredential").mockResolvedValue(
      credential({ status: "revoked", revoked_at: now })
    );
    renderWithProviders(
      <Routes>
        <Route path="/credentials/:id" element={<AuthenticityCredentialDetailPage />} />
      </Routes>,
      "/credentials/credential-1"
    );

    expect(await screen.findAllByText("credential-public-1")).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getComplianceEvidence").mockResolvedValue(
      complianceEvidence({ status: "finalized", content_hash: "a".repeat(64) })
    );
    const verifyComplianceEvidence = vi
      .spyOn(blockchainTraceabilityService, "verifyComplianceEvidence")
      .mockResolvedValue(verificationAttempt({ verification_type: "compliance" }));
    renderWithProviders(
      <Routes>
        <Route path="/compliance/:id" element={<ComplianceEvidenceDetailPage />} />
      </Routes>,
      "/compliance/compliance-1"
    );

    expect(await screen.findByTitle("a".repeat(64))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finalize" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Verify evidence" }));
    await waitFor(() => expect(verifyComplianceEvidence).toHaveBeenCalled());
    expect(verifyComplianceEvidence.mock.calls[0]?.[0]).toBe("compliance-1");
    expect(verifyComplianceEvidence.mock.calls[0]?.[1].idempotency_key).toMatch(
      /^verify-evidence:/
    );
  });

  it("clears stale verification success and exposes the failed dependency state", async () => {
    const verifyAuthenticity = vi
      .spyOn(blockchainTraceabilityService, "verifyAuthenticity")
      .mockResolvedValue(verificationAttempt({ verification_type: "authenticity" }));
    const verifyAssetChain = vi
      .spyOn(blockchainTraceabilityService, "verifyAssetChain")
      .mockRejectedValue(new Error("chain dependency unavailable"));

    renderWithProviders(<VerificationCenterPage />);

    fireEvent.change(await screen.findByLabelText("Credential public ID"), {
      target: { value: "public-1" },
    });
    fireEvent.change(screen.getByLabelText("Authenticity token"), {
      target: { value: "token-1" },
    });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: "verify-authenticity:test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify and persist attempt" }));

    await waitFor(() => expect(verifyAuthenticity).toHaveBeenCalled());
    expect(await screen.findByText("Provider is simulated.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "chain" }));
    fireEvent.change(screen.getByLabelText("Asset ID"), { target: { value: "asset-1" } });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: "verify-chain:test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify and persist attempt" }));

    await waitFor(() =>
      expect(verifyAssetChain).toHaveBeenCalledWith("asset-1", {
        idempotency_key: "verify-chain:test",
      })
    );
    expect(
      await screen.findByRole("heading", { name: "Traceability request failed" })
    ).toBeInTheDocument();
    expect(screen.queryByText("Provider is simulated.")).not.toBeInTheDocument();
  });

  it("covers recalled asset terminal actions, empty history, and mutable asset editing", async () => {
    vi.spyOn(blockchainTraceabilityService, "getAsset").mockResolvedValue(
      asset({
        status: "recalled",
        product_ref: "",
        batch_ref: "",
        serial_number: "",
        gtin: "",
        activated_at: null,
        attributes: { pressure: "high" },
      })
    );
    vi.spyOn(blockchainTraceabilityService, "getAssetHistory").mockResolvedValue(
      history({ items: [], failing_sequence: null, proof_status: "locally_consistent" })
    );
    const releaseAssetRecall = vi
      .spyOn(blockchainTraceabilityService, "releaseAssetRecall")
      .mockResolvedValue(asset({ status: "active" }));
    const retireAsset = vi
      .spyOn(blockchainTraceabilityService, "retireAsset")
      .mockResolvedValue(asset({ status: "retired" }));

    renderWithProviders(
      <Routes>
        <Route path="/assets/:id" element={<TraceabilityAssetDetailPage />} />
      </Routes>,
      "/assets/asset-1"
    );

    expect(await screen.findByText("No chain evidence yet")).toBeInTheDocument();
    expect(screen.getAllByText("— / —")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Release recall" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Release recall" })
    );
    await waitFor(() =>
      expect(releaseAssetRecall).toHaveBeenCalledWith("asset-1", expect.anything())
    );
    expect(releaseAssetRecall.mock.calls[0]?.[1].transition_key).toMatch(/^release-recall:/);

    fireEvent.click(screen.getByRole("button", { name: "Retire" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Retire" })
    );
    await waitFor(() => expect(retireAsset).toHaveBeenCalledWith("asset-1", expect.anything()));
    expect(retireAsset.mock.calls[0]?.[1].transition_key).toMatch(/^retire:/);
    cleanup();

    const updateAsset = vi
      .spyOn(blockchainTraceabilityService, "updateAsset")
      .mockResolvedValue(asset({ name: "Serialized Pump v2", attributes: { pressure: "normal" } }));
    renderWithProviders(
      <Routes>
        <Route path="/assets/:id/edit" element={<EditTraceabilityAssetPage />} />
      </Routes>,
      "/assets/asset-1/edit"
    );

    await screen.findByRole("heading", { name: "Edit Serialized Pump" });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Serialized Pump v2" } });
    fireEvent.change(screen.getByLabelText("Product reference"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Batch reference"), { target: { value: "batch-2" } });
    fireEvent.change(screen.getByLabelText("Attributes (JSON)"), {
      target: { value: '{"pressure":"normal"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save asset" }));

    await waitFor(() =>
      expect(updateAsset).toHaveBeenCalledWith("asset-1", {
        name: "Serialized Pump v2",
        asset_type: "serial",
        product_ref: undefined,
        batch_ref: "batch-2",
        serial_number: undefined,
        gtin: undefined,
        description: "Pump with custody evidence",
        attributes: { pressure: "normal" },
      })
    );
  });

  it("executes active network disable/delete and surfaces action errors without hiding detail state", async () => {
    vi.spyOn(blockchainTraceabilityService, "getNetwork").mockResolvedValue(network());
    const disableNetwork = vi
      .spyOn(blockchainTraceabilityService, "disableNetwork")
      .mockRejectedValue(new Error("provider lock is active"));
    const deleteNetwork = vi
      .spyOn(blockchainTraceabilityService, "deleteNetwork")
      .mockResolvedValue(undefined);

    renderWithProviders(
      <Routes>
        <Route path="/networks/:id" element={<LedgerNetworkDetailPage />} />
      </Routes>,
      "/networks/network-1"
    );

    expect(await screen.findByRole("heading", { name: "Ethereum mainnet" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Disable" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Disable" })
    );
    await waitFor(() =>
      expect(disableNetwork).toHaveBeenCalledWith("network-1", expect.anything())
    );
    expect(disableNetwork.mock.calls[0]?.[1].transition_key).toMatch(/^disable:/);
    expect(await screen.findByText("Traceability request failed")).toBeInTheDocument();
    expect(
      screen.getByText("The operation could not be completed. No success has been assumed.")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" })
    );
    await waitFor(() => expect(deleteNetwork).toHaveBeenCalledWith("network-1"));
  });

  it("covers filtered empty list guidance and dependency outcomes without target identifiers", async () => {
    const listAttempts = vi
      .spyOn(blockchainTraceabilityService, "listVerificationAttempts")
      .mockResolvedValue(pageResult([]));

    renderWithProviders(<VerificationAttemptListPage />, "/?status=dependency_unavailable");

    await waitFor(() =>
      expect(listAttempts).toHaveBeenCalledWith(
        expect.objectContaining({ outcome: "dependency_unavailable" })
      )
    );
    expect(await screen.findByText("No attempt found")).toBeInTheDocument();
    expect(
      screen.getByText(/No records match the selected server-side filters/u)
    ).toBeInTheDocument();
    cleanup();

    vi.spyOn(blockchainTraceabilityService, "getVerificationAttempt").mockResolvedValue(
      verificationAttempt({
        asset_id: undefined,
        anchor_id: undefined,
        credential_id: undefined,
        compliance_evidence_id: undefined,
        outcome: "dependency_unavailable",
        proof_evidence: {
          externally_anchored: false,
          simulated_provider: false,
        },
      })
    );
    renderWithProviders(
      <Routes>
        <Route path="/attempts/:id" element={<VerificationAttemptDetailPage />} />
      </Routes>,
      "/attempts/attempt-1"
    );

    expect(
      await screen.findByText("A required dependency could not provide conclusive evidence.")
    ).toBeInTheDocument();
    expect(screen.getByText("dependency_unavailable")).toBeInTheDocument();
  });
});
