/** Governed v2 contracts for the Compliance Risk Management open-source module. */
export const MODULE_API_PREFIX = '/api/v2/compliance-risk-management';

export type UUID = string;
export type ISODate = string;
export type ISODateTime = string;
export type Ordering = string;
export type RiskCategory = 'operational' | 'financial' | 'compliance' | 'strategic' | 'technology' | 'reputational';
export type RiskLevel = 'negligible' | 'low' | 'medium' | 'high' | 'critical';
export type RiskStatus = 'identified' | 'assessed' | 'mitigating' | 'accepted' | 'closed';
export type ControlFrequency = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annually' | 'custom';
export type ControlStatus = 'draft' | 'active' | 'retired';
export type TestResult = 'not_tested' | 'passed' | 'failed' | 'partially_passed';
export type TestStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled';
export type Applicability = 'mandatory' | 'conditional' | 'recommended';
export type RequirementStatus = 'not_assessed' | 'compliant' | 'partially_compliant' | 'non_compliant';
export type CalendarEventType = 'deadline' | 'review' | 'submission' | 'audit' | 'renewal';
export type CalendarStatus = 'upcoming' | 'overdue' | 'completed' | 'cancelled';
export type RemediationPriority = 'low' | 'medium' | 'high' | 'critical';
export type RemediationStatus = 'planned' | 'in_progress' | 'overdue' | 'completed' | 'cancelled';
export type Environment = 'development' | 'staging' | 'production';

export interface ApiPageMeta { page: number; page_size: number; count: number; total_pages: number; has_next: boolean; has_previous: boolean }
export interface ApiMeta { correlation_id: string; timestamp: ISODateTime; pagination?: ApiPageMeta }
export interface ApiSuccess<T> { data: T; meta: ApiMeta }
export interface GovernedFieldError { field: string; code: string; message: string }
export interface GovernedErrorDetail { fields?: readonly GovernedFieldError[]; retryable?: boolean }
export interface GovernedError { code: string; message: string; detail?: GovernedErrorDetail | string; correlation_id: string }
export interface ApiFailure { error: GovernedError }
export interface Paginated<T> { items: T[]; pagination: ApiPageMeta; correlation_id: string }

export interface AuditFields { id: UUID; created_at: ISODateTime; updated_at: ISODateTime; created_by_id: UUID; updated_by_id: UUID | null }
export interface TransitionRecord { command: string; from: string; to: string; actor_id: UUID; correlation_id: string; rationale?: string; occurred_at: ISODateTime }
export interface EvidenceReference { document_id: UUID; version_id: UUID; label: string; checksum: string }

export interface RiskAssessment extends AuditFields {
  risk_code: string; name: string; category: RiskCategory; description: string;
  likelihood: number; impact: number; inherent_score: string;
  residual_likelihood: number | null; residual_impact: number | null; residual_score: string | null;
  risk_level: RiskLevel; qualitative_rationale: string; mitigation_strategy: string;
  owner_id: UUID; review_date: ISODate; status: RiskStatus; accepted_until: ISODate | null;
  closed_at: ISODateTime | null; transition_history: TransitionRecord[];
}
export interface RiskAssessmentCreate { risk_code: string; name: string; category: RiskCategory; description: string; likelihood: number; impact: number; residual_likelihood?: number | null; residual_impact?: number | null; qualitative_rationale?: string; mitigation_strategy?: string; owner_id: UUID; review_date: ISODate; residual_override_rationale?: string }
export type RiskAssessmentUpdate = Partial<Omit<RiskAssessmentCreate, 'risk_code'>>;
export interface RiskTransition { command: 'assess' | 'start_mitigation' | 'accept' | 'close' | 'reopen'; transition_key: string; context: { rationale?: string; accepted_until?: ISODate; residual_override_rationale?: string } }
export interface RiskScorePreviewInput { likelihood: number; impact: number; residual_likelihood?: number | null; residual_impact?: number | null }
export interface RiskScorePreview { inherent_score: string; residual_score: string | null; risk_level: RiskLevel; likelihood_scale_max: number; impact_scale_max: number; explanation: { formula: string; likelihood: number; impact: number; threshold_version: number; matched_upper_bound: number } }
export interface RiskFilters { search?: string; category?: RiskCategory; risk_level?: RiskLevel; status?: RiskStatus; owner_id?: UUID; review_from?: ISODate; review_to?: ISODate; likelihood?: number; impact?: number; ordering?: Ordering; page?: number; page_size?: number }

