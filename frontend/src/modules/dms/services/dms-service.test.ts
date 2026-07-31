/* eslint-disable max-lines-per-function -- cohesive service contract coverage keeps shared fixtures local. */
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiEnvelope,
  type Document,
  type DocumentSummary,
  type Folder,
} from "../contracts";
import { DMS_QUERY_KEYS, DmsApiError, dmsService, serializeDmsQuery } from "./dms-service";

const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
} as const;
const meta = { correlation_id: "corr-dms", timestamp: "2026-07-22T00:00:00Z", pagination } as const;
const version = {
  id: "version-1",
  version_number: 1,
  original_filename: "policy.pdf",
  mime_type: "application/pdf",
  size_bytes: 42,
  checksum_sha256: "a".repeat(64),
  created_by: "actor-1",
  created_at: "2026-07-22T00:00:00Z",
} as const;
const document: Document = {
  id: "document-1",
  name: "Policy",
  description: "",
  folder_id: null,
  folder_name: null,
  tags: ["policy"],
  metadata: { department: "legal" },
  current_version: version,
  version_count: 1,
  created_by: "actor-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  allowed_actions: ["read", "download", "update"],
};
const folder: Folder = {
  id: "folder-1",
  name: "Legal",
  description: "",
  parent_id: null,
  path: "/Legal",
  depth: 0,
  sort_order: 0,
  created_by: "actor-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  allowed_actions: ["read", "update"],
};

