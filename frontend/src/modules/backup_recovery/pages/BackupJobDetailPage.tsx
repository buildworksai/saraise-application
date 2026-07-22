import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit, RefreshCcw, StopCircle, Trash2 } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { useAuthStore } from "@/stores/auth-store";
import {
  CommandButton,
  duration,
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

type Confirmation = "cancel" | "delete" | null;

export const BackupJobDetailPage = () => {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const client = useQueryClient();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.job(tenant, id),
    queryFn: () => backupRecoveryService.getBackupJob(id),
    enabled: Boolean(id),
    refetchInterval: (state) =>
      ["pending", "running"].includes(state.state.data?.status ?? "") ? 5000 : false,
  });
  const refresh = () =>
    void client.invalidateQueries({ queryKey: backupRecoveryQueryKeys.root(tenant) });
  const cancel = useMutation({
    mutationFn: () =>
      backupRecoveryService.cancelBackupJob(id, { transition_key: newIdempotencyKey("cancel") }),
    onSuccess: () => {
      refresh();
      setConfirmation(null);
      toast.success("Cancellation recorded");
    },
  });
  const retry = useMutation({
    mutationFn: () =>
      backupRecoveryService.retryBackupJob(id, { idempotency_key: newIdempotencyKey("retry") }),
    onSuccess: (receipt) => {
      refresh();
      toast.success("Retry durably queued");
      nav(`/backup-recovery/jobs/${receipt.job_id}`);
    },
  });
  const remove = useMutation({
    mutationFn: () => backupRecoveryService.deleteBackupJob(id),
    onSuccess: () => {
      refresh();
      toast.success("Job removed from active catalog");
      nav("/backup-recovery/jobs");
    },
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState
          error={query.error ?? new Error("Job unavailable")}
          onRetry={() => void query.refetch()}
        />
      </main>
    );
  const job = query.data;
  const commands = job.allowed_commands;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={`${titleCase(job.backup_type)} backup`}
        description={`Job ${job.id}`}
        backLabel="Backup jobs"
        onBack={() => nav("/backup-recovery/jobs")}
        actions={
          <>
            <StatusPill value={job.status} />
            <CommandButton
              capability={commands?.update}
              onClick={() => nav(`/backup-recovery/jobs/${id}/edit`)}
            >
              <Edit className="mr-2 h-4 w-4" />
              Edit context
            </CommandButton>
            <CommandButton
              capability={commands?.cancel}
              pending={cancel.isPending}
              onClick={() => setConfirmation("cancel")}
            >
              <StopCircle className="mr-2 h-4 w-4" />
              Cancel
            </CommandButton>
            <CommandButton
              capability={commands?.retry}
              pending={retry.isPending}
              onClick={() => retry.mutate()}
            >
              <RefreshCcw className="mr-2 h-4 w-4" />
              Retry
            </CommandButton>
            <CommandButton
              capability={commands?.delete}
              pending={remove.isPending}
              variant="danger"
              onClick={() => setConfirmation("delete")}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Remove
            </CommandButton>
          </>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      {(cancel.error || retry.error || remove.error) && (
        <ProblemState error={cancel.error ?? retry.error ?? remove.error} />
      )}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Job posture">
        <Card className="p-5">
          <Field label="Scope" value={`${titleCase(job.scope_type)} · ${job.scope_ref}`} />
        </Card>
        <Card className="p-5">
          <Field label="Duration" value={duration(job.started_at, job.completed_at)} />
        </Card>
        <Card className="p-5">
          <Field label="Bytes captured" value={formatBytes(job.size_bytes)} />
        </Card>
        <Card className="p-5">
          <Field label="Storage target" value={job.storage_target_name ?? job.storage_target} />
        </Card>
      </section>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="font-semibold">Execution evidence</h2>
          <dl className="mt-5 grid gap-5 sm:grid-cols-2">
            <Field label="Requested" value={formatDate(job.requested_at)} />
            <Field label="Started" value={formatDate(job.started_at)} />
            <Field label="Completed" value={formatDate(job.completed_at)} />
            <Field label="Data cutoff" value={formatDate(job.data_cutoff_at)} />
            <Field label="Schedule" value={job.schedule_name ?? job.schedule ?? "Manual request"} />
            <Field label="Async job" value={job.async_job_id ?? "Not yet enqueued"} mono />
            <Field
              label="Base job"
              value={
                job.base_job ? (
                  <button
                    className="text-primary hover:underline"
                    onClick={() => nav(`/backup-recovery/jobs/${job.base_job}`)}
                  >
                    {job.base_job}
                  </button>
                ) : (
                  "Not applicable"
                )
              }
              mono
            />
            <Field
              label="Retry of"
              value={
                job.retry_of ? (
                  <button
                    className="text-primary hover:underline"
                    onClick={() => nav(`/backup-recovery/jobs/${job.retry_of}`)}
                  >
                    {job.retry_of}
                  </button>
                ) : (
                  "Original request"
                )
              }
              mono
            />
            <div className="sm:col-span-2">
              <Field label="Operator context" value={job.description || "No description"} />
            </div>
            {job.correlation_id && (
              <div className="sm:col-span-2">
                <Field label="Correlation ID" value={job.correlation_id} mono />
              </div>
            )}
          </dl>
        </Card>
        <Card className="p-6">
          <h2 className="font-semibold">Artifact and outcome</h2>
          {job.archive ? (
            <dl className="mt-5 grid gap-5">
              <Field
                label="Artifact"
                value={
                  <button
                    className="text-primary hover:underline"
                    onClick={() => nav(`/backup-recovery/archives/${job.archive?.id}`)}
                  >
                    {job.archive.id}
                  </button>
                }
                mono
              />
              <Field label="Lifecycle" value={<StatusPill value={job.archive.lifecycle} />} />
              <Field
                label="Integrity"
                value={<StatusPill value={job.archive.integrity_status} />}
              />
              <Field
                label="Checksum"
                value={
                  job.archive.checksum_digest
                    ? `${job.archive.checksum_algorithm}:${job.archive.checksum_digest}`
                    : `${job.archive.checksum_algorithm} · available in artifact detail`
                }
                mono
              />
            </dl>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">
              No artifact evidence exists. A running or failed job is never represented as
              protected.
            </p>
          )}
          {job.error_code && (
            <div className="mt-5 rounded-md border border-destructive/30 bg-destructive/5 p-4">
              <p className="font-mono text-sm font-semibold text-destructive">{job.error_code}</p>
              <p className="mt-2 text-sm">
                {job.error_message || "No provider detail was exposed."}
              </p>
            </div>
          )}
        </Card>
      </div>
      <Card className="p-6">
        <h2 className="font-semibold">Auditable state timeline</h2>
        {job.transition_history.length ? (
          <ol className="mt-5 border-l pl-6">
            {job.transition_history.map((transition, index) => (
              <li key={`${transition.at}-${index}`} className="relative pb-6 last:pb-0">
                <span className="absolute -left-[29px] top-1.5 h-3 w-3 rounded-full border-2 border-background bg-primary" />
                <p className="font-medium">
                  {titleCase(transition.from)} → {titleCase(transition.to)}
                </p>
                <p className="text-sm text-muted-foreground">
                  {formatDate(transition.at)} · {titleCase(transition.command)}
                </p>
                {transition.correlation_id && (
                  <p className="font-mono text-xs text-muted-foreground">
                    {transition.correlation_id}
                  </p>
                )}
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">
            No transition evidence has been recorded yet.
          </p>
        )}
      </Card>
      <Dialog
        open={confirmation !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmation(null);
        }}
        title={
          confirmation === "cancel"
            ? "Cancel backup operation?"
            : "Remove job from the active catalog?"
        }
        description={
          confirmation === "cancel"
            ? "A running provider operation is cancelled only if the provider acknowledges it or has not crossed its commit boundary."
            : "Pending or running work is cancelled first. Terminal jobs are soft-deleted; artifact and verification evidence remains immutable."
        }
      >
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmation(null)}>
            Keep job
          </Button>
          <Button
            variant="danger"
            disabled={cancel.isPending || remove.isPending}
            onClick={() => (confirmation === "cancel" ? cancel.mutate() : remove.mutate())}
          >
            {cancel.isPending || remove.isPending
              ? "Applying…"
              : confirmation === "cancel"
                ? "Request cancellation"
                : "Remove safely"}
          </Button>
        </div>
      </Dialog>
    </main>
  );
};