export interface Control extends AuditFields { risk_id: UUID; control_code: string; name: string; description: string; test_procedure: string; frequency: ControlFrequency; frequency_days: number | null; owner_id: UUID; default_tester_id: UUID | null; next_test_due: ISODate; status: ControlStatus; transition_history: TransitionRecord[] }
export interface ControlCreate { risk_id: UUID; control_code: string; name: string; description: string; test_procedure: string; frequency: ControlFrequency; frequency_days?: number | null; owner_id: UUID; default_tester_id?: UUID | null; next_test_due: ISODate }
export type ControlUpdate = Partial<Omit<ControlCreate, 'risk_id' | 'control_code'>>;
export interface ControlTransition { command: 'activate' | 'retire' | 'reactivate'; transition_key: string }
export interface ControlFilters { risk_id?: UUID; status?: ControlStatus; frequency?: ControlFrequency; owner_id?: UUID; due_from?: ISODate; due_to?: ISODate; ordering?: Ordering; page?: number; page_size?: number }

export interface ControlTest extends AuditFields { control_id: UUID; scheduled_for: ISODate; started_at: ISODateTime | null; completed_at: ISODateTime | null; tester_id: UUID; result: TestResult; findings: string; evidence: EvidenceReference[]; status: TestStatus; cancellation_reason: string; transition_history: TransitionRecord[] }
export interface ControlTestCreate { control_id: UUID; scheduled_for: ISODate; tester_id: UUID }
export type ControlTestUpdate = Partial<Pick<ControlTestCreate, 'scheduled_for' | 'tester_id'>>;
export interface ControlTestResultInput { result: Exclude<TestResult, 'not_tested'>; findings?: string; evidence: EvidenceReference[]; remediation?: Omit<RemediationCreate, 'risk_id' | 'control_test_id'> }
export interface TestTransitionInput { transition_key: string }
export interface TestCancellationInput extends TestTransitionInput { reason: string }
export interface ControlTestFilters { control_id?: UUID; risk_id?: UUID; status?: TestStatus; result?: TestResult; tester_id?: UUID; date_from?: ISODate; date_to?: ISODate; ordering?: Ordering; page?: number; page_size?: number }

export interface ComplianceRequirement extends AuditFields { regulation_code: string; requirement_code: string; regulation_name: string; title: string; description: string; applicability: Applicability; applicability_rationale: string; status: RequirementStatus; owner_id: UUID; effective_date: ISODate | null; due_date: ISODate | null; last_assessed_at: ISODateTime | null; source_url: string; cross_references: UUID[]; transition_history: TransitionRecord[] }
export interface RequirementCreate { regulation_code: string; requirement_code: string; regulation_name: string; title: string; description: string; applicability: Applicability; applicability_rationale?: string; owner_id: UUID; effective_date?: ISODate | null; due_date?: ISODate | null; source_url?: string; cross_references?: UUID[] }
export type RequirementUpdate = Partial<Omit<RequirementCreate, 'regulation_code' | 'requirement_code'>>;
export interface RequirementAssessment { command: 'assess_compliant' | 'assess_partial' | 'assess_non_compliant' | 'remediate'; evidence: EvidenceReference[]; rationale: string; transition_key: string }
export interface RequirementFilters { search?: string; regulation_code?: string; applicability?: Applicability; status?: RequirementStatus; owner_id?: UUID; due_from?: ISODate; due_to?: ISODate; ordering?: Ordering; page?: number; page_size?: number }

export interface ComplianceCalendarEntry extends AuditFields { requirement_id: UUID; title: string; event_type: CalendarEventType; scheduled_date: ISODate; reminder_days: number[]; assigned_to_id: UUID; status: CalendarStatus; completed_date: ISODate | null; completion_notes: string; transition_history: TransitionRecord[] }
export interface CalendarEntryCreate { requirement_id: UUID; title: string; event_type: CalendarEventType; scheduled_date: ISODate; reminder_days: number[]; assigned_to_id: UUID }
export type CalendarEntryUpdate = Partial<Omit<CalendarEntryCreate, 'requirement_id'>>;
export interface CalendarTransition { command: 'complete' | 'cancel'; transition_key: string; context: { completion_date?: ISODate; completion_notes?: string; cancellation_reason?: string } }
export interface CalendarFilters { date_from: ISODate; date_to: ISODate; event_type?: CalendarEventType; status?: CalendarStatus; requirement_id?: UUID; assigned_to_id?: UUID; ordering?: Ordering; page?: number; page_size?: number }

