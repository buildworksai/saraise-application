import type { BackupDisasterRecoveryConfiguration } from '../contracts';

export const configurationFixture: BackupDisasterRecoveryConfiguration = {
  id: 'configuration-id',
  tenant_id: 'tenant-id',
  environment: 'default',
  version: 1,
  updated_at: '2026-07-23T00:00:00Z',
  rollout: { enabled: true, roles: [], cohorts: [] },
  document: {
    quota_costs: { default: 1, backup_execution: 10, verification: 5, restore_validation: 5, restore_execution: 25, exercise_execution: 20 },
    resilience: { timeout_seconds: 2, max_attempts: 3, initial_backoff_seconds: 0.1, max_backoff_seconds: 2, jitter_seconds: 0.1, circuit_failure_threshold: 3, circuit_reset_seconds: 30, checksum_chunk_bytes: 1048576 },
    health: { probe_timeout_seconds: 2, probe_timeout_max_seconds: 10, provider_stale_seconds: 30, outbox_max_lag_seconds: 60, exercise_freshness_seconds: 86400, registry_staleness_seconds: 30, exercise_registry_staleness_seconds: 86400, queue_degradation_seconds: 300 },
    providers: { storage_adapter_key: 'local-filesystem', local_filesystem_restore_modes: ['full'] },
    runbooks: { default_rpo_seconds: 3600, default_rto_seconds: 14400, objective_min_seconds: 1, objective_max_seconds: 315360000, min_publish_steps: 1, unpublished_scan_limit: 100 },
    steps: { default_timeout_seconds: 300, min_timeout_seconds: 1, max_timeout_seconds: 86400, default_retry_limit: 0, max_retry_limit: 10, default_on_failure: 'stop', allowed_failure_behaviors: ['stop', 'continue_degraded'], max_components: 100, max_verification_checks: 10, allowed_verification_checks: ['connectivity', 'integrity', 'application', 'security'], max_reorder_items: 500, reorder_collision_offset: 1000, require_draft_for_edits: true, require_manual_approval_permission: true },
    restores: { production_enabled: false, production_requires_approver: true, selective_requires_components: true, full_prohibits_components: true },
    exercises: { production_enabled: false, default_schedule_offset_ms: 3600000, evidence_freshness_days: 90 },
    reports: { allowed_buckets: ['day', 'week', 'month'], default_bucket: 'month', default_interval_days: 30, max_interval_days: 366, max_results: 1000, compliant_percent: 100, noncompliant_percent: 0 },
    presentation: { duration_minute_seconds: 60, duration_hour_seconds: 3600, byte_base: 1024, status_positive: ['available', 'ready', 'succeeded', 'passed', 'published', 'operational'], status_negative: ['corrupt', 'failed', 'unavailable'], status_warning: ['queued', 'validating', 'restoring', 'verifying', 'degraded'], status_positive_token: 'status-success', status_negative_token: 'status-danger', status_warning_token: 'status-warning' },
    polling: { dashboard_ms: 60000, recovery_point_ms: 4000, restore_ms: 4000, exercise_ms: 3000, exercise_page_size: 100, active_restore_statuses: ['queued', 'validating', 'ready', 'restoring', 'verifying'], active_exercise_statuses: ['queued', 'running'] },
    workflows: {
      recovery_point: { states: ['discovered', 'verifying', 'available', 'corrupt', 'expired', 'deleted'], terminal_states: ['deleted'], transitions: [], retention_guard_commands: ['expire'] },
      restore_run: { states: ['queued', 'validating', 'ready', 'restoring', 'verifying', 'succeeded', 'failed', 'cancelled'], terminal_states: ['succeeded', 'failed', 'cancelled'], transitions: [], retention_guard_commands: [] },
      runbook: { states: ['draft', 'published', 'retired'], terminal_states: ['retired'], transitions: [], retention_guard_commands: [] },
      exercise: { states: ['scheduled', 'queued', 'running', 'passed', 'failed', 'cancelled'], terminal_states: ['passed', 'failed', 'cancelled'], transitions: [], retention_guard_commands: [] },
      step_execution: { states: ['pending', 'running', 'passed', 'failed', 'degraded', 'skipped'], terminal_states: ['passed', 'failed', 'degraded', 'skipped'], transitions: [], retention_guard_commands: [] },
    },
  },
};
