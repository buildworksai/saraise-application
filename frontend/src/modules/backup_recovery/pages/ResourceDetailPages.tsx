import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit, Play, Power, ShieldCheck, Star } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { useAuthStore } from "@/stores/auth-store";
import {
  CommandButton,
  Field,
  formatBytes,
  formatDate,
  PageHeader,
  PageSkeleton,
  ProblemState,
  StaleIndicator,
  StatusPill,
  titleCase,
} from "../components/BackupRecoveryUI";
import {
  backupRecoveryQueryKeys,
  backupRecoveryService,
  newIdempotencyKey,
} from "../services/backup-recovery-service";

function useContext() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const client = useQueryClient();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const refresh = () =>
    void client.invalidateQueries({ queryKey: backupRecoveryQueryKeys.root(tenant) });
  return { id, nav, tenant, refresh };
}

export const BackupScheduleDetailPage = () => {
  const { id, nav, tenant, refresh } = useContext();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.schedule(tenant, id),
    queryFn: () => backupRecoveryService.getBackupSchedule(id),
    enabled: Boolean(id),
  });
  const activate = useMutation({
    mutationFn: () =>
      query.data?.is_active
        ? backupRecoveryService.deactivateBackupSchedule(id)
        : backupRecoveryService.activateBackupSchedule(id),
    onSuccess: () => {
      refresh();
      toast.success(query.data?.is_active ? "Schedule deactivated" : "Schedule activated");
    },
  });
  const run = useMutation({
    mutationFn: () =>
      backupRecoveryService.runBackupScheduleNow(id, {
        idempotency_key: newIdempotencyKey("schedule-run"),
      }),
    onSuccess: (receipt) => {
      refresh();
      toast.success("Scheduled backup durably queued");
      nav(`/backup-recovery/jobs/${receipt.job_id}`);
    },
  });
  const remove = useMutation({
    mutationFn: () => backupRecoveryService.deleteBackupSchedule(id),
    onSuccess: () => {
      refresh();
      toast.success("Schedule safely removed");
      nav("/backup-recovery/schedules");
    },
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error ?? new Error("Schedule unavailable")} />
      </main>
    );
  const item = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={item.name}
        description={`${titleCase(item.frequency)} ${titleCase(item.backup_type)} capture in ${item.timezone}`}
        backLabel="Schedules"
        onBack={() => nav("/backup-recovery/schedules")}
        actions={
          <>
            <StatusPill value={item.is_active ? "active" : "inactive"} />
            <CommandButton
              capability={item.allowed_commands?.update}
              onClick={() => nav(`/backup-recovery/schedules/${id}/edit`)}
            >
              <Edit className="mr-2 h-4 w-4" />
              Edit
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.execute}
              pending={run.isPending}
              onClick={() => run.mutate()}
            >
              <Play className="mr-2 h-4 w-4" />
              Run now
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.activate}
              pending={activate.isPending}
              onClick={() => activate.mutate()}
            >
              <Power className="mr-2 h-4 w-4" />
              {item.is_active ? "Deactivate" : "Activate"}
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.delete}
              variant="danger"
              onClick={() => setConfirmDelete(true)}
            >
              Delete
            </CommandButton>
          </>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      {(activate.error || run.error || remove.error) && (
        <ProblemState error={activate.error ?? run.error ?? remove.error} />
      )}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5">
          <Field label="Next run" value={formatDate(item.next_run_at)} />
        </Card>
        <Card className="p-5">
          <Field label="Last run" value={formatDate(item.last_run_at)} />
        </Card>
        <Card className="p-5">
          <Field label="Storage target" value={item.storage_target_name ?? item.storage_target} />
        </Card>
        <Card className="p-5">
          <Field
            label="Retention policy"
            value={item.retention_policy_name ?? item.retention_policy}
          />
        </Card>
      </section>
      <Card className="p-6">
        <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Scope" value={`${titleCase(item.scope_type)} · ${item.scope_ref}`} />
          <Field label="Backup type" value={titleCase(item.backup_type)} />
          <Field label="Frequency" value={titleCase(item.frequency)} />
          <Field label="Local time" value={item.schedule_time ?? "Every hour"} />
          <Field label="Day of week" value={item.day_of_week ?? "Not applicable"} />
          <Field label="Day of month" value={item.day_of_month ?? "Not applicable"} />
          <Field
            label="Timezone and DST"
            value={`${item.timezone}; ambiguous and nonexistent local times resolve deterministically`}
          />
          <div className="sm:col-span-2">
            <Field label="Description" value={item.description || "No description"} />
          </div>
        </dl>
      </Card>
      <Dialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete schedule?"
        description="The schedule is soft-deleted. Historical jobs and immutable artifacts remain available for audit."
      >
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
            Keep schedule
          </Button>
          <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
            {remove.isPending ? "Deleting…" : "Delete schedule"}
          </Button>
        </div>
      </Dialog>
    </main>
  );
};

