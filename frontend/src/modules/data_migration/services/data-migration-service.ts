import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiEnvelope,
  type CancelRunRequest,
  type ConnectionTestResult,
  type DefinitionDiff,
  type ExportDefinitionPayload,
  type ExternalConnection,
  type ExternalConnectionCreate,
  type ExternalConnectionUpdate,
  type ImportDefinitionPayload,
  type ImportDefinitionResult,
  type InspectRequest,
  type IssueFilters,
  type JobFilters,
  type MappingSuggestion,
  type MigrationJob,
  type MigrationJobCreate,
  type MigrationJobUpdate,
  type MigrationJobVersion,
  type MigrationMapping,
  type MigrationMappingCreate,
  type MigrationMappingUpdate,
  type MigrationRollback,
  type MigrationRun,
  type MigrationRunIssue,
  type PageFilters,
  type PaginatedResult,
  type PreviewResult,
  type RestoreVersionRequest,
  type RollbackRequest,
  type RuleReorderPayload,
  type RunFilters,
  type RunRequest,
  type SourceProfile,
  type AsyncOperationAccepted,
  type ValidationRule,
  type ValidationRuleCreate,
  type ValidationRuleUpdate,
  type MappingReorderPayload,
  type ConfigurationDiff,
  type ConfigurationExportDocument,
  type ConfigurationImportPayload,
  type ConfigurationPreviewResponse,
  type DataMigrationConfiguration,
  type DataMigrationConfigurationUpdate,
  type DataMigrationConfigurationVersion,
} from '../contracts';

export class DataMigrationApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = 'DataMigrationApiError';
  }
}

async function request<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    throw new DataMigrationApiError(
      error.message,
      error.status,
      error.code ?? 'request_failed',
      error.correlationId ?? null,
      error.status === 408 || error.status === 409 || error.status === 429 || error.status >= 500,
    );
  }
}

function withQuery(path: string, filters: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `${path}?${encoded}` : path;
}

async function unwrap<T>(operation: () => Promise<ApiEnvelope<T>>): Promise<T> {
  return (await request(operation)).data;
}

async function page<T>(operation: () => Promise<ApiEnvelope<readonly T[]>>): Promise<PaginatedResult<T>> {
  const envelope = await request(operation);
  if (!envelope.meta.pagination) {
    throw new DataMigrationApiError('The server omitted required pagination evidence.', 502, 'invalid_response', envelope.meta.correlation_id, false);
  }
  return { items: envelope.data, pagination: envelope.meta.pagination, correlationId: envelope.meta.correlation_id };
}

function idempotencyHeaders(key: string): RequestInit {
  return { headers: { 'Idempotency-Key': key } };
}

