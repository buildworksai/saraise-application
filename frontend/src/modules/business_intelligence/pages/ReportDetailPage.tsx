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
// eslint-disable-next-line max-lines-per-function -- cohesive report lifecycle and execution evidence view
export function ReportDetailPage() {
  useDocumentTitle("Report details");
  const { id = "" } = useParams();
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: biQueryKeys.report(tenant, id),
    queryFn: () => biService.getReport(id),
    enabled: Boolean(id),
  });
  const run = useMutation({
    mutationFn: () => biService.executeReport(id, {}, createIdempotencyKey()),
    onSuccess: (value) => {
      const runId = value.execution_id ?? value.execution_ids?.[0];
      if (runId) navigate(`${BI_PATH}/executions/${runId}`);
    },
  });
  const transition = useMutation({
    mutationFn: (command: "publish" | "archive" | "restore") =>
      biService.transitionReport(
        id,
        command,
        { version: query.data?.version ?? 0 },
        createIdempotencyKey()
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: biQueryKeys.report(tenant, id) }),
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return <RequestError error={query.error} onRetry={() => void query.refetch()} />;
  const report = query.data;
  return (
    <PageShell
      title={report.report_name}
      description={`${report.report_code} · ${report.report_type}`}
      actions={
        <>
          <Button variant="outline" onClick={() => navigate(`${BI_PATH}/reports/${id}/edit`)}>
            <Edit className="mr-2 h-4 w-4" />
            Edit
          </Button>
          {report.state === "draft" && (
            <Button
              variant="outline"
              disabled={transition.isPending}
              onClick={() => transition.mutate("publish")}
            >
              <Upload className="mr-2 h-4 w-4" />
              Publish
            </Button>
          )}
          {report.state !== "archived" && (
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
            disabled={report.state !== "published" || run.isPending}
            onClick={() => run.mutate()}
          >
            <Play className="mr-2 h-4 w-4" />
            {run.isPending ? "Queuing…" : "Run report"}
          </Button>
        </>
      }
    >
      <MutationError error={run.error ?? transition.error} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Result</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Run this report to produce durable results. Live or sample data is never fabricated.
            </p>
            {report.last_execution && (
              <Button
                variant="outline"
                className="mt-4"
                onClick={() => navigate(`${BI_PATH}/executions/${report.last_execution?.id}`)}
              >
                View latest execution
              </Button>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Definition & freshness</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <LifecycleBadge state={report.state} />
            <p>
              <span className="text-muted-foreground">Query: </span>
              <button
                className="text-primary underline"
                onClick={() => navigate(`${BI_PATH}/queries/${report.query_definition.id}`)}
              >
                {report.query_definition.name}
              </button>
            </p>
            <p>
              <span className="text-muted-foreground">Dataset: </span>
              {report.query_definition.dataset_key}
            </p>
            <p>
              <span className="text-muted-foreground">Updated: </span>
              {formatDate(report.updated_at)}
            </p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Execution & lifecycle history</CardTitle>
        </CardHeader>
        <CardContent>
          {report.transition_history.length ? (
            <ol className="space-y-2">
              {report.transition_history.map((event, index) => (
                <li
                  key={`${event.timestamp}-${index}`}
                  className="border-l-2 border-primary pl-3 text-sm"
                >
                  {event.command} → {event.to_state}
                  <div className="text-xs text-muted-foreground">{formatDate(event.timestamp)}</div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">No history yet.</p>
          )}
        </CardContent>
      </Card>
    </PageShell>
  );
}
