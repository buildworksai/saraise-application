/** Public, versioned frontend contract for the declarative customization platform. */

export type UUID = string;
export type JSONPrimitive = string | number | boolean | null;
export interface JSONObject { readonly [key: string]: JSONValue }
export type JSONValue = JSONPrimitive | JSONObject | JSONValue[];

export interface ApiV2PageMeta {
  readonly count: number;
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}

export interface ApiV2Meta {
  readonly correlation_id: UUID;
  readonly timestamp: string;
  readonly pagination?: ApiV2PageMeta;
}

export interface ApiV2Envelope<T> { readonly data: T; readonly meta: ApiV2Meta }
export interface ApiV2ErrorDetail { readonly code: string; readonly message: string; readonly field?: string; readonly pointer?: string }
export interface ApiV2Error {
  readonly error: { readonly code: string; readonly message: string; readonly detail?: readonly ApiV2ErrorDetail[]; readonly correlation_id: UUID };
}

export type FieldDataType = "text" | "long_text" | "integer" | "decimal" | "boolean" | "date" | "datetime" | "uuid" | "choice" | "multi_choice" | "json";
export type FieldStatus = "draft" | "active" | "deprecated" | "retired";
export type FieldValueSource = "ui" | "api" | "import" | "rule";
export type FormStatus = "draft" | "published" | "archived";
export type LayoutVersionStatus = "candidate" | "published" | "superseded" | "rejected";
export type RuleTrigger = "validate" | "before_create" | "before_update" | "form_change";
export type RuleStatus = "draft" | "published" | "paused" | "retired";
export type RuleVersionStatus = "candidate" | "published" | "superseded" | "rejected";
export type RuleOperator = "eq" | "ne" | "gt" | "gte" | "lt" | "lte" | "in" | "not_in" | "contains" | "starts_with" | "ends_with" | "is_null" | "not_null" | "changed" | "and" | "or" | "not";
export type RuleActionType = "reject-with-message" | "set-derived-value" | "set-required" | "set-visible" | "set-enabled" | "emit-field-diagnostic";
export type RuleExecutionStatus = "matched" | "not_matched" | "rejected" | "failed";
export type DiagnosticSeverity = "info" | "warning" | "error";
export type CapabilityState = "available" | "capability_unavailable";

export interface ResourceContract {
  readonly module: string; readonly resource: string; readonly version: string;
  readonly fields: JSONObject; readonly custom_field_types: readonly FieldDataType[];
  readonly form_surfaces: readonly string[]; readonly rule_triggers: readonly RuleTrigger[];
  readonly entitlement_keys: readonly string[]; readonly available: boolean; readonly discovery: JSONObject;
}

export interface TransitionEvidence { readonly command: string; readonly from: string; readonly to: string; readonly actor_id: UUID; readonly occurred_at: string; readonly correlation_id?: UUID }
export interface ValidationDiagnostic { readonly code: string; readonly message: string; readonly severity: DiagnosticSeverity; readonly field?: string; readonly pointer?: string; readonly remediation?: string }
export interface DependencyReference { readonly entity_type: "field" | "form" | "layout" | "rule" | "module"; readonly entity_id: UUID | null; readonly label: string; readonly module: string; readonly blocking: boolean; readonly capability_state: CapabilityState }
export interface ImpactEntityReference { readonly form_id?: UUID; readonly rule_id?: UUID; readonly version_id: UUID; readonly status: string }
export interface DependencyImpact { readonly entity_type: string; readonly entity_id: UUID; readonly dependency_count: number; readonly blocking: boolean; readonly blocking_count?: number; readonly capability_unavailable: boolean; readonly value_count?: number; readonly version_count?: number; readonly layout_version_count?: number; readonly execution_count?: number; readonly field_references?: readonly string[]; readonly forms?: readonly ImpactEntityReference[]; readonly rules?: readonly ImpactEntityReference[] }

export interface MutableAudit {
  readonly tenant_id: UUID;
  readonly created_by: UUID;
  readonly updated_by: UUID;
  readonly created_at: string;
  readonly updated_at: string;
  readonly deleted_at: string | null;
  readonly deleted_by: UUID | null;
  readonly lock_version: number;
}

export interface CustomFieldDefinition extends MutableAudit {
  readonly id: UUID; readonly key: string; readonly label: string; readonly description: string;
  readonly owner_module: string; readonly target_resource: string; readonly target_contract_version: string;
  readonly data_type: FieldDataType; readonly required: boolean; readonly searchable: boolean;
  readonly default_value: JSONValue | null; readonly validation_schema: JSONObject; readonly presentation_schema: JSONObject;
  readonly status: FieldStatus; readonly activated_at: string | null; readonly deprecated_at: string | null; readonly retired_at: string | null;
  readonly transition_history: readonly TransitionEvidence[]; readonly dependency_count?: number; readonly value_count?: number;
  readonly capability_state?: CapabilityState;
}

