import { ApiError, apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  ApiMeta, ApiSuccess, CalendarEntryCreate, CalendarEntryUpdate, CalendarFilters, CalendarTransition,
  ComplianceCalendarEntry, ComplianceRequirement, ConfigurationExportDocument, ConfigurationImportInput,
  ConfigurationPreview, ConfigurationPreviewInput, ConfigurationPublishInput, ConfigurationRollbackInput,
  Control, ControlCreate, ControlFilters, ControlTest, ControlTestCreate, ControlTestFilters,
  ControlTestResultInput, ControlTestUpdate, ControlTransition, ControlUpdate, DashboardFilters,
  DurableJob, Environment, HealthStatus, HeatmapCell, HeatmapFilters, Paginated, RemediationAction,
  RemediationCreate, RemediationFilters, RemediationTransition, RemediationUpdate, RequirementAssessment,
  RequirementCreate, RequirementFilters, RequirementUpdate, RiskAssessment, RiskAssessmentCreate,
  RiskAssessmentUpdate, RiskConfiguration, RiskConfigurationVersion, RiskDashboardSummary, RiskFilters,
  RiskScorePreview, RiskScorePreviewInput, RiskTransition, TestCancellationInput, TestTransitionInput,
} from '../contracts';

export class ComplianceRiskApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string, readonly correlationId?: string, readonly detail?: unknown) {
    super(message); this.name = 'ComplianceRiskApiError';
  }
}

function rethrow(error: unknown): never {
  if (error instanceof ApiError) throw new ComplianceRiskApiError(error.message, error.status, error.code, error.correlationId, error.details);
  throw error;
}

async function request<T>(work: () => Promise<ApiSuccess<T>>): Promise<T> {
  try { return (await work()).data; } catch (error) { rethrow(error); }
}

async function page<T>(work: () => Promise<ApiSuccess<T[]>>): Promise<Paginated<T>> {
  try {
    const response = await work();
    const pagination = response.meta.pagination;
    if (!pagination) throw new ComplianceRiskApiError('The governed response omitted pagination metadata.', 502, 'INVALID_RESPONSE', response.meta.correlation_id);
    return { items: response.data, pagination, correlation_id: response.meta.correlation_id };
  } catch (error) { if (error instanceof ComplianceRiskApiError) throw error; rethrow(error); }
}

type QueryValue = string | number | boolean | null | undefined;
function withQuery(path: string, values: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values) as [string, QueryValue][]) {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  }
  const encoded = query.toString(); return encoded ? `${path}?${encoded}` : path;
}

const get = <T>(path: string) => request(() => apiClient.get<ApiSuccess<T>>(path));
const post = <T, P>(path: string, payload: P) => request(() => apiClient.post<ApiSuccess<T>>(path, payload));
const patch = <T, P>(path: string, payload: P) => request(() => apiClient.patch<ApiSuccess<T>>(path, payload));
const put = <T, P>(path: string, payload: P) => request(() => apiClient.put<ApiSuccess<T>>(path, payload));
const remove = async (path: string): Promise<void> => { try { await apiClient.delete<void>(path); } catch (error) { rethrow(error); } };
const list = <T>(path: string) => page(() => apiClient.get<ApiSuccess<T[]>>(path));
const envQuery = (path: string, environment: Environment) => withQuery(path, { environment });

