import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Detail, DetailGrid, GovernedError, PageHeader, PageSkeleton, StatusChip, Surface } from "../components/CustomizationUI";
import { formatDate } from "../components/customization-utils";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function RuleExecutionDetailPage() {
  const { id = "" } = useParams();
  const query = useQuery({ queryKey: ["customization", "execution", id], queryFn: () => service.getExecution(id), enabled: Boolean(id) });
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data) return <GovernedError error={new Error("Execution not found.")}/>;
  const item = query.data.data;
  return <main className="space-y-6">
    <PageHeader title={`Execution ${item.id.slice(0, 8)}`} description="Redacted evaluation trace and immutable correlation evidence."/>
    <Surface><DetailGrid>
      <Detail label="Outcome"><StatusChip status={item.status}/></Detail>
      <Detail label="Rule">{item.rule_name}</Detail>
      <Detail label="Rule version"><span className="font-mono text-xs">{item.rule_version_id}</span></Detail>
      <Detail label="Trigger">{item.trigger}</Detail>
      <Detail label="Duration">{item.duration_ms} ms</Detail>
      <Detail label="Executed">{formatDate(item.executed_at)}</Detail>
      <Detail label="Correlation ID"><span className="font-mono text-xs">{item.correlation_id}</span></Detail>
      <Detail label="Target"><span className="font-mono text-xs">{item.target_record_id ?? "Not persisted"}</span></Detail>
    </DetailGrid></Surface>
    <div className="grid gap-6 lg:grid-cols-2"><Surface><h2 className="font-semibold">Returned actions and mutations</h2><pre className="mt-3 max-h-96 overflow-auto rounded bg-muted p-3 text-xs">{JSON.stringify(item.result, null, 2)}</pre></Surface><Surface><h2 className="font-semibold">Matched conditions and diagnostics</h2>{item.diagnostics.length ? <ol className="mt-3 space-y-3">{item.diagnostics.map(diagnostic => <li key={`${diagnostic.code}-${diagnostic.pointer}`} className="rounded border p-3 text-sm"><strong>{diagnostic.code}</strong><p>{diagnostic.message}</p>{diagnostic.pointer ? <p className="mt-1 font-mono text-xs text-muted-foreground">{diagnostic.pointer}</p> : null}</li>)}</ol> : <p className="mt-3 text-sm text-muted-foreground">No diagnostics were returned.</p>}</Surface></div>
    <p className="text-xs text-muted-foreground">Raw input, replay keys, actor identifiers, and secret-bearing payloads are deliberately omitted from this least-privilege response.</p>
  </main>;
}
