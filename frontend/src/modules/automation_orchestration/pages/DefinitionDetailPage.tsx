import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Copy, Edit3, Play, Send, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useDefinition, useRuns, useSchedules, orchestrationKeys } from "../hooks/use-orchestration";
import { automationOrchestrationService as service } from "../services/automation-orchestration-service";
import { LoadError, PageHeader, PageSkeleton, StatusPill, formatDate } from "../components/OrchestrationUI";
import { Topology } from "../components/Topology";

// Lifecycle, validation, execution, and related-query branches are deliberately visible here.
// eslint-disable-next-line complexity
export function DefinitionDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const definitionQuery = useDefinition(id);
  const schedulesQuery = useSchedules({ definition_id: id, page_size: 5 });
  const runsQuery = useRuns({ definition_id: id, page_size: 5, ordering: "-created_at" });
  const [showRunDialog, setShowRunDialog] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => crypto.randomUUID());

  const refresh = () => void queryClient.invalidateQueries({ queryKey: orchestrationKeys.definition(id) });
  const validate = useMutation({ mutationFn: () => service.validateDefinition(id), onSuccess: refresh });
  const publish = useMutation({ mutationFn: () => service.publishDefinition(id, crypto.randomUUID()), onSuccess: refresh });
  const clone = useMutation({ mutationFn: () => service.cloneDefinition(id), onSuccess: (next) => navigate(`/automation-orchestration/definitions/${next.id}/edit`) });
  const retire = useMutation({ mutationFn: () => service.retireDefinition(id, crypto.randomUUID()), onSuccess: refresh });
  const run = useMutation({ mutationFn: () => service.startRun({ definition_id: id, input: {}, idempotency_key: idempotencyKey, trigger_type: "manual" }), onSuccess: (created) => navigate(`/automation-orchestration/runs/${created.id}`) });

  if (definitionQuery.isLoading) return <PageSkeleton />;
  if (definitionQuery.error) return <LoadError error={definitionQuery.error} retry={() => void definitionQuery.refetch()} />;
  const definition = definitionQuery.data;
  if (!definition) return <LoadError error={new Error("Definition not found.")} retry={() => void definitionQuery.refetch()} />;
  const validation = validate.data;
  const actionError = validate.error ?? publish.error ?? clone.error ?? retire.error ?? run.error;

  return (
    <main className="space-y-6">
      <PageHeader eyebrow={`${definition.key} · version ${definition.version}`} title={definition.name} description={definition.description || "No description provided."} actions={<><StatusPill status={definition.status} />{definition.status === "draft" ? <Button variant="outline" onClick={() => navigate(`/automation-orchestration/definitions/${id}/edit`)}><Edit3 className="mr-2 h-4 w-4" />Edit graph</Button> : null}<Button variant="outline" onClick={() => validate.mutate()} disabled={validate.isPending}><ShieldCheck className="mr-2 h-4 w-4" />{validate.isPending ? "Validating…" : "Validate"}</Button>{definition.status === "draft" ? <Button onClick={() => { if (window.confirm("Publish this immutable version?")) publish.mutate(); }} disabled={publish.isPending}><Send className="mr-2 h-4 w-4" />Publish</Button> : null}{definition.status === "published" ? <><Button variant="outline" onClick={() => clone.mutate()} disabled={clone.isPending}><Copy className="mr-2 h-4 w-4" />Clone version</Button><Button onClick={() => setShowRunDialog(true)}><Play className="mr-2 h-4 w-4" />Execute</Button><Button variant="danger" onClick={() => { if (window.confirm("Retire this published version? Existing history remains available.")) retire.mutate(); }}>Retire</Button></> : null}</>} />
      {actionError ? <div role="alert" className="rounded-lg border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">{actionError.message}</div> : null}
      <section aria-label="Definition metrics" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[["Nodes", definition.nodes.length], ["Schedules", schedulesQuery.data?.pagination.count ?? "—"], ["Recent successes", runsQuery.data?.items.filter((item) => item.status === "succeeded").length ?? "—"], ["Last run", formatDate(runsQuery.data?.items[0]?.created_at ?? null)]].map(([label, value]) => <Card key={String(label)}><CardContent className="p-5"><p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold">{value}</p></CardContent></Card>)}</section>
      <Card><CardHeader className="flex-row items-center justify-between"><CardTitle>Topology</CardTitle>{validation ? <span className={validation.valid ? "text-sm text-emerald-600" : "text-sm text-destructive"}>{validation.valid ? "Validated" : `${validation.issues.length} validation issue(s)`}</span> : <span className="text-sm text-muted-foreground">Not validated in this session</span>}</CardHeader><CardContent><Topology nodes={definition.nodes} edges={definition.edges} />{validation && !validation.valid ? <ul className="mt-4 space-y-2" aria-label="Validation issues">{validation.issues.map((issue) => <li key={`${issue.code}-${issue.entity_id}`} className="rounded border border-destructive/30 p-3 text-sm"><strong>{issue.code}</strong>: {issue.message}{issue.remediation ? <p className="mt-1 text-muted-foreground">{issue.remediation}</p> : null}</li>)}</ul> : null}</CardContent></Card>
      <div className="grid gap-6 lg:grid-cols-2"><Card><CardHeader><CardTitle>Schedules</CardTitle></CardHeader><CardContent>{schedulesQuery.isLoading ? <p>Loading schedules…</p> : schedulesQuery.error ? <p role="alert">Schedules unavailable.</p> : schedulesQuery.data?.items.length ? <ul className="divide-y">{schedulesQuery.data.items.map((schedule) => <li key={schedule.id} className="flex justify-between py-3"><span>{schedule.name}<small className="block text-muted-foreground">{schedule.timezone} · {schedule.cron_expression}</small></span><StatusPill status={schedule.status} /></li>)}</ul> : <p className="text-sm text-muted-foreground">No schedules target this version.</p>}</CardContent></Card><Card><CardHeader><CardTitle>Recent runs</CardTitle></CardHeader><CardContent>{runsQuery.isLoading ? <p>Loading runs…</p> : runsQuery.error ? <p role="alert">Runs unavailable.</p> : runsQuery.data?.items.length ? <ul className="divide-y">{runsQuery.data.items.map((item) => <li key={item.id} className="flex justify-between py-3"><Link to={`/automation-orchestration/runs/${item.id}`} className="font-mono text-xs text-primary hover:underline">{item.id.slice(0, 8)}</Link><StatusPill status={item.status} /></li>)}</ul> : <p className="text-sm text-muted-foreground">This version has not run yet.</p>}</CardContent></Card></div>
      <Card><CardHeader><CardTitle>Audit evidence</CardTitle></CardHeader><CardContent>{definition.transition_history.length ? <ol className="border-l pl-5">{definition.transition_history.map((entry) => <li key={`${entry.occurred_at}-${entry.transition}`} className="mb-4"><p className="font-medium">{entry.transition}</p><p className="text-xs text-muted-foreground">{entry.from} → {entry.to} · {formatDate(entry.occurred_at)}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">No lifecycle transitions recorded yet.</p>}</CardContent></Card>
      {showRunDialog ? <div role="dialog" aria-modal="true" aria-labelledby="run-title" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"><Card className="w-full max-w-lg"><CardHeader><CardTitle id="run-title">Execute {definition.name}</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm text-muted-foreground">This run uses an empty input object. The backend validates it against the published input schema.</p><Input label="Idempotency key" value={idempotencyKey} onChange={(event) => setIdempotencyKey(event.target.value)} /><div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setShowRunDialog(false)}>Cancel</Button><Button onClick={() => run.mutate()} disabled={!idempotencyKey || run.isPending}>{run.isPending ? "Starting…" : "Start durable run"}</Button></div></CardContent></Card></div> : null}
    </main>
  );
}
