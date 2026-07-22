/** Governed API v2 contracts for the metadata kernel. */

export type JSONPrimitive = string | number | boolean | null;
export type JSONValue = JSONPrimitive | JSONObject | readonly JSONValue[];
export interface JSONObject { [key: string]: JSONValue }

export interface PaginationMeta {
  readonly page: number;
  readonly page_size: number;
  readonly count: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}

export interface ApiMeta {
  readonly correlation_id: string;
  readonly timestamp: string;
  readonly pagination?: PaginationMeta;
}

export interface ApiEnvelope<T> {
  readonly data: T;
  readonly meta: ApiMeta;
}

export type EntityStatus = "draft" | "published" | "archived";
export type EntityOrigin = "custom" | "system" | "extension";
export type NamingStrategy = "uuid" | "sequence" | "field";
export type DynamicResourceState = "draft" | "submitted" | "cancelled";
export type FieldType = "text" | "number" | "date" | "boolean" | "select" | "reference" | "json";
export type SchemaVersionStatus = "candidate" | "published" | "superseded" | "rejected";
export type SchemaCompatibility = "compatible" | "requires_backfill" | "breaking";

export interface GovernedFieldError {
  readonly code: string;
  readonly message: string;
  readonly field?: string;
}

export interface GovernedError {
  readonly code: string;
  readonly message: string;
  readonly correlation_id: string;
  readonly fields?: Readonly<Record<string, readonly GovernedFieldError[]>>;
}

export interface ValidationRules {
  readonly min_length?: number;
  readonly max_length?: number;
  readonly regex?: string;
  readonly minimum?: number;
  readonly maximum?: number;
  readonly integer_only?: boolean;
  readonly decimal_places?: number;
  readonly allow_blank?: boolean;
  readonly target_status?: "published";
  readonly type?: "object" | "array" | "string" | "number" | "boolean" | "null";
  readonly required?: readonly string[];
  readonly properties?: Readonly<Record<string, ValidationRules>>;
  readonly items?: ValidationRules;
  readonly enum?: readonly JSONValue[];
}

export interface FieldDefinitionInput {
  readonly name: string;
  readonly key: string;
  readonly field_type: FieldType;
  readonly is_required: boolean;
  readonly is_read_only: boolean;
  readonly is_searchable: boolean;
  readonly default_value: JSONValue;
  readonly validation_rules: ValidationRules;
  readonly options: readonly string[];
  readonly reference_entity_code: string | null;
  readonly help_text: string;
  readonly placeholder: string;
  readonly order: number;
}

export interface FieldDefinition extends FieldDefinitionInput {
  readonly id: string;
  readonly created_at: string;
}

export interface NamingConfiguration {
  readonly field_key?: string;
  readonly sequence_key?: string;
  readonly prefix_template?: string;
  readonly padding?: number;
  readonly reset_period?: "never" | "yearly" | "monthly";
}

export interface EntityDefinitionSummary {
  readonly id: string;
  readonly name: string;
  readonly plural_name: string;
  readonly code: string;
  readonly description: string;
  readonly owner_module: string;
  readonly icon: string;
  readonly origin: EntityOrigin;
  readonly status: EntityStatus;
  readonly active_version: string | null;
  readonly active_version_number: number | null;
  readonly record_count: number;
  readonly lock_version: number;
  readonly created_at: string;
  readonly updated_at: string;
  readonly allowed_actions?: readonly string[];
}

export interface EntityDefinitionDetail extends EntityDefinitionSummary {
  readonly is_submittable: boolean;
  readonly track_changes: boolean;
  readonly naming_strategy: NamingStrategy;
  readonly naming_config: NamingConfiguration;
  readonly active_fields: readonly FieldDefinition[];
  readonly current_version: EntitySchemaVersionSummary | null;
  readonly created_by: string;
  readonly updated_by: string;
  readonly archived_at: string | null;
  readonly archived_by: string | null;
}