export const BackupRetentionPolicyDetailPage = () => {
  const { id, nav, tenant, refresh } = useContext();
  const capturedAt = new Date().toISOString();
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.policy(tenant, id),
    queryFn: () => backupRecoveryService.getRetentionPolicy(id),
    enabled: Boolean(id),
  });
  const preview = useQuery({
    queryKey: backupRecoveryQueryKeys.policyPreview(tenant, id, capturedAt),
    queryFn: () => backupRecoveryService.previewRetentionPolicy(id, capturedAt),
    enabled: Boolean(id),
    staleTime: Infinity,
  });
  const toggle = useMutation({
    mutationFn: () =>
      query.data?.is_active
        ? backupRecoveryService.deactivateRetentionPolicy(id)
        : backupRecoveryService.activateRetentionPolicy(id),
    onSuccess: () => {
      refresh();
      toast.success("Policy state updated");
    },
  });
  const remove = useMutation({
    mutationFn: () => backupRecoveryService.deleteRetentionPolicy(id),
    onSuccess: () => {
      refresh();
      toast.success("Policy deleted");
      nav("/backup-recovery/retention-policies");
    },
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error ?? new Error("Policy unavailable")} />
      </main>
    );
  const item = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={item.name}
        description="Retention changes apply prospectively; historical artifact expiry evidence is immutable."
        backLabel="Retention"
        onBack={() => nav("/backup-recovery/retention-policies")}
        actions={
          <>
            <StatusPill value={item.is_active ? "active" : "inactive"} />
            <CommandButton
              capability={item.allowed_commands?.update}
              onClick={() => nav(`/backup-recovery/retention-policies/${id}/edit`)}
            >
              <Edit className="mr-2 h-4 w-4" />
              Edit
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.activate}
              pending={toggle.isPending}
              onClick={() => toggle.mutate()}
            >
              <Power className="mr-2 h-4 w-4" />
              {item.is_active ? "Deactivate" : "Activate"}
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.delete}
              pending={remove.isPending}
              variant="danger"
              onClick={() => remove.mutate()}
            >
              Delete
            </CommandButton>
          </>
        }
      />
      {(toggle.error || remove.error) && <ProblemState error={toggle.error ?? remove.error} />}
      <section className="grid gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <Field label="Retain" value={`${item.retention_days} days`} />
        </Card>
        <Card className="p-5">
          <Field
            label="Archive after"
            value={
              item.archive_after_days === null
                ? "No separate archive transition"
                : `${item.archive_after_days} days`
            }
          />
        </Card>
        <Card className="p-5">
          <Field
            label="Protected minimum"
            value={`${item.keep_last_successful} successful artifacts`}
          />
        </Card>
      </section>
      <Card className="p-6">
        <h2 className="font-semibold">Expiry preview for a capture now</h2>
        {preview.isLoading ? (
          <p role="status" className="mt-4 text-sm text-muted-foreground">
            Calculating authoritative dates…
          </p>
        ) : preview.error ? (
          <div className="mt-4">
            <ProblemState error={preview.error} onRetry={() => void preview.refetch()} />
          </div>
        ) : (
          preview.data && (
            <dl className="mt-5 grid gap-5 sm:grid-cols-3">
              <Field label="Captured" value={formatDate(preview.data.captured_at)} />
              <Field label="Archive" value={formatDate(preview.data.archive_at)} />
              <Field label="Expiry" value={formatDate(preview.data.expires_at)} />
            </dl>
          )
        )}
      </Card>
      <Card className="p-6">
        <Field label="Description" value={item.description || "No description"} />
      </Card>
    </main>
  );
};

