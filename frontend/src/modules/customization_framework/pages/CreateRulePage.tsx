import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { GovernedError, PageHeader, PageSkeleton, Surface } from "../components/CustomizationUI";
import { TargetContractSelector } from "../components/TargetContractSelector";
import { useRuntimeConfiguration } from "../components/useRuntimeConfiguration";
import { useUnsavedChanges } from "../components/useUnsavedChanges";
import { ROUTES, type RuleCreateRequest, type RuleTrigger } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function CreateRulePage() {
  const navigate = useNavigate();
  const configuration = useRuntimeConfiguration();
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [description, setDescription] = useState("");
  const [module, setModule] = useState("");
  const [resource, setResource] = useState("");
  const [version, setVersion] = useState("");
  const [trigger, setTrigger] = useState<RuleTrigger | "">("");
  const [priority, setPriority] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const document = configuration.data?.document;
    if (document) {
      if (!trigger) setTrigger(document.policies.rule_triggers[0] ?? "");
      if (!priority) setPriority(String(document.defaults.rule_priority));
    }
  }, [configuration.data, priority, trigger]);
  useUnsavedChanges(Boolean(name || key || description));
  const mutation = useMutation({ mutationFn: (request: RuleCreateRequest) => service.createRule(request), onSuccess: result => navigate(ROUTES.RULE_EDIT(result.data.id)) });
  function submit(event: React.FormEvent) {
    event.preventDefault();
    const document = configuration.data?.document;
    const numeric = Number(priority);
    if (!document || !name.trim() || !new RegExp(document.policies.slug_pattern, "u").test(key) || !module || !resource || !version || !trigger || !document.policies.rule_triggers.includes(trigger) || !Number.isInteger(numeric) || numeric < document.limits.rule_priority_min || numeric > document.limits.rule_priority_max) {
      setError("Complete every field within the configured rule policy.");
      return;
    }
    setError("");
    mutation.mutate({ key, name, description, owner_module: module, target_resource: resource, target_contract_version: version, trigger, priority: numeric, stop_on_match: document.defaults.rule_stop_on_match });
  }
  if (configuration.isLoading) return <PageSkeleton/>;
  if (configuration.error) return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
  if (!configuration.data) return <GovernedError error={new Error("Runtime configuration was not returned.")}/>;
  const runtime = configuration.data.document;
  return <main className="space-y-6">
    <PageHeader title="Create business rule" description="Define rule identity and deterministic order, then compose a candidate version with allowlisted operators and actions."/>
    <form onSubmit={submit} className="space-y-6"><Surface>
      <div className="grid gap-5 sm:grid-cols-2">
        <TargetContractSelector value={module ? `${module}/${resource}@${version}` : ""} onSelect={contract => { setModule(contract.module); setResource(contract.resource); setVersion(contract.version); const allowed = contract.rule_triggers.filter(item => runtime.policies.rule_triggers.includes(item)); setTrigger(allowed.includes(trigger as RuleTrigger) ? trigger : allowed[0] ?? ""); }}/>
        <Input id="rule-name" label="Name" required maxLength={runtime.limits.form_name_length} value={name} onChange={event => { setName(event.target.value); if (!key) setKey(event.target.value.toLowerCase().replace(/[^a-z0-9]+/gu, "-").replace(/^-|-$/gu, "")); }}/>
        <Input id="rule-key" label="Stable key" required maxLength={runtime.limits.form_key_length} value={key} onChange={event => setKey(event.target.value)}/>
        <label className="grid gap-1 text-sm font-medium">Trigger<select className="h-10 rounded-md border bg-background px-3" value={trigger} onChange={event => setTrigger(event.target.value as RuleTrigger)}>{runtime.policies.rule_triggers.map(value => <option key={value}>{value}</option>)}</select></label>
        <Input id="rule-priority" label="Priority" type="number" min={runtime.limits.rule_priority_min} max={runtime.limits.rule_priority_max} value={priority} onChange={event => setPriority(event.target.value)}/>
      </div>
      <Textarea id="rule-description" className="mt-5" aria-label="Description" value={description} onChange={event => setDescription(event.target.value)}/>
      {error ? <p role="alert" className="mt-4 text-sm text-destructive">{error}</p> : null}
    </Surface>
    {mutation.error ? <GovernedError error={mutation.error}/> : null}
    <div className="flex justify-end gap-3"><Button type="button" variant="outline" onClick={() => navigate(ROUTES.RULES)}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Creating…" : "Create and build"}</Button></div>
    </form>
  </main>;
}
