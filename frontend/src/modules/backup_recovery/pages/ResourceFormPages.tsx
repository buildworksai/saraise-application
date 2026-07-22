import { useRef, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { useAuthStore } from "@/stores/auth-store";
import type {
  BackupFrequency,
  BackupJobCreate,
  BackupRetentionPolicyCreate,
  BackupScheduleCreate,
  BackupStorageTargetCreate,
  BackupType,
  ScopeType,
} from "../contracts";
import { PageHeader, PageSkeleton, ProblemState, titleCase } from "../components/BackupRecoveryUI";
import {
  BackupRecoveryApiError,
  backupRecoveryQueryKeys,
  backupRecoveryService,
  newIdempotencyKey,
} from "../services/backup-recovery-service";

const field = (data: FormData, name: string) => String(data.get(name) ?? "").trim();
const optionalNumber = (data: FormData, name: string) => {
  const value = field(data, name);
  return value === "" ? null : Number(value);
};
const errorFor = (error: unknown, name: string) =>
  error instanceof BackupRecoveryApiError ? error.fieldError(name) : undefined;

function SelectField({
  id,
  label,
  name,
  defaultValue,
  required,
  children,
  error,
}: {
  id: string;
  label: string;
  name: string;
  defaultValue?: string;
  required?: boolean;
  children: ReactNode;
  error?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      <select
        id={id}
        name={name}
        defaultValue={defaultValue}
        required={required}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        className="h-10 w-full rounded-md border bg-background px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {children}
      </select>
      {error && (
        <p id={`${id}-error`} className="mt-1 text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

export const BackupJobCreatePage = () => {
  const nav = useNavigate();
  const client = useQueryClient();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const key = useRef(newIdempotencyKey("backup"));
  const targets = useQuery({
    queryKey: backupRecoveryQueryKeys.targets(tenant, { is_active: true, page_size: 100 }),
    queryFn: () => backupRecoveryService.listStorageTargets({ is_active: true, page_size: 100 }),
  });
  const policies = useQuery({
    queryKey: backupRecoveryQueryKeys.policies(tenant, { is_active: true, page_size: 100 }),
    queryFn: () => backupRecoveryService.listRetentionPolicies({ is_active: true, page_size: 100 }),
  });
  const mutation = useMutation({
    mutationFn: (data: BackupJobCreate) => backupRecoveryService.createBackupJob(data),
    onSuccess: (receipt) => {
      void client.invalidateQueries({ queryKey: backupRecoveryQueryKeys.root(tenant) });
      toast.success("Backup request durably queued");
      nav(`/backup-recovery/jobs/${receipt.job_id}`);
    },
  });
  if (targets.isLoading || policies.isLoading) return <PageSkeleton />;
  if (targets.error || policies.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState
          error={targets.error ?? policies.error}
          onRetry={() => {
            void targets.refetch();
            void policies.refetch();
          }}
        />
      </main>
    );
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Request backup"
        description="Capture executes asynchronously. Success appears only after durable provider and checksum evidence."
        backLabel="Backup jobs"
        onBack={() => nav("/backup-recovery/jobs")}
      />
      <Card className="mx-auto max-w-3xl p-6">
        <form
          className="grid gap-5 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            mutation.mutate({
              backup_type: field(data, "backup_type") as BackupType,
              scope_type: field(data, "scope_type") as ScopeType,
              scope_ref: field(data, "scope_ref"),
              storage_target_id: field(data, "storage_target_id") || undefined,
              retention_policy_id: field(data, "retention_policy_id") || undefined,
              description: field(data, "description"),
              idempotency_key: key.current,
            });
          }}
        >
          <SelectField
            id="backup-type"
            label="Backup type"
            name="backup_type"
            defaultValue="full"
            required
            error={errorFor(mutation.error, "backup_type")}
          >
            {["full", "incremental", "differential"].map((x) => (
              <option key={x} value={x}>
                {titleCase(x)}
              </option>
            ))}
          </SelectField>
          <SelectField
            id="scope-type"
            label="Scope"
            name="scope_type"
            defaultValue="tenant"
            required
            error={errorFor(mutation.error, "scope_type")}
          >
            {["tenant", "module", "database", "files"].map((x) => (
              <option key={x} value={x}>
                {titleCase(x)}
              </option>
            ))}
          </SelectField>
          <Input
            id="scope-ref"
            name="scope_ref"
            label="Scope reference"
            defaultValue="tenant"
            required
            maxLength={255}
            error={errorFor(mutation.error, "scope_ref")}
          />
          <SelectField
            id="target"
            label="Storage target"
            name="storage_target_id"
            defaultValue={targets.data?.items.find((x) => x.is_default)?.id ?? ""}
            error={errorFor(mutation.error, "storage_target_id")}
          >
            <option value="">Tenant default</option>
            {targets.data?.items.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} · {x.adapter_key}
              </option>
            ))}
          </SelectField>
          <SelectField
            id="policy"
            label="Retention policy"
            name="retention_policy_id"
            error={errorFor(mutation.error, "retention_policy_id")}
          >
            <option value="">No automatic expiry</option>
            {policies.data?.items.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} · {x.retention_days} days
              </option>
            ))}
          </SelectField>
          <div className="sm:col-span-2">
            <Textarea
              id="description"
              name="description"
              label="Operator context"
              maxLength={2000}
              error={errorFor(mutation.error, "description")}
            />
          </div>
          {mutation.error && (
            <div className="sm:col-span-2">
              <ProblemState error={mutation.error} />
            </div>
          )}
          <p className="text-xs text-muted-foreground sm:col-span-2">
            Incremental and differential requests require a compatible completed baseline. The
            server selects and validates lineage; unavailable baselines fail explicitly.
          </p>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="secondary" onClick={() => nav("/backup-recovery/jobs")}>
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending || !targets.data?.items.length}>
              {mutation.isPending ? "Durably queueing…" : "Request backup"}
            </Button>
          </div>
        </form>
      </Card>
    </main>
  );
};