export const BackupStorageTargetDetailPage = () => {
  const { id, nav, tenant, refresh } = useContext();
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.target(tenant, id),
    queryFn: () => backupRecoveryService.getStorageTarget(id),
    enabled: Boolean(id),
  });
  const toggle = useMutation({
    mutationFn: () =>
      query.data?.is_active
        ? backupRecoveryService.deactivateStorageTarget(id)
        : backupRecoveryService.activateStorageTarget(id),
    onSuccess: () => {
      refresh();
      toast.success("Target state updated");
    },
  });
  const setDefault = useMutation({
    mutationFn: () => backupRecoveryService.setDefaultStorageTarget(id),
    onSuccess: () => {
      refresh();
      toast.success("Default target updated");
    },
  });
  const probe = useMutation({
    mutationFn: () => backupRecoveryService.probeStorageTarget(id),
    onSuccess: (result) => {
      refresh();
      toast[result.healthy ? "success" : "error"](
        result.healthy ? "Provider probe passed" : "Provider probe reported degradation"
      );
    },
  });
  const remove = useMutation({
    mutationFn: () => backupRecoveryService.deleteStorageTarget(id),
    onSuccess: () => {
      refresh();
      toast.success("Unused target removed");
      nav("/backup-recovery/storage-targets");
    },
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error ?? new Error("Target unavailable")} />
      </main>
    );
  const item = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={item.name}
        description={`Provider adapter ${item.adapter_key}`}
        backLabel="Storage targets"
        onBack={() => nav("/backup-recovery/storage-targets")}
        actions={
          <>
            <StatusPill value={item.is_active ? "active" : "inactive"} />
            <CommandButton
              capability={item.allowed_commands?.update}
              onClick={() => nav(`/backup-recovery/storage-targets/${id}/edit`)}
            >
              <Edit className="mr-2 h-4 w-4" />
              Edit
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.set_default}
              pending={setDefault.isPending}
              onClick={() => setDefault.mutate()}
            >
              <Star className="mr-2 h-4 w-4" />
              Set default
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.probe}
              pending={probe.isPending}
              onClick={() => probe.mutate()}
            >
              <ShieldCheck className="mr-2 h-4 w-4" />
              {probe.isPending ? "Probing…" : "Probe provider"}
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.update}
              pending={toggle.isPending}
              onClick={() => toggle.mutate()}
            >
              <Power className="mr-2 h-4 w-4" />
              {item.is_active ? "Deactivate" : "Activate"}
            </CommandButton>
            <CommandButton
              capability={item.allowed_commands?.delete}
              pending={remove.isPending}
              variant="danger"
              onClick={() => remove.mutate()}
            >
              Delete
            </CommandButton>
          </>
        }
      />
      {(toggle.error || setDefault.error || probe.error || remove.error) && (
        <ProblemState error={toggle.error ?? setDefault.error ?? probe.error ?? remove.error} />
      )}{" "}
      {probe.data && (
        <Card
          role="status"
          className={`p-5 ${probe.data.healthy ? "border-green-500/30" : "border-destructive/40"}`}
        >
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Latest bounded provider probe</h2>
              <p className="mt-1 text-sm text-muted-foreground">{probe.data.message}</p>
            </div>
            <StatusPill value={probe.data.healthy ? "healthy" : "unavailable"} />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{formatDate(probe.data.checked_at)}</p>
        </Card>
      )}
      <Card className="p-6">
        <dl className="grid gap-5 sm:grid-cols-2">
          <Field label="Adapter" value={item.adapter_key} mono />
          <Field label="Role" value={item.is_default ? "Tenant default" : "Available target"} />
          <Field label="Locator prefix reference" value={item.locator_prefix_ref} mono />
          <Field label="Configuration reference" value={item.configuration_ref} mono />
          <Field
            label="Encryption key reference"
            value={item.encryption_key_ref || "Provider-managed / none"}
            mono
          />
          <Field label="Created" value={formatDate(item.created_at)} />
        </dl>
        <p className="mt-6 rounded-md bg-muted p-3 text-xs text-muted-foreground">
          These values are opaque references. Secrets and encryption key material are never returned
          by this API.
        </p>
      </Card>
    </main>
  );
};

