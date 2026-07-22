import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiV2Envelope,
  type ApiV2Page,
  type BackupExecutionCreateRequest,
  type BackupExecutionReceipt,
  type BackupExecutionStatus,
  type BackupDisasterRecoveryConfiguration,
  type BDRConfigurationMutation,
  type BDRConfigurationExport,
  type BDRConfigurationPreview,
  type BDRConfigurationRollbackRequest,
  type BDRConfigurationVersion,
  type DRExercise,
  type DRExerciseCancelRequest,
  type DRExerciseCreateRequest,
  type DRExerciseStartRequest,
  type DRExerciseUpdateRequest,
  type DRRunbook,
  type DRRunbookCreateRequest,
  type DRRunbookUpdateRequest,
  type DRStepExecution,
  type DurableJobReceipt,
  type ExerciseFilters,
  type GovernedErrorDTO,
  type GovernedFieldError,
  type GovernedValidationDetail,
  type ObjectiveReport,
  type ObjectiveReportFilters,
  type PaginatedResult,
  type ReadinessSummary,
  type RecoveryPoint,
  type RecoveryPointExpireRequest,
  type RecoveryPointFilters,
  type RecoveryPointVerifyRequest,
  type RestoreRun,
  type RestoreRunCancelRequest,
  type RestoreRunCreateRequest,
  type RestoreRunExecuteRequest,
  type RestoreRunFilters,
  type RunbookFilters,
  type RunbookStep,
  type RunbookStepCreateRequest,
  type RunbookStepReorderRequest,
  type RunbookStepUpdateRequest,
  type RunbookTransitionRequest,
  type StepExecutionFilters,
  type UUID,
} from '../contracts';

export class BackupDisasterRecoveryError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly fieldErrors: readonly GovernedFieldError[] = [],
  ) {
    super(message);
    this.name = 'BackupDisasterRecoveryError';
  }
}

const validationFields = [
  'name', 'slug', 'scope_type', 'scope_ref', 'backup_type', 'recovery_point_id',
  'target_environment', 'target_ref', 'restore_mode', 'selected_components',
  'runbook_id', 'scheduled_for', 'exercise_type', 'environment',
  'rpo_target_seconds', 'rto_target_seconds', 'parameters', 'non_field_errors',
  'document', 'environment', 'rollout',
] as const satisfies readonly (keyof GovernedValidationDetail)[];

const isMessages = (
  value: readonly string[] | string | number | undefined,
): value is readonly string[] => Array.isArray(value) && value.every((item: object) => typeof item === 'string');

const toFieldErrors = (detail: GovernedValidationDetail | null): readonly GovernedFieldError[] => {
  if (!detail) return [];
  return validationFields.flatMap((field) => {
    const messages = detail[field];
    return isMessages(messages) ? messages.map((message) => ({ field, code: 'invalid', message })) : [];
  });
};

const asModuleError = (error: Error): BackupDisasterRecoveryError => {
  if (error instanceof BackupDisasterRecoveryError) return error;
  if (error instanceof ApiError) {
    const details = error.details as GovernedErrorDTO | undefined;
    return new BackupDisasterRecoveryError(
      details?.error.message ?? error.message,
      error.status,
      details?.error.code ?? 'request_failed',
      details?.error.correlation_id ?? null,
      toFieldErrors(details?.error.detail ?? null),
    );
  }
  return new BackupDisasterRecoveryError(error.message, 0, 'network_error', null);
};

const request = async <T>(operation: () => Promise<ApiV2Envelope<T>>): Promise<T> => {
  try {
    return (await operation()).data;
  } catch (error) {
    throw asModuleError(error instanceof Error ? error : new Error('Request failed'));
  }
};

const requestPage = async <T>(operation: () => Promise<ApiV2Page<T>>): Promise<PaginatedResult<T>> => {
  try {
    const envelope = await operation();
    return {
      items: envelope.data,
      pagination: envelope.meta.pagination,
      correlationId: envelope.meta.correlation_id,
    };
  } catch (error) {
    throw asModuleError(error instanceof Error ? error : new Error('Request failed'));
  }
};

const append = (query: URLSearchParams, key: string, value: string | number | undefined): void => {
  if (value !== undefined && value !== '') query.set(key, String(value));
};