export const complianceRiskQueryKeys = {
  all: (tenantId: string | null) => ['compliance-risk-management', tenantId] as const,
  risks: (tenantId: string | null, filters: RiskFilters) => [...complianceRiskQueryKeys.all(tenantId), 'risks', filters, filters.page ?? 1, filters.page_size ?? 25] as const,
  risk: (tenantId: string | null, id: string) => [...complianceRiskQueryKeys.all(tenantId), 'risk', id] as const,
  controls: (tenantId: string | null, filters: ControlFilters) => [...complianceRiskQueryKeys.all(tenantId), 'controls', filters, filters.page ?? 1, filters.page_size ?? 25] as const,
  control: (tenantId: string | null, id: string) => [...complianceRiskQueryKeys.all(tenantId), 'control', id] as const,
  tests: (tenantId: string | null, filters: ControlTestFilters) => [...complianceRiskQueryKeys.all(tenantId), 'tests', filters, filters.page ?? 1, filters.page_size ?? 25] as const,
  test: (tenantId: string | null, id: string) => [...complianceRiskQueryKeys.all(tenantId), 'test', id] as const,
  requirements: (tenantId: string | null, filters: RequirementFilters) => [...complianceRiskQueryKeys.all(tenantId), 'requirements', filters, filters.page ?? 1, filters.page_size ?? 25] as const,
  requirement: (tenantId: string | null, id: string) => [...complianceRiskQueryKeys.all(tenantId), 'requirement', id] as const,
  calendar: (tenantId: string | null, filters: CalendarFilters) => [...complianceRiskQueryKeys.all(tenantId), 'calendar', filters, filters.page ?? 1, filters.page_size ?? 25] as const,
  calendarEntry: (tenantId: string | null, id: string) => [...complianceRiskQueryKeys.all(tenantId), 'calendar-entry', id] as const,
  remediations: (tenantId: string | null, filters: RemediationFilters) => [...complianceRiskQueryKeys.all(tenantId), 'remediations', filters, filters.page ?? 1, filters.page_size ?? 25] as const,
  remediation: (tenantId: string | null, id: string) => [...complianceRiskQueryKeys.all(tenantId), 'remediation', id] as const,
  dashboard: (tenantId: string | null, filters: DashboardFilters) => [...complianceRiskQueryKeys.all(tenantId), 'dashboard', filters] as const,
  heatmap: (tenantId: string | null, filters: HeatmapFilters) => [...complianceRiskQueryKeys.all(tenantId), 'heatmap', filters] as const,
  configuration: (tenantId: string | null, environment: Environment) => [...complianceRiskQueryKeys.all(tenantId), 'configuration', environment] as const,
  configurationVersions: (tenantId: string | null, environment: Environment, pageNumber = 1, pageSize = 25) => [...complianceRiskQueryKeys.all(tenantId), 'configuration-versions', environment, pageNumber, pageSize] as const,
  configurationVersion: (tenantId: string | null, environment: Environment, version: number) => [...complianceRiskQueryKeys.all(tenantId), 'configuration-version', environment, version] as const,
  job: (tenantId: string | null, id: string) => [...complianceRiskQueryKeys.all(tenantId), 'job', id] as const,
};

