import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit3, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { ConfirmAction, Detail, DetailGrid, EmptyPanel, GovernedError, PageHeader, PageSkeleton, Pagination, Surface } from "../components/CustomizationUI";
import { formatDate, parseJSON } from "../components/customization-utils";
import { useRuntimeConfiguration } from "../components/useRuntimeConfiguration";
import { ROUTES, type FieldValueCreateRequest, type FieldValueSource, type JSONValue } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function FieldValueListPage() {
  const navigate = useNavigate();
  const configuration = useRuntimeConfiguration();
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? "1");
  const pageSize = configuration.data?.document.list_preferences.page_size;
  const query = useQuery({ queryKey: ["customization", "field-values", page, pageSize], queryFn: () => service.listValues({ page, page_size: pageSize }), enabled: pageSize !== undefined });
  if (configuration.isLoading || query.isLoading) return <PageSkeleton/>;
  if (configuration.error) return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data) return <GovernedError error={new Error("No governed field-value response was received.")}/>;
  return <main className="space-y-6"><PageHeader title="Custom field values" description="Inspect and maintain tenant-isolated values through their active field contracts." actions={<Button onClick={() => navigate(ROUTES.FIELD_VALUE_CREATE)}><Plus className="mr-2 h-4 w-4"/>Create value</Button>}/>{query.data.data.length === 0 ? <EmptyPanel filtered={false} noun="field values" create={() => navigate(ROUTES.FIELD_VALUE_CREATE)}/> : <section className="overflow-hidden rounded-xl border bg-card"><div className="overflow-x-auto"><table className="w-full min-w-[800px] text-sm"><thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground"><tr><th className="px-4 py-3">Field</th><th className="px-4 py-3">Target record</th><th className="px-4 py-3">Source</th><th className="px-4 py-3">Updated</th></tr></thead><tbody className="divide-y">{query.data.data.map(item => <tr key={item.id}><td className="px-4 py-4"><button className="font-medium text-primary hover:underline" onClick={() => navigate(ROUTES.FIELD_VALUE_DETAIL(item.id))}>{item.definition_key}</button></td><td className="px-4 py-4 font-mono text-xs">{item.target_record_id}</td><td className="px-4 py-4">{item.source}</td><td className="px-4 py-4">{formatDate(item.updated_at)}</td></tr>)}</tbody></table></div><Pagination meta={query.data.meta.pagination} onPage={next => { const updated = new URLSearchParams(params); updated.set("page", String(next)); setParams(updated); }}/></section>}</main>;
}

export function CreateFieldValuePage() {
  const navigate = useNavigate();
  const configuration = useRuntimeConfiguration();
  const pageSize = configuration.data?.document.list_preferences.page_size;
  const definitions = useQuery({ queryKey: ["customization", "active-fields-for-values", pageSize], queryFn: () => service.listFields({ status: "active", page_size: pageSize }), enabled: pageSize !== undefined });
  const [definitionId, setDefinitionId] = useState("");
  const [targetRecordId, setTargetRecordId] = useState("");
  const [source, setSource] = useState<Exclude<FieldValueSource, "rule"> | "">("");
  const [value, setValue] = useState("null");
  const [error, setError] = useState("");
  useEffect(() => { const allowed = configuration.data?.document.policies.value_sources; if (allowed && !source) setSource(allowed[0] ?? ""); }, [configuration.data, source]);
  const mutation = useMutation({ mutationFn: (request: FieldValueCreateRequest) => service.createValue(request), onSuccess: result => navigate(ROUTES.FIELD_VALUE_DETAIL(result.data.id)) });
  function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const parsed = parseJSON(value);
      if (!definitionId || !targetRecordId || !source) throw new Error("Field, target record, and governed source are required.");
      setError("");
      mutation.mutate({ definition_id: definitionId, target_record_id: targetRecordId, source, value: parsed });
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Value must be valid JSON."); }
  }
  if (configuration.isLoading || definitions.isLoading) return <PageSkeleton/>;
  if (configuration.error) return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
  if (definitions.error) return <GovernedError error={definitions.error} retry={() => void definitions.refetch()}/>;
  if (!configuration.data || !definitions.data) return <GovernedError error={new Error("Field-value dependencies were not returned.")}/>;
  return <main className="space-y-6"><PageHeader title="Create custom field value" description="Persist a value only against an active tenant field definition."/><form className="space-y-6" onSubmit={submit}><Surface><div className="grid gap-5 sm:grid-cols-2"><label className="grid gap-1 text-sm font-medium">Active field<select required className="h-10 rounded-md border bg-background px-3" value={definitionId} onChange={event => setDefinitionId(event.target.value)}><option value="">Select a field</option>{definitions.data.data.map(field => <option key={field.id} value={field.id}>{field.label} ({field.key})</option>)}</select></label><Input id="field-value-target" label="Target record UUID" required value={targetRecordId} onChange={event => setTargetRecordId(event.target.value)}/><label className="grid gap-1 text-sm font-medium">Source<select required className="h-10 rounded-md border bg-background px-3" value={source} onChange={event => setSource(event.target.value as Exclude<FieldValueSource, "rule">)}>{configuration.data.document.policies.value_sources.map(item => <option key={item}>{item}</option>)}</select></label></div><Textarea className="mt-5 font-mono" aria-label="JSON value" rows={10} value={value} onChange={event => setValue(event.target.value)}/>{error ? <p role="alert" className="mt-3 text-sm text-destructive">{error}</p> : null}</Surface>{mutation.error ? <GovernedError error={mutation.error}/> : null}<div className="flex justify-end gap-3"><Button type="button" variant="outline" onClick={() => navigate(ROUTES.FIELD_VALUES)}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Creating…" : "Create value"}</Button></div></form></main>;
}

