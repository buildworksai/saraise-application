import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { GovernedError, PageHeader, PageSkeleton, Surface } from "../components/CustomizationUI";
import { TargetContractSelector } from "../components/TargetContractSelector";
import { asObject, parseJSON } from "../components/customization-utils";
import { useRuntimeConfiguration } from "../components/useRuntimeConfiguration";
import { useUnsavedChanges } from "../components/useUnsavedChanges";
import { ROUTES, type FieldDataType, type FieldDefinitionCreateRequest, type JSONObject } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function CreateFieldDefinitionPage() {
  const navigate = useNavigate();
  const configuration = useRuntimeConfiguration();
  const [step, setStep] = useState(1);
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [description, setDescription] = useState("");
  const [module, setModule] = useState("");
  const [resource, setResource] = useState("");
  const [version, setVersion] = useState("");
  const [dataType, setDataType] = useState<FieldDataType | "">("");
  const [schema, setSchema] = useState("{}");
  const [error, setError] = useState("");
  useEffect(() => {
    const document = configuration.data?.document;
    if (document && !dataType) {
      setDataType(document.policies.field_types[0] ?? "");
      setSchema(JSON.stringify({ maxLength: document.limits.field_label_length }, null, 2));
    }
  }, [configuration.data, dataType]);
  useUnsavedChanges(Boolean(label || key || description));
  const mutation = useMutation({ mutationFn: (request: FieldDefinitionCreateRequest) => service.createField(request), onSuccess: result => navigate(ROUTES.FIELD_DETAIL(result.data.id)) });
  function request(): FieldDefinitionCreateRequest | null {
    const document = configuration.data?.document;
    if (!document || !label.trim() || !new RegExp(document.policies.slug_pattern, "u").test(key) || !module || !resource || !version || !dataType || !document.policies.field_types.includes(dataType)) {
      setError("Complete every field using the tenant policy and selected contract.");
      return null;
    }
    try {
      const validation_schema: JSONObject = asObject(parseJSON(schema));
      setError("");
      return { key, label, description, owner_module: module, target_resource: resource, target_contract_version: version, data_type: dataType, required: document.defaults.field_required, searchable: document.defaults.field_searchable, validation_schema, presentation_schema: { label } };
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid JSON schema.");
      return null;
    }
  }
  if (configuration.isLoading) return <PageSkeleton/>;
  if (configuration.error) return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
  if (!configuration.data) return <GovernedError error={new Error("Runtime configuration was not returned.")}/>;
  const runtime = configuration.data.document;
  return <main className="space-y-6">
    <PageHeader title="Create custom field" description="Choose a registered target, define a safe field contract, validate it, then review before creation."/>
    <nav aria-label="Creation steps" className="flex gap-2">{["Target", "Definition", "Review"].map((item, index) => <Button key={item} type="button" variant={step === index + 1 ? "primary" : "outline"} onClick={() => setStep(index + 1)}>{index + 1}. {item}</Button>)}</nav>
    <Surface>
      {step === 1 ? <div className="grid gap-5 sm:grid-cols-2"><TargetContractSelector value={module ? `${module}/${resource}@${version}` : ""} onSelect={contract => { setModule(contract.module); setResource(contract.resource); setVersion(contract.version); if (!contract.custom_field_types.includes(dataType as FieldDataType)) setDataType(contract.custom_field_types[0] ?? ""); }}/><p className="sm:col-span-2 text-sm text-muted-foreground">Targets are explicitly registered and versioned. Unavailable capabilities remain visible without fabricated enablement.</p></div> : null}
      {step === 2 ? <div className="space-y-5"><div className="grid gap-5 sm:grid-cols-2"><Input id="field-label" label="Label" required maxLength={runtime.limits.field_label_length} value={label} onChange={event => { setLabel(event.target.value); if (!key) setKey(event.target.value.toLowerCase().replace(/[^a-z0-9]+/gu, "-").replace(/^-|-$/gu, "")); }}/><Input id="field-key" label="Stable key" required maxLength={runtime.limits.field_key_length} value={key} onChange={event => setKey(event.target.value)}/><label className="grid gap-1 text-sm font-medium">Data type<select className="h-10 rounded-md border bg-background px-3" value={dataType} onChange={event => setDataType(event.target.value as FieldDataType)}>{runtime.policies.field_types.map(type => <option key={type}>{type}</option>)}</select></label></div><Textarea id="field-description" aria-label="Description" value={description} onChange={event => setDescription(event.target.value)} placeholder="How administrators and users should understand this field"/><Textarea id="validation-schema" aria-label="Validation schema" rows={8} value={schema} onChange={event => setSchema(event.target.value)}/><p className="text-xs text-muted-foreground">Declarative JSON Schema only. Scripts, functions, network calls, and executable expressions are prohibited.</p></div> : null}
      {step === 3 ? <div><h2 className="font-semibold">Review contract</h2><pre className="mt-4 overflow-auto rounded-lg bg-muted p-4 text-xs">{JSON.stringify({ module, resource, version, key, label, dataType, schema }, null, 2)}</pre><p className="mt-4 text-sm text-muted-foreground">The lifecycle default is governed by tenant configuration: {runtime.defaults.field_status}.</p></div> : null}
      {error ? <p id="field-form-error" role="alert" className="mt-4 text-sm text-destructive">{error}</p> : null}
    </Surface>
    {mutation.error ? <GovernedError error={mutation.error}/> : null}
    <div className="flex justify-between"><Button variant="ghost" onClick={() => navigate(ROUTES.FIELDS)}>Cancel</Button><div className="flex gap-2">{step > 1 ? <Button variant="outline" onClick={() => setStep(step - 1)}>Back</Button> : null}{step < 3 ? <Button onClick={() => { if (step === 2 && !request()) return; setStep(step + 1); }}>Continue</Button> : <Button disabled={mutation.isPending} onClick={() => { const value = request(); if (value) mutation.mutate(value); }}>{mutation.isPending ? "Creating…" : "Create field"}</Button>}</div></div>
  </main>;
}
