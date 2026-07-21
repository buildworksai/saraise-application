import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { GovernedError, PageHeader, PageSkeleton, Surface } from "../components/CustomizationUI";
import { asObject, parseJSON } from "../components/customization-utils";
import { useUnsavedChanges } from "../components/useUnsavedChanges";
import { ROUTES } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function EditFieldDefinitionPage() {
  const { id = "" } = useParams(); const navigate = useNavigate(); const query = useQuery({ queryKey: ["customization", "field", id], queryFn: () => service.getField(id), enabled: Boolean(id) }); const [label, setLabel] = useState(""); const [description, setDescription] = useState(""); const [schema, setSchema] = useState("{}"); const [dirty, setDirty] = useState(false); const [error, setError] = useState("");
  useEffect(() => { if (query.data && !dirty) { setLabel(query.data.data.label); setDescription(query.data.data.description); setSchema(JSON.stringify(query.data.data.validation_schema, null, 2)); } }, [query.data, dirty]); useUnsavedChanges(dirty);
  const mutation = useMutation({ mutationFn: () => service.updateField(id, { label, description, validation_schema: asObject(parseJSON(schema)), expected_lock_version: query.data?.data.lock_version ?? 0 }), onSuccess: (result) => navigate(ROUTES.FIELD_DETAIL(result.data.id)), onError: (caught) => setError(caught instanceof Error ? caught.message : "Update failed.") });
  if (query.isLoading) return <PageSkeleton/>; if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>; if (!query.data) return <GovernedError error={new Error("Field not found.")}/>; const field = query.data.data;
  return <main className="space-y-6"><PageHeader title={`Edit ${field.label}`} description="Updates use optimistic concurrency. Active identity and data type remain immutable."/><Surface><div className="rounded-lg border bg-muted/40 p-4 text-sm"><strong>Immutable:</strong> {field.key} · {field.owner_module}/{field.target_resource} · {field.data_type}</div><div className="mt-5 space-y-5"><Input id="edit-field-label" label="Label" value={label} onChange={(event) => { setLabel(event.target.value); setDirty(true); }}/><Textarea id="edit-field-description" aria-label="Description" value={description} onChange={(event) => { setDescription(event.target.value); setDirty(true); }}/><Textarea id="edit-field-schema" aria-label="Validation schema" rows={10} value={schema} onChange={(event) => { setSchema(event.target.value); setDirty(true); }}/><p className="text-xs text-muted-foreground">Dependency impact: {field.dependency_count} references. Review impact before tightening validation.</p>{error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}</div></Surface>{mutation.error ? <GovernedError error={mutation.error} retry={() => mutation.reset()}/> : null}<div className="flex justify-end gap-3"><Button variant="outline" onClick={() => navigate(ROUTES.FIELD_DETAIL(id))}>Cancel</Button><Button disabled={!dirty || mutation.isPending} onClick={() => { try { asObject(parseJSON(schema)); setError(""); mutation.mutate(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Invalid schema."); } }}>{mutation.isPending ? "Saving…" : "Save revision"}</Button></div></main>;
}