export interface FieldDefinitionCreateRequest {
  readonly key: string; readonly label: string; readonly description?: string; readonly owner_module: string;
  readonly target_resource: string; readonly target_contract_version: string; readonly data_type: FieldDataType;
  readonly required?: boolean; readonly searchable?: boolean; readonly default_value?: JSONValue | null;
  readonly validation_schema?: JSONObject; readonly presentation_schema?: JSONObject;
}
export interface FieldDefinitionUpdateRequest { readonly label?: string; readonly description?: string; readonly required?: boolean; readonly searchable?: boolean; readonly default_value?: JSONValue | null; readonly validation_schema?: JSONObject; readonly presentation_schema?: JSONObject; readonly expected_lock_version: number }
export interface LifecycleRequest { readonly transition_key: string }
export interface ValueValidationRequest { readonly value: JSONValue }
export interface ValidationResult { readonly valid: boolean; readonly normalized_value?: JSONValue; readonly diagnostics: readonly ValidationDiagnostic[] }

export interface CustomFieldValue extends MutableAudit { readonly id: UUID; readonly definition_id: UUID; readonly definition_key: string; readonly target_record_id: UUID; readonly value: JSONValue; readonly definition_revision: number; readonly source: FieldValueSource }
export interface FieldValueCreateRequest { readonly definition_id: UUID; readonly target_record_id: UUID; readonly value: JSONValue; readonly source?: Exclude<FieldValueSource, "rule"> }
export interface FieldValueUpdateRequest { readonly value: JSONValue; readonly expected_lock_version: number }

export interface FormDefinition extends MutableAudit {
  readonly id: UUID; readonly key: string; readonly name: string; readonly description: string; readonly owner_module: string;
  readonly target_resource: string; readonly target_contract_version: string; readonly status: FormStatus;
  readonly published_version: number | null; readonly published_at: string | null; readonly published_by: UUID | null;
  readonly archived_at: string | null; readonly transition_history: readonly TransitionEvidence[]; readonly dependency_count?: number;
  readonly capability_state?: CapabilityState;
}
export interface FormCreateRequest { readonly key: string; readonly name: string; readonly description?: string; readonly owner_module: string; readonly target_resource: string; readonly target_contract_version: string }
export interface FormUpdateRequest { readonly name?: string; readonly description?: string; readonly expected_lock_version: number }
export interface LayoutComponent { readonly id: string; readonly type: "field" | "heading" | "help_text" | "divider"; readonly field_key?: string; readonly label: string; readonly accessibility_label: string; readonly width: 3 | 4 | 6 | 8 | 9 | 12 }
export interface LayoutSection { readonly id: string; readonly title: string; readonly components: readonly LayoutComponent[] }
export interface FormLayout { readonly schema_version: 1; readonly sections: readonly LayoutSection[] }
export interface FormLayoutVersion { readonly id: UUID; readonly tenant_id?: UUID; readonly form: UUID; readonly version: number; readonly schema_version: number; readonly layout: FormLayout; readonly content_hash: string; readonly change_summary: string; readonly status: LayoutVersionStatus; readonly validation_errors: readonly ValidationDiagnostic[]; readonly created_by: UUID; readonly created_at: string; readonly published_at: string | null; readonly published_by: UUID | null }
export interface LayoutVersionCreateRequest { readonly layout: FormLayout; readonly change_summary: string }
export interface FormPublishRequest extends LifecycleRequest { readonly layout_version_id: UUID }
export interface RenderSchema { readonly form_id: UUID; readonly form_key: string; readonly version: number; readonly contract_version: string; readonly layout: FormLayout; readonly fields: readonly CustomFieldDefinition[]; readonly content_hash: string }

