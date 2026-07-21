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
import type { DefinitionCreateRequest } from "../contracts";
import { PageHeader } from "../components/OrchestrationUI";

const schema = z.object({
  name: z.string().trim().min(3, "Use at least 3 characters").max(255),
  key: z.string().trim().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use lowercase letters, numbers, and hyphens"),
  description: z.string().max(2000),
  maxParallel: z.coerce.number().int().min(1).max(100),
  timeout: z.coerce.number().int().min(1).max(86400),
  attempts: z.coerce.number().int().min(1).max(20),
});

export function DefinitionCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [description, setDescription] = useState("");
  const [maxParallel, setMaxParallel] = useState("10");
  const [timeout, setTimeoutSeconds] = useState("300");
  const [attempts, setAttempts] = useState("3");
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const dirty = Boolean(name || key || description);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  const mutation = useMutation({
    mutationFn: (request: DefinitionCreateRequest) => service.createDefinition(request),
    onSuccess: (definition) => navigate(`/automation-orchestration/definitions/${definition.id}/edit`),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
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

  return (
    <main className="space-y-6">
      <PageHeader title="Create orchestration" description="Start with safe defaults, then compose and validate the graph in the visual builder." />
      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card><CardHeader><CardTitle>Identity and purpose</CardTitle></CardHeader><CardContent className="space-y-5"><Input id="name" label="Name" required value={name} error={errors.name} onChange={(event) => { setName(event.target.value); if (!key) setKey(event.target.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")); }} /><Input id="key" label="Stable key" required value={key} error={errors.key} onChange={(event) => setKey(event.target.value)} /><Textarea id="description" aria-label="Description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What business-safe technical outcome does this DAG produce?" /><p className="text-xs text-muted-foreground">Input starts as a closed JSON object schema. Add fields in the graph builder before publication.</p></CardContent></Card>
        <Card><CardHeader><CardTitle>Execution defaults</CardTitle></CardHeader><CardContent className="space-y-4"><Input id="maxParallel" label="Maximum parallel tasks" type="number" min="1" max="100" value={maxParallel} error={errors.maxParallel} onChange={(event) => setMaxParallel(event.target.value)} /><Input id="timeout" label="Task timeout (seconds)" type="number" min="1" max="86400" value={timeout} error={errors.timeout} onChange={(event) => setTimeoutSeconds(event.target.value)} /><Input id="attempts" label="Maximum attempts" type="number" min="1" max="20" value={attempts} error={errors.attempts} onChange={(event) => setAttempts(event.target.value)} /></CardContent></Card>
        {mutation.error ? <div role="alert" className="rounded-lg border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive lg:col-span-2">Creation failed: {mutation.error.message}. Review the fields and try again.</div> : null}
        <div className="flex flex-wrap justify-end gap-3 lg:col-span-2"><Button type="button" variant="ghost" onClick={() => { if (!dirty || window.confirm("Discard this unsaved definition?")) navigate("/automation-orchestration"); }}><ArrowLeft className="mr-2 h-4 w-4" />Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Creating…" : <><Sparkles className="mr-2 h-4 w-4" />Create and open builder</>}</Button></div>
      </form>
    </main>
  );
}
