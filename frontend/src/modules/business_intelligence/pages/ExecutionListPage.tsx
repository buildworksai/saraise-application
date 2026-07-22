import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { EmptyState, Input } from "@/components/ui";
import { biQueryKeys, biService } from "../services/bi-service";
import {
  BI_PATH,
  PageShell,
  PageSkeleton,
  Pagination,
  RequestError,
  formatDate,
  useDocumentTitle,
  useTenantIdentity,
} from "./shared";
const badge = (status: string) =>
  status === "succeeded"
    ? "bg-green-500/10 text-green-700 dark:text-green-300"
    : status === "failed" || status === "timed_out"
      ? "bg-destructive/10 text-destructive"
      : status === "running" || status === "queued"
        ? "bg-blue-500/10 text-blue-700 dark:text-blue-300"
        : "bg-muted text-muted-foreground";
export function ExecutionListPage() {
  useDocumentTitle("Execution history");
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const filters = useMemo(
    () => ({ status, created_after: from, created_before: to, page, ordering: "-created_at" }),
    [status, from, to, page]
  );
  const query = useQuery({
    queryKey: biQueryKeys.executions(tenant, filters),
    queryFn: () => biService.listExecutions(filters),
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error) return <RequestError error={query.error} />;
  const result = query.data;
  return (
    <PageShell
      title="Execution history"
      description="Durable, correlated evidence for every analytics run."
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <select
          aria-label="Status"
          className="h-10 rounded-md border bg-background px-3"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          {["queued", "running", "succeeded", "failed", "cancelled", "timed_out"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <label className="text-xs text-muted-foreground">
          From
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="text-xs text-muted-foreground">
          To
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      {!result?.items.length ? (
        <EmptyState
          icon={Activity}
          title="No executions found"
          description="Run a published query, report, or dashboard to create durable history."
        />
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="border-b bg-muted/60 text-left">
              <tr>
                <th className="p-3">Started</th>
                <th className="p-3">Dataset</th>
                <th className="p-3">Resource</th>
                <th className="p-3">Status</th>
                <th className="p-3">Rows</th>
                <th className="p-3">Duration</th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((item) => (
                <tr
                  key={item.id}
                  className="cursor-pointer border-b hover:bg-muted/40"
                  onClick={() => navigate(`${BI_PATH}/executions/${item.id}`)}
                >
                  <td className="p-3">{formatDate(item.created_at)}</td>
                  <td className="p-3">{item.dataset_key}</td>
                  <td className="p-3">
                    {item.report_id ? "Report" : item.dashboard_id ? "Dashboard" : "Query"} v
                    {item.definition_version}
                  </td>
                  <td className="p-3">
                    <span className={`rounded-full px-2 py-1 text-xs ${badge(item.status)}`}>
                      {item.status}
                    </span>
                  </td>
                  <td className="p-3">{item.row_count ?? "—"}</td>
                  <td className="p-3">
                    {item.duration_ms == null ? "—" : `${item.duration_ms} ms`}
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