export interface RuleConditionNode { readonly operator: RuleOperator; readonly field?: string; readonly value?: JSONValue; readonly operands?: readonly RuleConditionNode[] }
export interface RuleActionNode { readonly type: RuleActionType; readonly field?: string; readonly value?: JSONValue; readonly message?: string }
export interface BusinessRule extends MutableAudit {
  readonly id: UUID; readonly key: string; readonly name: string; readonly description: string; readonly owner_module: string;
  readonly target_resource: string; readonly target_contract_version: string; readonly trigger: RuleTrigger; readonly priority: number;
  readonly stop_on_match: boolean; readonly status: RuleStatus; readonly published_version: number | null; readonly published_at: string | null;
  readonly published_by: UUID | null; readonly transition_history: readonly TransitionEvidence[]; readonly diagnostic_count?: number;
  readonly execution_count?: number; readonly capability_state?: CapabilityState;
}
export interface RuleCreateRequest { readonly key: string; readonly name: string; readonly description?: string; readonly owner_module: string; readonly target_resource: string; readonly target_contract_version: string; readonly trigger: RuleTrigger; readonly priority?: number; readonly stop_on_match?: boolean }
export interface RuleUpdateRequest { readonly name?: string; readonly description?: string; readonly priority?: number; readonly stop_on_match?: boolean; readonly expected_lock_version: number }
export interface BusinessRuleVersion { readonly id: UUID; readonly tenant_id?: UUID; readonly rule: UUID; readonly version: number; readonly language_version: number; readonly condition_ast: RuleConditionNode; readonly action_ast: readonly RuleActionNode[]; readonly dependencies: readonly string[]; readonly content_hash: string; readonly status: RuleVersionStatus; readonly validation_errors: readonly ValidationDiagnostic[]; readonly change_summary: string; readonly created_by: UUID; readonly created_at: string; readonly published_at: string | null; readonly published_by: UUID | null }
export interface RuleVersionCreateRequest { readonly condition_ast: RuleConditionNode; readonly action_ast: readonly RuleActionNode[]; readonly change_summary: string }
export interface RulePublishRequest extends LifecycleRequest { readonly version_id: UUID }
export interface RuleEvaluateRequest { readonly record: JSONObject; readonly changed_fields: readonly string[]; readonly target_record_id?: UUID; readonly idempotency_key: string }
export interface EvaluationResult { readonly matched?: boolean; readonly rejected?: boolean; readonly mutations?: JSONObject; readonly actions?: readonly RuleActionNode[]; readonly diagnostics: readonly ValidationDiagnostic[]; readonly execution_id?: UUID; readonly duration_ms: number; readonly correlation_id: UUID }
export interface RuleExecution { readonly id: UUID; readonly tenant_id?: UUID; readonly rule: UUID; readonly rule_name?: string; readonly rule_version: UUID; readonly target_record_id: UUID | null; readonly trigger: RuleTrigger; readonly idempotency_key: string; readonly status: RuleExecutionStatus; readonly input_fingerprint: string; readonly result: JSONObject; readonly diagnostics: readonly ValidationDiagnostic[]; readonly duration_ms: number; readonly correlation_id: UUID; readonly executed_by: UUID; readonly executed_at: string }

export interface HealthCheck { readonly name: string; readonly status: "healthy" | "degraded" | "unhealthy"; readonly critical: boolean; readonly message: string }
export interface CustomizationHealth { readonly status: "healthy" | "degraded" | "unhealthy"; readonly checks: readonly HealthCheck[] }

export interface PageQuery { readonly page?: number; readonly page_size?: number; readonly search?: string }
export type FieldOrdering = "key" | "-key" | "label" | "-label" | "status" | "-status" | "created_at" | "-created_at" | "updated_at" | "-updated_at";
export interface FieldFilters extends PageQuery { readonly owner_module?: string; readonly target_resource?: string; readonly data_type?: FieldDataType; readonly status?: FieldStatus; readonly ordering?: FieldOrdering }
export type FormOrdering = "key" | "-key" | "name" | "-name" | "status" | "-status" | "created_at" | "-created_at" | "updated_at" | "-updated_at";
export interface FormFilters extends PageQuery { readonly owner_module?: string; readonly target_resource?: string; readonly status?: FormStatus; readonly ordering?: FormOrdering }
export type RuleOrdering = "priority" | "-priority" | "key" | "-key" | "status" | "-status" | "created_at" | "-created_at" | "updated_at" | "-updated_at";
export interface RuleFilters extends PageQuery { readonly owner_module?: string; readonly target_resource?: string; readonly trigger?: RuleTrigger; readonly status?: RuleStatus; readonly ordering?: RuleOrdering }
export interface FieldValueFilters extends PageQuery { readonly definition_id?: UUID; readonly target_record_id?: UUID; readonly source?: FieldValueSource; readonly updated_at_after?: string; readonly updated_at_before?: string; readonly ordering?: "updated_at" | "-updated_at" | "created_at" | "-created_at" }
export interface LayoutFilters extends PageQuery { readonly form_id?: UUID; readonly status?: LayoutVersionStatus; readonly version?: number }
export interface RuleVersionFilters extends PageQuery { readonly rule_id?: UUID; readonly status?: RuleVersionStatus; readonly version?: number }
export type ExecutionOrdering = "executed_at" | "-executed_at" | "duration_ms" | "-duration_ms" | "status" | "-status";
export interface ExecutionFilters extends PageQuery { readonly rule_id?: UUID; readonly rule_version_id?: UUID; readonly target_record_id?: UUID; readonly status?: RuleExecutionStatus; readonly executed_after?: string; readonly executed_before?: string; readonly correlation_id?: UUID; readonly ordering?: ExecutionOrdering }

