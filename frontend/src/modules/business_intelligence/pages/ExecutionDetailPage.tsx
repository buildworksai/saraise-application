import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban } from "lucide-react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { biQueryKeys, biService, createIdempotencyKey } from "../services/bi-service";
import {
  MutationError,
  PageShell,
  PageSkeleton,
  RequestError,
  formatDate,
  useDocumentTitle,
  useTenantIdentity,
} from "./shared";

const active = (status: string) => status === "queued" || status === "running";
const renderCell = (value: unknown): string => {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint")
    return `${value}`;
  return JSON.stringify(value) ?? "";
};

// This live view necessarily branches for polling, all terminal states, stored rows, and failures.
// eslint-disable-next-line complexity
// eslint-disable-next-line max-lines-per-function, complexity -- cohesive durable execution timeline and result state machine
export function ExecutionDetailPage() {
  useDocumentTitle("Execution details");
  const { id = "" } = useParams();
  const tenant = useTenantIdentity();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: biQueryKeys.execution(tenant, id),
    queryFn: () => biService.getExecution(id),
    enabled: Boolean(id),
    refetchInterval: (state) =>
      active(state.state.data?.status ?? "")
        ? Math.min(1000 * 2 ** state.state.dataUpdateCount, 10000)
        : false,
  });
  const result = useQuery({
    queryKey: biQueryKeys.result(tenant, id),
    queryFn: () => biService.getExecutionResult(id, { page: 1, page_size: 100 }),
    enabled: query.data?.status === "succeeded",
  });
  const cancel = useMutation({
    mutationFn: () => biService.cancelExecution(id, createIdempotencyKey()),
    onSuccess: () => void client.invalidateQueries({ queryKey: biQueryKeys.execution(tenant, id) }),
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data)
    return <RequestError error={query.error} onRetry={() => void query.refetch()} />;
  const item = query.data;
  const metrics: [string, string | number][] = [
    ["Status", item.status],
    ["Duration", item.duration_ms == null ? "—" : `${item.duration_ms} ms`],
    ["Rows", item.row_count ?? "—"],
    ["Cache", item.cache_hit ? "Hit" : "Miss"],
  ];
  return (
    <PageShell
      title="Execution details"
      description={`${item.dataset_key} · definition v${item.definition_version}`}
      actions={
        active(item.status) ? (
          <Button variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            <Ban className="mr-2 h-4 w-4" />
            {cancel.isPending ? "Cancelling…" : "Cancel"}
          </Button>
        ) : undefined
      }
    >
      <MutationError error={cancel.error} />
      <div className="grid gap-4 md:grid-cols-4">
        {metrics.map(([label, value]) => (
          <Card key={label}>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="mt-1 font-semibold">{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>State timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2">
            {item.transition_history.map((entry, index) => (
              <li
                key={`${entry.timestamp}-${index}`}
                className="border-l-2 border-primary pl-3 text-sm"
              >
                <span className="font-medium">{entry.to_state}</span>
                <div className="text-xs text-muted-foreground">{formatDate(entry.timestamp)}</div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
      {item.status === "succeeded" && (
        <Card>
          <CardHeader>
            <CardTitle>Results {result.data?.truncated ? "(truncated)" : ""}</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            {result.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading stored results…</p>
            ) : result.error ? (
              <RequestError error={result.error} />
            ) : !result.data?.rows.length ? (
              <p className="text-sm text-muted-foreground">The query completed with zero rows.</p>
            ) : (
              <table className="w-full min-w-max text-sm">
                <thead>
                  <tr>
                    {result.data.columns.map((column) => (
                      <th className="border-b p-2 text-left" key={column.key}>
                        {column.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.data.rows.map((row, index) => (
                    <tr key={index}>
                      {result.data?.columns.map((column) => (
                        <td className="border-b p-2" key={column.key}>
                          {renderCell(row[column.key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}
      {(item.status === "failed" || item.status === "timed_out") && (
        <Card>
          <CardHeader>
            <CardTitle>Sanitized failure evidence</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-medium">{item.error_code}</p>
            <p className="text-sm text-muted-foreground">{item.error_message}</p>
          </CardContent>
        </Card>
      )}
    </PageShell>
  );
}
