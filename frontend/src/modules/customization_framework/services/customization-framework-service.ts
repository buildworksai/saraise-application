import { apiClient } from "@/services/api-client";
import { ENDPOINTS, type ApiV2Envelope, type BusinessRule, type BusinessRuleVersion, type ConfigurationAuditRecord, type ConfigurationImportRequest, type ConfigurationPreview, type ConfigurationPreviewRequest, type ConfigurationRollbackRequest, type ConfigurationUpdateRequest, type CustomFieldDefinition, type CustomFieldValue, type CustomizationHealth, type DependencyImpact, type ExecutionFilters, type FieldDefinitionCreateRequest, type FieldDefinitionUpdateRequest, type FieldFilters, type FieldValueCreateRequest, type FieldValueFilters, type FieldValueUpdateRequest, type FormCreateRequest, type FormDefinition, type FormFilters, type FormLayoutVersion, type FormPublishRequest, type FormUpdateRequest, type LayoutFilters, type LayoutVersionCreateRequest, type LifecycleRequest, type RenderSchema, type ResourceContract, type RuleCreateRequest, type RuleEvaluateRequest, type RuleExecution, type RuleFilters, type RulePublishRequest, type RuleUpdateRequest, type RuleVersionCreateRequest, type RuleVersionFilters, type RuntimeConfiguration, type RuntimeConfigurationVersion, type UUID, type ValidationResult, type ValueValidationRequest } from "../contracts";

type Query = FieldFilters | FieldValueFilters | FormFilters | LayoutFilters | RuleFilters | RuleVersionFilters | ExecutionFilters;
function query(path: string, values: Query): string { const search = new URLSearchParams(); Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== "") search.set(key, String(value)); }); const encoded = search.toString(); return encoded ? `${path}?${encoded}` : path; }
function expectedVersion(path: string, value: number): string {
  const search = new URLSearchParams({ expected_lock_version: String(value) });
  return `${path}?${search.toString()}`;
}
function commandInit(): RequestInit {
  return { headers: { "Idempotency-Key": crypto.randomUUID(), "X-Correlation-ID": crypto.randomUUID() } };
}

