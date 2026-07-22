import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, LockKeyhole, Plus, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { EmptyState, Input } from "@/components/ui";
import { biQueryKeys, biService } from "../services/bi-service";
import {
  BI_PATH,
  PageShell,
  PageSkeleton,
  Pagination,
  RequestError,
  useDocumentTitle,
  useTenantIdentity,
} from "./shared";

// eslint-disable-next-line max-lines-per-function -- cohesive catalog loading, filtering, and state rendering
export function DatasetCatalogPage() {
  useDocumentTitle("Dataset catalog");
  const tenant = useTenantIdentity();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [moduleName, setModuleName] = useState("");
  const [page, setPage] = useState(1);
  const filters = useMemo(
    () => ({ search, module: moduleName, page, include_locked: true }),
    [search, moduleName, page]
  );
  const query = useQuery({
    queryKey: biQueryKeys.datasets(tenant, filters),
    queryFn: () => biService.listDatasets(filters),
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error) return <RequestError error={query.error} onRetry={() => void query.refetch()} />;
  const result = query.data;
  return (
    <PageShell
      title="Dataset catalog"
      description="Build analytics safely from datasets governed by installed SARAISE modules."
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="relative">
          <span className="sr-only">Search datasets</span>
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            placeholder="Search datasets"
          />
        </label>
        <Input
          aria-label="Filter by owning module"
          value={moduleName}
          onChange={(event) => {
            setModuleName(event.target.value);
            setPage(1);
          }}
          placeholder="Owning module"
        />
      </div>
      {!result?.items.length ? (
        <EmptyState
          icon={Database}
          title="No datasets available"
          description="No governed datasets match these filters. Installed modules can contribute datasets through the registry."
        />
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="Datasets">
            {result.items.map((dataset) => (
              <Card key={dataset.key} className="flex h-full flex-col">
                <CardHeader>
                  <div className="flex items-start justify-between gap-3">
                    <CardTitle>{dataset.label}</CardTitle>
                    {dataset.entitlement.state === "locked" && (
                      <LockKeyhole className="h-5 w-5" aria-label="Locked" />
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {dataset.module} · v{dataset.version}
                  </p>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col gap-4">
                  <p className="text-sm text-muted-foreground">{dataset.description}</p>
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-muted-foreground">Dimensions</dt>
                      <dd className="font-semibold">{dataset.dimension_count}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Measures</dt>
                      <dd className="font-semibold">{dataset.measure_count}</dd>
                    </div>
                    <div className="col-span-2">
                      <dt className="text-muted-foreground">Freshness</dt>
                      <dd>{dataset.freshness}</dd>
                    </div>
                  </dl>
                  {dataset.entitlement.state === "locked" ? (
                    <div className="mt-auto rounded-md bg-muted p-3 text-sm">
                      <p className="font-medium">
                        Requires {dataset.entitlement.required_entitlement}
                      </p>
                      <p className="text-muted-foreground">
                        Schema and data stay hidden until entitled.
                      </p>
                      {dataset.entitlement.upgrade_url && (
                        <a
                          className="mt-2 inline-block text-primary underline"
                          href={dataset.entitlement.upgrade_url}
                        >
                          View upgrade options
                        </a>
                      )}
                    </div>
                  ) : (
                    <Button
                      className="mt-auto"
                      onClick={() =>
                        navigate(
                          `${BI_PATH}/queries/new?dataset=${encodeURIComponent(dataset.key)}`
                        )
                      }
                    >
                      <Plus className="mr-2 h-4 w-4" />
                      Start query
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </section>
          <Pagination meta={result.meta} onPage={setPage} />
        </>
      )}
    </PageShell>
  );
}
