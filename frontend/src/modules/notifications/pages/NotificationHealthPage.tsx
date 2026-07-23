import { useQuery } from "@tanstack/react-query";
import { Activity, CheckCircle2, Clock3, Layers3 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { JsonValue } from "../contracts";
import { NOTIFICATION_QUERY_KEYS, notificationService } from "../services/notification-service";
import { GovernedError, PageShell, PageSkeleton, StatusPill, formatDate } from "../components/NotificationUI";

function numericDetail(value: JsonValue | undefined): number | null { return typeof value === "number" ? value : null; }
function detailText(value: JsonValue | undefined): string { if (value === undefined) return "No additional evidence."; return typeof value === "string" ? value : JSON.stringify(value); }

export function NotificationHealthPage() {
  const live = useQuery({ queryKey: [...NOTIFICATION_QUERY_KEYS.health, "live"], queryFn: ({ signal }) => notificationService.health.live(signal), refetchInterval: 30_000 });
  const ready = useQuery({ queryKey: [...NOTIFICATION_QUERY_KEYS.health, "ready"], queryFn: ({ signal }) => notificationService.health.ready(signal), refetchInterval: 30_000 });
  if (live.isLoading || ready.isLoading) return <PageSkeleton/>;
  if (live.error || ready.error || !ready.data) return <PageShell title="Notification health" description="Operational readiness evidence."><GovernedError error={live.error ?? ready.error} retry={() => { void live.refetch(); void ready.refetch(); }} subject="Notification health"/></PageShell>;
  const outbox = ready.data.components.outbox; const queueBacklog = numericDetail(outbox?.details?.pending); const oldestAge = numericDetail(outbox?.details?.oldest_age_seconds);
  return <PageShell title="Notification health" description="Real readiness evidence from the database, outbox, command handlers, active configuration, and adapters.">
    <div className="flex items-center justify-between rounded-md border bg-card p-4"><div className="flex items-center gap-3"><Activity className="h-5 w-5 text-primary"/><div><strong>Module readiness</strong><p className="text-xs text-muted-foreground">Fetched {formatDate(new Date(ready.dataUpdatedAt).toISOString())} · {ready.data.code}</p></div></div><StatusPill value={ready.data.status}/></div>
    <div className="grid gap-4 sm:grid-cols-3"><Card className="p-5"><Layers3 className="h-5 w-5 text-muted-foreground"/><p className="mt-3 text-2xl font-semibold">{queueBacklog === null ? "Unavailable" : queueBacklog.toLocaleString()}</p><p className="text-sm text-muted-foreground">Pending outbox events</p></Card><Card className="p-5"><Clock3 className="h-5 w-5 text-muted-foreground"/><p className="mt-3 text-sm font-semibold">{oldestAge === null ? "Unavailable" : `${oldestAge.toLocaleString()} seconds`}</p><p className="text-sm text-muted-foreground">Oldest pending event age</p></Card><Card className="p-5"><CheckCircle2 className="h-5 w-5 text-muted-foreground"/><p className="mt-3 text-sm font-semibold">Not exposed</p><p className="text-sm text-muted-foreground">Last successful delivery (no fabricated value)</p></Card></div>
    <Card className="overflow-hidden"><div className="border-b p-5"><h2 className="font-semibold">Readiness components</h2></div><ul className="divide-y">{Object.entries(ready.data.components).map(([name, component]) => <li key={name} className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><strong className="capitalize">{name.replaceAll("_", " ")}</strong><p className="mt-1 font-mono text-xs text-muted-foreground">{component.code}</p>{component.details ? <p className="mt-2 break-words text-xs text-muted-foreground">{detailText(component.details)}</p> : null}</div><StatusPill value={component.status}/></li>)}</ul></Card>
    <p className="text-xs text-muted-foreground">Freshness: this page polls the real readiness endpoint every 30 seconds. It does not claim a live stream.</p>
  </PageShell>;
}
