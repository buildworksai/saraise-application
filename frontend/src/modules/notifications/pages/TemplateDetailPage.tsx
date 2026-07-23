/* eslint-disable @typescript-eslint/no-unsafe-assignment -- JSON.parse output is immediately asserted to the closed JsonObject contract. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, RotateCcw } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PATHS, type JsonObject } from "../contracts";
import { NOTIFICATION_QUERY_KEYS, notificationService } from "../services/notification-service";
import { GovernedError, JsonEditor, MutationError, PageShell, PageSkeleton, StatusPill, formatDate, transitionKey } from "../components/NotificationUI";

export function TemplateDetailPage() {
  const { id = "" } = useParams(); const client = useQueryClient(); const [context, setContext] = useState("{}"); const [preview, setPreview] = useState<string | null>(null);
  const detail = useQuery({ queryKey: NOTIFICATION_QUERY_KEYS.template(id), queryFn: ({ signal }) => notificationService.templates.get(id, signal), enabled: Boolean(id) });
  const versions = useQuery({ queryKey: [...NOTIFICATION_QUERY_KEYS.template(id), "versions"], queryFn: ({ signal }) => notificationService.templates.versions(id, {}, signal), enabled: Boolean(id) });
  const previewMutation = useMutation({ mutationFn: () => notificationService.templates.preview(id, { context: JSON.parse(context) as JsonObject }), onSuccess: (value) => setPreview(value.body) });
  const activate = useMutation({ mutationFn: (version: number) => notificationService.templates.activate(id, { version, transition_key: transitionKey("activate") }), onSuccess: (value) => client.setQueryData(NOTIFICATION_QUERY_KEYS.template(id), value) });
  const rollback = useMutation({ mutationFn: (version: number) => notificationService.templates.rollback(id, { version, transition_key: transitionKey("rollback") }), onSuccess: (value) => client.setQueryData(NOTIFICATION_QUERY_KEYS.template(id), value) });
  if (detail.isLoading || versions.isLoading) return <PageSkeleton/>;
  if (detail.error || !detail.data) return <PageShell title="Template" description="Template details."><GovernedError error={detail.error} retry={() => void detail.refetch()} subject="Template"/></PageShell>;
  const item = detail.data;
  return <PageShell title={item.name} description={`${item.code} · ${item.channel} · ${item.locale}`} back={{ label: "Templates", to: PATHS.TEMPLATES }} actions={<Link className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground" to={PATHS.TEMPLATE_EDIT(id)}>Create new version</Link>}>
    <MutationError error={previewMutation.error ?? activate.error ?? rollback.error}/><div className="grid gap-5 lg:grid-cols-2"><Card className="p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">Active version</h2><StatusPill value={item.status}/></div>{item.active_version ? <div className="mt-4 space-y-3"><p className="text-sm">Version {item.active_version.version} · {item.active_version.content_type}</p><pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-4 text-sm">{item.active_version.body_template}</pre><p className="text-xs text-muted-foreground">Created {formatDate(item.active_version.created_at)} · Correlation {item.active_version.correlation_id}</p></div> : <p className="mt-4 text-sm text-muted-foreground">No active version. Activate a reviewed version from history.</p>}</Card><Card className="space-y-4 p-5"><h2 className="font-semibold">Sandbox preview</h2><JsonEditor id="preview-context" label="Example context" value={context} onChange={setContext} rows={5}/><Button variant="outline" disabled={previewMutation.isPending} onClick={() => previewMutation.mutate()}><Eye className="mr-2 h-4 w-4"/>{previewMutation.isPending ? "Rendering…" : "Render preview"}</Button>{preview !== null ? <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-4 text-sm">{preview}</pre> : null}</Card></div>
    <Card className="overflow-hidden"><div className="border-b p-5"><h2 className="font-semibold">Immutable version history</h2></div>{versions.error ? <GovernedError error={versions.error} retry={() => void versions.refetch()} subject="Version history"/> : <ul className="divide-y">{versions.data?.items.map((version) => <li key={version.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"><div><strong>Version {version.version}</strong><p className="text-xs text-muted-foreground">{formatDate(version.created_at)} · Correlation {version.correlation_id}</p></div><div className="flex gap-2"><Button size="sm" variant="outline" disabled={activate.isPending} onClick={() => activate.mutate(version.version)}>Activate</Button>{item.active_version && version.version < item.active_version.version ? <Button size="sm" variant="outline" disabled={rollback.isPending} onClick={() => rollback.mutate(version.version)}><RotateCcw className="mr-1 h-4 w-4"/>Rollback</Button> : null}</div></li>)}</ul>}</Card>
  </PageShell>;
}