const withQuery = (path: string, query: URLSearchParams): string => {
  const serialized = query.toString();
  return serialized ? `${path}?${serialized}` : path;
};

const recoveryPointQuery = (filters: RecoveryPointFilters): string => {
  const query = new URLSearchParams();
  append(query, 'status', filters.status);
  append(query, 'scope_type', filters.scope_type);
  append(query, 'scope_ref', filters.scope_ref);
  append(query, 'captured_after', filters.captured_after);
  append(query, 'captured_before', filters.captured_before);
  append(query, 'search', filters.search);
  append(query, 'ordering', filters.ordering);
  append(query, 'page', filters.page);
  append(query, 'page_size', filters.page_size);
  return withQuery(ENDPOINTS.RECOVERY_POINTS.LIST, query);
};

const restoreRunQuery = (filters: RestoreRunFilters): string => {
  const query = new URLSearchParams();
  append(query, 'status', filters.status);
  append(query, 'target_environment', filters.target_environment);
  append(query, 'recovery_point', filters.recovery_point);
  append(query, 'requested_after', filters.requested_after);
  append(query, 'requested_before', filters.requested_before);
  append(query, 'page', filters.page);
  append(query, 'page_size', filters.page_size);
  return withQuery(ENDPOINTS.RESTORE_RUNS.LIST, query);
};

const runbookQuery = (filters: RunbookFilters): string => {
  const query = new URLSearchParams();
  append(query, 'status', filters.status);
  append(query, 'scope_type', filters.scope_type);
  append(query, 'owner_id', filters.owner_id);
  append(query, 'search', filters.search);
  append(query, 'ordering', filters.ordering);
  append(query, 'page', filters.page);
  append(query, 'page_size', filters.page_size);
  return withQuery(ENDPOINTS.RUNBOOKS.LIST, query);
};

const exerciseQuery = (filters: ExerciseFilters): string => {
  const query = new URLSearchParams();
  append(query, 'status', filters.status);
  append(query, 'exercise_type', filters.exercise_type);
  append(query, 'runbook', filters.runbook);
  append(query, 'scheduled_after', filters.scheduled_after);
  append(query, 'scheduled_before', filters.scheduled_before);
  append(query, 'page', filters.page);
  append(query, 'page_size', filters.page_size);
  return withQuery(ENDPOINTS.EXERCISES.LIST, query);
};

