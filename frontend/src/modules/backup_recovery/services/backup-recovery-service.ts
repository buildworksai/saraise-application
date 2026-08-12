/* eslint-disable @typescript-eslint/no-redundant-type-constituents, @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-return -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiV2Envelope,
  type ApiV2Page,
  type ArchiveFilters,
  type BackupArchive,
  type BackupJob,
  type BackupJobCancelRequest,
  type BackupJobCreate,
  type BackupJobFilters,
  type BackupJobRetryRequest,
  type BackupJobUpdate,
  type BackupRequestReceipt,
  type BackupRetentionPolicy,
  type BackupRetentionPolicyCreate,
  type BackupRetentionPolicyUpdate,
  type BackupSchedule,
  type BackupScheduleCreate,
  type BackupScheduleFilters,
  type BackupScheduleUpdate,
  type BackupStorageTarget,
  type BackupStorageTargetCreate,
  type BackupStorageTargetUpdate,
  type BackupVerification,
  type BackupVerificationCancelRequest,
  type BackupVerificationCreate,
  type GovernedError,
  type GovernedErrorEnvelope,
  type GovernedFieldError,
  type ModuleHealth,
  type PaginatedResult,
  type RetentionPolicyFilters,
  type RetentionPreview,
  type ScheduleRunNowRequest,
  type StorageTargetFilters,
  type StorageTargetProbeResult,
  type VerificationFilters,
} from "../contracts";

export class BackupRecoveryApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly fieldErrors: readonly GovernedFieldError[] = []
  ) {
    super(message);
    this.name = "BackupRecoveryApiError";
  }

  fieldError(field: string): string | undefined {
    return this.fieldErrors.find((item) => item.field === field)?.message;
  }

  get permissionDenied(): boolean {
    return this.status === 403;
  }
}

// `object` intentionally accepts closed DTO interfaces without requiring an
// unsafe string index signature; values are normalized through Object.entries.
type Filters = object;

function governedError(details: unknown): GovernedError | undefined {
  if (!details || typeof details !== "object" || !("error" in details)) return undefined;
  const candidate = (details as GovernedErrorEnvelope).error;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    return {
      code: "MALFORMED_ERROR_ENVELOPE",
      message: "The server returned a malformed error envelope.",
      detail: null,
      status: 502,
    };
  }
  return candidate;
}

function normalizeFieldErrors(
  errors: GovernedError["field_errors"] | unknown
): GovernedFieldError[] {
  if (!errors) return [];
  if (Array.isArray(errors)) return [...errors];
  if (typeof errors !== "object") return [];
  return Object.entries(errors as Record<string, unknown>).flatMap(([field, value]) => {
    const messages = Array.isArray(value) ? value : [value];
    return messages
      .filter((message): message is string => typeof message === "string")
      .map((message) => ({ field, message }));
  });
}

async function translate<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (failure) {
    if (!(failure instanceof ApiError)) throw failure;
    throw backupRecoveryErrorFromApiError(failure);
  }
}

function backupRecoveryErrorFromApiError(failure: ApiError): BackupRecoveryApiError {
  const error = governedError(failure.details);
  const detailMessage = typeof error?.detail === "string" ? error.detail : undefined;
  return new BackupRecoveryApiError(
    detailMessage ?? error?.message ?? failure.message,
    error?.status ?? failure.status,
    error?.code ?? failure.code ?? "REQUEST_FAILED",
    error?.correlation_id ?? failure.correlationId ?? null,
    normalizeFieldErrors(error?.field_errors ?? error?.detail)
  );
}

export function serializeFilters(filters: Filters = {}): string {
  const params = new URLSearchParams();
  Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([key, value]) => params.set(key, String(value)));
  return params.toString();
}

function withFilters(path: string, filters: Filters = {}): string {
  const query = serializeFilters(filters);
  return query ? `${path}?${query}` : path;
}

export function normalizeFilters<T extends Filters>(
  filters: T = {} as T
): Readonly<Record<string, string>> {
  return Object.fromEntries(new URLSearchParams(serializeFilters(filters)).entries());
}

async function unwrap<T>(request: Promise<ApiV2Envelope<T>>): Promise<T> {
  const response = await translate(request);
  if (!response || typeof response !== "object" || !("data" in response)) {
    throw new BackupRecoveryApiError(
      "The server returned an invalid response envelope.",
      502,
      "MALFORMED_RESPONSE",
      null
    );
  }
  return response.data;
}

function isDependencyHealth(candidate: unknown): boolean {
  return (
    Boolean(candidate) &&
    typeof candidate === "object" &&
    typeof (candidate as Partial<ModuleHealth["database"]>).key === "string" &&
    ["healthy", "degraded", "unavailable"].includes(
      String((candidate as Partial<ModuleHealth["database"]>).status)
    ) &&
    typeof (candidate as Partial<ModuleHealth["database"]>).critical === "boolean"
  );
}

function isModuleHealth(candidate: unknown): candidate is ModuleHealth {
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return false;
  const health = candidate as Partial<ModuleHealth>;
  return (
    ["healthy", "degraded", "unavailable"].includes(String(health.status)) &&
    typeof health.ready === "boolean" &&
    typeof health.checked_at === "string" &&
    isDependencyHealth(health.database) &&
    isDependencyHealth(health.async_jobs) &&
    isDependencyHealth(health.outbox) &&
    isDependencyHealth(health.scheduler) &&
    Array.isArray(health.adapters) &&
    health.adapters.every(isDependencyHealth)
  );
}

async function unwrapHealth(request: Promise<ApiV2Envelope<ModuleHealth>>): Promise<ModuleHealth> {
  try {
    const response = await request;
    if (!response || typeof response !== "object" || !("data" in response)) {
      throw new BackupRecoveryApiError(
        "The server returned an invalid response envelope.",
        502,
        "MALFORMED_RESPONSE",
        null
      );
    }
    return response.data;
  } catch (failure) {
    if (failure instanceof ApiError && failure.status === 503 && isModuleHealth(failure.details)) {
      return failure.details;
    }
    if (failure instanceof ApiError) throw backupRecoveryErrorFromApiError(failure);
    throw failure;
  }
}

async function unwrapPage<T>(request: Promise<ApiV2Page<T>>): Promise<PaginatedResult<T>> {
  const response = await translate(request);
  if (!Array.isArray(response?.data) || !response.meta?.pagination) {
    throw new BackupRecoveryApiError(
      "The server returned an invalid paginated response.",
      502,
      "MALFORMED_RESPONSE",
      response?.meta?.correlation_id ?? null
    );
  }
  return {
    items: response.data,
    pagination: response.meta.pagination,
    correlationId: response.meta.correlation_id,
  };
}

function action<T>(path: string, body: object = {}) {
  return unwrap(apiClient.post<ApiV2Envelope<T>>(path, body));
}

class BackupRecoveryQueryKeys {
  root(tenantId: string | null) {
    return ["backup-recovery", tenantId ?? "no-tenant"] as const;
  }

  health(tenantId: string | null) {
    return [...this.root(tenantId), "health"] as const;
  }

  jobs(tenantId: string | null, filters: BackupJobFilters = {}) {
    return [...this.root(tenantId), "jobs", normalizeFilters(filters)] as const;
  }

  job(tenantId: string | null, id: string) {
    return [...this.root(tenantId), "job", id] as const;
  }

  schedules(tenantId: string | null, filters: BackupScheduleFilters = {}) {
    return [...this.root(tenantId), "schedules", normalizeFilters(filters)] as const;
  }

  schedule(tenantId: string | null, id: string) {
    return [...this.root(tenantId), "schedule", id] as const;
  }

  policies(tenantId: string | null, filters: RetentionPolicyFilters = {}) {
    return [...this.root(tenantId), "policies", normalizeFilters(filters)] as const;
  }

  policy(tenantId: string | null, id: string) {
    return [...this.root(tenantId), "policy", id] as const;
  }

  policyPreview(tenantId: string | null, id: string, capturedAt: string) {
    return [...this.policy(tenantId, id), "preview", capturedAt] as const;
  }

  targets(tenantId: string | null, filters: StorageTargetFilters = {}) {
    return [...this.root(tenantId), "targets", normalizeFilters(filters)] as const;
  }

  target(tenantId: string | null, id: string) {
    return [...this.root(tenantId), "target", id] as const;
  }

  archives(tenantId: string | null, filters: ArchiveFilters = {}) {
    return [...this.root(tenantId), "archives", normalizeFilters(filters)] as const;
  }

  archive(tenantId: string | null, id: string) {
    return [...this.root(tenantId), "archive", id] as const;
  }

  verifications(tenantId: string | null, filters: VerificationFilters = {}) {
    return [...this.root(tenantId), "verifications", normalizeFilters(filters)] as const;
  }

  verification(tenantId: string | null, id: string) {
    return [...this.root(tenantId), "verification", id] as const;
  }
}

export const backupRecoveryQueryKeys = new BackupRecoveryQueryKeys();

class BackupRecoveryService {
  health() {
    return unwrapHealth(apiClient.get<ApiV2Envelope<ModuleHealth>>(ENDPOINTS.HEALTH));
  }

  listBackupJobs(filters: BackupJobFilters = {}) {
    return unwrapPage(
      apiClient.get<ApiV2Page<BackupJob>>(withFilters(ENDPOINTS.JOBS.LIST, filters))
    );
  }

  getBackupJob(id: string) {
    return unwrap(apiClient.get<ApiV2Envelope<BackupJob>>(ENDPOINTS.JOBS.DETAIL(id)));
  }

  createBackupJob(data: BackupJobCreate) {
    return unwrap(apiClient.post<ApiV2Envelope<BackupRequestReceipt>>(ENDPOINTS.JOBS.CREATE, data));
  }

  updateBackupJob(id: string, data: BackupJobUpdate) {
    return unwrap(apiClient.patch<ApiV2Envelope<BackupJob>>(ENDPOINTS.JOBS.UPDATE(id), data));
  }

  deleteBackupJob(id: string) {
    return translate(apiClient.delete<void>(ENDPOINTS.JOBS.DELETE(id)));
  }

  cancelBackupJob(id: string, data: BackupJobCancelRequest) {
    return action<BackupJob>(ENDPOINTS.JOBS.CANCEL(id), data);
  }

  retryBackupJob(id: string, data: BackupJobRetryRequest) {
    return action<BackupRequestReceipt>(ENDPOINTS.JOBS.RETRY(id), data);
  }

  listBackupSchedules(filters: BackupScheduleFilters = {}) {
    return unwrapPage(
      apiClient.get<ApiV2Page<BackupSchedule>>(withFilters(ENDPOINTS.SCHEDULES.LIST, filters))
    );
  }

  getBackupSchedule(id: string) {
    return unwrap(apiClient.get<ApiV2Envelope<BackupSchedule>>(ENDPOINTS.SCHEDULES.DETAIL(id)));
  }

  createBackupSchedule(data: BackupScheduleCreate) {
    return unwrap(apiClient.post<ApiV2Envelope<BackupSchedule>>(ENDPOINTS.SCHEDULES.CREATE, data));
  }

  updateBackupSchedule(id: string, data: BackupScheduleUpdate) {
    return unwrap(
      apiClient.patch<ApiV2Envelope<BackupSchedule>>(ENDPOINTS.SCHEDULES.UPDATE(id), data)
    );
  }

  deleteBackupSchedule(id: string) {
    return translate(apiClient.delete<void>(ENDPOINTS.SCHEDULES.DELETE(id)));
  }

  activateBackupSchedule(id: string) {
    return action<BackupSchedule>(ENDPOINTS.SCHEDULES.ACTIVATE(id));
  }

  deactivateBackupSchedule(id: string) {
    return action<BackupSchedule>(ENDPOINTS.SCHEDULES.DEACTIVATE(id));
  }

  runBackupScheduleNow(id: string, data: ScheduleRunNowRequest) {
    return action<BackupRequestReceipt>(ENDPOINTS.SCHEDULES.RUN_NOW(id), data);
  }

  listRetentionPolicies(filters: RetentionPolicyFilters = {}) {
    return unwrapPage(
      apiClient.get<ApiV2Page<BackupRetentionPolicy>>(
        withFilters(ENDPOINTS.RETENTION_POLICIES.LIST, filters)
      )
    );
  }

  getRetentionPolicy(id: string) {
    return unwrap(
      apiClient.get<ApiV2Envelope<BackupRetentionPolicy>>(ENDPOINTS.RETENTION_POLICIES.DETAIL(id))
    );
  }

  createRetentionPolicy(data: BackupRetentionPolicyCreate) {
    return unwrap(
      apiClient.post<ApiV2Envelope<BackupRetentionPolicy>>(
        ENDPOINTS.RETENTION_POLICIES.CREATE,
        data
      )
    );
  }

  updateRetentionPolicy(id: string, data: BackupRetentionPolicyUpdate) {
    return unwrap(
      apiClient.patch<ApiV2Envelope<BackupRetentionPolicy>>(
        ENDPOINTS.RETENTION_POLICIES.UPDATE(id),
        data
      )
    );
  }

  deleteRetentionPolicy(id: string) {
    return translate(apiClient.delete<void>(ENDPOINTS.RETENTION_POLICIES.DELETE(id)));
  }

  activateRetentionPolicy(id: string) {
    return action<BackupRetentionPolicy>(ENDPOINTS.RETENTION_POLICIES.ACTIVATE(id));
  }

  deactivateRetentionPolicy(id: string) {
    return action<BackupRetentionPolicy>(ENDPOINTS.RETENTION_POLICIES.DEACTIVATE(id));
  }

  previewRetentionPolicy(id: string, capturedAt: string) {
    return unwrap(
      apiClient.get<ApiV2Envelope<RetentionPreview>>(
        withFilters(ENDPOINTS.RETENTION_POLICIES.PREVIEW(id), { captured_at: capturedAt })
      )
    );
  }

  listStorageTargets(filters: StorageTargetFilters = {}) {
    return unwrapPage(
      apiClient.get<ApiV2Page<BackupStorageTarget>>(
        withFilters(ENDPOINTS.STORAGE_TARGETS.LIST, filters)
      )
    );
  }

  getStorageTarget(id: string) {
    return unwrap(
      apiClient.get<ApiV2Envelope<BackupStorageTarget>>(ENDPOINTS.STORAGE_TARGETS.DETAIL(id))
    );
  }

  createStorageTarget(data: BackupStorageTargetCreate) {
    return unwrap(
      apiClient.post<ApiV2Envelope<BackupStorageTarget>>(ENDPOINTS.STORAGE_TARGETS.CREATE, data)
    );
  }

  updateStorageTarget(id: string, data: BackupStorageTargetUpdate) {
    return unwrap(
      apiClient.patch<ApiV2Envelope<BackupStorageTarget>>(
        ENDPOINTS.STORAGE_TARGETS.UPDATE(id),
        data
      )
    );
  }

  deleteStorageTarget(id: string) {
    return translate(apiClient.delete<void>(ENDPOINTS.STORAGE_TARGETS.DELETE(id)));
  }

  activateStorageTarget(id: string) {
    return action<BackupStorageTarget>(ENDPOINTS.STORAGE_TARGETS.ACTIVATE(id));
  }

  deactivateStorageTarget(id: string) {
    return action<BackupStorageTarget>(ENDPOINTS.STORAGE_TARGETS.DEACTIVATE(id));
  }

  setDefaultStorageTarget(id: string) {
    return action<BackupStorageTarget>(ENDPOINTS.STORAGE_TARGETS.SET_DEFAULT(id));
  }

  probeStorageTarget(id: string) {
    return action<StorageTargetProbeResult>(ENDPOINTS.STORAGE_TARGETS.PROBE(id));
  }

  listBackupArchives(filters: ArchiveFilters = {}) {
    return unwrapPage(
      apiClient.get<ApiV2Page<BackupArchive>>(withFilters(ENDPOINTS.ARCHIVES.LIST, filters))
    );
  }

  getBackupArchive(id: string) {
    return unwrap(apiClient.get<ApiV2Envelope<BackupArchive>>(ENDPOINTS.ARCHIVES.DETAIL(id)));
  }

  requestArchiveVerification(id: string, data: BackupVerificationCreate) {
    return action<BackupVerification>(ENDPOINTS.ARCHIVES.VERIFY(id), data);
  }

  listBackupVerifications(filters: VerificationFilters = {}) {
    return unwrapPage(
      apiClient.get<ApiV2Page<BackupVerification>>(
        withFilters(ENDPOINTS.VERIFICATIONS.LIST, filters)
      )
    );
  }

  getBackupVerification(id: string) {
    return unwrap(
      apiClient.get<ApiV2Envelope<BackupVerification>>(ENDPOINTS.VERIFICATIONS.DETAIL(id))
    );
  }

  cancelBackupVerification(id: string, data: BackupVerificationCancelRequest) {
    return action<BackupVerification>(ENDPOINTS.VERIFICATIONS.CANCEL(id), data);
  }
}

export const backupRecoveryService = new BackupRecoveryService();

export function newIdempotencyKey(operation: string): string {
  return `${operation}:${crypto.randomUUID()}`;
}
