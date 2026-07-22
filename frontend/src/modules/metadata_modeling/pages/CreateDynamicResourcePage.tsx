import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Eye, Save } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { DynamicResourceForm } from "../components/DynamicResourceForm";
import { validateDynamicValues } from "../components/dynamic-validation";
import { ROUTES, type JSONObject } from "../contracts";
import { metadataModelingService } from "../services/metadata-modeling-service";
import { GovernedErrorState, PageHeader, PageSkeleton, fieldErrorsFrom, idempotencyKey } from "./page-utils";

export function CreateDynamicResourcePage() {
  const navigate = useNavigate(); const [params] = useSearchParams(); const initialEntity = params.get("entity") ?? ""; const [entityId, setEntityId] = useState(initialEntity); const [values, setValues] = useState<JSONObject>({}); const [displayName, setDisplayName] = useState(""); const [namingPreview, setNamingPreview] = useState(""); const [busy, setBusy] = useState(false); const [serverError, setServerError] = useState<Error | null>(null); const [submitted, setSubmitted] = useState(false);
  const definitions = useQuery({ queryKey: ["metadata-definitions", "published"], queryFn: () => metadataModelingService.listDefinitions({ status: "published", page_size: 100, ordering: "name" }) }); const definition = useQuery({ queryKey: ["metadata-definition", entityId], queryFn: () => metadataModelingService.getDefinition(entityId), enabled: Boolean(entityId) });
  useEffect(() => { if (!definition.data) return; const defaults: JSONObject = {}; for (const field of definition.data.active_fields) if (field.default_value !== null) defaults[field.key] = field.default_value; setValues(defaults); setNamingPreview(""); setServerError(null); }, [definition.data]);
  const clientErrors = useMemo(() => definition.data ? validateDynamicValues(definition.data.active_fields, values) : {}, [definition.data, values]); const errors = { ...clientErrors, ...(serverError ? fieldErrorsFrom(serverError) : {}) };
  if (definitions.isLoading) return <PageSkeleton />; if (definitions.error) return <GovernedErrorState error={definitions.error} onRetry={() => void definitions.refetch()} />;
  const submit = async () => { setSubmitted(true); if (Object.keys(clientErrors).length > 0 || !entityId) return; setBusy(true); setServerError(null); try { const created = await metadataModelingService.createResource({ entity_id: entityId, data: values, display_name: displayName || undefined }, idempotencyKey()); navigate(ROUTES.recordDetail(created.id), { replace: true }); } catch (reason) { setServerError(reason instanceof Error ? reason : new Error("Creation failed.")); } finally { setBusy(false); } };
  const previewKey = async () => { setBusy(true); try { setNamingPreview(await metadataModelingService.previewRecordKey(entityId, values)); } finally { setBusy(false); } };
  return <main id="main-content" className="space-y-6 p-4 md:p-8"><PageHeader title="Create Dynamic Record" description="This form is generated from the selected model’s active published schema. The server remains the validation authority." />
    <section className="space-y-5 rounded-lg border border-border bg-card p-5"><div className="grid gap-4 md:grid-cols-2"><label><span className="text-sm font-medium">Metadata model</span><select className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3" value={entityId} onChange={(event) => setEntityId(event.target.value)}><option value="">Select a published model</option>{definitions.data?.items.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label><Input id="display-name" label="Display name (optional)" value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></div>
      {definition.isLoading && <PageSkeleton rows={4} />}{definition.error && <GovernedErrorState error={definition.error} onRetry={() => void definition.refetch()} />}{definition.data && <><DynamicResourceForm fields={definition.data.active_fields} values={values} errors={submitted || serverError ? errors : {}} disabled={busy} onChange={(next) => { setValues(next); setNamingPreview(""); setServerError(null); }} /><div className="rounded-lg border border-border bg-muted p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-medium">Record key preview</p><p className="font-mono text-sm text-muted-foreground">{namingPreview || "Not generated yet"}</p></div><Button variant="outline" disabled={busy || Object.keys(clientErrors).length > 0} onClick={() => void previewKey()}><Eye className="mr-2 h-4 w-4" />Preview key</Button></div></div></>}
      {serverError && <p role="alert" className="text-sm text-destructive">{serverError.message}</p>}<div className="flex justify-end gap-2"><Button variant="outline" onClick={() => navigate(ROUTES.records)}>Cancel</Button><Button disabled={busy || !definition.data} onClick={() => void submit()}><Save className="mr-2 h-4 w-4" />{busy ? "Creating…" : "Create record"}</Button></div>
    </section>
  </main>;
}
