import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
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
const EMPTY: ReportCreate = {
  report_code: "",
  report_name: "",
  description: "",
  report_type: "table",
  query_definition_id: "",
  visualization: {},
  default_parameters: {},
};
export function CreateReportPage() {
  useDocumentTitle("Create report");
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const queries = useQuery({
    queryKey: biQueryKeys.queries(tenant, { state: "published", page_size: 100 }),
    queryFn: () => biService.listQueries({ state: "published", page_size: 100 }),
  });
  const mutation = useMutation({
    mutationFn: (value: ReportCreate) => biService.createReport(value, createIdempotencyKey()),
    onSuccess: (value) => {
      localStorage.removeItem("bi-report-new");
      navigate(`${BI_PATH}/reports/${value.id}`);
    },
  });
  if (queries.isLoading) return <PageSkeleton />;
  if (queries.error) return <RequestError error={queries.error} />;
  return (
    <PageShell
      title="Create report"
      description="Turn a published semantic query into a reusable table, pivot, chart, or KPI."
    >
      <ReportForm
        initial={EMPTY}
        queries={queries.data?.items ?? []}
        onSubmit={(value) => mutation.mutate(value)}
        pending={mutation.isPending}
        error={mutation.error}
        submitLabel="Create draft report"
        storageKey="bi-report-new"
      />
    </PageShell>
  );
}
