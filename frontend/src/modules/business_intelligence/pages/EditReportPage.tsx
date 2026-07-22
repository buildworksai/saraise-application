import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import type { ReportCreate } from "../contracts";
import { biQueryKeys, biService, createIdempotencyKey } from "../services/bi-service";
import {
  BI_PATH,
  PageShell,
  PageSkeleton,
  RequestError,
  useDocumentTitle,
  useTenantIdentity,
} from "./shared";
import { ReportForm } from "./ReportForm";
export function EditReportPage() {
  useDocumentTitle("Edit report");
  const { id = "" } = useParams();
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const client = useQueryClient();
  const detail = useQuery({
    queryKey: biQueryKeys.report(tenant, id),
    queryFn: () => biService.getReport(id),
    enabled: Boolean(id),
  });
  const queries = useQuery({
    queryKey: biQueryKeys.queries(tenant, { state: "published", page_size: 100 }),
    queryFn: () => biService.listQueries({ state: "published", page_size: 100 }),
  });
  const mutation = useMutation({
    mutationFn: (value: ReportCreate) =>
      biService.updateReport(
        id,
        { ...value, version: detail.data?.version ?? 0 },
        createIdempotencyKey()
      ),
    onSuccess: (value) => {
      localStorage.removeItem(`bi-report-${id}`);
      void client.invalidateQueries({ queryKey: biQueryKeys.report(tenant, id) });
      navigate(`${BI_PATH}/reports/${value.id}`);
    },
  });
  if (detail.isLoading || queries.isLoading) return <PageSkeleton />;
  if (detail.error || queries.error || !detail.data)
    return <RequestError error={detail.error ?? queries.error} />;
  const item = detail.data;
  const initial: ReportCreate = {
    report_code: item.report_code,
    report_name: item.report_name,
    description: item.description,
    report_type: item.report_type,
    query_definition_id: item.query_definition.id,
    visualization: item.visualization,
    default_parameters: item.default_parameters,
  };
  const available = [...(queries.data?.items ?? [])];
  if (!available.some((x) => x.id === item.query_definition.id))
    available.unshift(item.query_definition as never);
  return (
    <PageShell
      title={`Edit ${item.report_name}`}
      description={`Optimistic version ${item.version}.`}
    >
      <ReportForm
        initial={initial}
        queries={available}
        onSubmit={(value) => mutation.mutate(value)}
        pending={mutation.isPending}
        error={mutation.error}
        submitLabel="Save report"
        storageKey={`bi-report-${id}`}
      />
    </PageShell>
  );
}