export const BackupJobEditPage = () => {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const client = useQueryClient();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.job(tenant, id),
    queryFn: () => backupRecoveryService.getBackupJob(id),
    enabled: Boolean(id),
  });
  const mutation = useMutation({
    mutationFn: (description: string) => backupRecoveryService.updateBackupJob(id, { description }),
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: backupRecoveryQueryKeys.root(tenant) });
      toast.success("Pending job description updated");
      nav(`/backup-recovery/jobs/${job.id}`);
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
  if (query.data.status !== "pending")
    return (
      <main className="space-y-6 p-4 sm:p-8">
        <PageHeader
          title="Job is no longer editable"
          description="Only a pending request description may change. Operational state remains worker-controlled."
          backLabel="Job detail"
          onBack={() => nav(`/backup-recovery/jobs/${id}`)}
        />
        <ProblemState
          error={
            new BackupRecoveryApiError(
              "This job has crossed the pending boundary.",
              409,
              "ILLEGAL_TRANSITION",
              query.data.correlation_id ?? null
            )
          }
        />
      </main>
    );
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Edit pending request"
        description="Only operator context is mutable; scope, evidence, and state are protected."
        backLabel="Job detail"
        onBack={() => nav(`/backup-recovery/jobs/${id}`)}
      />
      <Card className="mx-auto max-w-2xl p-6">
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate(field(new FormData(event.currentTarget), "description"));
          }}
        >
          <Textarea
            id="description"
            name="description"
            label="Operator context"
            defaultValue={query.data.description}
            maxLength={2000}
            error={errorFor(mutation.error, "description")}
          />
          {mutation.error && <ProblemState error={mutation.error} />}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => nav(`/backup-recovery/jobs/${id}`)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving…" : "Save description"}
            </Button>
          </div>
        </form>
      </Card>
    </main>
  );
};

