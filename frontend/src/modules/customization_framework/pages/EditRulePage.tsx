import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ConfirmAction, GovernedError, PageHeader, PageSkeleton, StatusChip, Surface } from "../components/CustomizationUI";
import { useUnsavedChanges } from "../components/useUnsavedChanges";
import { ROUTES, type JSONPrimitive, type RuleActionNode, type RuleActionType, type RuleConditionNode, type RuleExecution, type RuleOperator } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

const OPERATORS: readonly RuleOperator[] = ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "starts_with", "ends_with", "is_null", "not_null", "changed"];
const ACTIONS: readonly RuleActionType[] = ["reject-with-message", "set-derived-value", "set-required", "set-visible", "set-enabled", "emit-field-diagnostic"];

// eslint-disable-next-line complexity -- builder, dry sample evaluation, versioning, and publication remain visible together.
export function EditRulePage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const rule = useQuery({ queryKey: ["customization", "rule", id], queryFn: () => service.getRule(id), enabled: Boolean(id) });
  const versions = useQuery({ queryKey: ["customization", "rule-versions", id], queryFn: () => service.listRuleVersions(id), enabled: Boolean(id) });
  const [field, setField] = useState("");
  const [operator, setOperator] = useState<RuleOperator>("eq");
  const [value, setValue] = useState("");
  const [actionType, setActionType] = useState<RuleActionType>("emit-field-diagnostic");
  const [actionField, setActionField] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [actions, setActions] = useState<readonly RuleActionNode[]>([]);
  const [summary, setSummary] = useState("");
  const [publishId, setPublishId] = useState("");
  const [result, setResult] = useState<RuleExecution | null>(null);
  const dirty = Boolean(field || value || actions.length || summary);
  useUnsavedChanges(dirty);

  const condition: RuleConditionNode = { operator, field, value: parsePrimitive(value) };
  const save = useMutation({
    mutationFn: () => service.createRuleVersion(id, { condition_ast: condition, action_ast: actions, change_summary: summary }),
    onSuccess: response => { setPublishId(response.data.id); void client.invalidateQueries({ queryKey: ["customization", "rule-versions", id] }); },
  });
  const publish = useMutation({ mutationFn: () => service.publishRule(id, { version_id: publishId, transition_key: crypto.randomUUID() }), onSuccess: () => navigate(ROUTES.RULE_DETAIL(id)) });
  const evaluate = useMutation({ mutationFn: () => service.evaluateRule(id, { record: { [field]: parsePrimitive(value) }, changed_fields: [field], idempotency_key: crypto.randomUUID() }), onSuccess: response => setResult(response.data) });

  if (rule.isLoading) return <PageSkeleton/>;
  if (rule.error) return <GovernedError error={rule.error} retry={() => void rule.refetch()}/>;
  if (!rule.data) return <GovernedError error={new Error("Rule not found.")}/>;

  function addAction() {
    if (!actionField && !actionMessage) return;
    setActions([...actions, { type: actionType, field: actionField || undefined, message: actionMessage || undefined, value: actionType === "set-derived-value" ? parsePrimitive(actionMessage) : undefined }]);
    setActionMessage("");
  }

  return <main className="space-y-6"><PageHeader title={`${rule.data.data.name} builder`} description="Candidate versions use bounded operators and actions. Free-form code is never accepted."/><div className="grid gap-6 lg:grid-cols-2"><Surface><h2 className="font-semibold">When this condition matches</h2><div className="mt-4 grid gap-3 sm:grid-cols-3"><Input aria-label="Condition field" value={field} onChange={event => setField(event.target.value)} placeholder="field-key"/><select aria-label="Condition operator" className="rounded-md border bg-background px-3" value={operator} onChange={event => setOperator(event.target.value as RuleOperator)}>{OPERATORS.map(item => <option key={item}>{item}</option>)}</select><Input aria-label="Comparison value" value={value} onChange={event => setValue(event.target.value)}/></div></Surface><Surface><h2 className="font-semibold">Apply allowlisted actions</h2><div className="mt-4 grid gap-3"><select aria-label="Action type" className="h-10 rounded-md border bg-background px-3" value={actionType} onChange={event => setActionType(event.target.value as RuleActionType)}>{ACTIONS.map(item => <option key={item}>{item}</option>)}</select><Input aria-label="Action field" value={actionField} onChange={event => setActionField(event.target.value)} placeholder="field-key"/><Input aria-label="Action value or message" value={actionMessage} onChange={event => setActionMessage(event.target.value)}/><Button variant="outline" onClick={addAction}><Plus className="mr-2 h-4 w-4"/>Add action</Button></div><ul className="mt-4 space-y-2">{actions.map((action, index) => <li key={`${action.type}-${index}`} className="flex items-center justify-between rounded border p-2 text-sm"><span>{action.type} · {action.field ?? action.message}</span><Button size="sm" variant="ghost" aria-label={`Remove action ${index + 1}`} onClick={() => setActions(actions.filter((_, actionIndex) => actionIndex !== index))}><Trash2 className="h-4 w-4"/></Button></li>)}</ul></Surface></div><Surface><h2 className="font-semibold">Deterministic test console</h2><p className="mt-2 text-sm text-muted-foreground">The published rule is evaluated against a redacted sample; immutable evidence records the outcome.</p><Button className="mt-4" variant="outline" disabled={!field || evaluate.isPending} onClick={() => evaluate.mutate()}><Play className="mr-2 h-4 w-4"/>{evaluate.isPending ? "Evaluating…" : "Evaluate sample"}</Button>{result ? <div className="mt-4 rounded-lg border p-3 text-sm"><StatusChip status={result.status}/><span className="ml-3">{result.duration_ms} ms · correlation {result.correlation_id}</span><ul className="mt-3">{result.diagnostics.map((diagnostic, index) => <li key={`${diagnostic.code}-${index}`}>{diagnostic.message}</li>)}</ul></div> : null}</Surface><Surface><h2 className="font-semibold">Version diff and impact</h2><p className="mt-2 text-sm text-muted-foreground">Compared with {versions.data?.data[0] ? `version ${versions.data.data[0].version}` : "an empty rule"}. New condition: {field || "not configured"}; {actions.length} actions.</p><Input className="mt-4" id="rule-change-summary" label="Change summary" value={summary} onChange={event => setSummary(event.target.value)}/><div className="mt-4 flex justify-end gap-3"><Button variant="outline" onClick={() => navigate(ROUTES.RULE_DETAIL(id))}>Cancel</Button><Button disabled={!field || !actions.length || !summary.trim() || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Validating…" : "Save candidate version"}</Button></div></Surface>{save.error ? <GovernedError error={save.error}/> : null}{evaluate.error ? <GovernedError error={evaluate.error}/> : null}<ConfirmAction open={Boolean(publishId)} title="Publish validated rule?" description="Publication atomically supersedes the prior version. Evidence remains immutable." confirmLabel="Publish rule" pending={publish.isPending} onOpenChange={open => { if (!open) setPublishId(""); }} onConfirm={() => publish.mutate()}/>{publish.error ? <GovernedError error={publish.error}/> : null}</main>;
}

function parsePrimitive(value: string): JSONPrimitive {
  if (value === "true") return true;
  if (value === "false") return false;
  if (value === "null") return null;
  const number = Number(value);
  return value.trim() !== "" && Number.isFinite(number) ? number : value;
}
