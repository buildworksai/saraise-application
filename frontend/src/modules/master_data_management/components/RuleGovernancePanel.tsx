import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RotateCcw, Upload } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { ItemResult, RulePortableDocument, UUID, DataQualityRule, MatchingRule } from "../contracts";
import { masterDataService } from "../services/master-data-service";
import { GovernedError, MutationNotice, QUERY_KEYS, Surface, formatDate, idempotencyKey } from "./MdmUI";

type RuleKind = "quality" | "matching";

export function RuleGovernancePanel({ kind, ruleId }: { readonly kind: RuleKind; readonly ruleId: UUID }) {
  const cache = useQueryClient();
  const [reason, setReason] = useState("");
  const [document, setDocument] = useState<RulePortableDocument>();
  const [clientError, setClientError] = useState<Error | null>(null);
  const [rollbackKey, setRollbackKey] = useState(() => idempotencyKey(`${kind}-rule-rollback`));
  const [importKey, setImportKey] = useState(() => idempotencyKey(`${kind}-rule-import`));
  const historyKey = kind === "quality" ? QUERY_KEYS.qualityRuleHistory(ruleId) : QUERY_KEYS.matchingRuleHistory(ruleId);
  const detailKey = kind === "quality" ? QUERY_KEYS.qualityRule(ruleId) : QUERY_KEYS.matchingRule(ruleId);
  const history = useQuery({
    queryKey: historyKey,
    queryFn: () => kind === "quality"
      ? masterDataService.qualityRules.history(ruleId)
      : masterDataService.matchingRules.history(ruleId),
  });
  const refresh = async () => {
    await cache.invalidateQueries({ queryKey: historyKey });
    await cache.invalidateQueries({ queryKey: detailKey });
  };
  const rollback = useMutation<ItemResult<DataQualityRule> | ItemResult<MatchingRule>, unknown, number>({
    mutationFn: (versionNumber: number) => kind === "quality"
      ? masterDataService.qualityRules.rollback(ruleId, { version_number: versionNumber, reason, idempotency_key: rollbackKey })
      : masterDataService.matchingRules.rollback(ruleId, { version_number: versionNumber, reason, idempotency_key: rollbackKey }),
    onSuccess: async () => {
      setRollbackKey(idempotencyKey(`${kind}-rule-rollback`));
      await refresh();
    },
  });
  const imported = useMutation<ItemResult<DataQualityRule> | ItemResult<MatchingRule>, unknown, void>({
    mutationFn: () => {
      if (!document) throw new Error("Choose a portable rule document before importing.");
      return kind === "quality"
        ? masterDataService.qualityRules.importDocument(ruleId, { document, reason, idempotency_key: importKey })
        : masterDataService.matchingRules.importDocument(ruleId, { document, reason, idempotency_key: importKey });
    },
    onSuccess: async () => {
      setImportKey(idempotencyKey(`${kind}-rule-import`));
      setDocument(undefined);
      await refresh();
    },
  });
  const exported = useMutation({
    mutationFn: () => kind === "quality"
      ? masterDataService.qualityRules.exportDocument(ruleId)
      : masterDataService.matchingRules.exportDocument(ruleId),
    onSuccess: (response) => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(response.data, null, 2)], { type: "application/json" }));
      const anchor = globalThis.document.createElement("a");
      anchor.href = url;
      anchor.download = `${kind}-rule-${ruleId}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    },
  });
  const mutationError = clientError ?? rollback.error ?? imported.error ?? exported.error;

  if (history.error) return <GovernedError error={history.error} retry={() => void history.refetch()}/>;
  return <Surface title="Versioning and portability">
    <p className="text-sm text-muted-foreground">Every change is immutable and correlated. Supply a reason before rollback or import.</p>
    <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto]">
      <Input aria-label="Change reason" placeholder="Required change reason" value={reason} onChange={(event) => setReason(event.target.value)}/>
      <Button variant="outline" disabled={exported.isPending} onClick={() => exported.mutate()}><Download className="mr-2 h-4 w-4"/>Export</Button>
      <label className="inline-flex cursor-pointer items-center justify-center rounded-md border px-4 text-sm font-medium">
        <Upload className="mr-2 h-4 w-4"/>Choose import
        <input className="sr-only" type="file" accept="application/json" onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void file.text().then((text) => {
            try {
              setDocument(JSON.parse(text) as RulePortableDocument);
              setClientError(null);
            } catch {
              setDocument(undefined);
              setClientError(new Error("The selected rule document is not valid JSON."));
            }
          });
        }}/>
      </label>
    </div>
    <Button className="mt-3" disabled={!document || !reason.trim() || imported.isPending} onClick={() => imported.mutate()}>
      <Upload className="mr-2 h-4 w-4"/>Import selected document
    </Button>
    <MutationNotice error={mutationError}/>
    <div className="mt-5 space-y-2">
      {history.isLoading ? <p className="text-sm text-muted-foreground">Loading immutable history…</p> : history.data?.items.map((version) =>
        <div key={version.id} className="flex flex-col gap-2 rounded border p-3 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="text-sm font-medium">Version {version.version_number}</p><p className="text-xs text-muted-foreground">{version.change_reason} · {formatDate(version.created_at)} · {version.correlation_id}</p></div>
          <Button size="sm" variant="outline" disabled={!reason.trim() || rollback.isPending} onClick={() => rollback.mutate(version.version_number)}>
            <RotateCcw className="mr-2 h-4 w-4"/>Rollback
          </Button>
        </div>)}
    </div>
  </Surface>;
}