function ScheduleFormPage({ edit }: { edit: boolean }) {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const client = useQueryClient();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const schedule = useQuery({
    queryKey: backupRecoveryQueryKeys.schedule(tenant, id),
    queryFn: () => backupRecoveryService.getBackupSchedule(id),
    enabled: edit && Boolean(id),
  });
  const targets = useQuery({
    queryKey: backupRecoveryQueryKeys.targets(tenant, { is_active: true, page_size: 100 }),
    queryFn: () => backupRecoveryService.listStorageTargets({ is_active: true, page_size: 100 }),
  });
  const policies = useQuery({
    queryKey: backupRecoveryQueryKeys.policies(tenant, { is_active: true, page_size: 100 }),
    queryFn: () => backupRecoveryService.listRetentionPolicies({ is_active: true, page_size: 100 }),
  });
  const mutation = useMutation({
    mutationFn: (data: BackupScheduleCreate) =>
      edit
        ? backupRecoveryService.updateBackupSchedule(id, data)
        : backupRecoveryService.createBackupSchedule(data),
    onSuccess: (saved) => {
      void client.invalidateQueries({ queryKey: backupRecoveryQueryKeys.root(tenant) });
      toast.success(edit ? "Schedule updated" : "Schedule created");
      nav(`/backup-recovery/schedules/${saved.id}`);
    },
  });
  const loading = targets.isLoading || policies.isLoading || (edit && schedule.isLoading);
  const loadError = targets.error ?? policies.error ?? schedule.error;
  if (loading) return <PageSkeleton />;
  if (loadError)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={loadError} />
      </main>
    );
  const current = schedule.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={edit ? "Edit backup schedule" : "Create backup schedule"}
        description="All local times use the selected IANA timezone. DST gaps and overlaps resolve deterministically on the server."
        backLabel="Schedules"
        onBack={() => nav(edit ? `/backup-recovery/schedules/${id}` : "/backup-recovery/schedules")}
      />
      <Card className="mx-auto max-w-4xl p-6">
        <form
          className="grid gap-5 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            mutation.mutate({
              name: field(data, "name"),
              scope_type: field(data, "scope_type") as ScopeType,
              scope_ref: field(data, "scope_ref"),
              backup_type: field(data, "backup_type") as BackupType,
              frequency: field(data, "frequency") as BackupFrequency,
              schedule_time: field(data, "schedule_time") || null,
              day_of_week: optionalNumber(data, "day_of_week"),
              day_of_month: optionalNumber(data, "day_of_month"),
              timezone: field(data, "timezone"),
              storage_target_id: field(data, "storage_target_id"),
              retention_policy_id: field(data, "retention_policy_id"),
              description: field(data, "description"),
            });
          }}
        >
          <Input
            id="name"
            name="name"
            label="Schedule name"
            defaultValue={current?.name}
            required
            maxLength={120}
            error={errorFor(mutation.error, "name")}
          />
          <SelectField
            id="frequency"
            label="Frequency"
            name="frequency"
            defaultValue={current?.frequency ?? "daily"}
            required
            error={errorFor(mutation.error, "frequency")}
          >
            {["hourly", "daily", "weekly", "monthly"].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </SelectField>
          <SelectField
            id="scope-type"
            label="Scope type"
            name="scope_type"
            defaultValue={current?.scope_type ?? "tenant"}
            required
            error={errorFor(mutation.error, "scope_type")}
          >
            {["tenant", "module", "database", "files"].map((x) => (
              <option key={x}>{titleCase(x)}</option>
            ))}
          </SelectField>
          <Input
            id="scope-ref"
            name="scope_ref"
            label="Scope reference"
            defaultValue={current?.scope_ref ?? "tenant"}
            required
            maxLength={255}
            error={errorFor(mutation.error, "scope_ref")}
          />
          <SelectField
            id="backup-type"
            label="Backup type"
            name="backup_type"
            defaultValue={current?.backup_type ?? "full"}
            required
            error={errorFor(mutation.error, "backup_type")}
          >
            {["full", "incremental", "differential"].map((x) => (
              <option key={x}>{titleCase(x)}</option>
            ))}
          </SelectField>
          <Input
            id="timezone"
            name="timezone"
            label="Tenant timezone (IANA)"
            defaultValue={current?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone}
            required
            maxLength={64}
            error={errorFor(mutation.error, "timezone")}
          />
          <Input
            id="schedule-time"
            name="schedule_time"
            label="Local run time"
            type="time"
            defaultValue={current?.schedule_time?.slice(0, 5)}
            error={errorFor(mutation.error, "schedule_time")}
          />
          <Input
            id="day-of-week"
            name="day_of_week"
            label="Day of week (0 Monday–6 Sunday)"
            type="number"
            min={0}
            max={6}
            defaultValue={current?.day_of_week ?? ""}
            error={errorFor(mutation.error, "day_of_week")}
          />
          <Input
            id="day-of-month"
            name="day_of_month"
            label="Day of month (1–28)"
            type="number"
            min={1}
            max={28}
            defaultValue={current?.day_of_month ?? ""}
            error={errorFor(mutation.error, "day_of_month")}
          />
          <SelectField
            id="target"
            label="Storage target"
            name="storage_target_id"
            defaultValue={current?.storage_target}
            required
            error={errorFor(mutation.error, "storage_target_id")}
          >
            {targets.data?.items.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} · {x.adapter_key}
              </option>
            ))}
          </SelectField>
          <SelectField
            id="policy"
            label="Retention policy"
            name="retention_policy_id"
            defaultValue={current?.retention_policy}
            required
            error={errorFor(mutation.error, "retention_policy_id")}
          >
            {policies.data?.items.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} · retain {x.retention_days} days
              </option>
            ))}
          </SelectField>
          <div className="sm:col-span-2">
            <Textarea
              id="description"
              name="description"
              label="Description"
              defaultValue={current?.description}
              maxLength={2000}
              error={errorFor(mutation.error, "description")}
            />
          </div>
          <div className="rounded-md border bg-muted/40 p-4 text-sm sm:col-span-2">
            <strong>Next-run preview:</strong> the backend computes the next valid occurrence after
            save using the selected timezone. Hourly uses no calendar fields; daily uses time;
            weekly adds day of week; monthly adds day 1–28. Incremental schedules remain guarded
            until a compatible full baseline exists.
          </div>
          {mutation.error && (
            <div className="sm:col-span-2">
              <ProblemState error={mutation.error} />
            </div>
          )}
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => nav("/backup-recovery/schedules")}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                mutation.isPending || !targets.data?.items.length || !policies.data?.items.length
              }
            >
              {mutation.isPending ? "Saving…" : edit ? "Save schedule" : "Create schedule"}
            </Button>
          </div>
        </form>
      </Card>
    </main>
  );
}
export const BackupScheduleCreatePage = () => <ScheduleFormPage edit={false} />;
export const BackupScheduleEditPage = () => <ScheduleFormPage edit />;