describe("dmsService", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("serializes bounded collection queries deterministically", () => {
    expect(
      serializeDmsQuery(ENDPOINTS.DOCUMENTS.LIST, {
        folder: "folder-1",
        tags: ["legal", "signed"],
        search: "policy",
        ordering: "-updated_at",
        page: 2,
        page_size: 25,
      })
    ).toBe(
      "/api/v2/dms/documents/?folder=folder-1&search=policy&ordering=-updated_at&page=2&page_size=25&tags=legal&tags=signed"
    );
  });

  it("unwraps governed pages and exports stable query keys", async () => {
    const response: ApiEnvelope<readonly DocumentSummary[]> = { data: [document], meta };
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(response);
    await expect(dmsService.listDocuments({ page: 1 })).resolves.toEqual({
      items: [document],
      pagination,
      correlation_id: "corr-dms",
    });
    expect(get).toHaveBeenCalledWith(`${ENDPOINTS.DOCUMENTS.LIST}?page=1`);
    expect(DMS_QUERY_KEYS.documents({ page: 1 })).toEqual(["dms", "documents", { page: 1 }]);
  });

  it("rejects collection envelopes that omit pagination evidence", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [document],
      meta: { correlation_id: "corr-no-page", timestamp: meta.timestamp },
    });
    const failure = await dmsService.listDocuments().catch((error: Error) => error);
    expect(failure).toBeInstanceOf(DmsApiError);
    if (!(failure instanceof DmsApiError)) throw new Error("Expected normalized DMS error");
    expect(failure.problem).toEqual({
      kind: "unexpected",
      status: 502,
      message: "The DMS returned a collection without pagination evidence.",
      correlation_id: "corr-no-page",
    });
  });

  it("uses PATCH with optimistic concurrency and never PUT", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: document, meta });
    await dmsService.updateDocument(document.id, {
      name: "Policy 2026",
      expected_updated_at: document.updated_at,
    });
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.DOCUMENTS.UPDATE(document.id), {
      name: "Policy 2026",
      expected_updated_at: document.updated_at,
    });
  });

  it("delegates folder mutations to exact registry paths", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: folder, meta });
    await dmsService.createFolder({ name: "Legal" });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.FOLDERS.CREATE, { name: "Legal" });
  });

  it("uses exact endpoints for void deletes, restores, and principal lookup", async () => {
    const deleteCall = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: version, meta });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: [], meta });
    await expect(dmsService.deleteDocument("document/unsafe")).resolves.toBeUndefined();
    await dmsService.restoreVersion("version/1", { change_note: "restore current" });
    await dmsService.searchPrincipals("Ada Lovelace", "user", 10);
    expect(deleteCall).toHaveBeenCalledWith("/api/v2/dms/documents/document%2Funsafe/");
    expect(post).toHaveBeenCalledWith("/api/v2/dms/document-versions/version%2F1/restore/", {
      change_note: "restore current",
    });
    expect(get).toHaveBeenCalledWith(
      "/api/v2/dms/principals/?search=Ada+Lovelace&type=user&limit=10"
    );
  });

  it("routes every governed DMS command through its canonical endpoint", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: document, meta });
    const pageGet = { data: [], meta: { ...meta, pagination } };
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: document, meta });
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: document, meta });
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: document, meta });
    const deleteCall = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);

    get.mockResolvedValueOnce({ data: folder, meta });
    await dmsService.getFolder("folder-id");
    patch.mockResolvedValueOnce({ data: folder, meta });
    await dmsService.updateFolder("folder-id", { sort_order: 2 });
    await dmsService.moveFolder("folder-id", { parent_id: null });
    await dmsService.deleteFolder("folder-id");

    get.mockResolvedValueOnce({
      data: { folder, breadcrumbs: [], folders: [], documents: [] },
      meta,
    });
    await dmsService.getFolderContents("folder-id");
    await dmsService.getDocument("document-id");
    await dmsService.moveDocument("document-id", { folder_id: null });

    get.mockResolvedValueOnce(pageGet);
    await dmsService.listVersions("document-id", { page: 2 });
    get.mockResolvedValueOnce({ data: version, meta });
    await dmsService.getVersion("version-id");

    get.mockResolvedValueOnce(pageGet);
    await dmsService.listPermissions("document-id");
    await dmsService.createPermission({
      document_id: "document-id",
      principal_type: "user",
      principal_id: "actor-id",
      permission: "read",
    });
    await dmsService.getPermission("permission-id");
    await dmsService.updatePermission("permission-id", { permission: "write" });
    await dmsService.revokePermission("permission-id");

    get.mockResolvedValueOnce(pageGet);
    await dmsService.listShares("document-id");
    await dmsService.createShare({
      document_id: "document-id",
      version_id: "version-id",
      expires_at: meta.timestamp,
      max_access_count: 3,
    });
    await dmsService.getShare("share-id");
    await dmsService.revokeShare("share-id");

    get.mockResolvedValueOnce({ data: { status: "healthy", checks: {} }, meta });
    await dmsService.health();
    get.mockResolvedValueOnce({ data: document, meta });
    await dmsService.getConfiguration("development");
    await dmsService.updateConfiguration({
      environment: "development",
      values: {},
    } as Parameters<typeof dmsService.updateConfiguration>[0]);
    await dmsService.previewConfiguration({
      environment: "development",
      values: {},
    } as Parameters<typeof dmsService.previewConfiguration>[0]);
    get.mockResolvedValueOnce(pageGet);
    await dmsService.configurationHistory("development", { page: 2 });
    get.mockResolvedValueOnce(pageGet);
    await dmsService.configurationAudit("development", { page: 3 });
    await dmsService.rollbackConfiguration(1, "development");
    await dmsService.importConfiguration({
      schema_version: 1,
      module: "dms",
      environment: "development",
      version: 1,
      values: {},
    } as Parameters<typeof dmsService.importConfiguration>[0]);
    await dmsService.exportConfiguration("development");

    expect(get).toHaveBeenCalledWith(ENDPOINTS.FOLDERS.DETAIL("folder-id"));
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.FOLDERS.UPDATE("folder-id"), { sort_order: 2 });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.FOLDERS.MOVE("folder-id"), { parent_id: null });
    expect(deleteCall).toHaveBeenCalledWith(ENDPOINTS.FOLDERS.DELETE("folder-id"));
    expect(get).toHaveBeenCalledWith(ENDPOINTS.FOLDERS.CONTENTS("folder-id"));
    expect(get).toHaveBeenCalledWith(ENDPOINTS.DOCUMENTS.DETAIL("document-id"));
    expect(post).toHaveBeenCalledWith(ENDPOINTS.DOCUMENTS.MOVE("document-id"), { folder_id: null });
    expect(get).toHaveBeenCalledWith(`${ENDPOINTS.VERSIONS.LIST}?document_id=document-id&page=2`);
    expect(get).toHaveBeenCalledWith(ENDPOINTS.VERSIONS.DETAIL("version-id"));
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.PERMISSIONS.LIST}?document_id=document-id&page_size=100`
    );
    expect(post).toHaveBeenCalledWith(ENDPOINTS.PERMISSIONS.CREATE, {
      document_id: "document-id",
      principal_type: "user",
      principal_id: "actor-id",
      permission: "read",
    });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.PERMISSIONS.DETAIL("permission-id"));
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.PERMISSIONS.UPDATE("permission-id"), {
      permission: "write",
    });
    expect(deleteCall).toHaveBeenCalledWith(ENDPOINTS.PERMISSIONS.DELETE("permission-id"));
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.SHARES.LIST}?document_id=document-id&page_size=100`
    );
    expect(post).toHaveBeenCalledWith(ENDPOINTS.SHARES.CREATE, {
      document_id: "document-id",
      version_id: "version-id",
      expires_at: meta.timestamp,
      max_access_count: 3,
    });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.SHARES.DETAIL("share-id"));
    expect(post).toHaveBeenCalledWith(ENDPOINTS.SHARES.REVOKE("share-id"));
    expect(get).toHaveBeenCalledWith(ENDPOINTS.HEALTH);
    expect(get).toHaveBeenCalledWith(`${ENDPOINTS.CONFIGURATION.CURRENT}?environment=development`);
    expect(put).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.CURRENT, {
      environment: "development",
      values: {},
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.PREVIEW, {
      environment: "development",
      values: {},
    });
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.HISTORY}?environment=development&page=2`
    );
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.AUDIT}?environment=development&page=3`
    );
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.ROLLBACK, {
      version: 1,
      environment: "development",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.IMPORT, {
      schema_version: 1,
      module: "dms",
      environment: "development",
      version: 1,
      values: {},
    });
    expect(get).toHaveBeenCalledWith(`${ENDPOINTS.CONFIGURATION.EXPORT}?environment=development`);
  });

  it("normalizes governed denials into a discriminated module error", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("Denied", 403, {
        error: { code: "PERMISSION_DENIED", message: "Denied", correlation_id: "corr-denied" },
      })
    );
    const failure = await dmsService.getDocument("hidden").catch((error: Error) => error);
    expect(failure).toBeInstanceOf(DmsApiError);
    if (!(failure instanceof DmsApiError)) throw new Error("Expected normalized DMS error");
    expect(failure.problem).toEqual({
      kind: "denied",
      status: 403,
      message: "Denied",
      correlation_id: "corr-denied",
    });
  });

  it("preserves validation field errors, retry windows, and fallback unexpected errors", async () => {
    const get = vi.spyOn(apiClient, "get");
    get.mockRejectedValueOnce(
      new ApiError("Invalid", 422, {
        error: {
          code: "VALIDATION_ERROR",
          message: "Invalid",
          correlation_id: "corr-validation",
          detail: {
            field_errors: [
              { field: "name", code: "required", message: "Name is required" },
              { field: 42, code: "ignored", message: "Malformed field error" },
            ],
          },
        },
      })
    );
    get.mockRejectedValueOnce(
      new ApiError("Slow down", 429, {
        error: {
          code: "RATE_LIMITED",
          message: "Slow down",
          correlation_id: "corr-rate",
          detail: { retry_after_seconds: 30 },
        },
      })
    );
    get.mockRejectedValueOnce(new ApiError("Broken", 500, { error: { message: "missing code" } }));

    const validation = await dmsService.getDocument("bad").catch((error: Error) => error);
    const rateLimited = await dmsService.getDocument("busy").catch((error: Error) => error);
    const unexpected = await dmsService.getDocument("broken").catch((error: Error) => error);

    expect(validation).toBeInstanceOf(DmsApiError);
    expect(rateLimited).toBeInstanceOf(DmsApiError);
    expect(unexpected).toBeInstanceOf(DmsApiError);
    if (
      !(validation instanceof DmsApiError) ||
      !(rateLimited instanceof DmsApiError) ||
      !(unexpected instanceof DmsApiError)
    )
      throw new Error("Expected normalized DMS errors");
    expect(validation.problem).toMatchObject({
      kind: "validation",
      field_errors: [{ field: "name", code: "required", message: "Name is required" }],
      correlation_id: "corr-validation",
    });
    expect(rateLimited.problem).toMatchObject({
      kind: "rate_limited",
      retry_after_seconds: 30,
      correlation_id: "corr-rate",
    });
    expect(unexpected.problem).toEqual({
      kind: "unexpected",
      status: 500,
      message: "Broken",
      correlation_id: null,
    });
  });

  it("downloads with encoded version filters and governed filenames", async () => {
    const blob = new Blob(["policy"], { type: "application/pdf" });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(blob, {
        status: 200,
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''policy%202026.pdf",
          "Content-Type": "application/pdf",
        },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(dmsService.downloadDocument("document/1", "version/2")).resolves.toMatchObject({
      filename: "policy 2026.pdf",
      mime_type: "application/pdf",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v2/dms/documents/document%2F1/download/?version_id=version%2F2",
      { credentials: "include" }
    );
  });

  it("normalizes failed downloads without leaking transport response bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "OBJECT_STORAGE_DOWN",
              message: "Storage is down",
              correlation_id: "corr-download",
            },
          }),
          {
            status: 503,
            statusText: "Unavailable",
            headers: { "Content-Type": "application/json" },
          }
        )
      )
    );
    const failure = await dmsService
      .downloadPublicShare("token/unsafe")
      .catch((error: Error) => error);
    expect(failure).toBeInstanceOf(DmsApiError);
    if (!(failure instanceof DmsApiError)) throw new Error("Expected normalized DMS error");
    expect(failure.problem).toEqual({
      kind: "unavailable",
      status: 503,
      message: "Storage is down",
      correlation_id: "corr-download",
    });
  });
});