export const complianceRiskService = {
  listRisks: (filters: RiskFilters = {}) => list<RiskAssessment>(withQuery(ENDPOINTS.RISKS.LIST, filters)),
  getRisk: (id: string) => get<RiskAssessment>(ENDPOINTS.RISKS.DETAIL(id)),
  createRisk: (data: RiskAssessmentCreate, idempotencyKey: string) => post<RiskAssessment, RiskAssessmentCreate>(ENDPOINTS.RISKS.CREATE, dataWithIdempotency(data, idempotencyKey)),
  updateRisk: (id: string, data: RiskAssessmentUpdate) => patch<RiskAssessment, RiskAssessmentUpdate>(ENDPOINTS.RISKS.UPDATE(id), data),
  deleteRisk: (id: string) => remove(ENDPOINTS.RISKS.DELETE(id)),
  transitionRisk: (id: string, data: RiskTransition) => post<RiskAssessment, RiskTransition>(ENDPOINTS.RISKS.TRANSITION(id), data),
  previewScore: (data: RiskScorePreviewInput) => post<RiskScorePreview, RiskScorePreviewInput>(ENDPOINTS.RISKS.SCORE_PREVIEW, data),
  listRiskControls: (riskId: string, filters: ControlFilters = {}) => list<Control>(withQuery(ENDPOINTS.RISKS.CONTROLS(riskId), filters)),
  createRiskControl: (riskId: string, data: Omit<ControlCreate, 'risk_id'>) => post<Control, Omit<ControlCreate, 'risk_id'>>(ENDPOINTS.RISKS.CONTROLS(riskId), data),
  listRiskRemediations: (riskId: string, filters: RemediationFilters = {}) => list<RemediationAction>(withQuery(ENDPOINTS.RISKS.REMEDIATIONS(riskId), filters)),
  createRiskRemediation: (riskId: string, data: Omit<RemediationCreate, 'risk_id'>) => post<RemediationAction, Omit<RemediationCreate, 'risk_id'>>(ENDPOINTS.RISKS.REMEDIATIONS(riskId), data),

  listControls: (filters: ControlFilters = {}) => list<Control>(withQuery(ENDPOINTS.CONTROLS.LIST, filters)),
  getControl: (id: string) => get<Control>(ENDPOINTS.CONTROLS.DETAIL(id)),
  createControl: (data: ControlCreate) => post<Control, ControlCreate>(ENDPOINTS.CONTROLS.CREATE, data),
  updateControl: (id: string, data: ControlUpdate) => patch<Control, ControlUpdate>(ENDPOINTS.CONTROLS.UPDATE(id), data),
  deleteControl: (id: string) => remove(ENDPOINTS.CONTROLS.DELETE(id)),
  transitionControl: (id: string, data: ControlTransition) => post<Control, ControlTransition>(ENDPOINTS.CONTROLS.TRANSITION(id), data),
  listControlTests: (controlId: string, filters: ControlTestFilters = {}) => list<ControlTest>(withQuery(ENDPOINTS.CONTROLS.TESTS(controlId), filters)),
  scheduleControlTest: (controlId: string, data: Omit<ControlTestCreate, 'control_id'>, idempotencyKey: string) => post<ControlTest, Omit<ControlTestCreate, 'control_id'>>(ENDPOINTS.CONTROLS.TESTS(controlId), dataWithIdempotency(data, idempotencyKey)),

  listTests: (filters: ControlTestFilters = {}) => list<ControlTest>(withQuery(ENDPOINTS.TESTS.LIST, filters)),
  getTest: (id: string) => get<ControlTest>(ENDPOINTS.TESTS.DETAIL(id)),
  updateScheduledTest: (id: string, data: ControlTestUpdate) => patch<ControlTest, ControlTestUpdate>(ENDPOINTS.TESTS.UPDATE(id), data),
  startTest: (id: string, data: TestTransitionInput) => post<ControlTest, TestTransitionInput>(ENDPOINTS.TESTS.START(id), data),
  recordTestResult: (id: string, data: ControlTestResultInput & TestTransitionInput) => post<ControlTest, ControlTestResultInput & TestTransitionInput>(ENDPOINTS.TESTS.RESULT(id), data),
  cancelTest: (id: string, data: TestCancellationInput) => post<ControlTest, TestCancellationInput>(ENDPOINTS.TESTS.CANCEL(id), data),

  listRequirements: (filters: RequirementFilters = {}) => list<ComplianceRequirement>(withQuery(ENDPOINTS.REQUIREMENTS.LIST, filters)),
  getRequirement: (id: string) => get<ComplianceRequirement>(ENDPOINTS.REQUIREMENTS.DETAIL(id)),
  createRequirement: (data: RequirementCreate) => post<ComplianceRequirement, RequirementCreate>(ENDPOINTS.REQUIREMENTS.CREATE, data),
  updateRequirement: (id: string, data: RequirementUpdate) => patch<ComplianceRequirement, RequirementUpdate>(ENDPOINTS.REQUIREMENTS.UPDATE(id), data),
  deleteRequirement: (id: string) => remove(ENDPOINTS.REQUIREMENTS.DELETE(id)),
  assessRequirement: (id: string, data: RequirementAssessment) => post<ComplianceRequirement, RequirementAssessment>(ENDPOINTS.REQUIREMENTS.ASSESS(id), data),

  listCalendarEntries: (filters: CalendarFilters) => list<ComplianceCalendarEntry>(withQuery(ENDPOINTS.CALENDAR.LIST, filters)),
  getCalendarEntry: (id: string) => get<ComplianceCalendarEntry>(ENDPOINTS.CALENDAR.DETAIL(id)),
  createCalendarEntry: (data: CalendarEntryCreate) => post<ComplianceCalendarEntry, CalendarEntryCreate>(ENDPOINTS.CALENDAR.CREATE, data),
  updateCalendarEntry: (id: string, data: CalendarEntryUpdate) => patch<ComplianceCalendarEntry, CalendarEntryUpdate>(ENDPOINTS.CALENDAR.UPDATE(id), data),
  deleteCalendarEntry: (id: string) => remove(ENDPOINTS.CALENDAR.DELETE(id)),
  transitionCalendarEntry: (id: string, data: CalendarTransition) => post<ComplianceCalendarEntry, CalendarTransition>(ENDPOINTS.CALENDAR.TRANSITION(id), data),

  listRemediations: (filters: RemediationFilters = {}) => list<RemediationAction>(withQuery(ENDPOINTS.REMEDIATIONS.LIST, filters)),
  getRemediation: (id: string) => get<RemediationAction>(ENDPOINTS.REMEDIATIONS.DETAIL(id)),
  createRemediation: (data: RemediationCreate) => post<RemediationAction, RemediationCreate>(ENDPOINTS.REMEDIATIONS.CREATE, data),
  updateRemediation: (id: string, data: RemediationUpdate) => patch<RemediationAction, RemediationUpdate>(ENDPOINTS.REMEDIATIONS.UPDATE(id), data),
  deleteRemediation: (id: string) => remove(ENDPOINTS.REMEDIATIONS.DELETE(id)),
  transitionRemediation: (id: string, data: RemediationTransition) => post<RemediationAction, RemediationTransition>(ENDPOINTS.REMEDIATIONS.TRANSITION(id), data),

  getDashboard: (filters: DashboardFilters = {}) => get<RiskDashboardSummary>(withQuery(ENDPOINTS.DASHBOARD, filters)),
  getHeatmap: (filters: HeatmapFilters = {}) => get<HeatmapCell[]>(withQuery(ENDPOINTS.HEATMAP, filters)),
  getConfiguration: (environment: Environment) => get<RiskConfiguration>(envQuery(ENDPOINTS.CONFIGURATION.ACTIVE, environment)),
  previewConfiguration: (data: ConfigurationPreviewInput) => post<ConfigurationPreview, ConfigurationPreviewInput>(ENDPOINTS.CONFIGURATION.PREVIEW, data),
  publishConfiguration: (data: ConfigurationPublishInput) => put<RiskConfiguration, ConfigurationPublishInput>(ENDPOINTS.CONFIGURATION.ACTIVE, data),
  listConfigurationVersions: (environment: Environment, pageNumber = 1, pageSize = 25) => list<RiskConfigurationVersion>(withQuery(ENDPOINTS.CONFIGURATION.VERSIONS, { environment, page: pageNumber, page_size: pageSize })),
  getConfigurationVersion: (environment: Environment, version: number) => get<RiskConfigurationVersion>(envQuery(ENDPOINTS.CONFIGURATION.VERSION(version), environment)),
  rollbackConfiguration: (data: ConfigurationRollbackInput) => post<RiskConfiguration, ConfigurationRollbackInput>(ENDPOINTS.CONFIGURATION.ROLLBACK, data),
  exportConfiguration: (environment: Environment) => get<ConfigurationExportDocument>(envQuery(ENDPOINTS.CONFIGURATION.EXPORT, environment)),
  importConfiguration: (data: ConfigurationImportInput) => post<ConfigurationPreview | RiskConfiguration, ConfigurationImportInput>(ENDPOINTS.CONFIGURATION.IMPORT, data),
  getJob: (id: string) => get<DurableJob>(ENDPOINTS.JOB(id)),
  getLiveness: () => get<HealthStatus>(ENDPOINTS.HEALTH.LIVE),
  getReadiness: () => get<HealthStatus>(ENDPOINTS.HEALTH.READY),
};

function dataWithIdempotency<T extends object>(data: T, idempotencyKey: string): T & { idempotency_key: string } {
  return { ...data, idempotency_key: idempotencyKey };
}

export type GovernedResponseMeta = ApiMeta;
