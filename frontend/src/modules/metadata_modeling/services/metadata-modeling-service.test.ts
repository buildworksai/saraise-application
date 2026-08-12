/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- Test cases are fixture-heavy and assert mock method calls directly. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import type {
  ApiEnvelope,
  DynamicResourceDetail,
  DynamicResourceSummary,
  EntityDefinitionCreate,
  EntityDefinitionDetail,
  EntityDefinitionSummary,
  EntitySchemaVersionDetail,
  ExportDocument,
  ImportRequest,
  MetadataModelingConfiguration,
  MetadataModelingConfigurationValues,
  SchemaCandidateCreate,
} from "../contracts";
import { ENDPOINTS } from "../contracts";
import { metadataModelingService as service } from "./metadata-modeling-service";

vi.mock("@/services/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const meta = {
  correlation_id: "corr-meta",
  timestamp: "2026-07-21T00:00:00Z",
  pagination: {
    count: 1,
    page: 1,
    page_size: 25,
    total_pages: 1,
    has_next: false,
    has_previous: false,
  },
};

const definitionSummary: EntityDefinitionSummary = {
  id: "schema-1",
  name: "Asset",
  plural_name: "Assets",
  code: "asset",
  description: "Tracked asset",
  owner_module: "metadata_modeling",
  icon: "box",
  origin: "custom",
  status: "published",
  active_version: "version-1",
  active_version_number: 1,
  record_count: 3,
  lock_version: 7,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const definitionDetail: EntityDefinitionDetail = {
  ...definitionSummary,
  is_submittable: true,
  track_changes: true,
  naming_strategy: "uuid",
  naming_config: {},
  active_fields: [],
  current_version: null,
  created_by: "user-1",
  updated_by: "user-1",
  archived_at: null,
  archived_by: null,
};

const resource: DynamicResourceSummary = {
  id: "resource-1",
  entity_definition: "schema-1",
  entity_code: "asset",
  entity_name: "Asset",
  schema_version: "version-1",
  schema_version_number: 1,
  record_key: "AST-001",
  display_name: "Forklift",
  state: "draft",
  lock_version: 2,
  searchable_data: { serial: "FL-1" },
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const resourceDetail: DynamicResourceDetail = {
  ...resource,
  data: { serial: "FL-1" },
  fields: [],
  created_by: "user-1",
  updated_by: "user-1",
  submitted_at: null,
  submitted_by: null,
  cancelled_at: null,
  cancelled_by: null,
};

const versionDetail: EntitySchemaVersionDetail = {
  id: "version-2",
  version: 2,
  status: "candidate",
  schema_hash: "sha256:version-2",
  change_summary: "Add serial",
  compatibility: "compatible",
  published_at: null,
  published_by: null,
  created_by: "user-1",
  created_at: "2026-07-21T00:00:00Z",
  entity_definition: "schema-1",
  schema: {},
  fields: [],
  validation_report: {
    valid: true,
    compatibility: "compatible",
    resource_count: 1,
    incompatible_resource_count: 0,
    errors: [],
    warnings: [],
  },
  based_on_version: "version-1",
};

const configurationValues: MetadataModelingConfigurationValues = {
  synchronous_validation_limit: 100,
  max_fields_per_schema: 25,
  max_schema_bytes: 4096,
  max_record_data_bytes: 8192,
  max_regex_length: 120,
  default_page_size: 25,
  max_page_size: 100,
  allowed_field_types: ["text", "number"],
  feature_flags: { dynamic_records: true },
  rollout: {
    dynamic_records: { enabled: true, tenant_percentage: 50, roles: ["admin"], cohorts: ["all"] },
  },
};

const configuration: MetadataModelingConfiguration = {
  id: "metadata-config",
  environment: "development",
  version: 4,
  created_by: "user-1",
  created_at: "2026-07-20T00:00:00Z",
  updated_by: "user-2",
  updated_at: "2026-07-21T00:00:00Z",
  ...configurationValues,
};

function envelope<T>(data: T): ApiEnvelope<T> {
  return { data, meta };
}

describe("metadataModelingService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps paginated lists and drops empty query filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope([definitionSummary]));

    const result = await service.listDefinitions({
      status: "published",
      search: "",
      page: 1,
    });

    expect(result).toEqual({
      items: [definitionSummary],
      pagination: meta.pagination,
      correlationId: "corr-meta",
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.entityDefinitions}?status=published&page=1`
    );
  });

  it("fails explicitly when a paginated response omits pagination metadata", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta: { correlation_id: "corr-missing", timestamp: "2026-07-21T00:00:00Z" },
    });

    await expect(service.listResources()).rejects.toThrow("omitted pagination metadata");
  });

  it("sends idempotency and lock headers for governed mutations", async () => {
    const payload: EntityDefinitionCreate = {
      name: "Asset",
      plural_name: "Assets",
      code: "asset",
      description: "Tracked asset",
      icon: "box",
      is_submittable: true,
      track_changes: true,
      naming_strategy: "uuid",
      naming_config: {},
    };
    vi.mocked(apiClient.post).mockResolvedValue(envelope(definitionDetail));
    vi.mocked(apiClient.patch).mockResolvedValue(envelope(definitionDetail));
    vi.mocked(apiClient.delete).mockResolvedValue(
      envelope({ operation: "delete", status: "completed", id: "resource-1" })
    );

    await service.createDefinition(payload, "idem-create");
    await service.updateDefinition(
      "schema-1",
      { ...payload, code: "asset", name: "Asset register" },
      7
    );
    await service.deleteResource("resource-1", 2);

    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.entityDefinitions, payload, {
      headers: { "Idempotency-Key": "idem-create" },
    });
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.entityDefinition("schema-1"),
      { ...payload, code: "asset", name: "Asset register" },
      { headers: { "If-Match": "7" } }
    );
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.resource("resource-1"), {
      headers: { "If-Match": "2" },
    });
  });

  it("uses full replacement, resource filters, and combined submit headers", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope([resource]));
    vi.mocked(apiClient.put).mockResolvedValue(envelope(definitionDetail));
    vi.mocked(apiClient.post).mockResolvedValue(envelope({ ...resource, submitted_at: null }));

    const updatePayload: EntityDefinitionCreate = {
      name: "Asset",
      plural_name: "Assets",
      code: "asset",
      description: "Tracked asset",
      icon: "box",
      is_submittable: true,
      track_changes: true,
      naming_strategy: "uuid",
      naming_config: {},
    };
    await service.updateDefinition("schema-1", updatePayload, 7, false);
    await service.listResources({ entity_id: "schema-1", state: "draft", search: "", page: 2 });
    await service.submitResource("resource-1", 2, "idem-submit");

    expect(apiClient.put).toHaveBeenCalledWith(
      ENDPOINTS.entityDefinition("schema-1"),
      updatePayload,
      { headers: { "If-Match": "7" } }
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.resources}?entity_id=schema-1&state=draft&page=2`
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.submitResource("resource-1"),
      { lock_version: 2 },
      { headers: { "If-Match": "2", "Idempotency-Key": "idem-submit" } }
    );
  });

  it("routes configuration preview, update, rollback, import, and export", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(envelope({ valid: true }));
    vi.mocked(apiClient.put).mockResolvedValue(envelope(configuration));
    vi.mocked(apiClient.get).mockResolvedValue(
      envelope({
        format_version: "1.0",
        environment: "development",
        values: configurationValues,
        checksum: "sha256:test",
      })
    );

    await service.previewConfiguration("development", configurationValues);
    await service.updateConfiguration("development", configurationValues, 4);
    await service.rollbackConfiguration("development", 3);
    await service.importConfiguration({
      environment: "development",
      document: {
        format_version: "1.0",
        environment: "development",
        values: configurationValues,
        checksum: "sha256:test",
      },
      validate_only: true,
    });
    await service.exportConfiguration("development");

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.previewConfiguration}?environment=development`,
      { values: configurationValues }
    );
    expect(apiClient.put).toHaveBeenCalledWith(
      `${ENDPOINTS.configuration}?environment=development`,
      configurationValues,
      { headers: { "If-Match": "4" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.rollbackConfiguration(3)}?environment=development`,
      {}
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.importConfiguration}?environment=development`,
      expect.objectContaining({ validate_only: true })
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.exportConfiguration}?environment=development`
    );
  });

  it("routes schema candidate review, diff, publish, reject, rollback, import, and export", async () => {
    const candidate: SchemaCandidateCreate = {
      fields: [],
      based_on_version_id: "version-1",
      change_summary: "Review candidate",
    };
    const document: ExportDocument = {
      format_version: "1.0",
      entity: { code: "asset" },
      schema: { fields: [] },
      checksum: "sha256:asset",
    };
    const importRequest: ImportRequest = { document, mode: "validate_only" };
    vi.mocked(apiClient.get).mockResolvedValue(envelope(document));
    vi.mocked(apiClient.post).mockResolvedValue(envelope(versionDetail));

    await service.getDefinition("schema/1");
    await service.createCandidate("schema-1", candidate);
    await service.validateCandidate("schema-1", "version-2");
    await service.diffVersions("schema-1", "version-1", "version-2");
    await service.publishCandidate("schema-1", "version-2", "idem-publish");
    await service.rejectCandidate("schema-1", "version-2", "Needs field labels");
    await service.rollbackVersion("schema-1", "version-1", "idem-rollback");
    await service.exportDefinition("schema-1");
    await service.importDefinition(importRequest, "idem-import");

    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.entityDefinition("schema/1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.schemaVersions("schema-1"),
      candidate
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.validateSchemaVersion("schema-1", "version-2"),
      {}
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.diffSchemaVersions("schema-1")}?from=version-1&to=version-2`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.publishSchemaVersion("schema-1", "version-2"),
      {},
      { headers: { "Idempotency-Key": "idem-publish" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.rejectSchemaVersion("schema-1", "version-2"),
      { reason: "Needs field labels" }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      5,
      ENDPOINTS.rollbackSchemaVersion("schema-1", "version-1"),
      {},
      { headers: { "Idempotency-Key": "idem-rollback" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      6,
      ENDPOINTS.importEntityDefinition,
      importRequest,
      { headers: { "Idempotency-Key": "idem-import" } }
    );
  });

  it("routes dynamic resource lifecycle, version history, naming, and health requests", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope([resource]));
    vi.mocked(apiClient.post).mockResolvedValue(envelope(resourceDetail));
    vi.mocked(apiClient.patch).mockResolvedValue(envelope(resourceDetail));
    vi.mocked(apiClient.put).mockResolvedValue(envelope(resourceDetail));

    await service.getResource("resource/1");
    await service.createResource(
      { entity_id: "schema-1", data: { serial: "FL-1" } },
      "idem-create"
    );
    await service.replaceResource("resource-1", { data: { serial: "FL-2" } }, 3);
    await service.patchResource("resource-1", { changes: { serial: "FL-3" } }, 4);
    await service.cancelResource("resource-1", "Bad data", 5, "idem-cancel");
    await service.restoreResource("resource-1");
    await service.duplicateResource("resource-1");
    await service.listResourceVersions("resource-1", 2);
    await service.getResourceVersion("resource-1", 3);
    await service.listNamingSequences({ entity_id: "schema-1", is_active: true, page: 2 });
    await service.getNamingSequence("sequence-1");
    await service.resetNamingSequence("sequence-1", 99);
    await service.previewRecordKey("schema-1", { serial: "FL-3" });
    await service.health();

    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.resource("resource/1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.resources,
      { entity_id: "schema-1", data: { serial: "FL-1" } },
      { headers: { "Idempotency-Key": "idem-create" } }
    );
    expect(apiClient.put).toHaveBeenCalledWith(
      ENDPOINTS.resource("resource-1"),
      { data: { serial: "FL-2" } },
      { headers: { "If-Match": "3" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.resource("resource-1"),
      { changes: { serial: "FL-3" } },
      { headers: { "If-Match": "4" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.cancelResource("resource-1"),
      { reason: "Bad data", lock_version: 5 },
      { headers: { "If-Match": "5", "Idempotency-Key": "idem-cancel" } }
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.resourceVersions("resource-1")}?page=2`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      4,
      `${ENDPOINTS.namingSequences}?entity_id=schema-1&is_active=true&page=2`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(5, ENDPOINTS.resetNamingSequence("sequence-1"), {
      next_value: 99,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(6, ENDPOINTS.previewRecordKey, {
      entity_id: "schema-1",
      data: { serial: "FL-3" },
    });
    expect(apiClient.get).toHaveBeenLastCalledWith(ENDPOINTS.health);
  });
});
