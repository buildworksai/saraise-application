import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, ArrowUp, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import type {
  ActionStepConfig, ApprovalStepConfig, ConditionDescriptorDTO, DefinitionValidationResultDTO,
  HandlerDescriptorDTO, JsonValue, NotificationStepConfig, StepType, UISchemaField,
  WorkflowCreateDTO, WorkflowDetailDTO, WorkflowStepWriteDTO, WorkflowType,
  WorkflowConfigurationDocument,
} from "../contracts";
import { ROUTES } from "../contracts";
import { workflowService } from "../services/workflow-service";
import { StatusPill } from "./WorkflowUI";
import { useWorkflowConfiguration } from "../hooks/use-workflow-configuration";

interface WorkflowBuilderProps {
  initial?: WorkflowDetailDTO;
  submitting: boolean;
  submitLabel: string;
  serverError?: Error | null;
  onSubmit: (payload: WorkflowCreateDTO) => Promise<void>;
  onCancel: (path: string) => void;
}

const inputClass = "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const slug = (value: string, maximum: number): string => value.trim().toLowerCase().replace(/[^a-z0-9]+/gu, "_").replace(/^_+|_+$/gu, "").slice(0, maximum);
function recipientPath(config: NotificationStepConfig): string {
  const value = config.recipient_mapping[config.channel === "email" ? "recipient_email" : "recipient_id"];
  return typeof value === "string" ? value : "";
}

function newStep(type: StepType, order: number, policy: WorkflowConfigurationDocument): WorkflowStepWriteDTO {
  const key = `step_${order}`;
  if (type === "approval") return { key, name: `Approval ${order}`, step_type: type, order, config: { assignment_kind: policy.defaults.approval_assignment_kind, assignee_id: "", due_in_seconds: policy.defaults.approval_due_seconds, rejection_behavior: policy.defaults.approval_rejection_behavior, reject_step_key: null }, is_terminal: false };
  if (type === "notification") return { key, name: `Notification ${order}`, step_type: type, order, config: { channel: "in_app", recipient_mapping: { recipient_id: "actor.id" }, template_key: "workflow.task.created" }, is_terminal: false };
  if (type === "decision") return { key, name: `Decision ${order}`, step_type: type, order, config: { condition: {}, true_step_key: "", false_step_key: "" }, is_terminal: false };
  return { key, name: `Action ${order}`, step_type: type, order, config: { handler: "", schema_version: "", input_mapping: {}, configuration: {} }, is_terminal: false };
}

// Validation deliberately keeps every graph/config branch visible for step-linked feedback.
// eslint-disable-next-line complexity
function localIssues(payload: WorkflowCreateDTO): readonly string[] {
  const issues: string[] = [];
  if (!payload.key.trim()) issues.push("Workflow key is required.");
  if (!payload.name.trim()) issues.push("Workflow name is required.");
  if (payload.steps.length === 0) issues.push("Add at least one step.");
  const keys = new Set<string>();
  for (const step of payload.steps) {
    if (!step.key.trim() || keys.has(step.key)) issues.push(`Step ${step.order} needs a unique key.`);
    keys.add(step.key);
    if (!step.name.trim()) issues.push(`Step ${step.order} needs a name.`);
    if (step.step_type === "action" && !(step.config as ActionStepConfig).handler) issues.push(`${step.name}: choose an available action.`);
    if (step.step_type === "approval" && !(step.config as ApprovalStepConfig).assignee_id) issues.push(`${step.name}: choose an assignee.`);
    if (step.step_type === "decision") {
      const config = step.config;
      if (!("condition" in config) || typeof config.condition.handler !== "string" || !config.condition.handler) issues.push(`${step.name}: choose a condition.`);
      if (!("true_step_key" in config) || !keys.has(config.true_step_key) && !payload.steps.some((candidate) => candidate.key === config.true_step_key)) issues.push(`${step.name}: select a valid true branch.`);
      if (!("false_step_key" in config) || !keys.has(config.false_step_key) && !payload.steps.some((candidate) => candidate.key === config.false_step_key)) issues.push(`${step.name}: select a valid false branch.`);
    }
  }
  if (payload.steps.length > 0 && !payload.steps.some((step) => step.is_terminal)) issues.push("Mark at least one step as terminal.");
  return issues;
}

