import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Edit, Play, Upload } from "lucide-react";
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

// eslint-disable-next-line max-lines-per-function -- cohesive definition, lifecycle, and execution evidence view
export function QueryDetailPage() {
  useDocumentTitle("Query details");
  const { id = "" } = useParams();
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: biQueryKeys.query(tenant, id),
    queryFn: () => biService.getQuery(id),
    enabled: Boolean(id),
  });
  const execution = useMutation({
    mutationFn: () => biService.executeQuery(id, {}, createIdempotencyKey()),
    onSuccess: (value) => {
      const executionId = value.execution_id ?? value.execution_ids?.[0];
      if (executionId) navigate(`${BI_PATH}/executions/${executionId}`);
    },
  });
  const transition = useMutation({
    mutationFn: (command: "publish" | "archive" | "restore") =>
      biService.transitionQuery(
        id,
        command,
        { version: query.data?.version ?? 0 },
        createIdempotencyKey()
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: biQueryKeys.query(tenant, id) }),
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return <RequestError error={query.error} onRetry={() => void query.refetch()} />;
  const item = query.data;
  return (
    <PageShell
      title={item.name}
      description={`${item.query_code} · ${item.dataset_key}`}
      actions={
        <>
          <Button variant="outline" onClick={() => navigate(`${BI_PATH}/queries/${id}/edit`)}>
            <Edit className="mr-2 h-4 w-4" />
            Edit
          </Button>
          {item.state === "draft" && (
            <Button
              variant="outline"
              disabled={transition.isPending}
              onClick={() => transition.mutate("publish")}
            >
              <Upload className="mr-2 h-4 w-4" />
              Publish
            </Button>
          )}
          {item.state !== "archived" && (
            <Button
              variant="outline"
              disabled={transition.isPending}
              onClick={() => transition.mutate("archive")}
            >
              <Archive className="mr-2 h-4 w-4" />
              Archive
            </Button>
          )}
          <Button
            disabled={item.state !== "published" || execution.isPending}
            onClick={() => execution.mutate()}
          >
            <Play className="mr-2 h-4 w-4" />
            {execution.isPending ? "Queuing…" : "Run"}
          </Button>
        </>
      }
    >
      <MutationError error={execution.error ?? transition.error} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Human-readable definition</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <LifecycleBadge state={item.state} />
            <div>
              <h3 className="text-sm font-semibold">Dimensions</h3>
              <p className="text-sm text-muted-foreground">
                {item.dimensions.join(", ") || "None"}
              </p>
            </div>
            <div>
              <h3 className="text-sm font-semibold">Measures</h3>
              <p className="text-sm text-muted-foreground">
                {item.measures
                  .map((value) => (value.alias ? `${value.key} as ${value.alias}` : value.key))
                  .join(", ") || "None"}
              </p>
            </div>
            <div>
              <h3 className="text-sm font-semibold">Validation</h3>
              <p className="text-sm">
                Validated against the registered dataset when published and before each execution.
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Lineage</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-muted-foreground">Dataset</dt>
                <dd>{item.dataset_key}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Version</dt>
                <dd>{item.version}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Updated</dt>
                <dd>{formatDate(item.updated_at)}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Lifecycle & execution history</CardTitle>
        </CardHeader>
        <CardContent>
          {item.transition_history.length ? (
            <ol className="space-y-2">
              {item.transition_history.map((event, index) => (
                <li
                  key={`${event.timestamp}-${index}`}
                  className="border-l-2 border-primary pl-3 text-sm"
                >
                  <span className="font-medium">{event.command}</span> → {event.to_state}
                  <div className="text-xs text-muted-foreground">{formatDate(event.timestamp)}</div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">No lifecycle events recorded yet.</p>
          )}
        </CardContent>
      </Card>
    </PageShell>
  );
}
