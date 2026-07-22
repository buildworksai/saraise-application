/* eslint-disable complexity -- one tabbed workspace coordinates five governed resource projections. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { aiAgentService } from "../services/ai-agent-service";
import { EmptyState, GovernedError, MutationError, PageHeader, PageSkeleton, StatusPill, formatDate } from "../components/AgentUI";

type Tab = "sod" | "egress" | "switches" | "secrets" | "evidence";
interface ResourceItem { readonly id: string; readonly title: string; readonly detail: string; readonly status: string; }

function ResourceList({ items = [] }: { readonly items?: readonly ResourceItem[] }) {
  return items.length ? <ul className="divide-y rounded-xl border bg-card">{items.map((item) => <li key={item.id} className="flex items-center justify-between gap-3 p-4"><div><p className="font-medium">{item.title}</p><p className="text-sm text-muted-foreground">{item.detail}</p></div><StatusPill status={item.status}/></li>)}</ul> : <EmptyState title="No records" description="No tenant-scoped records exist in this governance area."/>;
}

export const GovernancePage = () => {
  const client = useQueryClient();
  const [tab, setTab] = useState<Tab>("sod");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const [secret, setSecret] = useState("");
  const policies = useQuery({ queryKey: ["ai-governance", "sod"], queryFn: () => aiAgentService.listSoDPolicies({ page_size: 100 }), enabled: tab === "sod" });
  const egress = useQuery({ queryKey: ["ai-governance", "egress"], queryFn: () => aiAgentService.listEgressRules({ page_size: 100 }), enabled: tab === "egress" });
  const switches = useQuery({ queryKey: ["ai-governance", "switches"], queryFn: () => aiAgentService.listKillSwitches({ page_size: 100 }), enabled: tab === "switches" });
  const secrets = useQuery({ queryKey: ["ai-governance", "secrets"], queryFn: () => aiAgentService.listSecrets({ page_size: 100 }), enabled: tab === "secrets" });
  const violations = useQuery({ queryKey: ["ai-governance", "violations"], queryFn: () => aiAgentService.listSoDViolations({ page_size: 25 }), enabled: tab === "evidence" });
  const accesses = useQuery({ queryKey: ["ai-governance", "accesses"], queryFn: () => aiAgentService.listSecretAccesses({ page_size: 25 }), enabled: tab === "evidence" });
  const create = useMutation<unknown, Error, void>({
    mutationFn: async () => {
      if (tab === "sod") return aiAgentService.createSoDPolicy({ name, action_1: first, action_2: second });
      if (tab === "egress") return aiAgentService.createEgressRule({ name, destination_type: "domain", destination: first, protocol: "https", port: second ? Number(second) : 443 });
      if (tab === "switches") return aiAgentService.activateKillSwitch({ name, scope: "tenant", reason: first, transition_key: crypto.randomUUID() });
      return aiAgentService.createSecret({ name, secret_type: "api_key", plaintext: secret, description: first });
    },
    onSuccess: () => {
      setShowForm(false); setName(""); setFirst(""); setSecond(""); setSecret("");
      void client.invalidateQueries({ queryKey: ["ai-governance"] });
    },
  });
  const current = tab === "sod" ? policies : tab === "egress" ? egress : tab === "switches" ? switches : tab === "secrets" ? secrets : violations;
  if (current.isLoading) return <PageSkeleton/>;
  if (current.error) return <GovernedError error={current.error} retry={() => void current.refetch()}/>;
  const createLabel = tab === "sod" ? "Create SoD policy" : tab === "egress" ? "Create egress rule" : tab === "switches" ? "Activate tenant switch" : "Store secret";
  return <main className="space-y-6">
    <PageHeader title="Governance controls" description="Manage separation of duties, deny-by-default egress, tenant emergency controls, and secret metadata without exposing secret material." actions={tab !== "evidence" ? <Button onClick={() => setShowForm((value) => !value)}>{createLabel}</Button> : undefined}/>
    <nav role="tablist" aria-label="Governance areas" className="flex overflow-x-auto border-b">{(["sod", "egress", "switches", "secrets", "evidence"] as const).map((item) => <button key={item} role="tab" aria-selected={tab === item} className={`border-b-2 px-4 py-3 text-sm ${tab === item ? "border-primary text-primary" : "border-transparent"}`} onClick={() => { setTab(item); setShowForm(false); }}>{item === "sod" ? "SoD policies" : item === "switches" ? "Kill switches" : item === "evidence" ? "Violations & accesses" : item}</button>)}</nav>
    {showForm ? <form className="space-y-4 rounded-xl border bg-card p-5" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}><Input label="Name" required value={name} onChange={(event) => setName(event.target.value)}/>{tab === "sod" ? <div className="grid gap-4 sm:grid-cols-2"><Input label="First action" required value={first} onChange={(event) => setFirst(event.target.value)}/><Input label="Conflicting action" required value={second} onChange={(event) => setSecond(event.target.value)}/></div> : tab === "egress" ? <div className="grid gap-4 sm:grid-cols-2"><Input label="Canonical destination domain" required value={first} onChange={(event) => setFirst(event.target.value)}/><Input label="Port" type="number" value={second} onChange={(event) => setSecond(event.target.value)}/></div> : tab === "switches" ? <Textarea aria-label="Activation reason" required value={first} onChange={(event) => setFirst(event.target.value)} placeholder="Auditable emergency reason"/> : <><Textarea aria-label="Secret description" value={first} onChange={(event) => setFirst(event.target.value)}/><Input label="Secret value" type="password" required value={secret} onChange={(event) => setSecret(event.target.value)} autoComplete="new-password"/><p className="text-xs text-muted-foreground">Plaintext is submitted once and is never returned by this module.</p></>}{create.error ? <MutationError error={create.error}/> : null}<Button disabled={create.isPending}>{create.isPending ? "Applying governed change…" : createLabel}</Button></form> : null}
    {tab === "sod" ? <ResourceList items={policies.data?.items.map((item) => ({ id: item.id, title: item.name, detail: `${item.action_1} ↔ ${item.action_2}`, status: item.is_active ? "active" : "disabled" }))}/> : tab === "egress" ? <ResourceList items={egress.data?.items.map((item) => ({ id: item.id, title: item.name, detail: `${item.protocol}://${item.destination}:${item.port ?? "default"}`, status: item.is_active ? "active" : "disabled" }))}/> : tab === "switches" ? <ResourceList items={switches.data?.items.map((item) => ({ id: item.id, title: item.name, detail: `${item.scope} · ${item.reason}`, status: item.status }))}/> : tab === "secrets" ? <ResourceList items={secrets.data?.items.map((item) => ({ id: item.id, title: item.name, detail: `${item.secret_type} · rotated ${formatDate(item.last_rotated_at)}`, status: item.is_active ? "active" : "disabled" }))}/> : <section className="grid gap-6 lg:grid-cols-2"><div><h2 className="mb-3 font-semibold">Recent SoD violations</h2><ResourceList items={violations.data?.items.map((item) => ({ id: item.id, title: item.policy_name ?? item.policy_id, detail: formatDate(item.violation_at), status: item.blocked ? "blocked" : "failed" }))}/></div><div><h2 className="mb-3 font-semibold">Recent secret accesses</h2><ResourceList items={accesses.data?.items.map((item) => ({ id: item.id, title: item.secret_name ?? item.secret_id, detail: `${item.purpose} · ${formatDate(item.accessed_at)}`, status: "success" }))}/></div></section>}
  </main>;
};
