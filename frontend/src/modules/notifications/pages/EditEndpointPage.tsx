import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, ShieldCheck } from "lucide-react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PATHS } from "../contracts";
import { NOTIFICATION_QUERY_KEYS, notificationService } from "../services/notification-service";
import { GovernedError, MutationError, PageShell, PageSkeleton, StatusPill, fieldClass, formatDate, labelClass, submitForm } from "../components/NotificationUI";

export function EditEndpointPage() {
  const { id = "" } = useParams(); const client = useQueryClient(); const query = useQuery({ queryKey: NOTIFICATION_QUERY_KEYS.endpoint(id), queryFn: ({ signal }) => notificationService.endpoints.get(id, signal), enabled: Boolean(id) }); const [name, setName] = useState(""); const [secretRef, setSecretRef] = useState(""); const [active, setActive] = useState(true);
  useEffect(() => { if (query.data) { setName(query.data.display_name); setSecretRef(query.data.secret_ref); setActive(query.data.is_active); } }, [query.data]);
  const update = useMutation({ mutationFn: () => notificationService.endpoints.update(id, { display_name: name.trim(), secret_ref: secretRef, is_active: active }), onSuccess: (value) => client.setQueryData(NOTIFICATION_QUERY_KEYS.endpoint(id), value) });
  const verify = useMutation({ mutationFn: () => notificationService.endpoints.verify(id), onSuccess: (result) => client.setQueryData(NOTIFICATION_QUERY_KEYS.endpoint(id), result.endpoint) });
  if (query.isLoading) return <PageSkeleton/>; if (query.error || !query.data) return <PageShell title="Edit endpoint" description="Update notification endpoint policy."><GovernedError error={query.error} retry={() => void query.refetch()} subject="Endpoint"/></PageShell>;
  const item = query.data;
  return <PageShell title={item.display_name} description={`${item.address_display} · Last verified ${formatDate(item.last_verified_at)}`} back={{ label: "Endpoints", to: PATHS.ENDPOINTS }} actions={<Button variant="outline" disabled={!active || verify.isPending} onClick={() => verify.mutate()}><ShieldCheck className="mr-2 h-4 w-4"/>{verify.isPending ? "Verifying…" : "Verify now"}</Button>}><MutationError error={update.error ?? verify.error}/><Card className="mx-auto max-w-2xl p-5"><form className="space-y-5" onSubmit={submitForm(() => update.mutate())}><div className="flex gap-2"><StatusPill value={item.health}/><StatusPill value={active ? "active" : "revoked"}/></div><label className={labelClass}>Display name<input className={fieldClass} required value={name} onChange={(event) => setName(event.target.value)}/></label>{item.kind === "webhook" ? <label className={labelClass}>Signing secret reference<input className={fieldClass} required pattern="(?:vault|aws-secrets|gcp-secrets|azure-keyvault)://[A-Za-z0-9_./-]+" value={secretRef} onChange={(event) => setSecretRef(event.target.value)}/><span className="block text-xs font-normal text-muted-foreground">Rotation stores only an approved secret-manager reference.</span></label> : null}<label className="flex items-center gap-3 rounded-md border p-4 text-sm"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)}/><span><strong>Endpoint enabled</strong><span className="block text-muted-foreground">Disabled endpoints cannot receive new deliveries.</span></span></label><div className="flex justify-end"><Button type="submit" disabled={!name.trim() || update.isPending}><Save className="mr-2 h-4 w-4"/>{update.isPending ? "Saving…" : "Save endpoint"}</Button></div></form></Card></PageShell>;
}
