import { apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiEnvelope,
  type DynamicResourceCreate,
  type DynamicResourceDetail,
  type DynamicResourceFilters,
  type DynamicResourcePatch,
  type DynamicResourceReplace,
  type DynamicResourceSummary,
  type DynamicResourceVersion,
  type EntityDefinitionCreate,
  type EntityDefinitionDetail,
  type EntityDefinitionFilters,
  type EntityDefinitionSummary,
  type EntityDefinitionUpdate,
  type EntitySchemaVersionDetail,
  type EntitySchemaVersionSummary,
  type ExportDocument,
  type ImportRequest,
  type ImportValidationResult,
  type JSONValue,
  type NamingSequence,
  type NamingSequenceFilters,
  type OperationResult,
  type PaginatedResult,
  type PreviewResult,
  type SchemaCandidateCreate,
  type SchemaDiff,
  type SchemaValidationReport,
  type ConfigurationExportDocument,
  type ConfigurationImportRequest,
  type ConfigurationPreview,
  type ConfigurationVersion,
  type MetadataEnvironment,
  type MetadataModelingConfiguration,
  type MetadataModelingConfigurationValues,
} from "../contracts";

type QueryValue = string | number | boolean | undefined;
type Query = Readonly<Record<string, QueryValue>>;

function withQuery(path: string, query: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const encoded = params.toString();
  return encoded ? `${path}?${encoded}` : path;
}

function unwrap<T>(envelope: ApiEnvelope<T>): T { return envelope.data; }
function unwrapPage<T>(envelope: ApiEnvelope<readonly T[]>): PaginatedResult<T> {
  if (!envelope.meta.pagination) throw new Error("Governed paginated response omitted pagination metadata.");
  return { items: envelope.data, pagination: envelope.meta.pagination, correlationId: envelope.meta.correlation_id };
}
function idempotencyHeaders(key: string): HeadersInit { return { "Idempotency-Key": key }; }
function lockHeaders(lockVersion: number): HeadersInit { return { "If-Match": String(lockVersion) }; }

