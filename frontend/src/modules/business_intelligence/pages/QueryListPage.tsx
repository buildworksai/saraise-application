import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, Input } from "@/components/ui";
import { biQueryKeys, biService } from "../services/bi-service";
import {
  BI_PATH,
  LifecycleBadge,
  PageShell,
  PageSkeleton,
  Pagination,
  RequestError,
  formatDate,
  useDocumentTitle,
  useTenantIdentity,
} from "./shared";
// eslint-disable-next-line max-lines-per-function -- cohesive paginated table state and filters
export function QueryListPage() {
  useDocumentTitle("Queries");
  const navigate = useNavigate();
  const tenant = useTenantIdentity();
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [page, setPage] = useState(1);
  const filters = useMemo(
    () => ({ search, state, page, ordering: "-updated_at" }),
    [search, state, page]
  );
  const query = useQuery({
    queryKey: biQueryKeys.queries(tenant, filters),
    queryFn: () => biService.listQueries(filters),
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error) return <RequestError error={query.error} onRetry={() => void query.refetch()} />;
  const result = query.data;
  return (
    <PageShell
      title="Semantic queries"
      description="Reusable, governed definitions—never client-authored SQL."
      actions={
        <Button onClick={() => navigate(`${BI_PATH}/queries/new`)}>
          <Plus className="mr-2 h-4 w-4" />
          New query
        </Button>
      }
    >
      <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
        <label className="relative">
          <span className="sr-only">Search queries</span>
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search code or name"
          />
        </label>
        <select
          aria-label="Filter by state"
          className="h-10 rounded-md border border-input bg-background px-3 text-sm"
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All states</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
          <option value="archived">Archived</option>
        </select>
      </div>
      {!result?.items.length ? (
        <EmptyState
          icon={Plus}
          title="No queries found"
          description="Create a semantic query from a governed dataset."
          action={{ label: "Create query", onClick: () => navigate(`${BI_PATH}/queries/new`) }}
        />
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="border-b bg-muted/60 text-left">
              <tr>
                <th className="p-3">Query</th>
                <th className="p-3">Dataset</th>
                <th className="p-3">State</th>
                <th className="p-3">Version</th>
                <th className="p-3">Last execution</th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((item) => (
                <tr key={item.id} className="border-b hover:bg-muted/40">
                  <td className="p-3">
                    <button
                      className="text-left font-medium text-primary hover:underline"
                      onClick={() => navigate(`${BI_PATH}/queries/${item.id}`)}
                    >
                      {item.name}
                    </button>
                    <div className="text-xs text-muted-foreground">{item.query_code}</div>
                  </td>
                  <td className="p-3">{item.dataset_key}</td>
                  <td className="p-3">
                    <LifecycleBadge state={item.state} />
                  </td>
                  <td className="p-3">v{item.version}</td>
                  <td className="p-3">
                    {formatDate(
                      item.last_execution?.completed_at ?? item.last_execution?.created_at
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination meta={result.meta} onPage={setPage} />
        </Card>
      )}
    </PageShell>
  );
}
