import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Archive,
  CalendarClock,
  DatabaseBackup,
  HardDrive,
  PlayCircle,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuthStore } from "@/stores/auth-store";
import {
  EmptyPanel,
  formatBytes,
  formatDate,
  PageHeader,
  PageSkeleton,
  ProblemState,
  StaleIndicator,
  StatusPill,
} from "../components/BackupRecoveryUI";
import {
  backupRecoveryQueryKeys,
  backupRecoveryService,
} from "../services/backup-recovery-service";

async function retainedStorage(): Promise<{ bytes: number; artifacts: number }> {
  const first = await backupRecoveryService.listBackupArchives({
    lifecycle: "available",
    page: 1,
    page_size: 100,
  });
  let bytes = first.items.reduce((sum, item) => sum + item.size_bytes, 0);
  for (let page = 2; page <= first.pagination.total_pages; page += 1) {
    const result = await backupRecoveryService.listBackupArchives({
      lifecycle: "available",
      page,
      page_size: 100,
    });
    bytes += result.items.reduce((sum, item) => sum + item.size_bytes, 0);
  }
  return { bytes, artifacts: first.pagination.count };
}

export const BackupRecoveryOverviewPage = () => {
  const navigate = useNavigate();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const health = useQuery({
    queryKey: backupRecoveryQueryKeys.health(tenant),
    queryFn: backupRecoveryService.health,
    refetchInterval: 30000,
  });
  const completed = useQuery({
    queryKey: backupRecoveryQueryKeys.jobs(tenant, {
      status: "completed",
      page: 1,
      page_size: 1,
      ordering: "-completed_at",
    }),
    queryFn: () =>
      backupRecoveryService.listBackupJobs({
        status: "completed",
        page: 1,
        page_size: 1,
        ordering: "-completed_at",
      }),
  });
  const running = useQuery({
    queryKey: backupRecoveryQueryKeys.jobs(tenant, { status: "running", page: 1, page_size: 25 }),
    queryFn: () =>
      backupRecoveryService.listBackupJobs({ status: "running", page: 1, page_size: 25 }),
  });
  const failed = useQuery({
    queryKey: backupRecoveryQueryKeys.jobs(tenant, {
      status: "failed",
      page: 1,
      page_size: 5,
      ordering: "-completed_at",
    }),
    queryFn: () =>
      backupRecoveryService.listBackupJobs({
        status: "failed",
        page: 1,
        page_size: 5,
        ordering: "-completed_at",
      }),
  });
  const schedules = useQuery({
    queryKey: backupRecoveryQueryKeys.schedules(tenant, {
      is_active: true,
      page: 1,
      page_size: 1,
      ordering: "next_run_at",
    }),
    queryFn: () =>
      backupRecoveryService.listBackupSchedules({
        is_active: true,
        page: 1,
        page_size: 1,
        ordering: "next_run_at",
      }),
  });
  const targets = useQuery({
    queryKey: backupRecoveryQueryKeys.targets(tenant, { is_active: true, page: 1, page_size: 1 }),
    queryFn: () =>
      backupRecoveryService.listStorageTargets({ is_active: true, page: 1, page_size: 1 }),
  });
  const storage = useQuery({
    queryKey: [...backupRecoveryQueryKeys.archives(tenant), "retained-total"],
    queryFn: retainedStorage,
  });
  const queries = [health, completed, running, failed, schedules, targets, storage];
  if (queries.some((query) => query.isLoading)) return <PageSkeleton />;
  const error = queries.find((query) => query.error)?.error;
  if (error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState
          error={error}
          onRetry={() => queries.forEach((query) => void query.refetch())}
        />
      </main>
    );

  const last = completed.data?.items[0];
  const next = schedules.data?.items[0];
  const targetCount = targets.data?.pagination.count ?? 0;
  const runningCount = running.data?.pagination.count ?? 0;
  const failedCount = failed.data?.pagination.count ?? 0;
  const protectedNow = Boolean(last && storage.data?.artifacts && targetCount);

  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Backup protection posture"
        description="Live tenant-scoped evidence across capture, scheduling, retained artifacts, verification dependencies, and required action."
        actions={
          <Button onClick={() => navigate("/backup-recovery/jobs/new")}>
            <DatabaseBackup className="mr-2 h-4 w-4" />
            Request backup
          </Button>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={queries.some((query) => query.isFetching)} />
      </div>
      <Card className={`p-6 ${protectedNow ? "border-green-500/30" : "border-amber-500/40"}`}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div
              className={`rounded-full p-3 ${protectedNow ? "bg-green-500/10" : "bg-amber-500/10"}`}
            >
              {protectedNow ? (
                <ShieldCheck className="h-7 w-7 text-green-600" />
              ) : (
                <AlertTriangle className="h-7 w-7 text-amber-600" />
              )}
            </div>
            <div>
              <h2 className="text-lg font-semibold">
                {protectedNow
                  ? "Provider-backed protection evidence is available"
                  : "Protection requires attention"}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {protectedNow
                  ? `${storage.data?.artifacts ?? 0} available artifacts are catalogued against ${targetCount} active targets.`
                  : "Configure an active storage target and complete a provider-evidenced backup."}
              </p>
            </div>
          </div>
          <StatusPill value={health.data?.status ?? "unavailable"} />
        </div>
      </Card>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Protection metrics">
        <MetricCard
          icon={<Archive className="h-5 w-5 text-primary" />}
          label="Last successful backup"
          value={last ? formatDate(last.completed_at) : "No verified completion"}
          detail={
            last
              ? `${last.scope_type} · ${formatBytes(last.size_bytes)}`
              : "A queued request is not protection."
          }
          onClick={() => navigate("/backup-recovery/jobs?status=completed")}
        />
        <MetricCard
          icon={<PlayCircle className="h-5 w-5 text-primary" />}
          label="Running now"
          value={String(runningCount)}
          detail="Active provider operations"
          onClick={() => navigate("/backup-recovery/jobs?status=running")}
        />
        <MetricCard
          icon={<CalendarClock className="h-5 w-5 text-primary" />}
          label="Next scheduled backup"
          value={next ? formatDate(next.next_run_at) : "None scheduled"}
          detail={next?.name ?? "Create a schedule to automate protection."}
          onClick={() => navigate("/backup-recovery/schedules")}
        />
        <MetricCard
          icon={<HardDrive className="h-5 w-5 text-primary" />}
          label="Retained storage"
          value={formatBytes(storage.data?.bytes)}
          detail={`Across ${storage.data?.artifacts ?? 0} available artifacts`}
          onClick={() => navigate("/backup-recovery/archives")}
        />
      </section>
      {failedCount > 0 ? (
        <Card className="border-destructive/30 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-destructive">Failures requiring action</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {failedCount} failed capture operations are retained for diagnosis.
              </p>
            </div>
            <Button
              variant="secondary"
              onClick={() => navigate("/backup-recovery/jobs?status=failed")}
            >
              Review all
            </Button>
          </div>
          <div className="mt-4 divide-y">
            {failed.data?.items.map((job) => (
              <button
                key={job.id}
                className="flex w-full items-center justify-between py-3 text-left hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => navigate(`/backup-recovery/jobs/${job.id}`)}
              >
                <span>
                  <strong>{job.error_code || "UNCLASSIFIED_FAILURE"}</strong>
                  <span className="ml-2 text-sm text-muted-foreground">
                    {job.description || job.scope_ref}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDate(job.completed_at)}
                </span>
              </button>
            ))}
          </div>
        </Card>
      ) : (
        <EmptyPanel
          title="No active backup failures"
          description="No terminal capture failures currently require operator action."
        />
      )}
      <Card className="p-6">
        <h2 className="font-semibold">Execution readiness</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {health.data &&
            [
              health.data.database,
              health.data.async_jobs,
              health.data.outbox,
              health.data.scheduler,
            ].map((dependency) => (
              <div key={dependency.key} className="rounded-md border p-4">
                <div className="flex items-center justify-between">
                  <strong className="text-sm">{dependency.key.replaceAll("_", " ")}</strong>
                  <StatusPill value={dependency.status} />
                </div>
                {dependency.detail && (
                  <p className="mt-2 text-xs text-muted-foreground">{dependency.detail}</p>
                )}
              </div>
            ))}
        </div>
        <h3 className="mt-6 text-sm font-semibold">Configured adapters</h3>
        {health.data?.adapters.length ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {health.data.adapters.map((adapter) => (
              <div
                key={adapter.key}
                className="flex items-center justify-between rounded-md border p-4"
              >
                <span className="font-mono text-sm">{adapter.key}</span>
                <StatusPill value={adapter.status} />
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            No adapter health evidence is available. This is not reported as healthy.
          </p>
        )}
      </Card>
    </main>
  );
};

function MetricCard({
  icon,
  label,
  value,
  detail,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      onClick={onClick}
    >
      <Card className="h-full p-5 hover:bg-muted/30">
        {icon}
        <p className="mt-4 text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-2 font-semibold">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
      </Card>
    </button>
  );
}
