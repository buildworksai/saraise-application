import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Share2, Trash2 } from "lucide-react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui";
import type { DashboardWidget, ShareCreate, WidgetCreate } from "../contracts";
import { biQueryKeys, biService, createIdempotencyKey } from "../services/bi-service";
import {
  MutationError,
  PageShell,
  PageSkeleton,
  RequestError,
  useDocumentTitle,
  useTenantIdentity,
} from "./shared";

const NEW_WIDGET: WidgetCreate = {
  query_definition_id: "",
  widget_type: "table",
  title: "",
  x: 0,
  y: 0,
  width: 6,
  height: 4,
  display_order: 0,
  visualization: {},
  filters: [],
};

// The builder intentionally coordinates four independent mutation workflows.
// eslint-disable-next-line complexity
// eslint-disable-next-line max-lines-per-function, complexity -- cohesive keyboard builder coordinates atomic layout and sharing
export function EditDashboardPage() {
  useDocumentTitle("Dashboard builder");
  const { id = "" } = useParams();
  const tenant = useTenantIdentity();
  const client = useQueryClient();
  const [panel, setPanel] = useState<"widget" | "share" | null>(null);
  const [widget, setWidget] = useState<WidgetCreate>(NEW_WIDGET);
  const [share, setShare] = useState<ShareCreate>({
    subject_type: "user",
    subject_id: "",
    access_level: "view",
  });
  const detail = useQuery({
    queryKey: biQueryKeys.dashboard(tenant, id),
    queryFn: () => biService.getDashboard(id),
    enabled: Boolean(id),
  });
  const queries = useQuery({
    queryKey: biQueryKeys.queries(tenant, { state: "published", page_size: 100 }),
    queryFn: () => biService.listQueries({ state: "published", page_size: 100 }),
  });
  const refresh = () =>
    void client.invalidateQueries({ queryKey: biQueryKeys.dashboard(tenant, id) });
  const add = useMutation({
    mutationFn: () =>
      biService.addWidget(
        id,
        {
          ...widget,
          display_order: detail.data?.widgets.length ?? 0,
          y: Math.max(0, ...(detail.data?.widgets.map((entry) => entry.y + entry.height) ?? [])),
        },
        createIdempotencyKey()
      ),
    onSuccess: () => {
      setPanel(null);
      setWidget(NEW_WIDGET);
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (widgetId: string) => biService.removeWidget(id, widgetId, createIdempotencyKey()),
    onSuccess: refresh,
  });
  const reorder = useMutation({
    mutationFn: (next: DashboardWidget[]) =>
      biService.reorderWidgets(
        id,
        detail.data?.version ?? 1,
        next.map((entry, index) => ({
          id: entry.id,
          x: entry.x,
          y: next.slice(0, index).reduce((offset, previous) => offset + previous.height, 0),
          width: entry.width,
          height: entry.height,
          display_order: index,
          version: entry.version,
        })),
        createIdempotencyKey()
      ),
    onSuccess: refresh,
  });
  const sharing = useMutation({
    mutationFn: () => biService.createShare(id, share, createIdempotencyKey()),
    onSuccess: () => {
      setPanel(null);
      refresh();
    },
  });
  if (detail.isLoading || queries.isLoading) return <PageSkeleton />;
  if (detail.error || queries.error || !detail.data)
    return <RequestError error={detail.error ?? queries.error} />;
  const item = detail.data;
  const move = (index: number, direction: -1 | 1) => {
    const next = [...item.widgets];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    const current = next[index];
    const replacement = next[target];
    if (!current || !replacement) return;
    next[index] = replacement;
    next[target] = current;
    reorder.mutate(next);
  };
  return (
    <PageShell
      title={`Build ${item.dashboard_name}`}
      description="Widget layout changes are keyboard-accessible and persisted atomically."
      actions={
        <>
          <Button variant="outline" onClick={() => setPanel("share")}>
            <Share2 className="mr-2 h-4 w-4" />
            Share
          </Button>
          <Button onClick={() => setPanel("widget")}>
            <Plus className="mr-2 h-4 w-4" />
            Add widget
          </Button>
        </>
      }
    >
      <MutationError error={add.error ?? remove.error ?? reorder.error ?? sharing.error} />
      {panel && (
        <Card role="dialog" aria-label={panel === "widget" ? "Add widget" : "Share dashboard"}>
          <CardHeader>
            <CardTitle>{panel === "widget" ? "Add widget" : "Share dashboard"}</CardTitle>
          </CardHeader>
          <CardContent>
            {panel === "widget" ? (
              <form
                className="grid gap-3 sm:grid-cols-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  add.mutate();
                }}
              >
                <label className="text-sm font-medium">
                  Title
                  <Input
                    required
                    value={widget.title}
                    onChange={(event) => setWidget({ ...widget, title: event.target.value })}
                  />
                </label>
                <label className="text-sm font-medium">
                  Published query
                  <select
                    required
                    className="mt-1 h-10 w-full rounded-md border bg-background px-3"
                    value={widget.query_definition_id ?? ""}
                    onChange={(event) =>
                      setWidget({ ...widget, query_definition_id: event.target.value })
                    }
                  >
                    <option value="">Choose query</option>
                    {queries.data?.items.map((query) => (
                      <option key={query.id} value={query.id}>
                        {query.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-sm font-medium">
                  Width (1–12)
                  <Input
                    type="number"
                    min={1}
                    max={12}
                    value={widget.width}
                    onChange={(event) =>
                      setWidget({ ...widget, width: Number(event.target.value) })
                    }
                  />
                </label>
                <label className="text-sm font-medium">
                  Height (1–24)
                  <Input
                    type="number"
                    min={1}
                    max={24}
                    value={widget.height}
                    onChange={(event) =>
                      setWidget({ ...widget, height: Number(event.target.value) })
                    }
                  />
                </label>
                <div className="flex gap-2 sm:col-span-2">
                  <Button disabled={add.isPending}>
                    {add.isPending ? "Adding…" : "Add widget"}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setPanel(null)}>
                    Cancel
                  </Button>
                </div>
              </form>
            ) : (
              <form
                className="grid gap-3 sm:grid-cols-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  sharing.mutate();
                }}
              >
                <label className="text-sm font-medium">
                  Subject type
                  <select
                    className="mt-1 h-10 w-full rounded-md border bg-background px-3"
                    value={share.subject_type}
                    onChange={(event) =>
                      setShare({ ...share, subject_type: event.target.value as "user" | "role" })
                    }
                  >
                    <option value="user">User</option>
                    <option value="role">Role</option>
                  </select>
                </label>
                <label className="text-sm font-medium">
                  User or role ID
                  <Input
                    required
                    value={share.subject_id}
                    onChange={(event) => setShare({ ...share, subject_id: event.target.value })}
                  />
                </label>
                <label className="text-sm font-medium">
                  Access
                  <select
                    className="mt-1 h-10 w-full rounded-md border bg-background px-3"
                    value={share.access_level}
                    onChange={(event) =>
                      setShare({ ...share, access_level: event.target.value as "view" | "edit" })
                    }
                  >
                    <option value="view">View</option>
                    <option value="edit">Edit</option>
                  </select>
                </label>
                <div className="flex items-end gap-2">
                  <Button disabled={sharing.isPending}>
                    {sharing.isPending ? "Sharing…" : "Share"}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setPanel(null)}>
                    Cancel
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      )}
      <section className="space-y-3" aria-label="Widget layout">
        {item.widgets.map((entry, index) => (
          <Card key={entry.id}>
            <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
              <div className="flex-1">
                <h2 className="font-semibold">{entry.title}</h2>
                <p className="text-sm text-muted-foreground">
                  {entry.widget_type} · {entry.width}×{entry.height}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => move(index, -1)}
                  disabled={index === 0 || reorder.isPending}
                  aria-label={`Move ${entry.title} up`}
                >
                  <ArrowUp className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => move(index, 1)}
                  disabled={index === item.widgets.length - 1 || reorder.isPending}
                  aria-label={`Move ${entry.title} down`}
                >
                  <ArrowDown className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(entry.id)}
                  aria-label={`Remove ${entry.title}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {!item.widgets.length && (
          <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
            Add the first widget to begin the layout.
          </p>
        )}
      </section>
    </PageShell>
  );
}
