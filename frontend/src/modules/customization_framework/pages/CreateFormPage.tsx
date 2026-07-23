import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { GovernedError, PageHeader, PageSkeleton, Surface } from "../components/CustomizationUI";
import { TargetContractSelector } from "../components/TargetContractSelector";
import { useRuntimeConfiguration } from "../components/useRuntimeConfiguration";
import { useUnsavedChanges } from "../components/useUnsavedChanges";
import { ROUTES } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function CreateFormPage() {
  const navigate = useNavigate();
  const configuration = useRuntimeConfiguration();
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [description, setDescription] = useState("");
  const [module, setModule] = useState("");
  const [resource, setResource] = useState("");
  const [version, setVersion] = useState("");
  const [error, setError] = useState("");
  useUnsavedChanges(Boolean(name || key || description));
  const mutation = useMutation({ mutationFn: () => service.createForm({ key, name, description, owner_module: module, target_resource: resource, target_contract_version: version }), onSuccess: result => navigate(ROUTES.FORM_EDIT(result.data.id)) });
  function submit(event: React.FormEvent) {
    event.preventDefault();
    const runtime = configuration.data?.document;
    if (!runtime || !name.trim() || !new RegExp(runtime.policies.slug_pattern, "u").test(key) || !module || !resource || !version) {
      setError("Name, governed key, module, resource, and contract version are required.");
      return;
    }
    setError("");
    mutation.mutate();
  }
  if (configuration.isLoading) return <PageSkeleton/>;
  if (configuration.error) return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
  if (!configuration.data) return <GovernedError error={new Error("Runtime configuration was not returned.")}/>;
  const runtime = configuration.data.document;
  return <main className="space-y-6"><PageHeader title="Create form" description="Start with a registered target contract, then compose the initial layout in the accessible designer."/><form onSubmit={submit} className="space-y-6"><Surface><div className="grid gap-5 sm:grid-cols-2"><TargetContractSelector value={module ? `${module}/${resource}@${version}` : ""} onSelect={contract => { setModule(contract.module); setResource(contract.resource); setVersion(contract.version); }}/><Input id="form-name" label="Name" required maxLength={runtime.limits.form_name_length} value={name} onChange={event => { setName(event.target.value); if (!key) setKey(event.target.value.toLowerCase().replace(/[^a-z0-9]+/gu, "-").replace(/^-|-$/gu, "")); }}/><Input id="form-key" label="Stable key" required maxLength={runtime.limits.form_key_length} value={key} onChange={event => setKey(event.target.value)}/></div><Textarea id="form-description" className="mt-5" aria-label="Description" value={description} onChange={event => setDescription(event.target.value)}/>{error ? <p role="alert" className="mt-4 text-sm text-destructive">{error}</p> : null}</Surface>{mutation.error ? <GovernedError error={mutation.error}/> : null}<div className="flex justify-end gap-3"><Button type="button" variant="outline" onClick={() => navigate(ROUTES.FORMS)}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Creating…" : "Create and design"}</Button></div></form></main>;
}