export function FieldValueDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const query = useQuery({ queryKey: ["customization", "field-value", id], queryFn: () => service.getValue(id), enabled: Boolean(id) });
  const remove = useMutation({ mutationFn: () => {
    if (!query.data) throw new Error("The current value revision is unavailable.");
    return service.deleteValue(id, query.data.data.lock_version);
  }, onSuccess: () => navigate(ROUTES.FIELD_VALUES) });
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data) return <GovernedError error={new Error("Field value not found.")}/>;
  const item = query.data.data;
  return <main className="space-y-6"><PageHeader title={item.definition_key} description="Tenant-isolated field value and optimistic-lock evidence." actions={<><Button variant="outline" onClick={() => navigate(ROUTES.FIELD_VALUE_EDIT(id))}><Edit3 className="mr-2 h-4 w-4"/>Edit</Button><Button variant="danger" onClick={() => setConfirmDelete(true)}><Trash2 className="mr-2 h-4 w-4"/>Delete</Button></>}/><Surface><DetailGrid><Detail label="Target record">{item.target_record_id}</Detail><Detail label="Source">{item.source}</Detail><Detail label="Definition revision">{item.definition_revision}</Detail><Detail label="Lock version">{item.lock_version}</Detail><Detail label="Updated">{formatDate(item.updated_at)}</Detail></DetailGrid><pre className="mt-5 overflow-auto rounded bg-muted p-4 text-xs">{JSON.stringify(item.value, null, 2)}</pre></Surface><ConfirmAction open={confirmDelete} title="Delete this field value?" description="Deletion uses the displayed optimistic-lock revision and is audit logged." confirmLabel="Delete value" pending={remove.isPending} onOpenChange={setConfirmDelete} onConfirm={() => remove.mutate()}/>{remove.error ? <GovernedError error={remove.error}/> : null}</main>;
}

export function EditFieldValuePage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["customization", "field-value", id], queryFn: () => service.getValue(id), enabled: Boolean(id) });
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { if (query.data && !value) setValue(JSON.stringify(query.data.data.value, null, 2)); }, [query.data, value]);
  const mutation = useMutation({ mutationFn: (parsed: JSONValue) => {
    if (!query.data) throw new Error("The current value revision is unavailable.");
    return service.updateValue(id, { value: parsed, expected_lock_version: query.data.data.lock_version });
  }, onSuccess: result => { void client.invalidateQueries({ queryKey: ["customization", "field-value", id] }); navigate(ROUTES.FIELD_VALUE_DETAIL(result.data.id)); } });
  function submit(event: React.FormEvent) {
    event.preventDefault();
    try { setError(""); mutation.mutate(parseJSON(value)); } catch (caught) { setError(caught instanceof Error ? caught.message : "Value must be valid JSON."); }
  }
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data) return <GovernedError error={new Error("Field value not found.")}/>;
  return <main className="space-y-6"><PageHeader title={`Edit ${query.data.data.definition_key}`} description="Update the value through its server-validated field contract."/><form className="space-y-6" onSubmit={submit}><Surface><Textarea aria-label="JSON value" className="font-mono" rows={14} value={value} onChange={event => setValue(event.target.value)}/>{error ? <p role="alert" className="mt-3 text-sm text-destructive">{error}</p> : null}</Surface>{mutation.error ? <GovernedError error={mutation.error}/> : null}<div className="flex justify-end gap-3"><Button type="button" variant="outline" onClick={() => navigate(ROUTES.FIELD_VALUE_DETAIL(id))}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Saving…" : "Save value"}</Button></div></form></main>;
}