export interface RemediationAction extends AuditFields { risk_id: UUID; control_test_id: UUID | null; action_code: string; description: string; assigned_to_id: UUID; due_date: ISODate; priority: RemediationPriority; status: RemediationStatus; completion_date: ISODate | null; completion_evidence: EvidenceReference[]; cancellation_reason: string; transition_history: TransitionRecord[] }
export interface RemediationCreate { risk_id: UUID; control_test_id?: UUID | null; action_code: string; description: string; assigned_to_id: UUID; due_date: ISODate; priority: RemediationPriority }
export type RemediationUpdate = Partial<Omit<RemediationCreate, 'risk_id' | 'action_code' | 'control_test_id'>>;
export interface RemediationTransition { command: 'start' | 'complete' | 'cancel'; transition_key: string; context: { completion_date?: ISODate; completion_evidence?: EvidenceReference[]; cancellation_reason?: string } }
export interface RemediationFilters { risk_id?: UUID; control_test_id?: UUID; status?: RemediationStatus; priority?: RemediationPriority; assigned_to_id?: UUID; due_from?: ISODate; due_to?: ISODate; ordering?: Ordering; page?: number; page_size?: number }

export interface RiskDashboardSummary { total_risks: number; critical_risks: number; overdue_reviews: number; overdue_controls: number; overdue_remediations: number; upcoming_events: number; risks_by_level: Record<RiskLevel, number>; risks_by_status: Record<RiskStatus, number>; overdue_work: { id: UUID; kind: 'risk' | 'control' | 'calendar' | 'remediation'; label: string; due_date: ISODate }[]; upcoming_compliance_events: ComplianceCalendarEntry[] }
export interface DashboardFilters { category?: RiskCategory; owner_id?: UUID; date_from?: ISODate; date_to?: ISODate }
export interface HeatmapFilters { category?: RiskCategory; owner_id?: UUID; status?: RiskStatus }
export interface HeatmapCell { likelihood: number; impact: number; count: number; level: RiskLevel; risk_ids: UUID[] }

export interface LevelThresholds { negligible: number; low: number; medium: number; high: number; critical: number }
export interface FeatureCohortRule { roles: string[]; cohorts: string[]; enabled: boolean }
export interface RiskConfigurationDocument { likelihood_scale_max: number; impact_scale_max: number; level_thresholds: LevelThresholds; default_review_days: number; default_reminder_days: number[]; acceptance_max_days: number; overdue_job_enabled: boolean; feature_flags: { risk_heatmap: FeatureCohortRule; recurring_control_tests: FeatureCohortRule; compliance_reminders: FeatureCohortRule } }
export interface RiskConfiguration extends AuditFields, RiskConfigurationDocument { environment: Environment; version: number; published_at: ISODateTime; published_by_id: UUID }
export interface ConfigurationPreviewInput { environment: Environment; candidate: RiskConfigurationDocument }
export interface ConfigurationPreview { valid: boolean; validation_errors: GovernedFieldError[]; score_band_changes: { score: number; from: RiskLevel; to: RiskLevel }[]; affected_record_counts: { risks: number; controls: number; calendar_entries: number } }
export interface ConfigurationPublishInput extends ConfigurationPreviewInput { expected_version: number; change_summary: string }
export interface RiskConfigurationVersion { id: UUID; environment: Environment; version: number; configuration: RiskConfigurationDocument; change_summary: string; actor_id: UUID; correlation_id: string; created_at: ISODateTime; restored_from_version: number | null }
export interface ConfigurationRollbackInput { environment: Environment; version: number; expected_version: number; change_summary: string }
export interface ConfigurationExportDocument { schema: 'saraise.compliance-risk.configuration'; schema_version: 1; environment: Environment; version: number; configuration: RiskConfigurationDocument }
export interface ConfigurationImportInput { environment: Environment; document: ConfigurationExportDocument; dry_run: boolean; expected_version?: number; change_summary?: string }