export const dataMigrationService = {
  jobs: {
    list: (filters: JobFilters = {}) => page(() => apiClient.get<ApiEnvelope<readonly MigrationJob[]>>(withQuery(ENDPOINTS.JOBS.LIST, filters))),
    get: (id: string) => unwrap(() => apiClient.get<ApiEnvelope<MigrationJob>>(ENDPOINTS.JOBS.DETAIL(id))),
    create: (payload: MigrationJobCreate) => unwrap(() => apiClient.post<ApiEnvelope<MigrationJob>>(ENDPOINTS.JOBS.CREATE, payload)),
    update: (id: string, payload: MigrationJobUpdate) => unwrap(() => apiClient.patch<ApiEnvelope<MigrationJob>>(ENDPOINTS.JOBS.DETAIL(id), payload)),
    delete: (id: string) => request(() => apiClient.delete<void>(ENDPOINTS.JOBS.DETAIL(id))),
    validate: (id: string) => unwrap(() => apiClient.post<ApiEnvelope<MigrationJob>>(ENDPOINTS.JOBS.VALIDATE(id))),
    archive: (id: string, transitionKey: string) => unwrap(() => apiClient.post<ApiEnvelope<MigrationJob>>(ENDPOINTS.JOBS.ARCHIVE(id), { transition_key: transitionKey })),
    restore: (id: string) => unwrap(() => apiClient.post<ApiEnvelope<MigrationJob>>(ENDPOINTS.JOBS.RESTORE(id))),
    attachSource: (id: string, sourceArtifactId: string, expectedVersion: number) => unwrap(() => apiClient.post<ApiEnvelope<MigrationJob>>(ENDPOINTS.JOBS.SOURCE(id), { source_artifact_id: sourceArtifactId, expected_version: expectedVersion })),
    inspect: (id: string, payload: InspectRequest) => unwrap(() => apiClient.post<ApiEnvelope<AsyncOperationAccepted>>(ENDPOINTS.JOBS.INSPECT(id), {}, idempotencyHeaders(payload.idempotency_key))),
    preview: (id: string, limit = 25) => unwrap(() => apiClient.get<ApiEnvelope<PreviewResult>>(withQuery(ENDPOINTS.JOBS.PREVIEW(id), { limit }))),
    export: (id: string) => unwrap(() => apiClient.get<ApiEnvelope<ExportDefinitionPayload>>(ENDPOINTS.JOBS.EXPORT(id))),
    import: (payload: ImportDefinitionPayload) => unwrap(() => apiClient.post<ApiEnvelope<ImportDefinitionResult>>(ENDPOINTS.JOBS.IMPORT, payload)),
    versions: (id: string, filters: PageFilters = {}) => page(() => apiClient.get<ApiEnvelope<readonly MigrationJobVersion[]>>(withQuery(ENDPOINTS.JOBS.VERSIONS(id), filters))),
    restoreVersion: (id: string, version: number, payload: RestoreVersionRequest) => unwrap(() => apiClient.post<ApiEnvelope<MigrationJob>>(ENDPOINTS.JOBS.RESTORE_VERSION(id, version), payload)),
  },
  mappings: {
    list: (jobId: string, filters: PageFilters = {}) => page(() => apiClient.get<ApiEnvelope<readonly MigrationMapping[]>>(withQuery(ENDPOINTS.JOBS.MAPPINGS(jobId), filters))),
    get: (id: string) => unwrap(() => apiClient.get<ApiEnvelope<MigrationMapping>>(ENDPOINTS.MAPPINGS.DETAIL(id))),
    create: (jobId: string, payload: MigrationMappingCreate) => unwrap(() => apiClient.post<ApiEnvelope<MigrationMapping>>(ENDPOINTS.JOBS.MAPPINGS(jobId), payload)),
    update: (id: string, payload: MigrationMappingUpdate) => unwrap(() => apiClient.patch<ApiEnvelope<MigrationMapping>>(ENDPOINTS.MAPPINGS.DETAIL(id), payload)),
    delete: (id: string) => request(() => apiClient.delete<void>(ENDPOINTS.MAPPINGS.DETAIL(id))),
    reorder: (jobId: string, payload: MappingReorderPayload) => unwrap(() => apiClient.post<ApiEnvelope<readonly MigrationMapping[]>>(ENDPOINTS.JOBS.MAPPINGS(jobId), { action: 'reorder', ...payload })),
    suggest: (jobId: string, provider: 'deterministic' | 'extension' = 'deterministic') => unwrap(() => apiClient.post<ApiEnvelope<readonly MappingSuggestion[]>>(ENDPOINTS.JOBS.SUGGEST_MAPPINGS(jobId), { provider })),
    apply: (jobId: string, suggestionIds: readonly string[]) => unwrap(() => apiClient.post<ApiEnvelope<readonly MigrationMapping[]>>(ENDPOINTS.JOBS.APPLY_MAPPINGS(jobId), { suggestion_ids: suggestionIds })),
  },
  rules: {
    list: (jobId: string, filters: PageFilters = {}) => page(() => apiClient.get<ApiEnvelope<readonly ValidationRule[]>>(withQuery(ENDPOINTS.JOBS.RULES(jobId), filters))),
    get: (id: string) => unwrap(() => apiClient.get<ApiEnvelope<ValidationRule>>(ENDPOINTS.RULES.DETAIL(id))),
    create: (jobId: string, payload: ValidationRuleCreate) => unwrap(() => apiClient.post<ApiEnvelope<ValidationRule>>(ENDPOINTS.JOBS.RULES(jobId), payload)),
    update: (id: string, payload: ValidationRuleUpdate) => unwrap(() => apiClient.patch<ApiEnvelope<ValidationRule>>(ENDPOINTS.RULES.DETAIL(id), payload)),
    delete: (id: string) => request(() => apiClient.delete<void>(ENDPOINTS.RULES.DETAIL(id))),
    reorder: (jobId: string, payload: RuleReorderPayload) => unwrap(() => apiClient.post<ApiEnvelope<readonly ValidationRule[]>>(ENDPOINTS.JOBS.RULES(jobId), { action: 'reorder', ...payload })),
  },
  runs: {
    list: (jobId: string, filters: RunFilters = {}) => page(() => apiClient.get<ApiEnvelope<readonly MigrationRun[]>>(withQuery(ENDPOINTS.JOBS.RUNS(jobId), filters))),
    get: (id: string) => unwrap(() => apiClient.get<ApiEnvelope<MigrationRun>>(ENDPOINTS.RUNS.DETAIL(id))),
    start: (jobId: string, payload: RunRequest) => unwrap(() => apiClient.post<ApiEnvelope<MigrationRun>>(ENDPOINTS.JOBS.RUNS(jobId), {}, idempotencyHeaders(payload.idempotency_key))),
    dryRun: (jobId: string, payload: RunRequest) => unwrap(() => apiClient.post<ApiEnvelope<MigrationRun>>(ENDPOINTS.JOBS.DRY_RUNS(jobId), {}, idempotencyHeaders(payload.idempotency_key))),
    cancel: (id: string, payload: CancelRunRequest) => unwrap(() => apiClient.post<ApiEnvelope<MigrationRun>>(ENDPOINTS.RUNS.CANCEL(id), payload)),
    issues: (id: string, filters: IssueFilters = {}) => page(() => apiClient.get<ApiEnvelope<readonly MigrationRunIssue[]>>(withQuery(ENDPOINTS.RUNS.ISSUES(id), filters))),
    exportIssuesUrl: (id: string) => ENDPOINTS.RUNS.EXPORT_ISSUES(id),
  },
  rollbacks: {
    request: (runId: string, payload: RollbackRequest) => unwrap(() => apiClient.post<ApiEnvelope<MigrationRollback>>(ENDPOINTS.RUNS.ROLLBACK(runId), {}, idempotencyHeaders(payload.idempotency_key))),
    get: (id: string) => unwrap(() => apiClient.get<ApiEnvelope<MigrationRollback>>(ENDPOINTS.ROLLBACKS.DETAIL(id))),
  },
  connections: {
    list: (filters: PageFilters = {}) => page(() => apiClient.get<ApiEnvelope<readonly ExternalConnection[]>>(withQuery(ENDPOINTS.CONNECTIONS.LIST, filters))),
    get: (id: string) => unwrap(() => apiClient.get<ApiEnvelope<ExternalConnection>>(ENDPOINTS.CONNECTIONS.DETAIL(id))),
    create: (payload: ExternalConnectionCreate) => unwrap(() => apiClient.post<ApiEnvelope<ExternalConnection>>(ENDPOINTS.CONNECTIONS.CREATE, payload)),
    update: (id: string, payload: ExternalConnectionUpdate) => unwrap(() => apiClient.patch<ApiEnvelope<ExternalConnection>>(ENDPOINTS.CONNECTIONS.DETAIL(id), payload)),
    rotateCredential: (id: string, credentialRef: string) => unwrap(() => apiClient.patch<ApiEnvelope<ExternalConnection>>(ENDPOINTS.CONNECTIONS.DETAIL(id), { credential_ref: credentialRef })),
    deactivate: (id: string) => unwrap(() => apiClient.post<ApiEnvelope<ExternalConnection>>(ENDPOINTS.CONNECTIONS.DEACTIVATE(id))),
    test: (id: string) => unwrap(() => apiClient.post<ApiEnvelope<ConnectionTestResult>>(ENDPOINTS.CONNECTIONS.TEST(id))),
  },
  configuration: {
    get: () => unwrap(() => apiClient.get<ApiEnvelope<DataMigrationConfiguration>>(ENDPOINTS.CONFIGURATION.DETAIL)),
    update: (payload: DataMigrationConfigurationUpdate) => unwrap(() => apiClient.patch<ApiEnvelope<DataMigrationConfiguration>>(ENDPOINTS.CONFIGURATION.DETAIL, payload)),
    preview: async (payload: DataMigrationConfigurationUpdate): Promise<ConfigurationDiff> => {
      const { expected_version: expectedVersion, ...values } = payload;
      void expectedVersion;
      return unwrap(() => apiClient.post<ApiEnvelope<ConfigurationPreviewResponse>>(ENDPOINTS.CONFIGURATION.PREVIEW, values));
    },
    versions: (filters: PageFilters = {}) => page(() => apiClient.get<ApiEnvelope<readonly DataMigrationConfigurationVersion[]>>(withQuery(ENDPOINTS.CONFIGURATION.VERSIONS, filters))),
    restore: (version: number, expectedVersion: number) => unwrap(() => apiClient.post<ApiEnvelope<DataMigrationConfiguration>>(ENDPOINTS.CONFIGURATION.RESTORE(version), { expected_version: expectedVersion })),
    export: () => unwrap(() => apiClient.get<ApiEnvelope<ConfigurationExportDocument>>(ENDPOINTS.CONFIGURATION.EXPORT)),
    import: (payload: ConfigurationImportPayload) => unwrap(() => apiClient.post<ApiEnvelope<DataMigrationConfiguration>>(ENDPOINTS.CONFIGURATION.IMPORT, payload)),
  },
  definitionDiff: (current: ExportDefinitionPayload, proposed: ExportDefinitionPayload): DefinitionDiff => {
    const entries: Array<DefinitionDiff['entries'][number]> = [];
    if (current.checksum !== proposed.checksum) entries.push({ path: 'checksum', operation: 'replace', before: current.checksum, after: proposed.checksum });
    if (current.job.name !== proposed.job.name) entries.push({ path: 'job.name', operation: 'replace', before: current.job.name, after: proposed.job.name });
    if (current.job.target_adapter !== proposed.job.target_adapter) entries.push({ path: 'job.target_adapter', operation: 'replace', before: current.job.target_adapter, after: proposed.job.target_adapter });
    if (current.mappings.length !== proposed.mappings.length) entries.push({ path: 'mappings', operation: 'replace', before: current.mappings.length, after: proposed.mappings.length });
    if (current.rules.length !== proposed.rules.length) entries.push({ path: 'rules', operation: 'replace', before: current.rules.length, after: proposed.rules.length });
    return { from_version: null, to_version: null, entries, warnings: [] };
  },
};

export const migrationService = dataMigrationService;
