import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { CalendarClock, Pause, Play, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { ScheduleStatus } from "../contracts";
import { useSchedules, orchestrationKeys } from "../hooks/use-orchestration";
import { automationOrchestrationService as service } from "../services/automation-orchestration-service";
import { EmptyPanel, LoadError, PageHeader, PageSkeleton, Pagination, StatusPill, formatDate } from "../components/OrchestrationUI";

export function SchedulesListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<ScheduleStatus | "">("");
  const [page, setPage] = useState(1);
  const filters = { search: search || undefined, status: status || undefined, page, page_size: 25, ordering: "next_run_at" as const };
  const query = useSchedules(filters);
  const lifecycle = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "pause" | "resume" }) => action === "pause" ? service.pauseSchedule(id, crypto.randomUUID()) : service.resumeSchedule(id, crypto.randomUUID()),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: orchestrationKeys.schedules(filters) }),
  });

  if (query.isLoading) return <PageSkeleton rows={7} />;
  if (query.error) return <LoadError error={query.error} retry={() => void query.refetch()} />;
  const result = query.data;
  if (!result) return <LoadError error={new Error("No schedule response was received.")} retry={() => void query.refetch()} />;
  const hasFilters = Boolean(search || status);

  return <main className="space-y-6"><PageHeader title="Schedules" description="Run published definition versions predictably across timezones, misfires, and concurrency boundaries." actions={<Button onClick={() => navigate("/automation-orchestration/schedules/new")}><Plus className="mr-2 h-4 w-4" />Create schedule</Button>} /><section aria-label="Schedule filters" className="grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-[1fr_200px]"><div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><Input aria-label="Search schedules" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} className="pl-9" placeholder="Search schedules" /></div><select aria-label="Schedule status" value={status} onChange={(event) => { setStatus(event.target.value as ScheduleStatus | ""); setPage(1); }} className="rounded-md border bg-background px-3 text-sm"><option value="">All states</option><option value="active">Active</option><option value="paused">Paused</option><option value="retired">Retired</option></select></section>{lifecycle.error ? <p role="alert" className="rounded border border-destructive/40 p-3 text-sm text-destructive">{lifecycle.error.message}</p> : null}{result.items.length === 0 ? hasFilters ? <EmptyPanel title="No schedules match" description="Clear the filters or broaden the status selection." action={<Button variant="outline" onClick={() => { setSearch(""); setStatus(""); }}>Clear filters</Button>} /> : <EmptyPanel title="No schedules yet" description="Attach a durable cron schedule to an exact published definition version." action={<Button onClick={() => navigate("/automation-orchestration/schedules/new")}>Create schedule</Button>} /> : <div className="overflow-hidden rounded-xl border bg-card"><div className="overflow-x-auto"><table className="w-full min-w-[960px] text-sm"><thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Schedule</th><th className="px-4 py-3">Definition</th><th className="px-4 py-3">Next due</th><th className="px-4 py-3">Timezone</th><th className="px-4 py-3">State</th><th className="px-4 py-3">Misfire</th><th className="px-4 py-3">Last enqueue</th><th className="px-4 py-3">Actions</th></tr></thead><tbody className="divide-y">{result.items.map((schedule) => <tr key={schedule.id}><td className="px-4 py-4 font-medium"><CalendarClock className="mr-2 inline h-4 w-4 text-primary" />{schedule.name}</td><td className="px-4 py-4">{schedule.definition_name}<small className="block text-muted-foreground">{schedule.definition_key} · v{schedule.definition_version}</small></td><td className="px-4 py-4">{formatDate(schedule.next_run_at)}</td><td className="px-4 py-4">{schedule.timezone}</td><td className="px-4 py-4"><StatusPill status={schedule.status} /></td><td className="px-4 py-4">{schedule.misfire_policy.replace("_", " ")}</td><td className="px-4 py-4">{formatDate(schedule.last_enqueued_at)}</td><td className="px-4 py-4"><div className="flex gap-1"><Button size="sm" variant="ghost" onClick={() => navigate(`/automation-orchestration/schedules/${schedule.id}/edit`)}>Edit</Button>{schedule.status === "active" ? <Button aria-label={`Pause ${schedule.name}`} size="icon" variant="ghost" disabled={lifecycle.isPending} onClick={() => lifecycle.mutate({ id: schedule.id, action: "pause" })}><Pause className="h-4 w-4" /></Button> : schedule.status === "paused" ? <Button aria-label={`Resume ${schedule.name}`} size="icon" variant="ghost" disabled={lifecycle.isPending} onClick={() => lifecycle.mutate({ id: schedule.id, action: "resume" })}><Play className="h-4 w-4" /></Button> : null}</div></td></tr>)}</tbody></table></div><div className="px-4 pb-4"><Pagination page={result.pagination.page} totalPages={result.pagination.total_pages} onPage={setPage} /></div></div>}{query.isFetching ? <p role="status" className="text-xs text-muted-foreground">Refreshing schedules…</p> : null}</main>;
}