export const MODULE_API_PREFIX = "/api/v2/customization-framework";
export const ENDPOINTS = {
  RESOURCE_CONTRACTS: `${MODULE_API_PREFIX}/resource-contracts/`,
  FIELD_DEFINITIONS: { LIST: `${MODULE_API_PREFIX}/field-definitions/`, CREATE: `${MODULE_API_PREFIX}/field-definitions/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/field-definitions/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/field-definitions/${id}/` as const, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/field-definitions/${id}/` as const, ACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/field-definitions/${id}/activate/` as const, DEPRECATE: (id: UUID) => `${MODULE_API_PREFIX}/field-definitions/${id}/deprecate/` as const, RETIRE: (id: UUID) => `${MODULE_API_PREFIX}/field-definitions/${id}/retire/` as const, IMPACT: (id: UUID) => `${MODULE_API_PREFIX}/field-definitions/${id}/impact/` as const, VALIDATE_VALUE: (id: UUID) => `${MODULE_API_PREFIX}/field-definitions/${id}/validate-value/` as const },
  FIELD_VALUES: { LIST: `${MODULE_API_PREFIX}/field-values/`, CREATE: `${MODULE_API_PREFIX}/field-values/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/field-values/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/field-values/${id}/` as const, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/field-values/${id}/` as const },
  FORMS: { LIST: `${MODULE_API_PREFIX}/forms/`, CREATE: `${MODULE_API_PREFIX}/forms/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/forms/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/forms/${id}/` as const, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/forms/${id}/` as const, LAYOUT_VERSIONS: (id: UUID) => `${MODULE_API_PREFIX}/forms/${id}/layout-versions/` as const, PUBLISH: (id: UUID) => `${MODULE_API_PREFIX}/forms/${id}/publish/` as const, ARCHIVE: (id: UUID) => `${MODULE_API_PREFIX}/forms/${id}/archive/` as const, RENDER_SCHEMA: (id: UUID) => `${MODULE_API_PREFIX}/forms/${id}/render-schema/` as const, IMPACT: (id: UUID) => `${MODULE_API_PREFIX}/forms/${id}/impact/` as const },
  FORM_LAYOUTS: { LIST: `${MODULE_API_PREFIX}/form-layouts/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/form-layouts/${id}/` as const },
  RULES: { LIST: `${MODULE_API_PREFIX}/rules/`, CREATE: `${MODULE_API_PREFIX}/rules/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/` as const, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/` as const, VERSIONS: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/versions/` as const, PUBLISH: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/publish/` as const, PAUSE: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/pause/` as const, RESUME: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/resume/` as const, RETIRE: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/retire/` as const, EVALUATE: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/evaluate/` as const, IMPACT: (id: UUID) => `${MODULE_API_PREFIX}/rules/${id}/impact/` as const },
  RULE_VERSIONS: { LIST: `${MODULE_API_PREFIX}/rule-versions/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/rule-versions/${id}/` as const },
  RULE_EXECUTIONS: { LIST: `${MODULE_API_PREFIX}/rule-executions/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/rule-executions/${id}/` as const },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTES = {
  FIELDS: "/customization-framework/fields", FIELD_CREATE: "/customization-framework/fields/new", FIELD_DETAIL: (id: UUID) => `/customization-framework/fields/${id}` as const, FIELD_EDIT: (id: UUID) => `/customization-framework/fields/${id}/edit` as const, FIELD_IMPACT: (id: UUID) => `/customization-framework/fields/${id}/impact` as const,
  FORMS: "/customization-framework/forms", FORM_CREATE: "/customization-framework/forms/new", FORM_DETAIL: (id: UUID) => `/customization-framework/forms/${id}` as const, FORM_EDIT: (id: UUID) => `/customization-framework/forms/${id}/designer` as const, FORM_VERSION: (formId: UUID, versionId: UUID) => `/customization-framework/forms/${formId}/versions/${versionId}` as const, FORM_IMPACT: (id: UUID) => `/customization-framework/forms/${id}/impact` as const,
  RULES: "/customization-framework/rules", RULE_CREATE: "/customization-framework/rules/new", RULE_DETAIL: (id: UUID) => `/customization-framework/rules/${id}` as const, RULE_EDIT: (id: UUID) => `/customization-framework/rules/${id}/edit` as const, RULE_VERSION: (ruleId: UUID, versionId: UUID) => `/customization-framework/rules/${ruleId}/versions/${versionId}` as const, RULE_IMPACT: (id: UUID) => `/customization-framework/rules/${id}/impact` as const,
  EXECUTIONS: "/customization-framework/executions", EXECUTION_DETAIL: (id: UUID) => `/customization-framework/executions/${id}` as const,
} as const;