export const metadataModelingService = Object.freeze({
  async listDefinitions(filters: EntityDefinitionFilters = {}): Promise<PaginatedResult<EntityDefinitionSummary>> {
    const result = await apiClient.get<ApiEnvelope<readonly EntityDefinitionSummary[]>>(withQuery(ENDPOINTS.entityDefinitions, filters));
    return unwrapPage(result);
  },
  async getDefinition(id: string): Promise<EntityDefinitionDetail> { return unwrap(await apiClient.get<ApiEnvelope<EntityDefinitionDetail>>(ENDPOINTS.entityDefinition(id))); },
  async createDefinition(payload: EntityDefinitionCreate, idempotencyKey: string): Promise<EntityDefinitionDetail> { return unwrap(await apiClient.post<ApiEnvelope<EntityDefinitionDetail>>(ENDPOINTS.entityDefinitions, payload, { headers: idempotencyHeaders(idempotencyKey) })); },
  async updateDefinition(id: string, payload: EntityDefinitionUpdate, lockVersion: number, partial = true): Promise<EntityDefinitionDetail> {
    const request = partial ? apiClient.patch<ApiEnvelope<EntityDefinitionDetail>>(ENDPOINTS.entityDefinition(id), payload, { headers: lockHeaders(lockVersion) }) : apiClient.put<ApiEnvelope<EntityDefinitionDetail>>(ENDPOINTS.entityDefinition(id), payload, { headers: lockHeaders(lockVersion) });
    return unwrap(await request);
  },
  async deleteDefinition(id: string): Promise<OperationResult> { return unwrap(await apiClient.delete<ApiEnvelope<OperationResult>>(ENDPOINTS.entityDefinition(id))); },
  async archiveDefinition(id: string, key: string): Promise<EntityDefinitionDetail> { return unwrap(await apiClient.post<ApiEnvelope<EntityDefinitionDetail>>(ENDPOINTS.archiveEntityDefinition(id), {}, { headers: idempotencyHeaders(key) })); },
  async restoreDefinition(id: string, key: string): Promise<EntityDefinitionDetail> { return unwrap(await apiClient.post<ApiEnvelope<EntityDefinitionDetail>>(ENDPOINTS.restoreEntityDefinition(id), {}, { headers: idempotencyHeaders(key) })); },
  async cloneDefinition(id: string, code: string, name: string): Promise<EntityDefinitionDetail> { return unwrap(await apiClient.post<ApiEnvelope<EntityDefinitionDetail>>(ENDPOINTS.cloneEntityDefinition(id), { code, name })); },
  async previewDefinition(id: string, candidateSchema: readonly SchemaCandidateCreate["fields"][number][], sampleData?: Readonly<Record<string, JSONValue>>): Promise<PreviewResult> { return unwrap(await apiClient.post<ApiEnvelope<PreviewResult>>(ENDPOINTS.previewEntityDefinition(id), { candidate_schema: candidateSchema, sample_data: sampleData })); },
  async previewNewDefinition(payload: EntityDefinitionCreate, fields: SchemaCandidateCreate["fields"]): Promise<PreviewResult> { return unwrap(await apiClient.post<ApiEnvelope<PreviewResult>>(ENDPOINTS.previewNewEntityDefinition, { entity: payload, candidate_schema: fields })); },
  async exportDefinition(id: string): Promise<ExportDocument> { return unwrap(await apiClient.get<ApiEnvelope<ExportDocument>>(ENDPOINTS.exportEntityDefinition(id))); },
  async importDefinition(payload: ImportRequest, key: string): Promise<EntityDefinitionDetail | ImportValidationResult> { return unwrap(await apiClient.post<ApiEnvelope<EntityDefinitionDetail | ImportValidationResult>>(ENDPOINTS.importEntityDefinition, payload, { headers: idempotencyHeaders(key) })); },
  async listVersions(id: string, page = 1): Promise<PaginatedResult<EntitySchemaVersionSummary>> { return unwrapPage(await apiClient.get<ApiEnvelope<readonly EntitySchemaVersionSummary[]>>(withQuery(ENDPOINTS.schemaVersions(id), { page }))); },
  async getVersion(id: string, versionId: string): Promise<EntitySchemaVersionDetail> { return unwrap(await apiClient.get<ApiEnvelope<EntitySchemaVersionDetail>>(ENDPOINTS.schemaVersion(id, versionId))); },
  async createCandidate(id: string, payload: SchemaCandidateCreate): Promise<EntitySchemaVersionDetail> { return unwrap(await apiClient.post<ApiEnvelope<EntitySchemaVersionDetail>>(ENDPOINTS.schemaVersions(id), payload)); },
  async validateCandidate(id: string, versionId: string): Promise<SchemaValidationReport> { return unwrap(await apiClient.post<ApiEnvelope<SchemaValidationReport>>(ENDPOINTS.validateSchemaVersion(id, versionId), {})); },
  async diffVersions(id: string, from: string, to: string): Promise<SchemaDiff> { return unwrap(await apiClient.get<ApiEnvelope<SchemaDiff>>(withQuery(ENDPOINTS.diffSchemaVersions(id), { from, to }))); },
  async publishCandidate(id: string, versionId: string, key: string): Promise<EntitySchemaVersionDetail> { return unwrap(await apiClient.post<ApiEnvelope<EntitySchemaVersionDetail>>(ENDPOINTS.publishSchemaVersion(id, versionId), {}, { headers: idempotencyHeaders(key) })); },
  async rejectCandidate(id: string, versionId: string, reason: string): Promise<EntitySchemaVersionDetail> { return unwrap(await apiClient.post<ApiEnvelope<EntitySchemaVersionDetail>>(ENDPOINTS.rejectSchemaVersion(id, versionId), { reason })); },
  async rollbackVersion(id: string, versionId: string, key: string): Promise<EntitySchemaVersionDetail> { return unwrap(await apiClient.post<ApiEnvelope<EntitySchemaVersionDetail>>(ENDPOINTS.rollbackSchemaVersion(id, versionId), {}, { headers: idempotencyHeaders(key) })); },
  async listResources(filters: DynamicResourceFilters = {}): Promise<PaginatedResult<DynamicResourceSummary>> { return unwrapPage(await apiClient.get<ApiEnvelope<readonly DynamicResourceSummary[]>>(withQuery(ENDPOINTS.resources, filters))); },
  async getResource(id: string): Promise<DynamicResourceDetail> { return unwrap(await apiClient.get<ApiEnvelope<DynamicResourceDetail>>(ENDPOINTS.resource(id))); },
  async createResource(payload: DynamicResourceCreate, key: string): Promise<DynamicResourceDetail> { return unwrap(await apiClient.post<ApiEnvelope<DynamicResourceDetail>>(ENDPOINTS.resources, payload, { headers: idempotencyHeaders(key) })); },
  async replaceResource(id: string, payload: DynamicResourceReplace, lockVersion: number): Promise<DynamicResourceDetail> { return unwrap(await apiClient.put<ApiEnvelope<DynamicResourceDetail>>(ENDPOINTS.resource(id), payload, { headers: lockHeaders(lockVersion) })); },
  async patchResource(id: string, payload: DynamicResourcePatch, lockVersion: number): Promise<DynamicResourceDetail> { return unwrap(await apiClient.patch<ApiEnvelope<DynamicResourceDetail>>(ENDPOINTS.resource(id), payload, { headers: lockHeaders(lockVersion) })); },
  async deleteResource(id: string, lockVersion: number): Promise<OperationResult> { return unwrap(await apiClient.delete<ApiEnvelope<OperationResult>>(ENDPOINTS.resource(id), { headers: lockHeaders(lockVersion) })); },
  async restoreResource(id: string): Promise<DynamicResourceDetail> { return unwrap(await apiClient.post<ApiEnvelope<DynamicResourceDetail>>(ENDPOINTS.restoreResource(id), {})); },
  async duplicateResource(id: string): Promise<DynamicResourceDetail> { return unwrap(await apiClient.post<ApiEnvelope<DynamicResourceDetail>>(ENDPOINTS.duplicateResource(id), {})); },
  async submitResource(id: string, lockVersion: number, key: string): Promise<DynamicResourceDetail> { return unwrap(await apiClient.post<ApiEnvelope<DynamicResourceDetail>>(ENDPOINTS.submitResource(id), { lock_version: lockVersion }, { headers: { ...lockHeaders(lockVersion), ...idempotencyHeaders(key) } })); },
  async cancelResource(id: string, reason: string, lockVersion: number, key: string): Promise<DynamicResourceDetail> { return unwrap(await apiClient.post<ApiEnvelope<DynamicResourceDetail>>(ENDPOINTS.cancelResource(id), { reason, lock_version: lockVersion }, { headers: { ...lockHeaders(lockVersion), ...idempotencyHeaders(key) } })); },
  async listResourceVersions(id: string, page = 1): Promise<PaginatedResult<DynamicResourceVersion>> { return unwrapPage(await apiClient.get<ApiEnvelope<readonly DynamicResourceVersion[]>>(withQuery(ENDPOINTS.resourceVersions(id), { page }))); },
  async getResourceVersion(id: string, version: number): Promise<DynamicResourceVersion> { return unwrap(await apiClient.get<ApiEnvelope<DynamicResourceVersion>>(ENDPOINTS.resourceVersion(id, version))); },
  async listNamingSequences(filters: NamingSequenceFilters = {}): Promise<PaginatedResult<NamingSequence>> { return unwrapPage(await apiClient.get<ApiEnvelope<readonly NamingSequence[]>>(withQuery(ENDPOINTS.namingSequences, filters))); },
  async getNamingSequence(id: string): Promise<NamingSequence> { return unwrap(await apiClient.get<ApiEnvelope<NamingSequence>>(ENDPOINTS.namingSequence(id))); },
  async resetNamingSequence(id: string, nextValue: number): Promise<NamingSequence> { return unwrap(await apiClient.post<ApiEnvelope<NamingSequence>>(ENDPOINTS.resetNamingSequence(id), { next_value: nextValue })); },
  async previewRecordKey(entityId: string, data: Readonly<Record<string, JSONValue>>): Promise<string> { return unwrap(await apiClient.post<ApiEnvelope<string>>(ENDPOINTS.previewRecordKey, { entity_id: entityId, data })); },
  async health(): Promise<Readonly<Record<string, JSONValue>>> { return unwrap(await apiClient.get<ApiEnvelope<Readonly<Record<string, JSONValue>>>>(ENDPOINTS.health)); },
  async getConfiguration(environment: MetadataEnvironment): Promise<MetadataModelingConfiguration> { return unwrap(await apiClient.get<ApiEnvelope<MetadataModelingConfiguration>>(withQuery(ENDPOINTS.configuration, { environment }))); },
  async previewConfiguration(environment: MetadataEnvironment, values: MetadataModelingConfigurationValues): Promise<ConfigurationPreview> { return unwrap(await apiClient.post<ApiEnvelope<ConfigurationPreview>>(withQuery(ENDPOINTS.previewConfiguration, { environment }), { values })); },
  async updateConfiguration(environment: MetadataEnvironment, values: MetadataModelingConfigurationValues, version: number): Promise<MetadataModelingConfiguration> { return unwrap(await apiClient.put<ApiEnvelope<MetadataModelingConfiguration>>(withQuery(ENDPOINTS.configuration, { environment }), values, { headers: lockHeaders(version) })); },
  async listConfigurationVersions(environment: MetadataEnvironment, page = 1): Promise<PaginatedResult<ConfigurationVersion>> { return unwrapPage(await apiClient.get<ApiEnvelope<readonly ConfigurationVersion[]>>(withQuery(ENDPOINTS.configurationVersions, { environment, page }))); },
  async rollbackConfiguration(environment: MetadataEnvironment, version: number): Promise<MetadataModelingConfiguration> { return unwrap(await apiClient.post<ApiEnvelope<MetadataModelingConfiguration>>(withQuery(ENDPOINTS.rollbackConfiguration(version), { environment }), {})); },
  async importConfiguration(request: ConfigurationImportRequest): Promise<ConfigurationPreview | MetadataModelingConfiguration> { return unwrap(await apiClient.post<ApiEnvelope<ConfigurationPreview | MetadataModelingConfiguration>>(withQuery(ENDPOINTS.importConfiguration, { environment: request.environment }), request)); },
  async exportConfiguration(environment: MetadataEnvironment): Promise<ConfigurationExportDocument> { return unwrap(await apiClient.get<ApiEnvelope<ConfigurationExportDocument>>(withQuery(ENDPOINTS.exportConfiguration, { environment }))); },
});
