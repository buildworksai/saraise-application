import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowUpDown, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useDefinitions, useRuntimeConfiguration } from "../hooks/use-orchestration";
import { ROUTE_PATHS, type DefinitionStatus } from "../contracts";
import { EmptyPanel, LoadError, PageHeader, PageSkeleton, Pagination, StatusPill, formatDate } from "../components/OrchestrationUI";

// Configuration availability and each operational UI state are intentionally explicit.
// eslint-disable-next-line complexity
export function DefinitionsListPage() {
  const navigate = useNavigate();
  const configurationQuery = useRuntimeConfiguration();
  const configuration = configurationQuery.data?.document;
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<DefinitionStatus | "">("");
  const [version, setVersion] = useState("");
  const [ordering, setOrdering] = useState<"updated_at" | "-updated_at" | "name" | "-name" | "version" | "-version">("-updated_at");
  const [page, setPage] = useState(1);
  const query = useDefinitions({
    search: search || undefined,
    status: status || undefined,
    version: version ? Number(version) : undefined,
    ordering,
    page,
    page_size: configuration?.ui.definition_page_size,
  });
  const hasFilters = Boolean(search || status || version);

  if (configurationQuery.isLoading || query.isLoading) return <PageSkeleton rows={configuration?.ui.skeleton_rows} />;
  if (configurationQuery.error || query.error || !configuration) return <LoadError error={configurationQuery.error ?? query.error ?? new Error("Runtime configuration is unavailable.")} retry={() => { void configurationQuery.refetch(); void query.refetch(); }} />;
  const result = query.data;
  if (!result) return <LoadError error={new Error("No definition response was received.")} retry={() => void query.refetch()} />;

  return (
    <main className="space-y-6">
      <PageHeader
        title="Orchestration definitions"
        description="Design, validate, version, and publish durable technical DAGs without losing operational history."
        actions={<Button onClick={() => navigate(ROUTE_PATHS.DEFINITION_CREATE)}><Plus className="mr-2 h-4 w-4" />Create orchestration</Button>}
      />
      <section aria-label="Definition filters" className="grid gap-3 rounded-xl border bg-card p-4 md:grid-cols-[minmax(220px,1fr)_180px_140px_190px]">
        <div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><Input aria-label="Search definitions" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Search name, key, description" className="pl-9" /></div>
        <select aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value as DefinitionStatus | ""); setPage(1); }} className="rounded-md border bg-background px-3 text-sm"><option value="">All statuses</option><option value="draft">Draft</option><option value="published">Published</option><option value="retired">Retired</option></select>
        <Input aria-label="Filter by version" type="number" min="1" value={version} onChange={(event) => { setVersion(event.target.value); setPage(1); }} placeholder="Version" />
        <select aria-label="Sort definitions" value={ordering} onChange={(event) => setOrdering(event.target.value as typeof ordering)} className="rounded-md border bg-background px-3 text-sm"><option value="-updated_at">Recently updated</option><option value="updated_at">Oldest updated</option><option value="name">Name A–Z</option><option value="-name">Name Z–A</option><option value="-version">Highest version</option><option value="version">Lowest version</option></select>
      </section>
      {result.items.length === 0 ? (
        hasFilters ? <EmptyPanel title="No definitions match" description="Adjust or clear the filters to see your orchestration catalog." action={<Button variant="outline" onClick={() => { setSearch(""); setStatus(""); setVersion(""); }}>Clear filters</Button>} /> : <EmptyPanel title="Build your first reliable automation" description="Orchestrations connect machine-executed steps into observable, retry-safe dependency graphs." action={<Button onClick={() => navigate(ROUTE_PATHS.DEFINITION_CREATE)}>Create orchestration</Button>} />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Definition</th><th className="px-4 py-3">Version</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Nodes</th><th className="px-4 py-3">Schedules</th><th className="px-4 py-3">Last run</th><th className="px-4 py-3">Success rate</th><th className="px-4 py-3"><ArrowUpDown className="h-4 w-4" /></th></tr></thead>
              <tbody className="divide-y">
                {result.items.map((definition) => (
                  <tr key={definition.id} className="hover:bg-muted/30">
                    <td className="px-4 py-4"><Link className="font-medium text-primary hover:underline" to={ROUTE_PATHS.DEFINITION_DETAIL(definition.id)}>{definition.name}</Link><p className="mt-1 text-xs text-muted-foreground">{definition.key}</p></td>
                    <td className="px-4 py-4">v{definition.version}{definition.is_current ? <span className="ml-2 text-xs text-primary">current</span> : null}</td>
                    <td className="px-4 py-4"><StatusPill status={definition.status} /></td>
                    <td className="px-4 py-4">{definition.node_count}</td><td className="px-4 py-4">{definition.schedule_count}</td><td className="px-4 py-4">{formatDate(definition.last_run_at)}</td><td className="px-4 py-4">{definition.success_rate === null ? "No runs" : `${Math.round(definition.success_rate * 100)}%`}</td>
                    <td className="px-4 py-4"><Button variant="ghost" size="sm" onClick={() => navigate(definition.status === "draft" ? ROUTE_PATHS.DEFINITION_EDIT(definition.id) : ROUTE_PATHS.DEFINITION_DETAIL(definition.id))}>{definition.status === "draft" ? "Edit graph" : "View"}</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 pb-4"><Pagination page={result.pagination.page} totalPages={result.pagination.total_pages} onPage={setPage} /></div>
        </div>
      )}
      {query.isFetching ? <p role="status" className="text-xs text-muted-foreground">Refreshing definitions…</p> : null}
    </main>
  );
}