function SchemaField({ field, value, onChange }: { field: UISchemaField; value: JsonValue | undefined; onChange: (value: JsonValue) => void }) {
  const lookup = useQuery({ queryKey: ["workflow-catalog-lookup", field.kind === "lookup" ? field.lookup_key : "none"], queryFn: () => field.kind === "lookup" ? workflowService.catalog.lookup(field.lookup_key) : Promise.resolve([]), enabled: field.kind === "lookup" });
  const id = `descriptor-${field.key}`;
  if (field.kind === "boolean") return <label className="flex items-center gap-2 text-sm"><input id={id} type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)}/>{field.label}</label>;
  if (field.kind === "select") return <label htmlFor={id} className="block text-sm font-medium">{field.label}<select id={id} required={field.required} className={`${inputClass} mt-1`} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)}><option value="">Select…</option>{field.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
  if (field.kind === "lookup") return <label htmlFor={id} className="block text-sm font-medium">{field.label}<select id={id} required={field.required} disabled={lookup.isLoading || lookup.isError} className={`${inputClass} mt-1`} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)}><option value="">{lookup.isError ? "Lookup unavailable" : "Select…"}</option>{lookup.data?.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>;
  return <Input id={id} label={field.label} type={field.kind === "number" ? "number" : "text"} required={field.required} min={field.kind === "number" ? field.minimum : undefined} max={field.kind === "number" ? field.maximum : undefined} placeholder={field.kind === "text" ? field.placeholder : undefined} value={typeof value === "string" || typeof value === "number" ? value : ""} onChange={(event) => onChange(field.kind === "number" ? Number(event.target.value) : event.target.value)}/>;
}

function DescriptorBadge({ descriptor }: { descriptor: HandlerDescriptorDTO | ConditionDescriptorDTO }) {
  return <div className="flex items-center justify-between gap-3 rounded border p-2"><div><p className="text-sm font-medium">{descriptor.display_name}</p><p className="text-xs text-muted-foreground">{descriptor.owning_module} · {descriptor.schema_version}</p></div><StatusPill status={descriptor.availability}/></div>;
}

