import { useMutation, useQuery } from "@tanstack/react-query";
import { Edit, RefreshCw } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { biQueryKeys, biService, createIdempotencyKey } from "../services/bi-service";
import {
  BI_PATH,
  LifecycleBadge,
  MutationError,
  PageShell,
  PageSkeleton,
  RequestError,
  formatDate,
  useDocumentTitle,
  useTenantIdentity,
} from "./shared";
export function DashboardDetailPage() {
  useDocumentTitle("Dashboard");
  const { id = "" } = useParams();
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: biQueryKeys.dashboard(tenant, id),
    queryFn: () => biService.getDashboard(id),
    enabled: Boolean(id),
  });
  const run = useMutation({
    mutationFn: () => biService.executeDashboard(id, {}, createIdempotencyKey()),
    onSuccess: () => void query.refetch(),
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return <RequestError error={query.error} onRetry={() => void query.refetch()} />;
  const item = query.data;
  return (
    <PageShell
      title={item.dashboard_name}
      description={item.description}
      actions={
        <>
          <Button variant="outline" onClick={() => navigate(`${BI_PATH}/dashboards/${id}/edit`)}>
            <Edit className="mr-2 h-4 w-4" />
            Edit
          </Button>
          <Button
            disabled={run.isPending || item.state !== "published"}
            onClick={() => run.mutate()}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${run.isPending ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </>
      }
    >
      <MutationError error={run.error} />
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <LifecycleBadge state={item.state} />
        <span className="text-muted-foreground">Last refresh: {formatDate(item.last_refresh)}</span>
        <span className="text-muted-foreground">Access: {item.effective_access ?? "owner"}</span>
      </div>
      {!item.widgets.length ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            No widgets yet. Open the builder to add a report or query.
          </CardContent>
        </Card>
      ) : (
        <section
          className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-12"
          aria-label="Dashboard widgets"
        >
          {item.widgets.map((widget) => (
            <Card
              key={widget.id}
              className="xl:col-span-6"
              style={{ minHeight: `${Math.min(widget.height, 8) * 3}rem` }}
            >
              <CardHeader>
                <CardTitle className="text-base">{widget.title}</CardTitle>
                <p className="text-xs text-muted-foreground">
                  {widget.widget_type} · refreshed {formatDate(widget.updated_at)}
                </p>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Widget results are shown after a successful durable execution.
                </p>
                <p className="sr-only">
                  Accessible tabular results are available from the associated execution.
                </p>
              </CardContent>
            </Card>
          ))}
        </section>
      )}
    </PageShell>
  );
}
