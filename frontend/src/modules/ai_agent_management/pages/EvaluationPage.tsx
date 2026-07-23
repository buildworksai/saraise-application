import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import type { JSONValue } from "../contracts";
import { aiAgentService } from "../services/ai-agent-service";
import {
  GovernedError,
  JsonEvidence,
  MutationError,
  PageHeader,
  PageSkeleton,
  StatusPill,
  Unavailable,
} from "../components/AgentUI";

const ACTIVE_JOB_STATES = new Set(["queued", "running", "retrying"]);

function isJSONObject(value: JSONValue): value is Readonly<Record<string, JSONValue>> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function resultStatus(value: JSONValue | null | undefined): string | null {
  if (value === null || value === undefined || !isJSONObject(value)) return null;
  return typeof value.status === "string" ? value.status : null;
}

function jobEvidence(value: unknown): { readonly result?: JSONValue | null; readonly error_message?: string | null } {
  return value !== null && typeof value === "object" ? value as { readonly result?: JSONValue | null; readonly error_message?: string | null } : {};
}

export const EvaluationPage = () => {
  const { id = "" } = useParams();
  const [suite, setSuite] = useState("");
  const agent = useQuery({
    queryKey: ["ai-agent", id],
    queryFn: () => aiAgentService.getAgent(id),
    enabled: Boolean(id),
  });
  const start = useMutation({
    mutationFn: () => aiAgentService.evaluateAgent(id, {
      suite_key: suite,
      idempotency_key: crypto.randomUUID(),
    }),
  });
  const jobId = start.data?.id;
  const job = useQuery({
    queryKey: ["ai-evaluation-job", jobId],
    queryFn: () => aiAgentService.getJob(jobId ?? ""),
    enabled: Boolean(jobId),
    refetchInterval: (query) => ACTIVE_JOB_STATES.has(query.state.data?.status ?? "") ? 2_000 : false,
  });

  if (agent.isLoading) return <PageSkeleton/>;
  if (agent.error) return <GovernedError error={agent.error} retry={() => void agent.refetch()}/>;
  if (!agent.data) return <GovernedError error={new Error("Agent not found.")}/>;

  const durableJob = job.data ?? start.data;
  const evidence = jobEvidence(durableJob);
  const evaluationStatus = resultStatus(evidence.result);

  return <main className="space-y-6">
    <PageHeader
      title={`Evaluate ${agent.data.name}`}
      description="Run a registered deterministic suite as a durable job and inspect its reproducible result evidence."
    />
    <form
      className="grid gap-4 rounded-xl border bg-card p-6 sm:grid-cols-[1fr_auto]"
      onSubmit={(event) => { event.preventDefault(); start.mutate(); }}
    >
      <Input
        label="Evaluation suite key"
        required
        value={suite}
        onChange={(event) => setSuite(event.target.value)}
        placeholder="governance_baseline_v1"
      />
      <Button className="self-end" disabled={start.isPending || !suite.trim()}>
        {start.isPending ? "Enqueuing…" : "Start evaluation"}
      </Button>
    </form>
    {start.error ? <MutationError error={start.error}/> : null}
    {job.error ? <GovernedError error={job.error} retry={() => void job.refetch()}/> : null}
    {durableJob ? <Card><CardContent className="space-y-4 p-5">
      <div className="flex items-center justify-between gap-4">
        <div><strong>Durable evaluation job</strong><p className="font-mono text-xs text-muted-foreground">{durableJob.id}</p></div>
        <StatusPill status={durableJob.status}/>
      </div>
      <p className="text-sm text-muted-foreground">Attempt {durableJob.attempts} · correlation {durableJob.correlation_id}</p>
      {evidence.error_message ? <Unavailable title="Evaluation did not complete" detail={evidence.error_message}/> : null}
      {evidence.result !== undefined && evidence.result !== null ? <JsonEvidence label="Evaluation metric and regression evidence" value={evidence.result}/> : <p role="status" className="text-sm text-muted-foreground">Waiting for the registered suite to publish metric evidence…</p>}
      {evaluationStatus ? <p className="text-sm">Suite outcome: <StatusPill status={evaluationStatus}/></p> : null}
    </CardContent></Card> : null}
  </main>;
};
