/* eslint-disable max-lines-per-function, complexity */
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Boxes, Plus, Search } from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { AuditTimeline, ConfirmButton, Detail, DetailGrid, EmptyPanel, GovernedError, MutationError, PageHeader, PageSkeleton, Pagination, StatusChip, Surface, formatDate, useUnsavedChanges } from "../components/SecurityUI";
import { QUERY_KEYS, ROUTES, type DeletionReasonInput, type PermissionSet } from "../contracts";
import { securityService } from "../services/security-service";
import { useSecurityConfiguration } from "../hooks/use-security-configuration";
function update(params: URLSearchParams, set: (next: URLSearchParams) => void, key: string, value: string): void { const next = new URLSearchParams(params);
 if (value)
    next.set(key, value);
else
    next.delete(key);
 if (key !== "page")
    next.delete("page"); set(next); }
export function PermissionSetsPage() { const navigate = useNavigate();
 const configuration = useSecurityConfiguration();
 const [params, setParams] = useSearchParams();
 const search = params.get("search") ?? "";
 const active = params.get("is_active") ?? "";
 const ordering = params.get("ordering") ?? configuration.data?.data.document.ordering.permission_sets.join(",") ?? "";
 const page = Math.max(1, Number(params.get("page") ?? 1));
 const pageSize = configuration.data?.data.document.limits.list_page_size;
 const query = useQuery({ queryKey: QUERY_KEYS.permissionSets({ search, is_active: active ? active === "true" : undefined, ordering, page, page_size: pageSize }), queryFn: () => securityService.permissionSets.list({ search: search || undefined, is_active: active ? active === "true" : undefined, ordering, page, page_size: pageSize }), enabled: pageSize !== undefined && Boolean(ordering) });
 const reset = () => setParams(new URLSearchParams());
 const filtered = Boolean(search || active);
 if (query.isLoading)
    return <PageSkeleton />;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
 if (!query.data)
    return <GovernedError error={new Error("No governed permission-set response was received.")}/>; return <main className="space-y-6"><PageHeader title="Permission sets" description="Build reusable, time-bound capability bundles with atomic membership replacement." actions={<Button onClick={() => navigate(ROUTES.PERMISSION_SET_CREATE)}><Plus className="mr-2 h-4 w-4"/>Create permission set</Button>}/><section aria-label="Permission-set filters" className="grid gap-3 rounded-xl border bg-card p-4 md:grid-cols-[1fr_160px_180px_auto]"><div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"/><Input aria-label="Search permission sets" className="pl-9" value={search} onChange={(event) => update(params, setParams, "search", event.target.value)} placeholder="Search name or description"/></div><select aria-label="Filter active permission sets" value={active} onChange={(event) => update(params, setParams, "is_active", event.target.value)} className="rounded-md border bg-background px-3"><option value="">Any status</option><option value="true">Active</option><option value="false">Inactive</option></select><select aria-label="Sort permission sets" value={ordering} onChange={(event) => update(params, setParams, "ordering", event.target.value)} className="rounded-md border bg-background px-3"><option value="name">Name A–Z</option><option value="-created_at">Newest</option><option value="created_at">Oldest</option></select><Button variant="outline" onClick={reset}>Reset</Button></section>{query.data.items.length === 0 ? <EmptyPanel filtered={filtered} noun="permission sets" onReset={reset} create={() => navigate(ROUTES.PERMISSION_SET_CREATE)}/> : <section className="overflow-hidden rounded-xl border bg-card"><div className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">{query.data.items.map((item) => <Link key={item.id} to={ROUTES.PERMISSION_SET_DETAIL(item.id)} className="rounded-lg border p-4 transition hover:border-primary focus-visible:outline-none focus-visible:ring-2"><div className="flex justify-between gap-3"><h2 className="font-semibold">{item.name}</h2><StatusChip active={item.is_active}/></div><p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{item.description || "No description"}</p><p className="mt-4 text-xs">{item.permission_ids.length} capabilities · {item.active_grant_count ?? 0} active grants</p><p className="mt-1 text-xs text-muted-foreground">{item.default_duration_days ? `${item.default_duration_days}-day default` : "Explicit expiry required"}</p></Link>)}</div><Pagination value={query.data.pagination} onPage={(next) => update(params, setParams, "page", String(next))}/>{query.isFetching ? <p role="status" className="border-t px-4 py-2 text-xs text-muted-foreground">Loading updated permission sets…</p> : null}</section>}</main>; }