// eslint-disable-next-line complexity
export function WorkflowBuilder({ initial, submitting, submitLabel, serverError, onSubmit, onCancel }: WorkflowBuilderProps) {
  const configuration = useWorkflowConfiguration();
  const policy = configuration.data?.document;
  const [name, setName] = useState(initial?.name ?? "");
  const [key, setKey] = useState(initial?.key ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [workflowType, setWorkflowType] = useState<WorkflowType | null>(initial?.workflow_type ?? null);
  const [triggerType, setTriggerType] = useState<WorkflowDetailDTO["trigger_type"] | null>(initial?.trigger_type ?? null);
  const [steps, setSteps] = useState<readonly WorkflowStepWriteDTO[]>(initial?.steps.map(({ key: stepKey, name: stepName, step_type, order, config, timeout_seconds, timeout_action, is_terminal }) => ({ key: stepKey, name: stepName, step_type, order, config, timeout_seconds, timeout_action, is_terminal })) ?? []);
  const [dirty, setDirty] = useState(false);
  const [validation, setValidation] = useState<DefinitionValidationResultDTO | null>(null);
  const actions = useQuery({ queryKey: ["workflow-catalog-actions"], queryFn: workflowService.catalog.actions });
  const conditions = useQuery({ queryKey: ["workflow-catalog-conditions"], queryFn: workflowService.catalog.conditions });
  const assignees = useQuery({ queryKey: ["workflow-catalog-assignees"], queryFn: () => workflowService.catalog.assignees() });
  const resolvedWorkflowType = workflowType ?? policy?.defaults.workflow_type;
  const resolvedTriggerType = triggerType ?? policy?.defaults.trigger_type;
  const payload = useMemo<WorkflowCreateDTO | null>(() => resolvedWorkflowType && resolvedTriggerType ? ({ key, name, description, workflow_type: resolvedWorkflowType, trigger_type: resolvedTriggerType, trigger_config: initial?.trigger_config ?? {}, required_context_schema: initial?.required_context_schema ?? {}, steps }) : null, [description, initial?.required_context_schema, initial?.trigger_config, key, name, resolvedTriggerType, resolvedWorkflowType, steps]);
  const issues = useMemo(() => payload ? localIssues(payload) : ["Workflow configuration is unavailable."], [payload]);
  const validateMutation = useMutation({ mutationFn: () => { if (!payload) throw new Error("Workflow configuration is unavailable."); return workflowService.workflows.validate(payload); }, onSuccess: setValidation });

  useEffect(() => { const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); }; window.addEventListener("beforeunload", guard); return () => window.removeEventListener("beforeunload", guard); }, [dirty]);
  const changed = (): void => { setDirty(true); setValidation(null); };
  const replaceStep = (index: number, next: WorkflowStepWriteDTO): void => { setSteps((current) => current.map((step, position) => position === index ? next : step)); changed(); };
  const add = (type: StepType): void => { if (!policy) return; setSteps((current) => [...current, newStep(type, current.length + 1, policy)]); changed(); };
  const remove = (index: number): void => { setSteps((current) => current.filter((_, position) => position !== index).map((step, position) => ({ ...step, order: position + 1 }))); changed(); };
  const move = (index: number, offset: -1 | 1): void => { const target = index + offset; if (target < 0 || target >= steps.length) return; const reordered = [...steps]; const sourceStep = reordered[index]; const targetStep = reordered[target]; if (!sourceStep || !targetStep) return; reordered[index] = targetStep; reordered[target] = sourceStep; setSteps(reordered.map((step, position) => ({ ...step, order: position + 1 }))); changed(); };
  const navigateAway = (): void => { if (!dirty || window.confirm("Discard unsaved workflow changes?")) onCancel(initial ? ROUTES.WORKFLOW_DETAIL(initial.id) : ROUTES.WORKFLOWS); };

  if (!policy || !payload) return <main role="status" className="rounded border p-6">Loading governed workflow configuration…</main>;
  return <main className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><Button variant="ghost" onClick={navigateAway}><ArrowLeft className="mr-2 h-4 w-4"/>Back</Button><div className="flex gap-2"><Button variant="outline" disabled={validateMutation.isPending || issues.length > 0} onClick={() => validateMutation.mutate()}><ShieldCheck className="mr-2 h-4 w-4"/>Validate</Button><Button disabled={submitting || issues.length > 0} onClick={() => void onSubmit(payload).then(() => setDirty(false))}><Save className="mr-2 h-4 w-4"/>{submitting ? "Saving…" : submitLabel}</Button></div></div>
    {serverError ? <div role="alert" className="rounded border border-destructive/40 p-3 text-sm text-destructive">{serverError.message}</div> : null}
    <div className="grid gap-5 xl:grid-cols-[310px_minmax(0,1fr)]">
      <aside className="space-y-5"><Card className="space-y-4 p-5"><h2 className="font-semibold">Definition</h2><Input id="workflow-name" label="Name" value={name} onChange={(event) => { setName(event.target.value); if (!initial) setKey(slug(event.target.value, policy.limits.generated_step_key_max_length)); changed(); }}/><Input id="workflow-key" label="Stable key" value={key} readOnly={Boolean(initial)} onChange={(event) => { setKey(slug(event.target.value, policy.limits.generated_step_key_max_length)); changed(); }}/><label htmlFor="workflow-description" className="block text-sm font-medium">Description<Textarea id="workflow-description" className="mt-1" value={description} onChange={(event) => { setDescription(event.target.value); changed(); }}/></label><label className="block text-sm font-medium">Workflow type<select className={`${inputClass} mt-1`} value={resolvedWorkflowType} onChange={(event) => { setWorkflowType(event.target.value as WorkflowType); changed(); }}>{policy.allowed_values.workflow_types.map((value) => <option key={value}>{value}</option>)}</select></label><label className="block text-sm font-medium">Trigger<select className={`${inputClass} mt-1`} value={resolvedTriggerType} onChange={(event) => { setTriggerType(event.target.value as WorkflowDetailDTO["trigger_type"]); changed(); }}>{policy.allowed_values.trigger_types.map((value) => <option key={value}>{value}</option>)}</select></label></Card>
        <Card className="space-y-3 p-5"><h2 className="font-semibold">Step palette</h2><p className="text-xs text-muted-foreground">Choose a type. Every extension is discovered from the governed catalog.</p>{(["action","approval","notification","decision"] as const).map((type) => <Button key={type} className="w-full justify-start" variant="outline" onClick={() => add(type)}><Plus className="mr-2 h-4 w-4"/>Add {type}</Button>)}</Card>
        {(actions.error || conditions.error) ? <div role="alert" className="rounded border border-destructive/40 p-3 text-sm">Extension catalog unavailable. Saving action or decision steps is blocked.</div> : null}
      </aside>
      <section aria-label="Workflow steps" className="space-y-4">{steps.length === 0 ? <Card className="border-dashed p-10 text-center"><h2 className="font-semibold">Design the first step</h2><p className="mt-2 text-sm text-muted-foreground">Use the palette. No JSON, scripts, URLs, or raw identifiers are accepted.</p></Card> : null}
        {steps.map(
          // Rendering is discriminated by the four governed step contracts.
          // eslint-disable-next-line complexity
          (step, index) => {
          const action = step.step_type === "action" ? actions.data?.find((descriptor) => descriptor.key === (step.config as ActionStepConfig).handler) : undefined;
          const configuration = step.step_type === "action" && "configuration" in step.config ? step.config.configuration ?? {} : {};
          const decisionConfig = step.step_type === "decision" && "condition" in step.config ? step.config : null;
          const conditionHandler = decisionConfig && typeof decisionConfig.condition.handler === "string" ? decisionConfig.condition.handler : "";
          const conditionDescriptor = conditions.data?.find((descriptor) => descriptor.key === conditionHandler);
          return <Card key={`${step.key}-${index}`} className="p-5"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div className="flex-1 space-y-4"><div className="grid gap-3 sm:grid-cols-2"><Input id={`step-name-${index}`} label={`Step ${index + 1} name`} value={step.name} onChange={(event) => replaceStep(index, { ...step, name: event.target.value, key: slug(event.target.value, policy.limits.generated_step_key_max_length) || step.key })}/><Input id={`step-key-${index}`} label="Step key" value={step.key} onChange={(event) => replaceStep(index, { ...step, key: slug(event.target.value, policy.limits.generated_step_key_max_length) })}/></div>
            {step.step_type === "action" ? <div className="space-y-3"><label className="block text-sm font-medium">Registered action<select className={`${inputClass} mt-1`} value={(step.config as ActionStepConfig).handler} onChange={(event) => { const descriptor = actions.data?.find((item) => item.key === event.target.value); if (descriptor?.availability !== "available") return; replaceStep(index, { ...step, config: { handler: descriptor.key, schema_version: descriptor.schema_version, input_mapping: {}, configuration: {} } }); }}><option value="">Select an available action…</option>{actions.data?.map((descriptor) => <option key={descriptor.key} value={descriptor.key} disabled={descriptor.availability !== "available"}>{descriptor.display_name} — {descriptor.availability.replaceAll("_", " ")}</option>)}</select></label>{action ? <><DescriptorBadge descriptor={action}/><div className="grid gap-3 sm:grid-cols-2">{action.ui_schema.map((field) => <SchemaField key={field.key} field={field} value={configuration[field.key]} onChange={(value) => replaceStep(index, { ...step, config: { ...(step.config as ActionStepConfig), configuration: { ...configuration, [field.key]: value } } })}/>)}</div></> : null}</div> : null}
            {step.step_type === "approval" ? <div className="grid gap-3 sm:grid-cols-2"><label className="block text-sm font-medium">Assignment<select className={`${inputClass} mt-1`} value={(step.config as ApprovalStepConfig).assignee_id} disabled={assignees.isLoading || assignees.isError} onChange={(event) => { const option = assignees.data?.find((item) => item.id === event.target.value); if (!option) return; replaceStep(index, { ...step, config: { ...(step.config as ApprovalStepConfig), assignment_kind: option.kind === "role" ? "role" : "user", assignee_id: option.id } }); }}><option value="">{assignees.isError ? "Assignee directory unavailable" : "Choose a user or role…"}</option>{assignees.data?.map((option) => <option key={option.id} value={option.id}>{option.label} ({option.kind})</option>)}</select></label><Input label="Due time units" type="number" min={policy.ui.minimum_due_time_units} value={Math.round((step.config as ApprovalStepConfig).due_in_seconds / policy.ui.due_time_unit_seconds)} onChange={(event) => replaceStep(index, { ...step, config: { ...(step.config as ApprovalStepConfig), due_in_seconds: Number(event.target.value) * policy.ui.due_time_unit_seconds } })}/><label className="block text-sm font-medium">On rejection<select className={`${inputClass} mt-1`} value={(step.config as ApprovalStepConfig).rejection_behavior} onChange={(event) => replaceStep(index, { ...step, config: { ...(step.config as ApprovalStepConfig), rejection_behavior: event.target.value as ApprovalStepConfig["rejection_behavior"], reject_step_key: event.target.value === "goto" ? (step.config as ApprovalStepConfig).reject_step_key : null } })}>{policy.allowed_values.approval_rejection_behaviors.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>{(step.config as ApprovalStepConfig).rejection_behavior === "goto" ? <label className="block text-sm font-medium">Rejection branch<select className={`${inputClass} mt-1`} value={(step.config as ApprovalStepConfig).reject_step_key ?? ""} onChange={(event) => replaceStep(index, { ...step, config: { ...(step.config as ApprovalStepConfig), reject_step_key: event.target.value } })}><option value="">Choose a step…</option>{steps.filter((candidate) => candidate.key !== step.key).map((candidate) => <option key={candidate.key} value={candidate.key}>{candidate.name}</option>)}</select></label> : null}</div> : null}
            {step.step_type === "notification" ? <div className="grid gap-3 sm:grid-cols-3"><label className="block text-sm font-medium">Channel<select className={`${inputClass} mt-1`} value={(step.config as NotificationStepConfig).channel} onChange={(event) => { const channel = event.target.value as NotificationStepConfig["channel"]; replaceStep(index, { ...step, config: { ...(step.config as NotificationStepConfig), channel, recipient_mapping: channel === "email" ? { recipient_email: "actor.email" } : { recipient_id: "actor.id" } } }); }}><option value="in_app">In-app</option><option value="email">Email via delivery contract</option></select></label><Input label="Recipient context path" value={recipientPath(step.config as NotificationStepConfig)} onChange={(event) => { const config = step.config as NotificationStepConfig; const field = config.channel === "email" ? "recipient_email" : "recipient_id"; replaceStep(index, { ...step, config: { ...config, recipient_mapping: { [field]: event.target.value } } }); }}/><Input label="Registered template key" value={(step.config as NotificationStepConfig).template_key} onChange={(event) => replaceStep(index, { ...step, config: { ...(step.config as NotificationStepConfig), template_key: event.target.value } })}/></div> : null}
            {step.step_type === "decision" && decisionConfig ? <div className="space-y-3"><div className="grid gap-3 sm:grid-cols-3"><label className="block text-sm font-medium">Condition<select className={`${inputClass} mt-1`} value={conditionHandler} onChange={(event) => { const descriptor = conditions.data?.find((item) => item.key === event.target.value); if (descriptor?.availability !== "available") return; replaceStep(index, { ...step, config: { ...decisionConfig, condition: { handler: descriptor.key } } }); }}><option value="">Choose a safe condition…</option>{conditions.data?.map((descriptor) => <option key={descriptor.key} value={descriptor.key} disabled={descriptor.availability !== "available"}>{descriptor.display_name} — {descriptor.availability.replaceAll("_", " ")}</option>)}</select></label>{(["true_step_key","false_step_key"] as const).map((branch) => <label key={branch} className="block text-sm font-medium">{branch === "true_step_key" ? "True branch" : "False branch"}<select className={`${inputClass} mt-1`} value={decisionConfig[branch]} onChange={(event) => replaceStep(index, { ...step, config: { ...decisionConfig, [branch]: event.target.value } })}><option value="">Choose a step…</option>{steps.filter((candidate) => candidate.key !== step.key).map((candidate) => <option key={candidate.key} value={candidate.key}>{candidate.name}</option>)}</select></label>)}</div>{conditionDescriptor ? <><DescriptorBadge descriptor={conditionDescriptor}/><div className="grid gap-3 sm:grid-cols-2">{conditionDescriptor.ui_schema.map((field) => <SchemaField key={field.key} field={field} value={decisionConfig.condition[field.key]} onChange={(value) => replaceStep(index, { ...step, config: { ...decisionConfig, condition: { ...decisionConfig.condition, [field.key]: value } } })}/>)}</div></> : null}</div> : null}
            <div className="grid gap-3 sm:grid-cols-3"><Input label="Timeout seconds" type="number" min={1} max={policy.limits.duration_max_seconds} value={step.timeout_seconds ?? ""} onChange={(event) => replaceStep(index, { ...step, timeout_seconds: event.target.value ? Number(event.target.value) : null, timeout_action: event.target.value ? step.timeout_action ?? policy.defaults.timeout_action : null })}/><label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={step.is_terminal ?? false} onChange={(event) => replaceStep(index, { ...step, is_terminal: event.target.checked })}/>Terminal step</label></div></div>
            <div className="flex gap-1"><Button size="icon" variant="ghost" aria-label={`Move ${step.name} up`} disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp className="h-4 w-4"/></Button><Button size="icon" variant="ghost" aria-label={`Move ${step.name} down`} disabled={index === steps.length - 1} onClick={() => move(index, 1)}><ArrowDown className="h-4 w-4"/></Button><Button size="icon" variant="ghost" aria-label={`Remove ${step.name}`} onClick={() => remove(index)}><Trash2 className="h-4 w-4 text-destructive"/></Button></div></div></Card>;
          },
        )}
        {issues.length > 0 ? <div role="alert" className="rounded border border-amber-500/40 bg-amber-500/5 p-4"><h2 className="font-semibold">Definition needs attention</h2><ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div> : null}
        {validation ? <div role="status" className={`rounded border p-4 ${validation.valid ? "border-emerald-500/40" : "border-destructive/40"}`}><h2 className="font-semibold">{validation.valid ? "Definition is publishable" : "Server validation found issues"}</h2><ul className="mt-2 space-y-2">{[...validation.issues, ...validation.warnings].map((issue) => <li key={`${issue.code}-${issue.pointer}`} className="text-sm"><StatusPill status={issue.severity}/> <strong className="ml-2">{issue.code}</strong> — {issue.message}</li>)}</ul></div> : null}
      </section>
    </div>
  </main>;
}
