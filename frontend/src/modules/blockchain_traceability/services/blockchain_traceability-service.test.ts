/* eslint-disable max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { ApiError, apiClient } from "@/services/api-client";
import type {
  ApiV2Envelope,
  ApiV2PaginatedEnvelope,
  LedgerNetwork,
  QueuedAnchor,
  TraceabilityAsset,
} from "../contracts";
import {
  BlockchainTraceabilityApiError,
  anchorQuery,
  attemptQuery,
  assetQuery,
  blockchainTraceabilityService,
  credentialQuery,
  eventQuery,
  evidenceQuery,
  networkQuery,
} from "./blockchain_traceability-service";

const meta = { correlation_id: "corr-1", timestamp: "2026-07-22T10:00:00Z" };
const pagination = {
  page: 2,
  page_size: 25,
  total_pages: 3,
  count: 52,
  has_next: true,
  has_previous: true,
};

describe("blockchain traceability v2 service", () => {
  afterEach(() => vi.restoreAllMocks());

  it("serializes filters with URLSearchParams and preserves page metadata", async () => {
    const envelope = {
      data: [],
      meta: { ...meta, pagination },
    } satisfies ApiV2PaginatedEnvelope<TraceabilityAsset>;
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(envelope);
    await expect(
      blockchainTraceabilityService.listAssets({
        page: 2,
        status: "recalled",
        product_ref: "A&B",
        ordering: "-created_at",
      })
    ).resolves.toEqual({ items: [], pagination, correlationId: "corr-1" });
    expect(get).toHaveBeenCalledWith(
      "/api/v2/blockchain-traceability/assets/?page=2&ordering=-created_at&status=recalled&product_ref=A%26B"
    );
    expect(assetQuery({ search: "serial 1" })).toContain("search=serial+1");
  });

  it("serializes every list filter family through governed query helpers", () => {
    expect(networkQuery({ search: "main net", status: "active", provider_type: "fabric" })).toBe(
      "/api/v2/blockchain-traceability/networks/?search=main+net&status=active&provider_type=fabric"
    );
    expect(
      eventQuery({
        asset_id: "asset-1",
        event_type: "SHIP",
        occurred_after: "2026-07-01T00:00:00Z",
        actor_ref: "warehouse",
      })
    ).toContain("occurred_after=2026-07-01T00%3A00%3A00Z");
    expect(anchorQuery({ asset_id: "asset-1", network_id: "network-1", status: "failed" })).toBe(
      "/api/v2/blockchain-traceability/anchors/?asset_id=asset-1&network_id=network-1&status=failed"
    );
    expect(credentialQuery({ status: "revoked", credential_type: "authenticity" })).toContain(
      "credential_type=authenticity"
    );
    expect(evidenceQuery({ standard: "FDA", jurisdiction: "US", result: "pass" })).toContain(
      "jurisdiction=US"
    );
    expect(attemptQuery({ verification_type: "chain", outcome: "dependency_unavailable" })).toBe(
      "/api/v2/blockchain-traceability/verification-attempts/?verification_type=chain&outcome=dependency_unavailable"
    );
  });

  it("uses PATCH for partial network updates", async () => {
    const network = { id: "network-1" } as LedgerNetwork;
    const patch = vi
      .spyOn(apiClient, "patch")
      .mockResolvedValue({ data: network, meta } satisfies ApiV2Envelope<LedgerNetwork>);
    await blockchainTraceabilityService.updateNetwork("network-1", { name: "Primary" });
    expect(patch).toHaveBeenCalledWith("/api/v2/blockchain-traceability/networks/network-1/", {
      name: "Primary",
    });
  });

  it("keeps accepted anchor work distinct from completed work", async () => {
    const accepted = {
      queued: true,
      anchor: { id: "anchor-1", status: "queued" },
      job: { id: "job-1", status: "queued" },
    } as QueuedAnchor;
    vi.spyOn(apiClient, "post").mockResolvedValue({
      data: accepted,
      meta,
    } satisfies ApiV2Envelope<QueuedAnchor>);
    const result = await blockchainTraceabilityService.requestAnchor({
      asset_id: "asset-1",
      network_id: "network-1",
      start_sequence: 1,
      end_sequence: 3,
      idempotency_key: "anchor-once",
    });
    expect(result.queued).toBe(true);
    expect(result.anchor.status).toBe("queued");
  });

  it("maps governed failures with field and correlation evidence", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(
      new ApiError("failed", 503, {
        error: {
          code: "provider_unavailable",
          message: "Provider unavailable",
          detail: {
            field_errors: [
              { field: "network_id", code: "unavailable", message: "Network unavailable" },
            ],
          },
          correlation_id: "corr-provider",
        },
      })
    );
    const failure = await blockchainTraceabilityService
      .requestAnchor({
        asset_id: "asset-1",
        network_id: "network-1",
        start_sequence: 1,
        end_sequence: 1,
        idempotency_key: "once",
      })
      .catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(BlockchainTraceabilityApiError);
    if (!(failure instanceof BlockchainTraceabilityApiError))
      throw new Error("Expected governed module error");
    expect(failure.status).toBe(503);
    expect(failure.correlationId).toBe("corr-provider");
    expect(failure.fieldErrors.get("network_id")).toBe("Network unavailable");
  });

  it("unwraps the governed singleton configuration endpoints", async () => {
    const configuration = {
      id: "configuration-1",
      tenant_id: "tenant-1",
      environment: "default",
      version: 1,
      document: {},
      updated_at: meta.timestamp,
      updated_by: "actor-1",
    };
    const envelope = { data: configuration, meta } satisfies ApiV2Envelope<typeof configuration>;
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(envelope);
    await expect(blockchainTraceabilityService.getConfiguration()).resolves.toBe(configuration);
    expect(get).toHaveBeenCalledWith("/api/v2/blockchain-traceability/configuration/");

    const put = vi.spyOn(apiClient, "put").mockResolvedValue(envelope);
    await blockchainTraceabilityService.updateConfiguration({
      document: configuration.document as never,
    });
    expect(put).toHaveBeenCalledWith("/api/v2/blockchain-traceability/configuration/current/", {
      document: configuration.document,
    });
  });

  it("routes configuration preview, history, import, export, and capability calls with environment scope", async () => {
    const response = { data: { id: "configuration-1" }, meta } satisfies ApiV2Envelope<unknown>;
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(response);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(response);

    await blockchainTraceabilityService.previewConfiguration({ document: {} } as never);
    await blockchainTraceabilityService.listConfigurationHistory("production");
    await blockchainTraceabilityService.rollbackConfiguration({
      version: 3,
      change_reason: "rollback",
    } as never);
    await blockchainTraceabilityService.importConfiguration({ document: {} } as never);
    await blockchainTraceabilityService.exportConfiguration("staging");
    await blockchainTraceabilityService.getCapabilities("development");

    expect(post).toHaveBeenCalledWith("/api/v2/blockchain-traceability/configuration/preview/", {
      document: {},
    });
    expect(get).toHaveBeenCalledWith(
      "/api/v2/blockchain-traceability/configuration/history/?environment=production"
    );
    expect(post).toHaveBeenCalledWith("/api/v2/blockchain-traceability/configuration/rollback/", {
      version: 3,
      change_reason: "rollback",
    });
    expect(post).toHaveBeenCalledWith(
      "/api/v2/blockchain-traceability/configuration/import-document/",
      { document: {} }
    );
    expect(get).toHaveBeenCalledWith(
      "/api/v2/blockchain-traceability/configuration/export-document/?environment=staging"
    );
    expect(get).toHaveBeenCalledWith(
      "/api/v2/blockchain-traceability/configuration/capabilities/?environment=development"
    );
  });

  it("routes asset, event, credential, evidence, and verification transitions without synthetic completion", async () => {
    const response = { data: { id: "resource-1" }, meta } satisfies ApiV2Envelope<unknown>;
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(response);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(response);
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue(response);
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);

    await blockchainTraceabilityService.createNetwork({ name: "Main" } as never);
    await blockchainTraceabilityService.deleteNetwork("network-1");
    await blockchainTraceabilityService.activateNetwork("network-1", {
      transition_key: "activate",
    });
    await blockchainTraceabilityService.disableNetwork("network-1", { transition_key: "disable" });
    await blockchainTraceabilityService.probeNetwork("network-1");
    await blockchainTraceabilityService.registerAsset({ product_ref: "sku-1" } as never);
    await blockchainTraceabilityService.getAsset("asset-1");
    await blockchainTraceabilityService.updateAsset("asset-1", { status: "active" } as never);
    await blockchainTraceabilityService.deleteAsset("asset-1");
    await blockchainTraceabilityService.recallAsset("asset-1", { reason: "recall" } as never);
    await blockchainTraceabilityService.releaseAssetRecall("asset-1", {
      transition_key: "release",
    });
    await blockchainTraceabilityService.getAssetHistory("asset-1", { page: 2 });
    await blockchainTraceabilityService.verifyAssetChain("asset-1", { idempotency_key: "chain" });
    await blockchainTraceabilityService.appendEvent({ asset_id: "asset-1" } as never);
    await blockchainTraceabilityService.getEvent("event-1");
    await blockchainTraceabilityService.retryAnchor("anchor-1", { transition_key: "retry" });
    await blockchainTraceabilityService.refreshAnchor("anchor-1");
    await blockchainTraceabilityService.verifyAnchor("anchor-1", { idempotency_key: "verify" });
    await blockchainTraceabilityService.issueCredential({ asset_id: "asset-1" } as never);
    await blockchainTraceabilityService.getCredential("credential-1");
    await blockchainTraceabilityService.revokeCredential("credential-1", {
      transition_key: "revoke",
      reason: "leaked",
    });
    await blockchainTraceabilityService.verifyAuthenticity({ asset_id: "asset-1" } as never);
    await blockchainTraceabilityService.createComplianceEvidence({ asset_id: "asset-1" } as never);
    await blockchainTraceabilityService.updateComplianceEvidence("evidence-1", {
      result: "pass",
    } as never);
    await blockchainTraceabilityService.finalizeComplianceEvidence("evidence-1", {
      transition_key: "finalize",
    });
    await blockchainTraceabilityService.supersedeComplianceEvidence("evidence-1", {
      reason: "new evidence",
    } as never);
    await blockchainTraceabilityService.verifyComplianceEvidence("evidence-1", {
      idempotency_key: "verify-evidence",
    });
    await blockchainTraceabilityService.getVerificationAttempt("attempt-1");
    await blockchainTraceabilityService.getHealth();

    expect(post).toHaveBeenCalledWith("/api/v2/blockchain-traceability/networks/", {
      name: "Main",
    });
    expect(del).toHaveBeenCalledWith("/api/v2/blockchain-traceability/networks/network-1/");
    expect(post).toHaveBeenCalledWith("/api/v2/blockchain-traceability/networks/network-1/probe/");
    expect(patch).toHaveBeenCalledWith("/api/v2/blockchain-traceability/assets/asset-1/", {
      status: "active",
    });
    expect(get).toHaveBeenCalledWith(
      "/api/v2/blockchain-traceability/assets/asset-1/history/?page=2"
    );
    expect(post).toHaveBeenCalledWith("/api/v2/blockchain-traceability/anchors/anchor-1/refresh/");
    expect(post).toHaveBeenCalledWith(
      "/api/v2/blockchain-traceability/credentials/credential-1/revoke/",
      { transition_key: "revoke", reason: "leaked" }
    );
    expect(post).toHaveBeenCalledWith(
      "/api/v2/blockchain-traceability/compliance-evidence/evidence-1/finalize/",
      { transition_key: "finalize" }
    );
    expect(get).toHaveBeenCalledWith("/api/v2/blockchain-traceability/health/");
  });
});
