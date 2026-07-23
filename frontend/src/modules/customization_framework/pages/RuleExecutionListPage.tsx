import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Input } from "@/components/ui/Input";
import { EmptyPanel, GovernedError, PageHeader, PageSkeleton, Pagination, StatusChip } from "../components/CustomizationUI";
import { formatDate } from "../components/customization-utils";
import { useRuntimeConfiguration } from "../components/useRuntimeConfiguration";
import { ROUTES, type ExecutionOrdering, type RuleExecutionStatus } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function RuleExecutionListPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const configuration = useRuntimeConfiguration();
  const status = (params.get("status") ?? "") as RuleExecutionStatus | "";
  const correlation = params.get("correlation_id") ?? "";
  const ordering = (params.get("ordering") ?? configuration.data?.document.list_preferences.execution_ordering ?? "") as ExecutionOrdering | "";
  const page = Number(params.get("page") ?? "1");
  const pageSize = configuration.data?.document.list_preferences.page_size;
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  };
  const query = useQuery({
    queryKey: ["customization", "executions", status, correlation, ordering, page, pageSize],
    queryFn: () => service.listExecutions({ status: status || undefined, correlation_id: correlation || undefined, ordering: ordering || undefined, page, page_size: pageSize }),
    enabled: pageSize !== undefined && Boolean(ordering),
  });
  if (configuration.isLoading || query.isLoading) return <PageSkeleton/>;
  if (configuration.error) return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data) return <GovernedError error={new Error("No governed execution response was received.")}/>;
  const filtered = Boolean(status || correlation);
  return <main className="space-y-6">
    <PageHeader title="Rule executions" description="Immutable, redacted evidence for deterministic rule outcomes. Executions cannot be created, edited, or deleted here."/>
    <section aria-label="Execution filters" className="grid gap-3 rounded-xl border bg-card p-4 md:grid-cols-[1fr_180px_200px]">
      <div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"/><Input aria-label="Filter by correlation ID" className="pl-9 font-mono" value={correlation} onChange={event => update("correlation_id", event.target.value)} placeholder="Correlation ID"/></div>
      <select aria-label="Filter execution status" className="rounded-md border bg-background px-3" value={status} onChange={event => update("status", event.target.value)}><option value="">All outcomes</option>{["matched", "not_matched", "rejected", "failed"].map(item => <option key={item}>{item}</option>)}</select>
      <select aria-label="Order executions" className="rounded-md border bg-background px-3" value={ordering} onChange={event => update("ordering", event.target.value)}><option value="-executed_at">Newest first</option><option value="executed_at">Oldest first</option><option value="-duration_ms">Slowest first</option><option value="status">Outcome</option></select>
    </section>
    {query.data.data.length === 0 ? <EmptyPanel filtered={filtered} noun="executions"/> : <section className="overflow-hidden rounded-xl border bg-card"><div className="overflow-x-auto"><table className="w-full min-w-[900px] text-sm"><thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground"><tr><th className="px-4 py-3">Rule</th><th className="px-4 py-3">Target</th><th className="px-4 py-3">Outcome</th><th className="px-4 py-3">Duration</th><th className="px-4 py-3">Executed</th><th className="px-4 py-3">Correlation ID</th></tr></thead><tbody className="divide-y">{query.data.data.map(item => <tr key={item.id} className="hover:bg-muted/30"><td className="px-4 py-4"><button className="font-medium text-primary hover:underline" onClick={() => navigate(ROUTES.EXECUTION_DETAIL(item.id))}>{item.rule_name}</button><p className="font-mono text-xs text-muted-foreground">{item.rule_version_id}</p></td><td className="px-4 py-4 font-mono text-xs">{item.target_record_id ?? "No persisted target"}</td><td className="px-4 py-4"><StatusChip status={item.status}/></td><td className="px-4 py-4">{item.duration_ms} ms</td><td className="px-4 py-4">{formatDate(item.executed_at)}</td><td className="px-4 py-4 font-mono text-xs">{item.correlation_id}</td></tr>)}</tbody></table></div><Pagination meta={query.data.meta.pagination} onPage={next => update("page", String(next))}/></section>}
  </main>;
}