export const BackupArchiveDetailPage = () => {
  const { id, nav, tenant, refresh } = useContext();
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.archive(tenant, id),
    queryFn: () => backupRecoveryService.getBackupArchive(id),
    enabled: Boolean(id),
  });
  const verify = useMutation({
    mutationFn: () =>
      backupRecoveryService.requestArchiveVerification(id, {
        idempotency_key: newIdempotencyKey("verify"),
      }),
    onSuccess: (record) => {
      refresh();
      toast.success("Verification durably queued");
      nav(`/backup-recovery/verifications/${record.id}`);
    },
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error ?? new Error("Artifact unavailable")} />
      </main>
    );
  const item = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Immutable backup artifact"
        description={`Catalog record ${item.id}`}
        backLabel="Artifacts"
        onBack={() => nav("/backup-recovery/archives")}
        actions={
          <>
            <StatusPill value={item.lifecycle} />
            <StatusPill value={item.integrity_status} />
            <CommandButton
              capability={item.allowed_commands?.verify}
              pending={verify.isPending}
              onClick={() => verify.mutate()}
            >
              <ShieldCheck className="mr-2 h-4 w-4" />
              {verify.isPending ? "Queueing…" : "Verify integrity"}
            </CommandButton>
          </>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      {verify.error && <ProblemState error={verify.error} />}
      <section className="grid gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <Field label="Captured" value={formatDate(item.captured_at)} />
        </Card>
        <Card className="p-5">
          <Field label="Retained size" value={formatBytes(item.size_bytes)} />
        </Card>
        <Card className="p-5">
          <Field label="Expires" value={formatDate(item.expires_at)} />
        </Card>
      </section>
      <Card className="p-6">
        <h2 className="font-semibold">Provider evidence</h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2">
          <Field
            label="Backup job"
            value={
              <button
                className="text-primary hover:underline"
                onClick={() => nav(`/backup-recovery/jobs/${item.backup_job}`)}
              >
                {item.backup_job}
              </button>
            }
            mono
          />
          <Field label="Adapter" value={item.adapter_key} mono />
          <Field label="Artifact locator reference" value={item.artifact_locator_ref} mono />
          <Field label="Provider acknowledgement" value={item.provider_acknowledgement} mono />
          <Field label="Checksum algorithm" value={item.checksum_algorithm} mono />
          <Field label="Checksum digest" value={item.checksum_digest} mono />
          <Field label="Data cutoff" value={formatDate(item.data_cutoff_at)} />
          <Field label="Archived" value={formatDate(item.archived_at)} />
          <Field label="Last verified" value={formatDate(item.last_verified_at)} />
          <Field label="Purged" value={formatDate(item.purged_at)} />
        </dl>
        <p className="mt-6 rounded-md bg-muted p-3 text-xs text-muted-foreground">
          This opaque evidence supports audit and integrity checks. It is not a credential, signed
          download URL, or a claim of restore readiness.
        </p>
      </Card>
    </main>
  );
};

export const BackupVerificationDetailPage = () => {
  const { id, nav, tenant, refresh } = useContext();
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.verification(tenant, id),
    queryFn: () => backupRecoveryService.getBackupVerification(id),
    enabled: Boolean(id),
    refetchInterval: (state) =>
      ["pending", "running"].includes(state.state.data?.status ?? "") ? 5000 : false,
  });
  const cancel = useMutation({
    mutationFn: () =>
      backupRecoveryService.cancelBackupVerification(id, {
        transition_key: newIdempotencyKey("verification-cancel"),
      }),
    onSuccess: () => {
      refresh();
      toast.success("Verification cancelled");
    },
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error ?? new Error("Verification unavailable")} />
      </main>
    );
  const item = query.data;
  const result = (value: boolean | null) =>
    value === null ? "Pending" : value ? "Passed" : "Failed";
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Integrity verification"
        description={`Verification ${item.id}`}
        backLabel="Verification history"
        onBack={() => nav("/backup-recovery/verifications")}
        actions={
          <>
            <StatusPill value={item.status} />
            <CommandButton
              capability={item.allowed_commands?.cancel}
              pending={cancel.isPending}
              variant="danger"
              onClick={() => cancel.mutate()}
            >
              {cancel.isPending ? "Cancelling…" : "Cancel verification"}
            </CommandButton>
          </>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      {cancel.error && <ProblemState error={cancel.error} />}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Checksum matches", item.checksum_matches],
          ["Artifact available", item.artifact_available],
          ["Encryption metadata", item.encryption_metadata_valid],
          ["Provider acknowledged", item.provider_acknowledged],
        ].map(([label, value]) => (
          <Card key={String(label)} className="p-5">
            <Field
              label={String(label)}
              value={<StatusPill value={result(value as boolean | null).toLowerCase()} />}
            />
          </Card>
        ))}
      </section>
      <Card className="p-6">
        <dl className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Archive"
            value={
              <button
                className="text-primary hover:underline"
                onClick={() => nav(`/backup-recovery/archives/${item.archive}`)}
              >
                {item.archive}
              </button>
            }
            mono
          />
          <Field label="Requested" value={formatDate(item.requested_at)} />
          <Field label="Started" value={formatDate(item.started_at)} />
          <Field label="Completed" value={formatDate(item.completed_at)} />
          <Field label="Error classification" value={item.error_code || "None"} mono />
          <Field label="Error detail" value={item.error_message || "None"} />
          <div className="sm:col-span-2">
            <Field
              label="Sanitized evidence"
              value={
                <pre className="mt-2 overflow-x-auto rounded bg-muted p-3 text-xs">
                  {JSON.stringify(item.evidence, null, 2)}
                </pre>
              }
            />
          </div>
          {item.correlation_id && <Field label="Correlation ID" value={item.correlation_id} mono />}
        </dl>
      </Card>
    </main>
  );
};
