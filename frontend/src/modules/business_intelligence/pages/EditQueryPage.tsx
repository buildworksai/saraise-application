import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
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
export function EditQueryPage() {
  useDocumentTitle("Edit query");
  const { id = "" } = useParams();
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const client = useQueryClient();
  const detail = useQuery({
    queryKey: biQueryKeys.query(tenant, id),
    queryFn: () => biService.getQuery(id),
    enabled: Boolean(id),
  });
  const [datasetKey, setDatasetKey] = useState("");
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
  const choose = useCallback((key: string) => setDatasetKey(key), []);
  const mutation = useMutation({
    mutationFn: (value: QueryCreate) =>
      biService.updateQuery(
        id,
        { ...value, version: detail.data?.version ?? 0 },
        createIdempotencyKey()
      ),
    onSuccess: (value) => {
      localStorage.removeItem(`bi-query-${id}`);
      void client.invalidateQueries({ queryKey: biQueryKeys.query(tenant, id) });
      navigate(`${BI_PATH}/queries/${value.id}`);
    },
  });
  if (detail.isLoading || catalog.isLoading || datasets.isLoading) return <PageSkeleton />;
  if (detail.error || catalog.error || datasets.error || !detail.data)
    return <RequestError error={detail.error ?? catalog.error ?? datasets.error} />;
  const value = detail.data;
  const initial: QueryCreate = {
    query_code: value.query_code,
    name: value.name,
    description: value.description,
    dataset_key: value.dataset_key,
    dimensions: value.dimensions,
    measures: value.measures,
    filters: value.filters,
    grouping: value.grouping,
    ordering: value.ordering,
    parameters_schema: value.parameters_schema,
    row_limit: value.row_limit,
    cache_ttl_seconds: value.cache_ttl_seconds,
  };
  return (
    <PageShell
      title={`Edit ${value.name}`}
      description={`Optimistic version ${value.version}. Published definitions return to draft when edited.`}
    >
      <QueryForm
        initial={initial}
        datasets={datasets.data ?? []}
        dataset={datasets.data?.find((x) => x.key === (datasetKey || value.dataset_key))}
        onDatasetChange={choose}
        onSubmit={(entry) => mutation.mutate(entry)}
        error={mutation.error}
        pending={mutation.isPending}
        storageKey={`bi-query-${id}`}
        submitLabel="Save query"
      />
    </PageShell>
  );
}
