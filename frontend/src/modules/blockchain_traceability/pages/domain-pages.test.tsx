/* eslint-disable max-lines-per-function -- domain page mutation tests need shared builders and end-to-end page branches in one focused file. */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type {
  AssetHistory,
  LedgerAnchor,
  LedgerNetworkListItem,
  TraceabilityAsset,
  TraceabilityCapabilities,
  TraceabilityEvent,
  VerificationAttempt,
} from "../contracts";
import { blockchainTraceabilityService } from "../services/blockchain_traceability-service";
import {
  CreateComplianceEvidencePage,
  CreateLedgerAnchorPage,
  LedgerNetworkListPage,
  TraceabilityAssetDetailPage,
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
});