function PolicyFormPage({ edit }: { edit: boolean }) {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const client = useQueryClient();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.policy(tenant, id),
    queryFn: () => backupRecoveryService.getRetentionPolicy(id),
    enabled: edit && Boolean(id),
  });
  const mutation = useMutation({
    mutationFn: (data: BackupRetentionPolicyCreate) =>
      edit
        ? backupRecoveryService.updateRetentionPolicy(id, data)
        : backupRecoveryService.createRetentionPolicy(data),
    onSuccess: (saved) => {
      void client.invalidateQueries({ queryKey: backupRecoveryQueryKeys.root(tenant) });
      toast.success(edit ? "Retention policy updated" : "Retention policy created");
      nav(`/backup-recovery/retention-policies/${saved.id}`);
    },
  });
  if (edit && query.isLoading) return <PageSkeleton />;
  if (query.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error} />
      </main>
    );
  const current = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={edit ? "Edit retention policy" : "Create retention policy"}
        description="Policy edits never rewrite expiry evidence already attached to artifacts."
        backLabel="Retention"
        onBack={() =>
          nav(
            edit
              ? `/backup-recovery/retention-policies/${id}`
              : "/backup-recovery/retention-policies"
          )
        }
      />
      <Card className="mx-auto max-w-3xl p-6">
        <form
          className="grid gap-5 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            mutation.mutate({
              name: field(data, "name"),
              retention_days: Number(field(data, "retention_days")),
              archive_after_days: optionalNumber(data, "archive_after_days"),
              keep_last_successful: Number(field(data, "keep_last_successful")),
              description: field(data, "description"),
            });
          }}
        >
          <Input
            id="name"
            name="name"
            label="Policy name"
            defaultValue={current?.name}
            required
            maxLength={120}
            error={errorFor(mutation.error, "name")}
          />
          <Input
            id="retention-days"
            name="retention_days"
            label="Retention days"
            type="number"
            min={1}
            max={3650}
            defaultValue={current?.retention_days ?? 30}
            required
            error={errorFor(mutation.error, "retention_days")}
          />
          <Input
            id="archive-days"
            name="archive_after_days"
            label="Archive after days (optional)"
            type="number"
            min={1}
            max={3649}
            defaultValue={current?.archive_after_days ?? ""}
            error={errorFor(mutation.error, "archive_after_days")}
          />
          <Input
            id="keep-last"
            name="keep_last_successful"
            label="Always keep successful"
            type="number"
            min={1}
            defaultValue={current?.keep_last_successful ?? 3}
            required
            error={errorFor(mutation.error, "keep_last_successful")}
          />
          <div className="sm:col-span-2">
            <Textarea
              id="description"
              name="description"
              label="Description"
              defaultValue={current?.description}
              error={errorFor(mutation.error, "description")}
            />
          </div>
          {mutation.error && (
            <div className="sm:col-span-2">
              <ProblemState error={mutation.error} />
            </div>
          )}
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => nav("/backup-recovery/retention-policies")}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving…" : "Save policy"}
            </Button>
          </div>
        </form>
      </Card>
    </main>
  );
}
export const BackupRetentionPolicyCreatePage = () => <PolicyFormPage edit={false} />;
export const BackupRetentionPolicyEditPage = () => <PolicyFormPage edit />;

