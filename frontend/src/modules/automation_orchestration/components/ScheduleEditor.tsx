import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import type { ConcurrencyPolicy, MisfirePolicy } from "../contracts";
import { useDefinitions, useRuntimeConfiguration, useSchedule } from "../hooks/use-orchestration";
import { automationOrchestrationService as service } from "../services/automation-orchestration-service";
import { ROUTE_PATHS } from "../contracts";
import { CronPreview, nextCronRuns } from "./CronPreview";
import { LoadError, PageHeader, PageSkeleton } from "./OrchestrationUI";

// Form state branches represent explicit loading, denial, validation, and mutation outcomes.
// eslint-disable-next-line complexity
export function ScheduleEditor({ scheduleId }: { scheduleId?: string }) {
  const navigate = useNavigate();
  const configurationQuery = useRuntimeConfiguration();
  const configuration = configurationQuery.data?.document;
  const existingQuery = useSchedule(scheduleId ?? "");
  const definitionsQuery = useDefinitions({
    status: "published",
    is_current: true,
    page_size: configuration?.ui.published_definition_page_size,
    ordering: "name",
  });
  const [name, setName] = useState("");
  const [definitionId, setDefinitionId] = useState("");
  const [cron, setCron] = useState("");
  const [timezone, setTimezone] = useState("");
  const [misfire, setMisfire] = useState<MisfirePolicy | "">("");
  const [concurrency, setConcurrency] = useState<ConcurrencyPolicy | "">("");
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const editing = Boolean(scheduleId);

  useEffect(() => {
    if (!configuration || editing) return;
    setCron((value) => value || configuration.defaults.cron_expression);
    setTimezone((value) => value || configuration.defaults.timezone);
    setMisfire((value) => value || configuration.defaults.misfire_policy);
    setConcurrency((value) => value || configuration.defaults.concurrency_policy);
  }, [configuration, editing]);

  useEffect(() => {
    const value = existingQuery.data;
    if (!value) return;
    setName(value.name); setDefinitionId(value.definition_id); setCron(value.cron_expression); setTimezone(value.timezone); setMisfire(value.misfire_policy); setConcurrency(value.concurrency_policy);
  }, [existingQuery.data]);

  const mutation = useMutation({
    mutationFn: () => {
      if (!misfire || !concurrency) throw new Error("Configuration defaults are unavailable.");
      return editing && scheduleId
        ? service.updateSchedule(scheduleId, { name, cron_expression: cron, timezone, misfire_policy: misfire, concurrency_policy: concurrency, input: {} })
        : service.createSchedule({ name, definition_id: definitionId, cron_expression: cron, timezone, misfire_policy: misfire, concurrency_policy: concurrency, input: {} });
    },
    onSuccess: () => navigate(ROUTE_PATHS.SCHEDULES),
  });

  const loading = configurationQuery.isLoading || definitionsQuery.isLoading || (editing && existingQuery.isLoading);
  const error = configurationQuery.error ?? definitionsQuery.error ?? (editing ? existingQuery.error : null);
  if (loading) return <PageSkeleton rows={configuration?.ui.skeleton_rows} />;
  if (error || !configuration) return <LoadError error={error ?? new Error("Runtime configuration is unavailable.")} retry={() => { void configurationQuery.refetch(); void definitionsQuery.refetch(); if (editing) void existingQuery.refetch(); }} />;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!configuration) {
      setErrors({ configuration: "Runtime configuration is unavailable." });
      return;
    }
    const formSchema = z.object({
      name: z.string().trim().min(configuration.limits.schedule_name_min).max(configuration.limits.schedule_name_max),
      definitionId: z.string().uuid("Choose a published definition"),
      cron: z.string().trim().refine((value) => value.split(/\s+/).length === configuration.scheduler.cron_fields, `Use a ${configuration.scheduler.cron_fields}-field cron expression`),
      timezone: z.string().trim().min(1),
    });
    const result = formSchema.safeParse({ name, definitionId, cron, timezone });
    const previewValid = (() => { try { return nextCronRuns(cron, timezone, 1, configuration.scheduler.search_horizon_days).length === 1; } catch { return false; } })();
    if (!result.success || !previewValid) {
      const next: Record<string, string> = {};
      if (!result.success) for (const issue of result.error.issues) next[String(issue.path[0])] = issue.message;
      if (!previewValid) next.cron = "Cron expression or timezone cannot produce a valid upcoming run";
      setErrors(next); return;
    }
    setErrors({}); mutation.mutate();
  }

  const definitions = definitionsQuery.data?.items ?? [];
  return <main className="space-y-6"><PageHeader title={editing ? "Edit schedule" : "Create schedule"} description="Preview the exact cadence before attaching it to an immutable published definition version." /><form onSubmit={submit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]"><Card><CardHeader><CardTitle>Schedule policy</CardTitle></CardHeader><CardContent className="space-y-5"><Input label="Name" value={name} error={errors.name} onChange={(event) => setName(event.target.value)} /><label className="block text-sm font-medium">Published definition<select aria-label="Published definition" disabled={editing} value={definitionId} onChange={(event) => setDefinitionId(event.target.value)} className="mt-1 block h-10 w-full rounded-md border bg-background px-3"><option value="">Choose a definition</option>{definitions.map((definition) => <option key={definition.id} value={definition.id}>{definition.name} · {definition.key} v{definition.version}</option>)}</select>{errors.definitionId ? <span className="mt-1 block text-sm text-destructive">{errors.definitionId}</span> : null}</label>{definitions.length === 0 ? <p role="status" className="rounded border border-secondary p-3 text-sm text-secondary-foreground">Publish a validated definition before creating a schedule.</p> : null}<Input label="Cron expression" value={cron} error={errors.cron} onChange={(event) => setCron(event.target.value)} /><Input label="IANA timezone" value={timezone} error={errors.timezone} onChange={(event) => setTimezone(event.target.value)} /><div className="grid gap-4 sm:grid-cols-2"><label className="text-sm font-medium">Misfire policy<select value={misfire} onChange={(event) => setMisfire(event.target.value as MisfirePolicy)} className="mt-1 block h-10 w-full rounded-md border bg-background px-3"><option value="run_once">Run once</option><option value="skip">Skip</option></select></label><label className="text-sm font-medium">Concurrency<select value={concurrency} onChange={(event) => setConcurrency(event.target.value as ConcurrencyPolicy)} className="mt-1 block h-10 w-full rounded-md border bg-background px-3"><option value="forbid">Forbid overlap</option><option value="allow">Allow overlap</option></select></label></div></CardContent></Card><div className="space-y-5"><CronPreview expression={cron} timezone={timezone} count={configuration.ui.cron_preview_count} searchHorizonDays={configuration.scheduler.search_horizon_days} /><Card><CardContent className="space-y-2 p-5 text-sm"><p className="font-medium">Execution safeguards</p><p className="text-muted-foreground">Misfires are applied deterministically. “Forbid overlap” will not enqueue while this schedule already has a nonterminal run.</p></CardContent></Card></div>{mutation.error ? <p role="alert" className="rounded border border-destructive/40 p-3 text-sm text-destructive lg:col-span-2">{mutation.error.message}</p> : null}<div className="flex justify-end gap-3 lg:col-span-2"><Button type="button" variant="ghost" onClick={() => navigate(ROUTE_PATHS.SCHEDULES)}>Cancel</Button><Button type="submit" disabled={mutation.isPending || definitions.length === 0}>{mutation.isPending ? "Saving…" : editing ? "Save schedule" : "Create schedule"}</Button></div></form></main>;
}
