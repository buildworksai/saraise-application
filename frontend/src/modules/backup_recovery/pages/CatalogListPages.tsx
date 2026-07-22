import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/stores/auth-store";
import type {
  ArchiveFilters,
  BackupFrequency,
  BackupScheduleFilters,
  IntegrityStatus,
  RetentionPolicyFilters,
  StorageTargetFilters,
  VerificationFilters,
  VerificationStatus,
} from "../contracts";
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

function useFilters() {
  const [params, setParams] = useSearchParams();
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.set("page", "1");
    setParams(next);
  };
  return { params, setParams, update, page: Number(params.get("page") ?? 1) };
}

export const BackupScheduleListPage = () => {
  const nav = useNavigate();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const { params, setParams, update, page } = useFilters();
  const filters: BackupScheduleFilters = {
    page,
    page_size: 25,
    search: params.get("search") || undefined,
    frequency: (params.get("frequency") as BackupFrequency | null) ?? undefined,
    is_active: params.has("is_active") ? params.get("is_active") === "true" : undefined,
    ordering: "name",
  };
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.schedules(tenant, filters),
    queryFn: () => backupRecoveryService.listBackupSchedules(filters),
  });
  if (query.isLoading) return <PageSkeleton table />;
  if (query.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error} onRetry={() => void query.refetch()} />
      </main>
    );
  const filtered = Boolean(filters.search || filters.frequency || filters.is_active !== undefined);
  const result = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Backup schedules"
        description="Timezone-aware automated capture with explicit retention and target selection."
        actions={
          <Button onClick={() => nav("/backup-recovery/schedules/new")}>
            <Plus className="mr-2 h-4 w-4" />
            Create schedule
          </Button>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      <Card className="grid gap-3 p-4 sm:grid-cols-3">
        <Input
          aria-label="Search schedules"
          placeholder="Name, scope, or description"
          value={filters.search ?? ""}
          onChange={(e) => update("search", e.target.value)}
        />
        <select
          aria-label="Frequency filter"
          className="h-10 rounded-md border bg-background px-3"
          value={filters.frequency ?? ""}
          onChange={(e) => update("frequency", e.target.value)}
        >
          <option value="">All frequencies</option>
          {["hourly", "daily", "weekly", "monthly"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <select
          aria-label="Schedule state filter"
          className="h-10 rounded-md border bg-background px-3"
          value={params.get("is_active") ?? ""}
          onChange={(e) => update("is_active", e.target.value)}
        >
          <option value="">All states</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          filtered={filtered}
          onReset={() => setParams({})}
          title={filtered ? "No schedules match" : "No schedules configured"}
          description={
            filtered
              ? "Reset the server filters."
              : "Automate capture with a timezone-aware schedule."
          }
          action={
            !filtered
              ? { label: "Create schedule", onClick: () => nav("/backup-recovery/schedules/new") }
              : undefined
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Schedule", "State", "Cadence", "Scope", "Next run", "Target"].map((h) => (
                    <th key={h} className="px-4 py-3">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.items.map((row) => (
                  <tr key={row.id} className="border-t">
                    <td className="px-4 py-3">
                      <button
                        className="font-medium text-primary hover:underline"
                        onClick={() => nav(`/backup-recovery/schedules/${row.id}`)}
                      >
                        {row.name}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={row.is_active ? "active" : "inactive"} />
                    </td>
                    <td className="px-4 py-3">{titleCase(row.frequency)}</td>
                    <td className="px-4 py-3">
                      {titleCase(row.scope_type)} · {row.scope_ref}
                    </td>
                    <td className="px-4 py-3">{formatDate(row.next_run_at)}</td>
                    <td className="px-4 py-3">{row.storage_target_name ?? row.storage_target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination meta={result.pagination} onPage={(p) => update("page", String(p))} />
        </Card>
      )}
    </main>
  );
};

export const BackupRetentionPolicyListPage = () => {
  const nav = useNavigate();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const { params, setParams, update, page } = useFilters();
  const filters: RetentionPolicyFilters = {
    page,
    page_size: 25,
    search: params.get("search") || undefined,
    is_active: params.has("is_active") ? params.get("is_active") === "true" : undefined,
    ordering: "name",
  };
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.policies(tenant, filters),
    queryFn: () => backupRecoveryService.listRetentionPolicies(filters),
  });
  if (query.isLoading) return <PageSkeleton table />;
  if (query.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error} onRetry={() => void query.refetch()} />
      </main>
    );
  const filtered = Boolean(filters.search || filters.is_active !== undefined);
  const result = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Retention policies"
        description="Make expiry intent explicit while preserving immutable historical evidence."
        actions={
          <Button onClick={() => nav("/backup-recovery/retention-policies/new")}>
            <Plus className="mr-2 h-4 w-4" />
            Create policy
          </Button>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      <Card className="grid gap-3 p-4 sm:grid-cols-2">
        <Input
          aria-label="Search retention policies"
          placeholder="Name or description"
          value={filters.search ?? ""}
          onChange={(e) => update("search", e.target.value)}
        />
        <select
          aria-label="Policy state filter"
          className="h-10 rounded-md border bg-background px-3"
          value={params.get("is_active") ?? ""}
          onChange={(e) => update("is_active", e.target.value)}
        >
          <option value="">All states</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          filtered={filtered}
          onReset={() => setParams({})}
          title={filtered ? "No policies match" : "No retention policy"}
          description={
            filtered
              ? "Reset the server filters."
              : "Define retention before enabling automated schedules."
          }
          action={
            !filtered
              ? {
                  label: "Create policy",
                  onClick: () => nav("/backup-recovery/retention-policies/new"),
                }
              : undefined
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Policy", "State", "Retain", "Archive after", "Protected minimum"].map((h) => (
                    <th key={h} className="px-4 py-3">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.items.map((row) => (
                  <tr key={row.id} className="border-t">
                    <td className="px-4 py-3">
                      <button
                        className="font-medium text-primary hover:underline"
                        onClick={() => nav(`/backup-recovery/retention-policies/${row.id}`)}
                      >
                        {row.name}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={row.is_active ? "active" : "inactive"} />
                    </td>
                    <td className="px-4 py-3">{row.retention_days} days</td>
                    <td className="px-4 py-3">
                      {row.archive_after_days === null ? "Never" : `${row.archive_after_days} days`}
                    </td>
                    <td className="px-4 py-3">Last {row.keep_last_successful} successful</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination meta={result.pagination} onPage={(p) => update("page", String(p))} />
        </Card>
      )}
    </main>
  );
};

export const BackupStorageTargetListPage = () => {
  const nav = useNavigate();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const { params, setParams, update, page } = useFilters();
  const filters: StorageTargetFilters = {
    page,
    page_size: 25,
    search: params.get("search") || undefined,
    is_active: params.has("is_active") ? params.get("is_active") === "true" : undefined,
    adapter_key: params.get("adapter_key") || undefined,
    ordering: "name",
  };
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.targets(tenant, filters),
    queryFn: () => backupRecoveryService.listStorageTargets(filters),
  });
  if (query.isLoading) return <PageSkeleton table />;
  if (query.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error} onRetry={() => void query.refetch()} />
      </main>
    );
  const filtered = Boolean(
    filters.search || filters.is_active !== undefined || filters.adapter_key
  );
  const result = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Storage targets"
        description="Secret-free references to capture providers. Credentials never enter this catalog."
        actions={
          <Button onClick={() => nav("/backup-recovery/storage-targets/new")}>
            <Plus className="mr-2 h-4 w-4" />
            Add target
          </Button>
        }
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      <Card className="grid gap-3 p-4 sm:grid-cols-3">
        <Input
          aria-label="Search storage targets"
          placeholder="Target name"
          value={filters.search ?? ""}
          onChange={(e) => update("search", e.target.value)}
        />
        <Input
          aria-label="Adapter filter"
          placeholder="Adapter key"
          value={filters.adapter_key ?? ""}
          onChange={(e) => update("adapter_key", e.target.value)}
        />
        <select
          aria-label="Target state filter"
          className="h-10 rounded-md border bg-background px-3"
          value={params.get("is_active") ?? ""}
          onChange={(e) => update("is_active", e.target.value)}
        >
          <option value="">All states</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          filtered={filtered}
          onReset={() => setParams({})}
          title={filtered ? "No targets match" : "No storage target"}
          description={
            filtered
              ? "Reset the server filters."
              : "Configure a provider reference before requesting backup capture."
          }
          action={
            !filtered
              ? { label: "Add target", onClick: () => nav("/backup-recovery/storage-targets/new") }
              : undefined
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Target", "State", "Adapter", "Locator reference", "Role"].map((h) => (
                    <th key={h} className="px-4 py-3">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.items.map((row) => (
                  <tr key={row.id} className="border-t">
                    <td className="px-4 py-3">
                      <button
                        className="font-medium text-primary hover:underline"
                        onClick={() => nav(`/backup-recovery/storage-targets/${row.id}`)}
                      >
                        {row.name}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={row.is_active ? "active" : "inactive"} />
                    </td>
                    <td className="px-4 py-3 font-mono">{row.adapter_key}</td>
                    <td className="max-w-sm truncate px-4 py-3 font-mono text-xs">
                      {row.locator_prefix_ref}
                    </td>
                    <td className="px-4 py-3">{row.is_default ? "Default" : "Available"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination meta={result.pagination} onPage={(p) => update("page", String(p))} />
        </Card>
      )}
    </main>
  );
};