export function PermissionSetDetailPage() { const { id = "" } = useParams();
 const navigate = useNavigate();
 const configuration = useSecurityConfiguration();
 const grantPageSize = configuration.data?.data.document.limits.list_page_size;
 const grantOrdering = configuration.data?.data.document.ordering.permission_set_grants.join(",");
 const query = useQuery({ queryKey: QUERY_KEYS.permissionSet(id), queryFn: () => securityService.permissionSets.get(id), enabled: Boolean(id) });
 const grants = useQuery({ queryKey: QUERY_KEYS.userPermissionSets({ permission_set_id: id, page_size: grantPageSize, ordering: grantOrdering }), queryFn: () => securityService.userPermissionSets.list({ permission_set_id: id, page_size: grantPageSize, ordering: grantOrdering }), enabled: Boolean(id) && grantPageSize !== undefined && grantOrdering !== undefined });
 const remove = useMutation({ mutationFn: (input: DeletionReasonInput) => securityService.permissionSets.delete(id, input), onSuccess: () => navigate(ROUTES.PERMISSION_SETS) });
 if (query.isLoading || configuration.isLoading)
    return <PageSkeleton />;
 if (configuration.error)
    return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
 if (!query.data)
    return <GovernedError error={new Error("Permission set not found.")}/>;
 const item = query.data.data; return <main className="space-y-6"><PageHeader title={item.name} description={item.description || "Reusable permission bundle."} actions={<><StatusChip active={item.is_active}/><Button variant="outline" onClick={() => navigate(ROUTES.PERMISSION_SET_EDIT(item.id))}>Edit capability matrix</Button>
<ConfirmButton label="Delete set" question="Soft-delete this permission set? Active protected grants will prevent removal." pending={remove.isPending}
 onConfirm={(input) => remove.mutate(input)}/>
</>}/>{remove.error ? <MutationError error={remove.error}/> : null}<Surface><DetailGrid><Detail label="Capabilities">{item.permission_ids.length}</Detail><Detail label="Default duration">{item.default_duration_days ? `${item.default_duration_days} days` : "No default"}</Detail><Detail label="Active grants">{item.active_grant_count ?? grants.data?.pagination.count ?? "—"}</Detail><Detail label="Created">{formatDate(item.created_at)}</Detail><Detail label="Updated">{formatDate(item.updated_at)}</Detail><Detail label="Identifier"><span className="font-mono text-xs">{item.id}</span></Detail></DetailGrid></Surface><Surface title="Capability membership">{item.permissions?.length ? <ul className="grid gap-2 lg:grid-cols-2">{item.permissions.map((permission) => <li key={permission.id} className="rounded border p-3"><Link className="font-mono text-sm text-primary hover:underline" to={ROUTES.PERMISSION_DETAIL(permission.id)}>{permission.code}</Link><p className="text-xs text-muted-foreground">{permission.name} · {permission.risk_level} risk</p></li>)}</ul> : item.permission_ids.length ? <p className="text-sm text-muted-foreground">{item.permission_ids.length} normalized capability IDs are attached. Open the editor for catalog details.</p> : <p className="text-sm text-muted-foreground">No capabilities are attached. This set grants no access.</p>}</Surface><Surface title="Recent grants">{grants.isLoading ? <PageSkeleton rows={2}/> : grants.error ? <GovernedError error={grants.error} retry={() => void grants.refetch()}/> : grants.data?.items.length ? <ul className="divide-y">{grants.data.items.map((grant) => <li key={grant.id} className="flex justify-between gap-3 py-3"><Link className="text-primary hover:underline" to={ROUTES.USER_PERMISSION_SET_DETAIL(grant.id)}>{grant.user_display ?? grant.user_id}</Link><StatusChip active={grant.is_active} label={grant.revoked_at ? "Revoked" : grant.is_active ? "Active" : "Expired"}/></li>)}</ul> : <p className="text-sm text-muted-foreground">No user has received this set.</p>}</Surface><AuditTimeline resourceType="permission_set" resourceId={item.id}/></main>; }
function PermissionSetForm({ initial }: {
    readonly initial?: PermissionSet;
}) { const navigate = useNavigate();
 const configuration = useSecurityConfiguration();
 const limits = configuration.data?.data.document.limits;
 const schema = z.object({ name: z.string().trim().min(limits?.name_min_length ?? 1).max(limits?.name_max_length ?? 1), description: z.string().max(limits?.description_max_length ?? 1), default_duration_days: z.union([z.number().int().min(limits?.permission_set_duration_min_days ?? 1).max(limits?.permission_set_duration_max_days ?? 1), z.null()]) });
 const [name, setName] = useState(initial?.name ?? "");
 const [description, setDescription] = useState(initial?.description ?? "");
 const [duration, setDuration] = useState(initial?.default_duration_days ? String(initial.default_duration_days) : "");
 const [active, setActive] = useState(initial?.is_active ?? true);
 const [selected, setSelected] = useState<readonly string[]>(initial?.permission_ids ?? []);
 const [search, setSearch] = useState("");
 const [error, setError] = useState("");
 const dirty = Boolean(name || description || selected.length) && (name !== initial?.name || description !== initial?.description || selected.join() !== initial?.permission_ids.join()); useUnsavedChanges(dirty);
 const lookupSize = limits?.lookup_page_size;
 const catalog = useQuery({ queryKey: QUERY_KEYS.permissions({ search, page_size: lookupSize, ordering: "module,resource,action" }), queryFn: () => securityService.permissions.list({ search: search || undefined, page_size: lookupSize, ordering: "module,resource,action" }), enabled: lookupSize !== undefined });
 const mutation = useMutation({ mutationFn: async () => { const validated = schema.parse({ name, description, default_duration_days: duration ? Number(duration) : null });
 const base = initial ? await securityService.permissionSets.update(initial.id, { ...validated, is_active: active }) : await securityService.permissionSets.create({ ...validated, is_active: active }); return securityService.permissionSets.replacePermissions(base.data.id, { permission_ids: selected }); }, onSuccess: (result) => navigate(ROUTES.PERMISSION_SET_DETAIL(result.data.id)), onError: () => setError("The governed change was rejected. Review field errors or reload after a conflict.") });
 const toggle = (id: string) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]); return <main className="space-y-6"><PageHeader title={initial ? `Edit ${initial.name}` : "Create permission set"} description="Search the immutable catalog and atomically replace normalized capability membership."/><form onSubmit={(event) => { event.preventDefault();
 const parsed = schema.safeParse({ name, description, default_duration_days: duration ? Number(duration) : null });
 if (!parsed.success) {
    setError(parsed.error.issues[0]?.message ?? "Review the form.");
    return;
} setError(""); mutation.mutate(); }} className="space-y-6"><Surface><div className="grid gap-5 sm:grid-cols-2"><Input id="set-name" label="Name" required value={name} onChange={(event) => setName(event.target.value)}/><Input id="set-duration" label="Default duration (days)" type="number" min={limits?.permission_set_duration_min_days} max={limits?.permission_set_duration_max_days} value={duration} onChange={(event) => setDuration(event.target.value)} placeholder="Explicit expiry if blank"/></div><Textarea id="set-description" aria-label="Description" className="mt-5" value={description} onChange={(event) => setDescription(event.target.value)}/>{initial ? <label className="mt-4 flex gap-2 text-sm"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)}/>Permission set is active</label> : null}</Surface><Surface title="Searchable capability matrix"><Input aria-label="Search capability matrix" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search capability name or description"/><p className="mt-3 text-sm text-muted-foreground" aria-live="polite">{selected.length} capabilities selected. Membership is applied only after the governed response succeeds.</p>{catalog.isLoading ? <PageSkeleton rows={4}/> : catalog.error ? <GovernedError error={catalog.error} retry={() => void catalog.refetch()}/> : <div className="mt-4 max-h-[520px] overflow-auto rounded border"><table className="w-full min-w-[680px] text-sm"><thead className="sticky top-0 bg-card text-left"><tr><th className="p-3">Include</th><th className="p-3">Capability</th><th className="p-3">Risk</th></tr></thead><tbody className="divide-y">{catalog.data?.items.map((permission) => <tr key={permission.id}><td className="p-3"><input aria-label={`Include ${permission.code}`} type="checkbox" checked={selected.includes(permission.id)} onChange={() => toggle(permission.id)}/></td><td className="p-3"><span className="font-mono">{permission.code}</span><small className="block text-muted-foreground">{permission.name}</small></td><td className="p-3">{permission.risk_level}</td></tr>)}</tbody></table></div>}</Surface>{error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}{mutation.error ? <MutationError error={mutation.error}/> : null}<div className="flex justify-end gap-3"><Button type="button" variant="outline" onClick={() => { if (!dirty || window.confirm("Discard unsaved permission-set changes?"))
    navigate(initial ? ROUTES.PERMISSION_SET_DETAIL(initial.id) : ROUTES.PERMISSION_SETS); }}>Cancel</Button><Button type="submit" disabled={mutation.isPending || catalog.isLoading}><Boxes className="mr-2 h-4 w-4"/>{mutation.isPending ? "Applying atomic change…" : "Save permission set"}</Button></div></form></main>; }
export function PermissionSetCreatePage() { return <PermissionSetForm />; }
export function PermissionSetEditPage() { const { id = "" } = useParams();
 const query = useQuery({ queryKey: QUERY_KEYS.permissionSet(id), queryFn: () => securityService.permissionSets.get(id), enabled: Boolean(id) });
 if (query.isLoading)
    return <PageSkeleton />;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>; return query.data ? <PermissionSetForm key={query.data.data.updated_at} initial={query.data.data}/> : <GovernedError error={new Error("Permission set not found.")}/>; }
