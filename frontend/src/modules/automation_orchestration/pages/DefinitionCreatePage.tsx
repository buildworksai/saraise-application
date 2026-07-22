import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { ArrowLeft, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { automationOrchestrationService as service } from "../services/automation-orchestration-service";
import { ROUTE_PATHS, type DefinitionCreateRequest } from "../contracts";
import { useRuntimeConfiguration } from "../hooks/use-orchestration";
import { LoadError, PageHeader, PageSkeleton } from "../components/OrchestrationUI";

export function DefinitionCreatePage() {
  const navigate = useNavigate();
  const configurationQuery = useRuntimeConfiguration();
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [description, setDescription] = useState("");
  const [maxParallel, setMaxParallel] = useState("");
  const [timeout, setTimeoutSeconds] = useState("");
  const [attempts, setAttempts] = useState("");
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const dirty = Boolean(name || key || description);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  useEffect(() => {
    const defaults = configurationQuery.data?.document.defaults;
    if (!defaults) return;
    setMaxParallel(String(defaults.max_parallel_tasks));
    setTimeoutSeconds(String(defaults.timeout_seconds));
    setAttempts(String(defaults.max_attempts));
  }, [configurationQuery.data]);

  const mutation = useMutation({
    mutationFn: (request: DefinitionCreateRequest) => service.createDefinition(request),
    onSuccess: (definition) => navigate(ROUTE_PATHS.DEFINITION_EDIT(definition.id)),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!configurationQuery.data) return;
    const limits = configurationQuery.data.document.limits;
    const schema = z.object({
      name: z.string().trim().min(limits.definition_name_min).max(limits.definition_name_max),
      key: z.string().trim().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use lowercase letters, numbers, and hyphens"),
      description: z.string().max(limits.description_max),
      maxParallel: z.coerce.number().int().min(limits.parallel_tasks_min).max(limits.parallel_tasks_max),
      timeout: z.coerce.number().int().min(limits.timeout_seconds_min).max(limits.timeout_seconds_max),
      attempts: z.coerce.number().int().min(limits.attempts_min).max(limits.attempts_max),
    });
    const result = schema.safeParse({ name, key, description, maxParallel, timeout, attempts });
    if (!result.success) {
      const next: Record<string, string> = {};
      for (const issue of result.error.issues) next[String(issue.path[0])] = issue.message;
      setErrors(next);
      return;
    }
    setErrors({});
    mutation.mutate({
      name: result.data.name,
      key: result.data.key,
      description: result.data.description,
      max_parallel_tasks: result.data.maxParallel,
      default_timeout_seconds: result.data.timeout,
      default_max_attempts: result.data.attempts,
      input_schema: { type: "object", properties: {}, additionalProperties: false },
    });
  }

  if (configurationQuery.isLoading) return <PageSkeleton />;
  if (configurationQuery.error || !configurationQuery.data) return <LoadError error={configurationQuery.error ?? new Error("Runtime configuration unavailable.")} retry={() => void configurationQuery.refetch()} />;
  const limits = configurationQuery.data.document.limits;

  return (
    <main className="space-y-6">
      <PageHeader title="Create orchestration" description="Start with safe defaults, then compose and validate the graph in the visual builder." />
      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card><CardHeader><CardTitle>Identity and purpose</CardTitle></CardHeader><CardContent className="space-y-5"><Input id="name" label="Name" required value={name} error={errors.name} onChange={(event) => { setName(event.target.value); if (!key) setKey(event.target.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")); }} /><Input id="key" label="Stable key" required value={key} error={errors.key} onChange={(event) => setKey(event.target.value)} /><Textarea id="description" aria-label="Description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What business-safe technical outcome does this DAG produce?" /><p className="text-xs text-muted-foreground">Input starts as a closed JSON object schema. Add fields in the graph builder before publication.</p></CardContent></Card>
        <Card><CardHeader><CardTitle>Execution defaults</CardTitle></CardHeader><CardContent className="space-y-4"><Input id="maxParallel" label="Maximum parallel tasks" type="number" min={limits.parallel_tasks_min} max={limits.parallel_tasks_max} value={maxParallel} error={errors.maxParallel} onChange={(event) => setMaxParallel(event.target.value)} /><Input id="timeout" label="Task timeout (seconds)" type="number" min={limits.timeout_seconds_min} max={limits.timeout_seconds_max} value={timeout} error={errors.timeout} onChange={(event) => setTimeoutSeconds(event.target.value)} /><Input id="attempts" label="Maximum attempts" type="number" min={limits.attempts_min} max={limits.attempts_max} value={attempts} error={errors.attempts} onChange={(event) => setAttempts(event.target.value)} /></CardContent></Card>
        {mutation.error ? <div role="alert" className="rounded-lg border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive lg:col-span-2">Creation failed: {mutation.error.message}. Review the fields and try again.</div> : null}
        <div className="flex flex-wrap justify-end gap-3 lg:col-span-2"><Button type="button" variant="ghost" onClick={() => { if (!dirty || window.confirm("Discard this unsaved definition?")) navigate(ROUTE_PATHS.DEFINITIONS); }}><ArrowLeft className="mr-2 h-4 w-4" />Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Creating…" : <><Sparkles className="mr-2 h-4 w-4" />Create and open builder</>}</Button></div>
      </form>
    </main>
  );
}