export interface EntityDefinitionCreate {
  readonly name: string;
  readonly plural_name: string;
  readonly code: string;
  readonly description: string;
  readonly icon: string;
  readonly is_submittable: boolean;
  readonly track_changes: boolean;
  readonly naming_strategy: NamingStrategy;
  readonly naming_config: NamingConfiguration;
}

export type EntityDefinitionUpdate = Omit<EntityDefinitionCreate, "code"> & { readonly code?: string };

export interface SchemaValidationReport {
  readonly valid: boolean;
  readonly compatibility: SchemaCompatibility;
  readonly resource_count: number;
  readonly incompatible_resource_count: number;
  readonly errors: readonly GovernedFieldError[];
  readonly warnings: readonly GovernedFieldError[];
}

export interface EntitySchemaVersionSummary {
  readonly id: string;
  readonly version: number;
  readonly status: SchemaVersionStatus;
  readonly schema_hash: string;
  readonly change_summary: string;
  readonly compatibility: SchemaCompatibility;
  readonly published_at: string | null;
  readonly published_by: string | null;
  readonly created_by: string;
  readonly created_at: string;
}

export interface EntitySchemaVersionDetail extends EntitySchemaVersionSummary {
  readonly entity_definition: string;
  readonly schema: JSONObject;
  readonly fields: readonly FieldDefinition[];
  readonly validation_report: SchemaValidationReport;
  readonly based_on_version: string | null;
}

export interface SchemaCandidateCreate {
  readonly fields: readonly FieldDefinitionInput[];
  readonly based_on_version_id: string | null;
  readonly change_summary: string;
}

export interface SchemaFieldChange {
  readonly key: string;
  readonly kind: "added" | "removed" | "changed";
  readonly before?: FieldDefinitionInput;
  readonly after?: FieldDefinitionInput;
}
export interface SchemaDiff {
  readonly from_version: number;
  readonly to_version: number;
  readonly compatibility: SchemaCompatibility;
  readonly changes: readonly SchemaFieldChange[];
}

export interface DynamicResourceSummary {
  readonly id: string;
  readonly entity_definition: string;
  readonly entity_code: string;
  readonly entity_name: string;
  readonly schema_version: string;
  readonly schema_version_number: number;
  readonly record_key: string;
  readonly display_name: string;
  readonly state: DynamicResourceState;
  readonly lock_version: number;
  readonly searchable_data: JSONObject;
  readonly created_at: string;
  readonly updated_at: string;
  readonly allowed_actions?: readonly string[];
}

export interface DynamicResourceDetail extends DynamicResourceSummary {
  readonly data: JSONObject;
  readonly fields: readonly FieldDefinition[];
  readonly created_by: string;
  readonly updated_by: string;
  readonly submitted_at: string | null;
  readonly submitted_by: string | null;
  readonly cancelled_at: string | null;
  readonly cancelled_by: string | null;
}

export interface DynamicResourceCreate { readonly entity_id: string; readonly data: JSONObject; readonly display_name?: string }
export interface DynamicResourceReplace { readonly data: JSONObject; readonly display_name?: string }
export interface DynamicResourcePatch { readonly changes: JSONObject; readonly display_name?: string }

export interface DynamicResourceVersion {
  readonly id: string;
  readonly version: number;
  readonly schema_version: string;
  readonly state: DynamicResourceState;
  readonly record_key: string;
  readonly display_name: string;
  readonly data: JSONObject;
  readonly changed_fields: readonly string[];
  readonly operation: "create" | "update" | "submit" | "cancel" | "delete" | "restore";
  readonly changed_by: string;
  readonly correlation_id: string;
  readonly changed_at: string;
}