export const BackupArchiveListPage = () => {
  const nav = useNavigate();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const { params, setParams, update, page } = useFilters();
  const filters: ArchiveFilters = {
    page,
    page_size: 25,
    search: params.get("search") || undefined,
    lifecycle: (params.get("lifecycle") as ArchiveFilters["lifecycle"]) ?? undefined,
    integrity_status: (params.get("integrity_status") as IntegrityStatus | null) ?? undefined,
    ordering: "-captured_at",
  };
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.archives(tenant, filters),
    queryFn: () => backupRecoveryService.listBackupArchives(filters),
  });
  if (query.isLoading) return <PageSkeleton table />;
  if (query.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error} onRetry={() => void query.refetch()} />
      </main>
    );
  const filtered = Boolean(filters.search || filters.lifecycle || filters.integrity_status);
  const result = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Backup artifacts"
        description="Immutable catalog evidence. Locator references are masked in list views."
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      <Card className="grid gap-3 p-4 sm:grid-cols-3">
        <Input
          aria-label="Search artifacts"
          placeholder="Exact archive or job ID"
          value={filters.search ?? ""}
          onChange={(e) => update("search", e.target.value)}
        />
        <select
          aria-label="Lifecycle filter"
          className="h-10 rounded-md border bg-background px-3"
          value={filters.lifecycle ?? ""}
          onChange={(e) => update("lifecycle", e.target.value)}
        >
          <option value="">All lifecycle states</option>
          {["available", "expired", "purged"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <select
          aria-label="Integrity filter"
          className="h-10 rounded-md border bg-background px-3"
          value={filters.integrity_status ?? ""}
          onChange={(e) => update("integrity_status", e.target.value)}
        >
          <option value="">All integrity states</option>
          {["unknown", "verifying", "verified", "corrupt"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          filtered={filtered}
          onReset={() => setParams({})}
          title={filtered ? "No artifacts match" : "No completed artifacts"}
          description={
            filtered
              ? "Reset the server filters."
              : "Artifacts appear only after provider evidence is durably recorded."
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[850px] text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Captured", "Lifecycle", "Integrity", "Size", "Adapter", "Job"].map((h) => (
                    <th key={h} className="px-4 py-3">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.items.map((row) => (
                  <tr key={row.id} className="border-t">
                    <td className="px-4 py-3">
                      <button
                        className="font-medium text-primary hover:underline"
                        onClick={() => nav(`/backup-recovery/archives/${row.id}`)}
                      >
                        {formatDate(row.captured_at)}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={row.lifecycle} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={row.integrity_status} />
                    </td>
                    <td className="px-4 py-3">{formatBytes(row.size_bytes)}</td>
                    <td className="px-4 py-3 font-mono">{row.adapter_key}</td>
                    <td className="px-4 py-3 font-mono text-xs">{row.backup_job}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination meta={result.pagination} onPage={(p) => update("page", String(p))} />
        </Card>
      )}
    </main>
  );
};

export const BackupVerificationListPage = () => {
  const nav = useNavigate();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const { params, setParams, update, page } = useFilters();
  const filters: VerificationFilters = {
    page,
    page_size: 25,
    status: (params.get("status") as VerificationStatus | null) ?? undefined,
    archive_id: params.get("archive_id") || undefined,
    ordering: "-requested_at",
  };
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.verifications(tenant, filters),
    queryFn: () => backupRecoveryService.listBackupVerifications(filters),
  });
  if (query.isLoading) return <PageSkeleton table />;
  if (query.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error} onRetry={() => void query.refetch()} />
      </main>
    );
  const filtered = Boolean(filters.status || filters.archive_id);
  const result = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Integrity verifications"
        description="Append-only availability and checksum evidence. This is not restore-readiness testing."
      />
      <div className="flex justify-end">
        <StaleIndicator fetching={query.isFetching} />
      </div>
      <Card className="grid gap-3 p-4 sm:grid-cols-2">
        <Input
          aria-label="Archive filter"
          placeholder="Archive ID"
          value={filters.archive_id ?? ""}
          onChange={(e) => update("archive_id", e.target.value)}
        />
        <select
          aria-label="Verification status filter"
          className="h-10 rounded-md border bg-background px-3"
          value={filters.status ?? ""}
          onChange={(e) => update("status", e.target.value)}
        >
          <option value="">All states</option>
          {["pending", "running", "passed", "failed", "cancelled"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          filtered={filtered}
          onReset={() => setParams({})}
          title={filtered ? "No verifications match" : "No verification history"}
          description={
            filtered
              ? "Reset the server filters."
              : "Open an available artifact to request a real provider verification."
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[750px] text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Requested", "State", "Archive", "Checksum", "Available"].map((h) => (
                    <th key={h} className="px-4 py-3">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.items.map((row) => (
                  <tr key={row.id} className="border-t">
                    <td className="px-4 py-3">
                      <button
                        className="font-medium text-primary hover:underline"
                        onClick={() => nav(`/backup-recovery/verifications/${row.id}`)}
                      >
                        {formatDate(row.requested_at)}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={row.status} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{row.archive}</td>
                    <td className="px-4 py-3">
                      {row.checksum_matches === null
                        ? "Pending"
                        : row.checksum_matches
                          ? "Matches"
                          : "Mismatch"}
                    </td>
                    <td className="px-4 py-3">
                      {row.artifact_available === null
                        ? "Pending"
                        : row.artifact_available
                          ? "Confirmed"
                          : "Unavailable"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination meta={result.pagination} onPage={(p) => update("page", String(p))} />
        </Card>
      )}
    </main>
  );
};