export const customizationFrameworkService = {
  listResourceContracts: (includeUnavailable = true) => apiClient.get<ApiV2Envelope<readonly ResourceContract[]>>(`${ENDPOINTS.RESOURCE_CONTRACTS}?include_unavailable=${includeUnavailable}`),
  listFields: (filters: FieldFilters = {}) => apiClient.get<ApiV2Envelope<readonly CustomFieldDefinition[]>>(query(ENDPOINTS.FIELD_DEFINITIONS.LIST, filters)),
  getField: (id: UUID) => apiClient.get<ApiV2Envelope<CustomFieldDefinition>>(ENDPOINTS.FIELD_DEFINITIONS.DETAIL(id)),
  createField: (request: FieldDefinitionCreateRequest) => apiClient.post<ApiV2Envelope<CustomFieldDefinition>>(ENDPOINTS.FIELD_DEFINITIONS.CREATE, request, commandInit()),
  updateField: (id: UUID, request: FieldDefinitionUpdateRequest) => apiClient.patch<ApiV2Envelope<CustomFieldDefinition>>(ENDPOINTS.FIELD_DEFINITIONS.UPDATE(id), request, commandInit()),
  deleteField: (id: UUID, expectedLockVersion: number) => apiClient.delete<void>(expectedVersion(ENDPOINTS.FIELD_DEFINITIONS.DELETE(id), expectedLockVersion), commandInit()),
  transitionField: (id: UUID, command: "activate" | "deprecate" | "retire", request: LifecycleRequest) => apiClient.post<ApiV2Envelope<CustomFieldDefinition>>(ENDPOINTS.FIELD_DEFINITIONS[command.toUpperCase() as "ACTIVATE" | "DEPRECATE" | "RETIRE"](id), request, commandInit()),
  getFieldImpact: (id: UUID) => apiClient.get<ApiV2Envelope<DependencyImpact>>(ENDPOINTS.FIELD_DEFINITIONS.IMPACT(id)),
  listFieldVersions: (id: UUID) => apiClient.get<ApiV2Envelope<readonly import("../contracts").FieldDefinitionVersion[]>>(ENDPOINTS.FIELD_DEFINITIONS.VERSIONS(id)),
  rollbackField: (id: UUID, request: import("../contracts").FieldDefinitionRollbackRequest) => apiClient.post<ApiV2Envelope<CustomFieldDefinition>>(ENDPOINTS.FIELD_DEFINITIONS.ROLLBACK(id), request, commandInit()),
  validateValue: (id: UUID, request: ValueValidationRequest) => apiClient.post<ApiV2Envelope<ValidationResult>>(ENDPOINTS.FIELD_DEFINITIONS.VALIDATE_VALUE(id), request),
  listValues: (filters: FieldValueFilters) => apiClient.get<ApiV2Envelope<readonly CustomFieldValue[]>>(query(ENDPOINTS.FIELD_VALUES.LIST, filters)),
  getValue: (id: UUID) => apiClient.get<ApiV2Envelope<CustomFieldValue>>(ENDPOINTS.FIELD_VALUES.DETAIL(id)),
  createValue: (request: FieldValueCreateRequest) => apiClient.post<ApiV2Envelope<CustomFieldValue>>(ENDPOINTS.FIELD_VALUES.CREATE, request, commandInit()),
  updateValue: (id: UUID, request: FieldValueUpdateRequest) => apiClient.patch<ApiV2Envelope<CustomFieldValue>>(ENDPOINTS.FIELD_VALUES.UPDATE(id), request, commandInit()),
  deleteValue: (id: UUID, expectedLockVersion: number) => apiClient.delete<void>(expectedVersion(ENDPOINTS.FIELD_VALUES.DELETE(id), expectedLockVersion), commandInit()),
  listForms: (filters: FormFilters = {}) => apiClient.get<ApiV2Envelope<readonly FormDefinition[]>>(query(ENDPOINTS.FORMS.LIST, filters)),
  getForm: (id: UUID) => apiClient.get<ApiV2Envelope<FormDefinition>>(ENDPOINTS.FORMS.DETAIL(id)),
  createForm: (request: FormCreateRequest) => apiClient.post<ApiV2Envelope<FormDefinition>>(ENDPOINTS.FORMS.CREATE, request, commandInit()),
  updateForm: (id: UUID, request: FormUpdateRequest) => apiClient.patch<ApiV2Envelope<FormDefinition>>(ENDPOINTS.FORMS.UPDATE(id), request, commandInit()),
  deleteForm: (id: UUID, expectedLockVersion: number) => apiClient.delete<void>(expectedVersion(ENDPOINTS.FORMS.DELETE(id), expectedLockVersion), commandInit()),
  listFormLayouts: (id: UUID) => apiClient.get<ApiV2Envelope<readonly FormLayoutVersion[]>>(ENDPOINTS.FORMS.LAYOUT_VERSIONS(id)),
  createFormLayout: (id: UUID, request: LayoutVersionCreateRequest) => apiClient.post<ApiV2Envelope<FormLayoutVersion>>(ENDPOINTS.FORMS.LAYOUT_VERSIONS(id), request, commandInit()),
  getFormLayout: (id: UUID) => apiClient.get<ApiV2Envelope<FormLayoutVersion>>(ENDPOINTS.FORM_LAYOUTS.DETAIL(id)),
  listLayouts: (filters: LayoutFilters = {}) => apiClient.get<ApiV2Envelope<readonly FormLayoutVersion[]>>(query(ENDPOINTS.FORM_LAYOUTS.LIST, filters)),
  publishForm: (id: UUID, request: FormPublishRequest) => apiClient.post<ApiV2Envelope<FormLayoutVersion>>(ENDPOINTS.FORMS.PUBLISH(id), request, commandInit()),
  archiveForm: (id: UUID, request: LifecycleRequest) => apiClient.post<ApiV2Envelope<FormDefinition>>(ENDPOINTS.FORMS.ARCHIVE(id), request, commandInit()),
  getRenderSchema: (id: UUID) => apiClient.get<ApiV2Envelope<RenderSchema>>(ENDPOINTS.FORMS.RENDER_SCHEMA(id)),
  getFormImpact: (id: UUID) => apiClient.get<ApiV2Envelope<DependencyImpact>>(ENDPOINTS.FORMS.IMPACT(id)),
  listRules: (filters: RuleFilters = {}) => apiClient.get<ApiV2Envelope<readonly BusinessRule[]>>(query(ENDPOINTS.RULES.LIST, filters)),
  getRule: (id: UUID) => apiClient.get<ApiV2Envelope<BusinessRule>>(ENDPOINTS.RULES.DETAIL(id)),
  createRule: (request: RuleCreateRequest) => apiClient.post<ApiV2Envelope<BusinessRule>>(ENDPOINTS.RULES.CREATE, request, commandInit()),
  updateRule: (id: UUID, request: RuleUpdateRequest) => apiClient.patch<ApiV2Envelope<BusinessRule>>(ENDPOINTS.RULES.UPDATE(id), request, commandInit()),
  deleteRule: (id: UUID, expectedLockVersion: number) => apiClient.delete<void>(expectedVersion(ENDPOINTS.RULES.DELETE(id), expectedLockVersion), commandInit()),
  listRuleVersions: (id: UUID) => apiClient.get<ApiV2Envelope<readonly BusinessRuleVersion[]>>(ENDPOINTS.RULES.VERSIONS(id)),
  createRuleVersion: (id: UUID, request: RuleVersionCreateRequest) => apiClient.post<ApiV2Envelope<BusinessRuleVersion>>(ENDPOINTS.RULES.VERSIONS(id), request, commandInit()),
  getRuleVersion: (id: UUID) => apiClient.get<ApiV2Envelope<BusinessRuleVersion>>(ENDPOINTS.RULE_VERSIONS.DETAIL(id)),
  listRuleVersionCatalog: (filters: RuleVersionFilters = {}) => apiClient.get<ApiV2Envelope<readonly BusinessRuleVersion[]>>(query(ENDPOINTS.RULE_VERSIONS.LIST, filters)),
  publishRule: (id: UUID, request: RulePublishRequest) => apiClient.post<ApiV2Envelope<BusinessRuleVersion>>(ENDPOINTS.RULES.PUBLISH(id), request, commandInit()),
  transitionRule: (id: UUID, command: "pause" | "resume" | "retire", request: LifecycleRequest) => apiClient.post<ApiV2Envelope<BusinessRule>>(ENDPOINTS.RULES[command.toUpperCase() as "PAUSE" | "RESUME" | "RETIRE"](id), request, commandInit()),
  evaluateRule: (id: UUID, request: RuleEvaluateRequest) => apiClient.post<ApiV2Envelope<RuleExecution>>(ENDPOINTS.RULES.EVALUATE(id), request),
  getRuleImpact: (id: UUID) => apiClient.get<ApiV2Envelope<DependencyImpact>>(ENDPOINTS.RULES.IMPACT(id)),
  listExecutions: (filters: ExecutionFilters = {}) => apiClient.get<ApiV2Envelope<readonly RuleExecution[]>>(query(ENDPOINTS.RULE_EXECUTIONS.LIST, filters)),
  getExecution: (id: UUID) => apiClient.get<ApiV2Envelope<RuleExecution>>(ENDPOINTS.RULE_EXECUTIONS.DETAIL(id)),
  getConfiguration: () => apiClient.get<RuntimeConfiguration>(ENDPOINTS.CONFIGURATION.DETAIL),
  updateConfiguration: (request: ConfigurationUpdateRequest) => apiClient.patch<RuntimeConfiguration>(ENDPOINTS.CONFIGURATION.UPDATE, request, commandInit()),
  previewConfiguration: (request: ConfigurationPreviewRequest) => apiClient.post<ConfigurationPreview>(ENDPOINTS.CONFIGURATION.PREVIEW, request, commandInit()),
  listConfigurationVersions: () => apiClient.get<ApiV2Envelope<readonly RuntimeConfigurationVersion[]>>(ENDPOINTS.CONFIGURATION.VERSIONS),
  rollbackConfiguration: (request: ConfigurationRollbackRequest) => apiClient.post<RuntimeConfiguration>(ENDPOINTS.CONFIGURATION.ROLLBACK, request, commandInit()),
  listConfigurationAudit: () => apiClient.get<ApiV2Envelope<readonly ConfigurationAuditRecord[]>>(ENDPOINTS.CONFIGURATION.AUDIT),
  importConfiguration: (request: ConfigurationImportRequest) => apiClient.post<RuntimeConfiguration>(ENDPOINTS.CONFIGURATION.IMPORT, request, commandInit()),
  exportConfiguration: () => apiClient.get<import("../contracts").ConfigurationExportDocument>(ENDPOINTS.CONFIGURATION.EXPORT),
  getHealth: () => apiClient.get<ApiV2Envelope<CustomizationHealth>>(ENDPOINTS.HEALTH),
};