export interface NamingSequence {
  readonly id: string;
  readonly entity_definition: string;
  readonly sequence_key: string;
  readonly prefix_template: string;
  readonly next_value: number;
  readonly padding: number;
  readonly reset_period: "never" | "yearly" | "monthly";
  readonly period_key: string;
  readonly is_active: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ExportDocument extends JSONObject {
  readonly format_version: string;
  readonly entity: JSONObject;
  readonly schema: JSONObject;
  readonly checksum: string;
}
export interface ImportRequest { readonly document: ExportDocument; readonly mode: "create" | "new_version" | "validate_only"; readonly definition_id?: string }
export interface ImportValidationResult { readonly valid: boolean; readonly checksum_valid: boolean; readonly normalized_document: ExportDocument; readonly report: SchemaValidationReport }
export interface OperationResult { readonly operation: string; readonly status: "completed" | "accepted"; readonly id: string; readonly version?: number }
export interface PreviewResult { readonly normalized_schema: JSONObject; readonly form_descriptor: readonly FieldDefinitionInput[]; readonly sample_validation: SchemaValidationReport; readonly impact: SchemaValidationReport; readonly naming_preview?: string }

export interface EntityDefinitionFilters { readonly [key: string]: string | number | boolean | undefined; readonly status?: EntityStatus; readonly owner_module?: string; readonly origin?: EntityOrigin; readonly search?: string; readonly ordering?: "name" | "-name" | "created_at" | "-created_at" | "updated_at" | "-updated_at"; readonly page?: number; readonly page_size?: number }
export interface DynamicResourceFilters { readonly [key: string]: string | number | boolean | undefined; readonly entity_id?: string; readonly entity_code?: string; readonly state?: DynamicResourceState; readonly search?: string; readonly created_after?: string; readonly created_before?: string; readonly ordering?: "record_key" | "-record_key" | "display_name" | "-display_name" | "created_at" | "-created_at" | "updated_at" | "-updated_at"; readonly page?: number; readonly page_size?: number }
export interface NamingSequenceFilters { readonly [key: string]: string | number | boolean | undefined; readonly entity_id?: string; readonly is_active?: boolean; readonly page?: number; readonly page_size?: number }
export interface PaginatedResult<T> { readonly items: readonly T[]; readonly pagination: PaginationMeta; readonly correlationId: string }

export type MetadataEnvironment = "development" | "staging" | "production";
export interface FeatureRollout {
  readonly enabled: boolean;
  readonly tenant_percentage: number;
  readonly roles: readonly string[];
  readonly cohorts: readonly string[];
}
export interface MetadataModelingConfigurationValues {
  readonly synchronous_validation_limit: number;
  readonly max_fields_per_schema: number;
  readonly max_schema_bytes: number;
  readonly max_record_data_bytes: number;
  readonly max_regex_length: number;
  readonly default_page_size: number;
  readonly max_page_size: number;
  readonly allowed_field_types: readonly FieldType[];
  readonly feature_flags: Readonly<Record<string, boolean>>;
  readonly rollout: Readonly<Record<string, FeatureRollout>>;
}
export interface MetadataModelingConfiguration extends MetadataModelingConfigurationValues {
  readonly id: string;
  readonly environment: MetadataEnvironment;
  readonly version: number;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly updated_by: string;
}
export interface ConfigurationDiffEntry { readonly path: string; readonly before: JSONValue; readonly after: JSONValue }
export interface ConfigurationPreview { readonly valid: boolean; readonly errors: readonly GovernedFieldError[]; readonly warnings: readonly GovernedFieldError[]; readonly diff: readonly ConfigurationDiffEntry[]; readonly effective_values: MetadataModelingConfigurationValues }
export interface ConfigurationVersion {
  readonly id: string;
  readonly version: number;
  readonly before: MetadataModelingConfigurationValues | null;
  readonly after: MetadataModelingConfigurationValues;
  readonly changed_by: string;
  readonly changed_at: string;
  readonly correlation_id: string;
  readonly changes: readonly ConfigurationDiffEntry[];
  readonly operation: "create" | "update" | "rollback" | "import";
}
export interface ConfigurationExportDocument { readonly format_version: string; readonly environment: MetadataEnvironment; readonly values: MetadataModelingConfigurationValues; readonly checksum: string }
export interface ConfigurationImportRequest { readonly environment: MetadataEnvironment; readonly document: ConfigurationExportDocument; readonly validate_only: boolean }

const API_ROOT = "/api/v2/metadata-modeling";
const detail = (collection: string, id: string) => `${API_ROOT}/${collection}/${encodeURIComponent(id)}/`;
const versionDetail = (definitionId: string, versionId: string) => `${detail("entity-definitions", definitionId)}versions/${encodeURIComponent(versionId)}/`;

export const ENDPOINTS = Object.freeze({
  entityDefinitions: `${API_ROOT}/entity-definitions/`,
  entityDefinition: (id: string) => detail("entity-definitions", id),
  archiveEntityDefinition: (id: string) => `${detail("entity-definitions", id)}archive/`,
  restoreEntityDefinition: (id: string) => `${detail("entity-definitions", id)}restore/`,
  cloneEntityDefinition: (id: string) => `${detail("entity-definitions", id)}clone/`,
  previewEntityDefinition: (id: string) => `${detail("entity-definitions", id)}preview/`,
  previewNewEntityDefinition: `${API_ROOT}/entity-definitions/preview/`,
  exportEntityDefinition: (id: string) => `${detail("entity-definitions", id)}export/`,
  importEntityDefinition: `${API_ROOT}/entity-definitions/import/`,
  schemaVersions: (id: string) => `${detail("entity-definitions", id)}versions/`,
  schemaVersion: versionDetail,
  validateSchemaVersion: (id: string, versionId: string) => `${versionDetail(id, versionId)}validate/`,
  publishSchemaVersion: (id: string, versionId: string) => `${versionDetail(id, versionId)}publish/`,
  rejectSchemaVersion: (id: string, versionId: string) => `${versionDetail(id, versionId)}reject/`,
  rollbackSchemaVersion: (id: string, versionId: string) => `${versionDetail(id, versionId)}rollback/`,
  diffSchemaVersions: (id: string) => `${detail("entity-definitions", id)}versions/diff/`,
  resources: `${API_ROOT}/resources/`,
  resource: (id: string) => detail("resources", id),
  restoreResource: (id: string) => `${detail("resources", id)}restore/`,
  duplicateResource: (id: string) => `${detail("resources", id)}duplicate/`,
  submitResource: (id: string) => `${detail("resources", id)}submit/`,
  cancelResource: (id: string) => `${detail("resources", id)}cancel/`,
  resourceVersions: (id: string) => `${detail("resources", id)}versions/`,
  resourceVersion: (id: string, version: number) => `${detail("resources", id)}versions/${version}/`,
  namingSequences: `${API_ROOT}/naming-sequences/`,
  namingSequence: (id: string) => detail("naming-sequences", id),
  resetNamingSequence: (id: string) => `${detail("naming-sequences", id)}reset/`,
  previewRecordKey: `${API_ROOT}/naming-sequences/preview/`,
  health: `${API_ROOT}/health/`,
  configuration: `${API_ROOT}/configuration/`,
  previewConfiguration: `${API_ROOT}/configuration/preview/`,
  configurationVersions: `${API_ROOT}/configuration/versions/`,
  rollbackConfiguration: (version: number) => `${API_ROOT}/configuration/versions/${version}/rollback/`,
  importConfiguration: `${API_ROOT}/configuration/import/`,
  exportConfiguration: `${API_ROOT}/configuration/export/`,
} as const);

export const ROUTES = Object.freeze({
  schemas: "/metadata-modeling/schemas",
  schemaCreate: "/metadata-modeling/schemas/new",
  schemaDetail: (id: string) => `/metadata-modeling/schemas/${encodeURIComponent(id)}`,
  schemaEdit: (id: string) => `/metadata-modeling/schemas/${encodeURIComponent(id)}/edit`,
  records: "/metadata-modeling/records",
  recordCreate: "/metadata-modeling/records/new",
  recordCreateFor: (entityId: string) => `/metadata-modeling/records/new?entity=${encodeURIComponent(entityId)}`,
  recordDetail: (id: string) => `/metadata-modeling/records/${encodeURIComponent(id)}`,
  recordEdit: (id: string) => `/metadata-modeling/records/${encodeURIComponent(id)}/edit`,
  settings: "/metadata-modeling/settings",
} as const);
