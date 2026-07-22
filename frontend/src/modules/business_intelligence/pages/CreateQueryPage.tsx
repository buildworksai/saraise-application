import { useCallback, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { QueryCreate } from "../contracts";
import { biQueryKeys, biService, createIdempotencyKey } from "../services/bi-service";
import {
  BI_PATH,
  PageShell,
  PageSkeleton,
  RequestError,
  useDocumentTitle,
  useTenantIdentity,
} from "./shared";
import { QueryForm } from "./QueryForm";
const EMPTY: QueryCreate = {
  query_code: "",
  name: "",
  description: "",
  dataset_key: "",
  dimensions: [],
  measures: [],
  filters: [],
  grouping: [],
  ordering: [],
  parameters_schema: {},
  row_limit: 500,
  cache_ttl_seconds: 300,
};
export function CreateQueryPage() {
  useDocumentTitle("Create query");
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [datasetKey, setDatasetKey] = useState(params.get("dataset") ?? "");
  const catalog = useQuery({
    queryKey: biQueryKeys.datasets(tenant, { page_size: 100, locked: false }),
    queryFn: () => biService.listDatasets({ page_size: 100, locked: false }),
  });
  const datasets = useQuery({
    queryKey: [
      "business-intelligence",
      tenant,
      "dataset-details",
      catalog.data?.items.map((x) => x.key),
    ],
    enabled: Boolean(catalog.data),
    queryFn: () =>
      Promise.all(
        (catalog.data?.items ?? [])
          .filter((x) => x.entitlement.state !== "locked")
          .map((x) => biService.getDataset(x.key))
      ),
  });
  const selected = datasets.data?.find((x) => x.key === datasetKey);
  const choose = useCallback((key: string) => setDatasetKey(key), []);
  const mutation = useMutation({
    mutationFn: (value: QueryCreate) => biService.createQuery(value, createIdempotencyKey()),
    onSuccess: (value) => {
      localStorage.removeItem("bi-query-new");
      navigate(`${BI_PATH}/queries/${value.id}`);
    },
  });
  if (catalog.isLoading || datasets.isLoading) return <PageSkeleton />;
  if (catalog.error || datasets.error)
    return <RequestError error={catalog.error ?? datasets.error} />;
  return (
    <PageShell
      title="Create semantic query"
      description="Select governed fields and measures. SQL and executable expressions are intentionally unavailable."
    >
      <QueryForm
        initial={{ ...EMPTY, dataset_key: datasetKey }}
        datasets={datasets.data ?? []}
        dataset={selected}
        onDatasetChange={choose}
        onSubmit={(value) => mutation.mutate(value)}
        error={mutation.error}
        pending={mutation.isPending}
        storageKey="bi-query-new"
        submitLabel="Create draft query"
      />
    </PageShell>
  );
}