export const backupDisasterRecoveryService = {
  requestBackup: (payload: BackupExecutionCreateRequest) =>
    request(() => apiClient.post<ApiV2Envelope<BackupExecutionReceipt>>(ENDPOINTS.BACKUP_EXECUTIONS.CREATE, payload)),
  getBackupStatus: (backupJobId: UUID) =>
    request(() => apiClient.get<ApiV2Envelope<BackupExecutionStatus>>(ENDPOINTS.BACKUP_EXECUTIONS.DETAIL(backupJobId))),

  listRecoveryPoints: (filters: RecoveryPointFilters = {}) =>
    requestPage(() => apiClient.get<ApiV2Page<RecoveryPoint>>(recoveryPointQuery(filters))),
  getRecoveryPoint: (id: UUID) =>
    request(() => apiClient.get<ApiV2Envelope<RecoveryPoint>>(ENDPOINTS.RECOVERY_POINTS.DETAIL(id))),
  verifyRecoveryPoint: (id: UUID, payload: RecoveryPointVerifyRequest) =>
    request(() => apiClient.post<ApiV2Envelope<DurableJobReceipt>>(ENDPOINTS.RECOVERY_POINTS.VERIFY(id), payload)),
  expireRecoveryPoint: (id: UUID, payload: RecoveryPointExpireRequest) =>
    request(() => apiClient.post<ApiV2Envelope<RecoveryPoint>>(ENDPOINTS.RECOVERY_POINTS.EXPIRE(id), payload)),

  listRestoreRuns: (filters: RestoreRunFilters = {}) =>
    requestPage(() => apiClient.get<ApiV2Page<RestoreRun>>(restoreRunQuery(filters))),
  getRestoreRun: (id: UUID) =>
    request(() => apiClient.get<ApiV2Envelope<RestoreRun>>(ENDPOINTS.RESTORE_RUNS.DETAIL(id))),
  createRestoreRun: (payload: RestoreRunCreateRequest) =>
    request(() => apiClient.post<ApiV2Envelope<RestoreRun>>(ENDPOINTS.RESTORE_RUNS.CREATE, payload)),
  executeRestoreRun: (id: UUID, payload: RestoreRunExecuteRequest) =>
    request(() => apiClient.post<ApiV2Envelope<DurableJobReceipt>>(ENDPOINTS.RESTORE_RUNS.EXECUTE(id), payload)),
  cancelRestoreRun: (id: UUID, payload: RestoreRunCancelRequest) =>
    request(() => apiClient.post<ApiV2Envelope<RestoreRun>>(ENDPOINTS.RESTORE_RUNS.CANCEL(id), payload)),

  listRunbooks: (filters: RunbookFilters = {}) =>
    requestPage(() => apiClient.get<ApiV2Page<DRRunbook>>(runbookQuery(filters))),
  getRunbook: (id: UUID) =>
    request(() => apiClient.get<ApiV2Envelope<DRRunbook>>(ENDPOINTS.RUNBOOKS.DETAIL(id))),
  createRunbook: (payload: DRRunbookCreateRequest) =>
    request(() => apiClient.post<ApiV2Envelope<DRRunbook>>(ENDPOINTS.RUNBOOKS.CREATE, payload)),
  updateRunbook: (id: UUID, payload: DRRunbookUpdateRequest) =>
    request(() => apiClient.patch<ApiV2Envelope<DRRunbook>>(ENDPOINTS.RUNBOOKS.UPDATE(id), payload)),
  deleteRunbook: async (id: UUID): Promise<void> => {
    try {
      await apiClient.delete<void>(ENDPOINTS.RUNBOOKS.DELETE(id));
    } catch (error) {
      throw asModuleError(error instanceof Error ? error : new Error('Request failed'));
    }
  },
  cloneRunbook: (id: UUID) =>
    request(() => apiClient.post<ApiV2Envelope<DRRunbook>>(ENDPOINTS.RUNBOOKS.CLONE(id))),
  publishRunbook: (id: UUID, payload: RunbookTransitionRequest) =>
    request(() => apiClient.post<ApiV2Envelope<DRRunbook>>(ENDPOINTS.RUNBOOKS.PUBLISH(id), payload)),
  retireRunbook: (id: UUID, payload: RunbookTransitionRequest) =>
    request(() => apiClient.post<ApiV2Envelope<DRRunbook>>(ENDPOINTS.RUNBOOKS.RETIRE(id), payload)),
  reorderRunbookSteps: (id: UUID, payload: RunbookStepReorderRequest) =>
    request(() => apiClient.post<ApiV2Envelope<readonly RunbookStep[]>>(ENDPOINTS.RUNBOOKS.REORDER_STEPS(id), payload)),

  listRunbookSteps: (runbookId: UUID) => {
    const query = new URLSearchParams({ runbook_id: runbookId });
    return requestPage(() => apiClient.get<ApiV2Page<RunbookStep>>(withQuery(ENDPOINTS.RUNBOOK_STEPS.LIST, query)));
  },
  getRunbookStep: (id: UUID) =>
    request(() => apiClient.get<ApiV2Envelope<RunbookStep>>(ENDPOINTS.RUNBOOK_STEPS.DETAIL(id))),
  createRunbookStep: (payload: RunbookStepCreateRequest) =>
    request(() => apiClient.post<ApiV2Envelope<RunbookStep>>(ENDPOINTS.RUNBOOK_STEPS.CREATE, payload)),
  updateRunbookStep: (id: UUID, payload: RunbookStepUpdateRequest) =>
    request(() => apiClient.patch<ApiV2Envelope<RunbookStep>>(ENDPOINTS.RUNBOOK_STEPS.UPDATE(id), payload)),
  deleteRunbookStep: async (id: UUID): Promise<void> => {
    try {
      await apiClient.delete<void>(ENDPOINTS.RUNBOOK_STEPS.DELETE(id));
    } catch (error) {
      throw asModuleError(error instanceof Error ? error : new Error('Request failed'));
    }
  },

  listExercises: (filters: ExerciseFilters = {}) =>
    requestPage(() => apiClient.get<ApiV2Page<DRExercise>>(exerciseQuery(filters))),
  getExercise: (id: UUID) =>
    request(() => apiClient.get<ApiV2Envelope<DRExercise>>(ENDPOINTS.EXERCISES.DETAIL(id))),
  createExercise: (payload: DRExerciseCreateRequest) =>
    request(() => apiClient.post<ApiV2Envelope<DRExercise>>(ENDPOINTS.EXERCISES.CREATE, payload)),
  updateExercise: (id: UUID, payload: DRExerciseUpdateRequest) =>
    request(() => apiClient.patch<ApiV2Envelope<DRExercise>>(ENDPOINTS.EXERCISES.UPDATE(id), payload)),
  startExercise: (id: UUID, payload: DRExerciseStartRequest) =>
    request(() => apiClient.post<ApiV2Envelope<DurableJobReceipt>>(ENDPOINTS.EXERCISES.START(id), payload)),
  cancelExercise: (id: UUID, payload: DRExerciseCancelRequest) =>
    request(() => apiClient.post<ApiV2Envelope<DRExercise>>(ENDPOINTS.EXERCISES.CANCEL(id), payload)),

  listStepExecutions: (filters: StepExecutionFilters) => {
    const query = new URLSearchParams();
    append(query, 'exercise', filters.exercise);
    append(query, 'runbook_step', filters.runbook_step);
    append(query, 'status', filters.status);
    append(query, 'page', filters.page);
    append(query, 'page_size', filters.page_size);
    return requestPage(() => apiClient.get<ApiV2Page<DRStepExecution>>(withQuery(ENDPOINTS.STEP_EXECUTIONS.LIST, query)));
  },
  getStepExecution: (id: UUID) =>
    request(() => apiClient.get<ApiV2Envelope<DRStepExecution>>(ENDPOINTS.STEP_EXECUTIONS.DETAIL(id))),

  getReadiness: () => request(() => apiClient.get<ApiV2Envelope<ReadinessSummary>>(ENDPOINTS.READINESS)),
  getObjectiveReport: (filters: ObjectiveReportFilters) => {
    const query = new URLSearchParams();
    append(query, 'runbook_id', filters.runbook_id);
    append(query, 'from', filters.from);
    append(query, 'to', filters.to);
    append(query, 'bucket', filters.bucket);
    return request(() => apiClient.get<ApiV2Envelope<ObjectiveReport>>(withQuery(ENDPOINTS.REPORTS.OBJECTIVES, query)));
  },

  getConfiguration: () => request(() => apiClient.get<ApiV2Envelope<BackupDisasterRecoveryConfiguration>>(ENDPOINTS.CONFIGURATIONS.CURRENT)),
  updateConfiguration: (payload: BDRConfigurationMutation) =>
    request(() => apiClient.patch<ApiV2Envelope<BackupDisasterRecoveryConfiguration>>(ENDPOINTS.CONFIGURATIONS.CURRENT, payload)),
  previewConfiguration: (payload: BDRConfigurationMutation) =>
    request(() => apiClient.post<ApiV2Envelope<BDRConfigurationPreview>>(ENDPOINTS.CONFIGURATIONS.PREVIEW, payload)),
  listConfigurationVersions: () =>
    request(() => apiClient.get<ApiV2Envelope<readonly BDRConfigurationVersion[]>>(ENDPOINTS.CONFIGURATIONS.VERSIONS)),
  rollbackConfiguration: (payload: BDRConfigurationRollbackRequest) =>
    request(() => apiClient.post<ApiV2Envelope<BackupDisasterRecoveryConfiguration>>(ENDPOINTS.CONFIGURATIONS.ROLLBACK, payload)),
  importConfiguration: (payload: BDRConfigurationMutation) =>
    request(() => apiClient.post<ApiV2Envelope<BackupDisasterRecoveryConfiguration>>(ENDPOINTS.CONFIGURATIONS.IMPORT, payload)),
  exportConfiguration: () =>
    request(() => apiClient.get<ApiV2Envelope<BDRConfigurationExport>>(ENDPOINTS.CONFIGURATIONS.EXPORT)),
};

// Compatibility with the repository's historic snake_case symbol while callers migrate.
export const backup_disaster_recoveryService = backupDisasterRecoveryService;
