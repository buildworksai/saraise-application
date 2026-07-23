/* eslint-disable @typescript-eslint/no-unsafe-member-access -- router state is narrowed before display. */
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ROUTES } from "../contracts";
import { masterDataService } from "../services/master-data-service";
import { ConfirmAction, Detail, DetailGrid, GovernedError, MutationNotice, PageHeader, PageSkeleton, QUERY_KEYS, StatusPill, Surface, formatDate, useStableIdempotencyKey } from "../components/MdmUI";

export function MergeHistoryDetailPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const [reason, setReason] = useState("");
  const query = useQuery({ queryKey: QUERY_KEYS.merge(id), queryFn: () => masterDataService.merges.get(id), enabled: Boolean(id) });
  const preview = useMutation({ mutationFn: () => masterDataService.merges.reversalPreview(id) });
  const reversalKey = useStableIdempotencyKey("merge-reversal");
  const reverse = useMutation({
    mutationFn: () => {
      if (!preview.data?.data.can_reverse) throw new Error("A successful authoritative reversal preview is required.");
      return masterDataService.merges.reverse(id, { reason, transition_key: reversalKey });
    },
    onSuccess: () => void query.refetch(),
  });
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data) return <GovernedError error={new Error("Merge history not found.")}/>;
  const merge = query.data.data;
  const success = typeof location.state === "object" && location.state && "success" in location.state ? String(location.state.success) : reverse.isSuccess ? "Merge reversal applied." : undefined;
  const reversal = preview.data?.data;
  return <main className="space-y-6">
    <PageHeader title="Merge provenance" description={merge.reason} actions={<><StatusPill value={merge.status}/><Link to={ROUTES.ENTITY_DETAIL(merge.golden_record)}><Button variant="outline">Open golden record</Button></Link></>}/>
    <MutationNotice error={reverse.error} success={success}/>
    <Surface title="Transaction evidence"><DetailGrid><Detail label="Merge ID"><span className="font-mono text-xs">{merge.id}</span></Detail><Detail label="Applied">{formatDate(merge.created_at)}</Detail><Detail label="Merged by"><span className="font-mono text-xs">{merge.merged_by}</span></Detail><Detail label="Correlation"><span className="font-mono text-xs">{merge.correlation_id}</span></Detail><Detail label="Reversed">{formatDate(merge.reversed_at)}</Detail><Detail label="Reversed by"><span className="font-mono text-xs">{merge.reversed_by ?? "—"}</span></Detail></DetailGrid></Surface>
    <Surface title="Participants and snapshots">{merge.participants?.length ? <div className="grid gap-4 md:grid-cols-2">{merge.participants.map((participant) => <article key={participant.id} className="rounded-lg border p-4"><div className="flex items-center justify-between"><Link className="font-medium text-primary hover:underline" to={ROUTES.ENTITY_DETAIL(participant.source_entity)}>{participant.source_entity}</Link><span className="rounded-full bg-muted px-2 py-1 text-xs">{participant.role}</span></div><p className="mt-2 text-xs text-muted-foreground">Source version {participant.source_version}</p><dl className="mt-4 space-y-2">{Object.entries(participant.source_snapshot).slice(0, 8).map(([key, value]) => <div key={key} className="grid grid-cols-[130px_1fr] gap-2 text-sm"><dt className="font-mono text-xs text-muted-foreground">{key}</dt><dd className="break-all">{JSON.stringify(value)}</dd></div>)}</dl></article>)}</div> : <p className="text-sm text-muted-foreground">Participant evidence was not included in this response.</p>}</Surface>
    {merge.status === "applied" ? <Surface title="Reversal safety preview">
      <p className="text-sm text-muted-foreground">The dedicated preview endpoint validates every participant version. A missing or unavailable capability fails closed.</p>
      <Button className="mt-3" variant="outline" disabled={preview.isPending} onClick={() => preview.mutate()}>{preview.isPending ? "Checking conflicts…" : "Check reversal conflicts"}</Button>
      {preview.error ? <div className="mt-4"><GovernedError error={preview.error} retry={() => preview.mutate()}/></div> : null}
      {reversal ? reversal.conflicts.length ? <ul role="alert" className="mt-4 space-y-2 rounded border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{reversal.conflicts.map((conflict) => <li key={`${conflict.code}-${conflict.entity_id}`}>{conflict.code}: {conflict.message}</li>)}</ul> : reversal.can_reverse ? <div className="mt-4"><p className="rounded border border-primary/30 bg-primary/10 p-3 text-sm text-primary">The authoritative reversal preview reports no conflicts. Submission performs the final locked validation.</p><label className="mt-4 block text-sm font-medium" htmlFor="reversal-reason">Reversal reason<textarea id="reversal-reason" required className="mt-1 block min-h-24 w-full rounded-md border bg-background p-3" value={reason} onChange={(event) => setReason(event.target.value)}/></label><div className="mt-3"><ConfirmAction label="Reverse merge" title="Reverse this merge?" description="Recorded snapshots are restored only if the locked version check still passes." pending={reverse.isPending} danger onConfirm={() => reverse.mutate()}/></div></div> : <GovernedError error={new Error("The server denied reversal without reporting fabricated success.")}/> : null}
    </Surface> : null}
  </main>;
}
