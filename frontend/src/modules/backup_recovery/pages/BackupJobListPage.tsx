import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/stores/auth-store";
import type { BackupJobFilters, BackupJobStatus, BackupType } from "../contracts";
import {
  EmptyPanel,
  formatBytes,
  formatDate,
  PageHeader,
  PageSkeleton,
  Pagination,
  ProblemState,
  StaleIndicator,
  StatusPill,
  titleCase,
} from "../components/BackupRecoveryUI";
import {
  backupRecoveryQueryKeys,
  backupRecoveryService,
} from "../services/backup-recovery-service";

function filtersFrom(params: URLSearchParams): BackupJobFilters {
  return {
    page: Number(params.get("page") ?? 1),
    page_size: 25,
    search: params.get("search") || undefined,
    status: (params.get("status") as BackupJobStatus | null) ?? undefined,
    backup_type: (params.get("backup_type") as BackupType | null) ?? undefined,
    ordering: (params.get("ordering") as BackupJobFilters["ordering"]) ?? "-requested_at",
  };
}

export const BackupJobListPage = () => {
  const navigate = useNavigate();
  const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const [params, setParams] = useSearchParams();
  const filters = filtersFrom(params);
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.jobs(tenantId, filters),
    queryFn: () => backupRecoveryService.listBackupJobs(filters),
  });
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.set("page", "1");
    setParams(next);
  };
  const filtered = Boolean(filters.search || filters.status || filters.backup_type);
  if (query.isLoading) return <PageSkeleton table />;
  if (query.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error} onRetry={() => void query.refetch()} />
      </main>
    );
  const result = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Backup jobs"
        description="Provider-backed capture work, state transitions, and evidence—never inferred success."
        actions={
          <Button onClick={() => navigate("/backup-recovery/jobs/new")}>
            <Plus className="mr-2 h-4 w-4" />
            Request backup
          </Button>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      <Card className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Input
          aria-label="Search backup jobs"
          placeholder="Description or exact job ID"
          value={filters.search ?? ""}
          onChange={(event) => update("search", event.target.value)}
        />
        <select
          aria-label="Status filter"
          className="h-10 rounded-md border bg-background px-3"
          value={filters.status ?? ""}
          onChange={(event) => update("status", event.target.value)}
        >
          <option value="">All states</option>
          {["pending", "running", "completed", "failed", "cancelled"].map((value) => (
            <option key={value} value={value}>
              {titleCase(value)}
            </option>
          ))}
        </select>
        <select
          aria-label="Backup type filter"
          className="h-10 rounded-md border bg-background px-3"
          value={filters.backup_type ?? ""}
          onChange={(event) => update("backup_type", event.target.value)}
        >
          <option value="">All types</option>
          {["full", "incremental", "differential"].map((value) => (
            <option key={value} value={value}>
              {titleCase(value)}
            </option>
          ))}
        </select>
        <select
          aria-label="Sort jobs"
          className="h-10 rounded-md border bg-background px-3"
          value={filters.ordering}
          onChange={(event) => update("ordering", event.target.value)}
        >
          <option value="-requested_at">Newest requested</option>
          <option value="requested_at">Oldest requested</option>
          <option value="-completed_at">Recently completed</option>
          <option value="-size_bytes">Largest</option>
        </select>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          filtered={filtered}
          onReset={() => setParams({})}
          title={filtered ? "No jobs match these filters" : "No backups requested yet"}
          description={
            filtered
              ? "Reset the governed server filters to see the full job history."
              : "Request a full backup to establish the first auditable baseline."
          }
          action={
            !filtered
              ? {
                  label: "Request first backup",
                  onClick: () => navigate("/backup-recovery/jobs/new"),
                }
              : undefined
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Requested", "State", "Type", "Scope", "Captured", "Description"].map(
                    (heading) => (
                      <th key={heading} className="px-4 py-3 font-medium">
                        {heading}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {result.items.map((job) => (
                  <tr key={job.id} className="border-t hover:bg-muted/50">
                    <td className="px-4 py-3">
                      <button
                        className="font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => navigate(`/backup-recovery/jobs/${job.id}`)}
                      >
                        {formatDate(job.requested_at)}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={job.status} />
                      {job.error_code && (
                        <p className="mt-1 font-mono text-xs text-destructive">{job.error_code}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">{titleCase(job.backup_type)}</td>
                    <td className="px-4 py-3">
                      {titleCase(job.scope_type)} · {job.scope_ref}
                    </td>
                    <td className="px-4 py-3">{formatBytes(job.size_bytes)}</td>
                    <td className="max-w-xs truncate px-4 py-3">{job.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination meta={result.pagination} onPage={(page) => update("page", String(page))} />
        </Card>
      )}
    </main>
  );
};
