import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ROUTES } from "../contracts";
import { masterDataService } from "../services/master-data-service";
import { useMasterDataConfiguration } from "../hooks/useMasterDataConfiguration";
import { Detail, DetailGrid, GovernedError, PageHeader, PageSkeleton, QUERY_KEYS, StatusPill, Surface, formatDate } from "../components/MdmUI";

export function AsyncJobDetailPage() {
  const { id = "" } = useParams();
  const configuration = useMasterDataConfiguration();
  const policy = configuration.data?.data.document.operational;
  const query = useQuery({
    queryKey: QUERY_KEYS.job(id),
    queryFn: () => masterDataService.jobs.get(id),
    enabled: Boolean(id) && policy !== undefined,
    refetchInterval: (state) => policy?.job_poll_statuses.includes(state.state.data?.data.status ?? "succeeded")
      ? policy.job_poll_interval_ms
      : false,
  });
  if (configuration.isLoading || query.isLoading) return <PageSkeleton cards={configuration.data?.data.document.ui.skeleton_cards}/>;
  if (configuration.error) return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data || !policy) return <GovernedError error={new Error("Job or tenant polling configuration was not returned.")}/>;
  const job = query.data.data;
  const terminalError = ["failed", "timed_out", "cancelled"].includes(job.status);
  return <main className="space-y-6">
    <PageHeader title="Durable scan job" description={job.command} actions={<><StatusPill value={job.status}/><Link to={job.command.endsWith("quality_scan") ? ROUTES.QUALITY_ISSUES : ROUTES.MATCHES}><Button variant="outline">Open results queue</Button></Link></>}/>
    <Surface title="Authoritative status"><p className="text-sm text-muted-foreground">{policy.job_poll_statuses.includes(job.status) ? `Status is refreshed every ${policy.job_poll_interval_ms} ms while work remains active.` : "This job is in a terminal state; automatic polling has stopped."}</p></Surface>
    {terminalError ? <section role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-5 text-destructive"><h2 className="font-semibold">Job did not complete</h2><p className="mt-2 text-sm">{job.error_message || "No provider detail was exposed."}</p><p className="mt-2 text-xs">The job is not shown as successful. Retry according to the configured durable job policy.</p></section> : null}
    <Surface title="Execution evidence"><DetailGrid><Detail label="Job ID"><span className="font-mono text-xs">{job.id}</span></Detail><Detail label="Attempts">{job.attempts}</Detail><Detail label="Created">{formatDate(job.created_at)}</Detail><Detail label="Updated">{formatDate(job.updated_at)}</Detail><Detail label="Started">{formatDate(job.started_at)}</Detail><Detail label="Completed">{formatDate(job.completed_at)}</Detail><Detail label="Correlation"><span className="font-mono text-xs">{job.correlation_id}</span></Detail></DetailGrid></Surface>
  </main>;
}
