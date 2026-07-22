import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LayoutDashboard, Plus, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
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
export function DashboardListPage() {
  useDocumentTitle("Dashboards");
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [access, setAccess] = useState("");
  const [page, setPage] = useState(1);
  const filters = useMemo(
    () => ({ search, access, page, ordering: "-updated_at" }),
    [search, access, page]
  );
  const query = useQuery({
    queryKey: biQueryKeys.dashboards(tenant, filters),
    queryFn: () => biService.listDashboards(filters),
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error) return <RequestError error={query.error} />;
  const result = query.data;
  return (
    <PageShell
      title="Dashboards"
      description="Monitor governed metrics across responsive, shareable workspaces."
      actions={
        <Button onClick={() => navigate(`${BI_PATH}/dashboards/new`)}>
          <Plus className="mr-2 h-4 w-4" />
          New dashboard
        </Button>
      }
    >
      <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
        <label className="relative">
          <span className="sr-only">Search dashboards</span>
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search dashboards"
          />
        </label>
        <select
          aria-label="Access"
          className="rounded-md border bg-background px-3"
          value={access}
          onChange={(e) => setAccess(e.target.value)}
        >
          <option value="">Owned and shared</option>
          <option value="owner">Owned by me</option>
          <option value="shared">Shared with me</option>
        </select>
      </div>
      {!result?.items.length ? (
        <EmptyState
          icon={LayoutDashboard}
          title="No dashboards found"
          description="Create a dashboard and add a governed widget."
        />
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {result.items.map((item) => (
              <Card
                key={item.id}
                className="cursor-pointer hover:border-primary"
                onClick={() => navigate(`${BI_PATH}/dashboards/${item.id}`)}
              >
                <CardContent className="space-y-3 p-5">
                  <div className="flex justify-between gap-2">
                    <h2 className="font-semibold">{item.dashboard_name}</h2>
                    <LifecycleBadge state={item.state} />
                  </div>
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {item.description || "No description"}
                  </p>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>
                      {item.effective_access ?? "owner"} · {item.widget_count ?? 0} widgets
                    </span>
                    <span>{formatDate(item.last_refresh)}</span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </section>
          <Pagination meta={result.meta} onPage={setPage} />
        </>
      )}
    </PageShell>
  );
}