export interface DurableJob { id: UUID; name: string; status: 'queued' | 'running' | 'retrying' | 'succeeded' | 'failed' | 'timed_out' | 'cancelled'; attempts: number; correlation_id: string; submitted_at: ISODateTime; completed_at: ISODateTime | null; stable_error_code: string | null }
export interface HealthComponent { name: string; status: 'healthy' | 'degraded' | 'unavailable'; error_code?: string }
export interface HealthStatus { status: 'healthy' | 'degraded' | 'unavailable'; components: HealthComponent[] }

const detail = (resource: string, id: string) => `${MODULE_API_PREFIX}/${resource}/${encodeURIComponent(id)}/` as const;
export const ENDPOINTS = {
  RISKS: { LIST: `${MODULE_API_PREFIX}/risks/`, CREATE: `${MODULE_API_PREFIX}/risks/`, DETAIL: (id: string) => detail('risks', id), UPDATE: (id: string) => detail('risks', id), DELETE: (id: string) => detail('risks', id), TRANSITION: (id: string) => `${detail('risks', id)}transition/` as const, SCORE_PREVIEW: `${MODULE_API_PREFIX}/risks/score-preview/`, CONTROLS: (id: string) => `${detail('risks', id)}controls/` as const, REMEDIATIONS: (id: string) => `${detail('risks', id)}remediations/` as const },
  CONTROLS: { LIST: `${MODULE_API_PREFIX}/controls/`, CREATE: `${MODULE_API_PREFIX}/controls/`, DETAIL: (id: string) => detail('controls', id), UPDATE: (id: string) => detail('controls', id), DELETE: (id: string) => detail('controls', id), TRANSITION: (id: string) => `${detail('controls', id)}transition/` as const, TESTS: (id: string) => `${detail('controls', id)}tests/` as const },
  TESTS: { LIST: `${MODULE_API_PREFIX}/tests/`, DETAIL: (id: string) => detail('tests', id), UPDATE: (id: string) => detail('tests', id), START: (id: string) => `${detail('tests', id)}start/` as const, RESULT: (id: string) => `${detail('tests', id)}result/` as const, CANCEL: (id: string) => `${detail('tests', id)}cancel/` as const },
  REQUIREMENTS: { LIST: `${MODULE_API_PREFIX}/requirements/`, CREATE: `${MODULE_API_PREFIX}/requirements/`, DETAIL: (id: string) => detail('requirements', id), UPDATE: (id: string) => detail('requirements', id), DELETE: (id: string) => detail('requirements', id), ASSESS: (id: string) => `${detail('requirements', id)}assess/` as const },
  CALENDAR: { LIST: `${MODULE_API_PREFIX}/calendar/`, CREATE: `${MODULE_API_PREFIX}/calendar/`, DETAIL: (id: string) => detail('calendar', id), UPDATE: (id: string) => detail('calendar', id), DELETE: (id: string) => detail('calendar', id), TRANSITION: (id: string) => `${detail('calendar', id)}transition/` as const },
  REMEDIATIONS: { LIST: `${MODULE_API_PREFIX}/remediations/`, CREATE: `${MODULE_API_PREFIX}/remediations/`, DETAIL: (id: string) => detail('remediations', id), UPDATE: (id: string) => detail('remediations', id), DELETE: (id: string) => detail('remediations', id), TRANSITION: (id: string) => `${detail('remediations', id)}transition/` as const },
  DASHBOARD: `${MODULE_API_PREFIX}/dashboard/`, HEATMAP: `${MODULE_API_PREFIX}/heatmap/`,
  CONFIGURATION: { ACTIVE: `${MODULE_API_PREFIX}/configuration/`, PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`, VERSIONS: `${MODULE_API_PREFIX}/configuration/versions/`, VERSION: (version: number) => `${MODULE_API_PREFIX}/configuration/versions/${version}/` as const, ROLLBACK: `${MODULE_API_PREFIX}/configuration/rollback/`, EXPORT: `${MODULE_API_PREFIX}/configuration/export/`, IMPORT: `${MODULE_API_PREFIX}/configuration/import/` },
  JOB: (id: string) => `${MODULE_API_PREFIX}/jobs/${encodeURIComponent(id)}/` as const,
  HEALTH: { LIVE: `${MODULE_API_PREFIX}/health/live/`, READY: `${MODULE_API_PREFIX}/health/ready/` },
} as const;