function TargetFormPage({ edit }: { edit: boolean }) {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const client = useQueryClient();
  const tenant = useAuthStore((state) => state.user?.tenant_id ?? null);
  const query = useQuery({
    queryKey: backupRecoveryQueryKeys.target(tenant, id),
    queryFn: () => backupRecoveryService.getStorageTarget(id),
    enabled: edit && Boolean(id),
  });
  const mutation = useMutation({
    mutationFn: (data: BackupStorageTargetCreate) =>
      edit
        ? backupRecoveryService.updateStorageTarget(id, data)
        : backupRecoveryService.createStorageTarget(data),
    onSuccess: (saved) => {
      void client.invalidateQueries({ queryKey: backupRecoveryQueryKeys.root(tenant) });
      toast.success(edit ? "Storage target updated" : "Storage target created");
      nav(`/backup-recovery/storage-targets/${saved.id}`);
    },
  });
  if (edit && query.isLoading) return <PageSkeleton />;
  if (query.error)
    return (
      <main className="p-4 sm:p-8">
        <ProblemState error={query.error} />
      </main>
    );
  const current = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={edit ? "Edit storage target" : "Add storage target"}
        description="Store opaque configuration references only—never credentials, signed URLs, tokens, or inline keys."
        backLabel="Storage targets"
        onBack={() =>
          nav(edit ? `/backup-recovery/storage-targets/${id}` : "/backup-recovery/storage-targets")
        }
      />
      <Card className="mx-auto max-w-3xl p-6">
        <form
          className="grid gap-5 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            mutation.mutate({
              name: field(data, "name"),
              adapter_key: field(data, "adapter_key"),
              locator_prefix_ref: field(data, "locator_prefix_ref"),
              configuration_ref: field(data, "configuration_ref"),
              encryption_key_ref: field(data, "encryption_key_ref") || undefined,
            });
          }}
        >
          <Input
            id="name"
            name="name"
            label="Target name"
            defaultValue={current?.name}
            required
            maxLength={120}
            error={errorFor(mutation.error, "name")}
          />
          <Input
            id="adapter-key"
            name="adapter_key"
            label="Adapter key"
            defaultValue={current?.adapter_key ?? "local-filesystem"}
            required
            pattern="[a-z0-9]+(?:[-_.][a-z0-9]+)*"
            error={errorFor(mutation.error, "adapter_key")}
          />
          <div className="sm:col-span-2">
            <Input
              id="locator"
              name="locator_prefix_ref"
              label="Locator prefix reference"
              defaultValue={current?.locator_prefix_ref}
              required
              maxLength={1024}
              error={errorFor(mutation.error, "locator_prefix_ref")}
            />
          </div>
          <Input
            id="config"
            name="configuration_ref"
            label="Configuration reference"
            defaultValue={current?.configuration_ref}
            required
            maxLength={255}
            error={errorFor(mutation.error, "configuration_ref")}
          />
          <Input
            id="key-ref"
            name="encryption_key_ref"
            label="Encryption key reference (optional)"
            defaultValue={current?.encryption_key_ref}
            maxLength={255}
            error={errorFor(mutation.error, "encryption_key_ref")}
          />
          {mutation.error && (
            <div className="sm:col-span-2">
              <ProblemState error={mutation.error} />
            </div>
          )}
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => nav("/backup-recovery/storage-targets")}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving securely…" : "Save target"}
            </Button>
          </div>
        </form>
      </Card>
    </main>
  );
}
export const BackupStorageTargetCreatePage = () => <TargetFormPage edit={false} />;
export const BackupStorageTargetEditPage = () => <TargetFormPage edit />;
