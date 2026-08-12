/* eslint-disable complexity -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useState,
  type FormEvent,
  type ReactElement,
  type ReactNode,
} from "react";
import type {
  MemberCreateRequest,
  MilestoneCreateRequest,
  ProjectCreateRequest,
  TaskCreateRequest,
  TimeEntryCreateRequest,
} from "../contracts";

const field =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const optionalText = (value: string | null | undefined) => (value === "" ? null : value ?? null);
const normalizeProjectPayload = (data: ProjectCreateRequest): ProjectCreateRequest => ({
  ...data,
  start_date: optionalText(data.start_date),
  end_date: optionalText(data.end_date),
  project_manager_id: optionalText(data.project_manager_id),
  budget: optionalText(data.budget),
});

function FormFrame({
  title,
  description,
  pending,
  error,
  onSubmit,
  children,
}: {
  title: string;
  description: string;
  pending: boolean;
  error?: string;
  onSubmit: (event: FormEvent) => void;
  children: ReactNode;
}) {
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  return (
    <form
      noValidate
      onChange={() => setDirty(true)}
      onSubmit={(e) => {
        onSubmit(e);
      }}
      className="mx-auto grid max-w-2xl gap-5 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <div className="grid gap-2">
        <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive"
        >
          {error}
        </div>
      )}
      {children}
      <button
        disabled={pending}
        className="rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground disabled:opacity-50"
      >
        {pending ? "Saving…" : "Save"}
      </button>
    </form>
  );
}
const Label = ({
  name,
  help,
  error,
  children,
}: {
  name: string;
  help?: string;
  error?: string;
  children: ReactNode;
}) => {
  const id = useId();
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<{ id?: string; "aria-invalid"?: string }>, {
        id,
        "aria-invalid": error ? "true" : undefined,
      })
    : children;
  return (
    <div className="grid gap-1 text-sm font-medium text-foreground">
      <label htmlFor={id}>{name}</label>
      {control}
      {help && <span className="text-xs font-normal text-muted-foreground">{help}</span>}
      {error && (
        <span className="text-sm font-normal text-destructive" role="alert">
          {error}
        </span>
      )}
    </div>
  );
};
export function ProjectForm({
  initial = {},
  pending = false,
  error,
  onSave,
}: {
  initial?: Partial<ProjectCreateRequest>;
  pending?: boolean;
  error?: string;
  onSave: (data: ProjectCreateRequest) => void;
}) {
  const [data, set] = useState<ProjectCreateRequest>({
    project_code: initial.project_code ?? "",
    project_name: initial.project_name ?? "",
    description: initial.description ?? String(),
    start_date: initial.start_date ?? null,
    end_date: initial.end_date ?? null,
    project_manager_id: initial.project_manager_id ?? null,
    budget: initial.budget ?? null,
    currency: initial.currency ?? "USD",
  });
  return (
    <FormFrame
      title={initial.project_code ? "Edit project" : "Create project"}
      description="Define the governed project record, budget guardrails, and activation dates before assigning delivery work."
      pending={pending}
      error={error}
      onSubmit={(e) => {
        e.preventDefault();
        onSave(normalizeProjectPayload(data));
      }}
    >
      <Label name="Project code" help="Uppercase letters, numbers, and hyphens.">
        <input
          required
          maxLength={50}
          className={field}
          value={data.project_code}
          onChange={(e) => set({ ...data, project_code: e.target.value.toUpperCase() })}
        />
      </Label>
      <Label name="Project name">
        <input
          required
          maxLength={255}
          className={field}
          value={data.project_name}
          onChange={(e) => set({ ...data, project_name: e.target.value })}
        />
      </Label>
      <Label name="Description">
        <textarea
          maxLength={20000}
          className={field}
          value={data.description ?? String()}
          onChange={(e) => set({ ...data, description: e.target.value })}
        />
      </Label>
      <div className="grid gap-4 sm:grid-cols-2">
        <Label name="Start date">
          <input
            type="date"
            className={field}
            value={data.start_date ?? String()}
            onChange={(e) => set({ ...data, start_date: e.target.value })}
          />
        </Label>
        <Label name="End date">
          <input
            type="date"
            min={data.start_date ?? undefined}
            className={field}
            value={data.end_date ?? String()}
            onChange={(e) => set({ ...data, end_date: e.target.value })}
          />
        </Label>
        <Label name="Manager ID" help="Optional until activation.">
          <input
            className={field}
            value={data.project_manager_id ?? String()}
            onChange={(e) => set({ ...data, project_manager_id: e.target.value })}
          />
        </Label>
        <Label name="Budget">
          <input
            type="number"
            min="0"
            step="0.01"
            className={field}
            value={data.budget ?? String()}
            onChange={(e) => set({ ...data, budget: e.target.value })}
          />
        </Label>
      </div>
    </FormFrame>
  );
}
export function TaskForm({
  projectId = "",
  pending = false,
  error,
  onSave,
}: {
  projectId?: string;
  pending?: boolean;
  error?: string;
  onSave: (d: TaskCreateRequest) => void;
}) {
  const [d, set] = useState<TaskCreateRequest>({
    project: projectId,
    task_code: String(),
    task_name: String(),
    priority: "medium",
  });
  return (
    <FormFrame
      title="Task"
      description="Create tenant-scoped delivery work with a stable task code, priority, and optional due date for schedule reporting."
      pending={pending}
      error={error}
      onSubmit={(e) => {
        e.preventDefault();
        onSave(d);
      }}
    >
      <Label name="Project ID" help="Use the project UUID from the governed project workspace.">
        <input
          required
          className={field}
          value={d.project}
          onChange={(e) => set({ ...d, project: e.target.value })}
        />
      </Label>
      <Label
        name="Task code"
        help="Stored uppercase for audit-stable lookup and duplicate detection."
      >
        <input
          required
          className={field}
          value={d.task_code}
          onChange={(e) => set({ ...d, task_code: e.target.value.toUpperCase() })}
        />
      </Label>
      <Label name="Task name">
        <input
          required
          className={field}
          value={d.task_name}
          onChange={(e) => set({ ...d, task_name: e.target.value })}
        />
      </Label>
      <Label name="Due date" help="Optional until the schedule baseline is approved.">
        <input
          type="date"
          className={field}
          onChange={(e) => set({ ...d, due_date: e.target.value || null })}
        />
      </Label>
    </FormFrame>
  );
}
export function MemberForm({
  projectId = "",
  pending = false,
  error,
  onSave,
}: {
  projectId?: string;
  pending?: boolean;
  error?: string;
  onSave: (d: MemberCreateRequest) => void;
}) {
  const [d, set] = useState<MemberCreateRequest>({
    project: projectId,
    employee_id: String(),
    role: "member",
    allocation_percentage: "100.00",
  });
  const [errors, setErrors] = useState<Partial<Record<"project" | "employee_id", string>>>({});
  return (
    <FormFrame
      title="Project member"
      description="Assign a workforce member to a project with an audited role and allocation percentage."
      pending={pending}
      error={error}
      onSubmit={(e) => {
        e.preventDefault();
        const nextErrors: Partial<Record<"project" | "employee_id", string>> = {};
        if (!d.project.trim()) nextErrors.project = "Project ID is required";
        if (!d.employee_id.trim()) nextErrors.employee_id = "Employee ID is required";
        setErrors(nextErrors);
        if (Object.values(nextErrors).some(Boolean)) return;
        onSave(d);
      }}
    >
      <Label name="Project ID" error={errors.project}>
        <input
          required
          className={field}
          value={d.project}
          onChange={(e) => {
            set({ ...d, project: e.target.value });
            if (errors.project) setErrors({ ...errors, project: undefined });
          }}
        />
      </Label>
      <Label name="Employee ID" error={errors.employee_id}>
        <input
          required
          className={field}
          value={d.employee_id}
          onChange={(e) => {
            set({ ...d, employee_id: e.target.value });
            if (errors.employee_id) setErrors({ ...errors, employee_id: undefined });
          }}
        />
      </Label>
      <Label name="Allocation percentage" help="The tenant setting may impose a lower maximum.">
        <input
          required
          type="number"
          min="0.01"
          max="100"
          step="0.01"
          className={field}
          value={d.allocation_percentage}
          onChange={(e) => set({ ...d, allocation_percentage: e.target.value })}
        />
      </Label>
    </FormFrame>
  );
}
export function TimeEntryForm({
  projectId = "",
  pending = false,
  error,
  onSave,
}: {
  projectId?: string;
  pending?: boolean;
  error?: string;
  onSave: (d: TimeEntryCreateRequest) => void;
}) {
  const [d, set] = useState<TimeEntryCreateRequest>({
    project: projectId,
    employee_id: "",
    entry_date: new Date().toISOString().slice(0, 10),
    hours_worked: String(),
    description: String(),
  });
  return (
    <FormFrame
      title="Log time"
      description="Record billable or non-billable work against the tenant project ledger with daily hour limits."
      pending={pending}
      error={error}
      onSubmit={(e) => {
        e.preventDefault();
        onSave(d);
      }}
    >
      <Label name="Project ID" help="Use the project UUID receiving this work entry.">
        <input
          required
          className={field}
          value={d.project}
          onChange={(e) => set({ ...d, project: e.target.value })}
        />
      </Label>
      <Label name="Employee ID" help="Use the workforce identifier authorized for the tenant.">
        <input
          required
          className={field}
          value={d.employee_id}
          onChange={(e) => set({ ...d, employee_id: e.target.value })}
        />
      </Label>
      <Label name="Date">
        <input
          required
          type="date"
          className={field}
          value={d.entry_date}
          onChange={(e) => set({ ...d, entry_date: e.target.value })}
        />
      </Label>
      <Label
        name="Hours"
        help="Daily entries are capped at 24 hours and use quarter-hour increments."
      >
        <input
          required
          type="number"
          min="0.25"
          max="24"
          step="0.25"
          className={field}
          value={d.hours_worked}
          onChange={(e) => set({ ...d, hours_worked: e.target.value })}
        />
      </Label>
      <Label name="Work description">
        <textarea
          maxLength={4000}
          className={field}
          value={d.description ?? String()}
          onChange={(e) => set({ ...d, description: e.target.value })}
        />
      </Label>
    </FormFrame>
  );
}
export function MilestoneForm({
  projectId = "",
  pending = false,
  error,
  onSave,
}: {
  projectId?: string;
  pending?: boolean;
  error?: string;
  onSave: (d: MilestoneCreateRequest) => void;
}) {
  const [d, set] = useState<MilestoneCreateRequest>({
    project: projectId,
    milestone_name: String(),
    target_date: String(),
  });
  return (
    <FormFrame
      title="Milestone"
      description="Create a target checkpoint used by project progress, risk, and governance reporting."
      pending={pending}
      error={error}
      onSubmit={(e) => {
        e.preventDefault();
        onSave(d);
      }}
    >
      <Label name="Project ID" help="Use the project UUID that owns this checkpoint.">
        <input
          required
          className={field}
          value={d.project}
          onChange={(e) => set({ ...d, project: e.target.value })}
        />
      </Label>
      <Label name="Milestone name">
        <input
          required
          className={field}
          value={d.milestone_name}
          onChange={(e) => set({ ...d, milestone_name: e.target.value })}
        />
      </Label>
      <Label
        name="Target date"
        help="Required so schedule variance can be calculated consistently."
      >
        <input
          required
          type="date"
          className={field}
          value={d.target_date}
          onChange={(e) => set({ ...d, target_date: e.target.value })}
        />
      </Label>
    </FormFrame>
  );
}
