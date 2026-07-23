/* eslint-disable max-lines-per-function, complexity */
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { AuditTimeline, ConfirmButton, Detail, DetailGrid, EmptyPanel, GovernedError, MutationError, PageHeader, PageSkeleton, Pagination, StatusChip, Surface, formatDate, useUnsavedChanges } from "../components/SecurityUI";
import { QUERY_KEYS, ROUTES, type DeletionReasonInput, type SecurityProfileAssignment } from "../contracts";
import { securityService } from "../services/security-service";
import { useSecurityConfiguration } from "../hooks/use-security-configuration";
function change(params: URLSearchParams, set: (next: URLSearchParams) => void, key: string, value: string): void { const next = new URLSearchParams(params);
 if (value)
    next.set(key, value);
else
    next.delete(key);
 if (key !== "page")
    next.delete("page"); set(next); }
export function ProfileAssignmentsPage() { const navigate = useNavigate();
 const configuration = useSecurityConfiguration();
 const [params, setParams] = useSearchParams();
 const profile = params.get("profile_id") ?? "";
 const user = params.get("user_id") ?? "";
 const role = params.get("role_id") ?? "";
 const revoked = params.get("revoked") ?? "";
 const page = Math.max(1, Number(params.get("page") ?? 1));
 const pageSize = configuration.data?.data.document.limits.list_page_size;
 const query = useQuery({ queryKey: QUERY_KEYS.profileAssignments({ profile_id: profile || undefined, user_id: user || undefined, role_id: role || undefined, revoked: revoked ? revoked === "true" : undefined, page, page_size: pageSize }), queryFn: () => securityService.profileAssignments.list({ profile_id: profile || undefined, user_id: user || undefined, role_id: role || undefined, revoked: revoked ? revoked === "true" : undefined, page, page_size: pageSize }), enabled: pageSize !== undefined });
 const reset = () => setParams(new URLSearchParams());
 const filtered = Boolean(profile || user || role || revoked);
 if (query.isLoading)
    return <PageSkeleton />;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
 if (!query.data)
    return <GovernedError error={new Error("No profile-assignment response was received.")}/>; return <main className="space-y-6"><PageHeader title="Profile assignments" description="Apply contextual profiles to exactly one user or role with explicit precedence and validity." actions={<><Button variant="outline" onClick={() => navigate(ROUTES.ASSIGNMENTS)}>Role assignments</Button><Button onClick={() => navigate(ROUTES.PROFILE_ASSIGNMENT_CREATE)}><Plus className="mr-2 h-4 w-4"/>Assign profile</Button></>}/><section aria-label="Profile assignment filters" className="grid gap-3 rounded-xl border bg-card p-4 lg:grid-cols-[1fr_1fr_1fr_160px_auto]"><Input aria-label="Filter profile UUID" value={profile} onChange={(event) => change(params, setParams, "profile_id", event.target.value)} placeholder="Profile UUID"/><Input aria-label="Filter user UUID" value={user} onChange={(event) => change(params, setParams, "user_id", event.target.value)} placeholder="User UUID"/><Input aria-label="Filter role UUID" value={role} onChange={(event) => change(params, setParams, "role_id", event.target.value)} placeholder="Role UUID"/><select aria-label="Filter revoked profile assignments" className="rounded-md border bg-background px-3" value={revoked} onChange={(event) => change(params, setParams, "revoked", event.target.value)}><option value="">Any state</option><option value="false">Not revoked</option><option value="true">Revoked</option></select><Button variant="outline" onClick={reset}>Reset</Button></section>{query.data.items.length === 0 ? <EmptyPanel filtered={filtered} noun="profile assignments" onReset={reset} create={() => navigate(ROUTES.PROFILE_ASSIGNMENT_CREATE)}/> : <section className="overflow-hidden rounded-xl border bg-card"><div className="divide-y">{query.data.items.map((item) => <Link key={item.id} to={ROUTES.PROFILE_ASSIGNMENT_DETAIL(item.id)} className="grid gap-3 p-4 hover:bg-muted/30 md:grid-cols-[1fr_1fr_120px_140px]"><span>{item.security_profile_name ?? item.security_profile_id}</span><span>{item.user_display ?? item.user_id ?? item.role_name ?? item.role_id}</span><span>Priority {item.precedence}</span><StatusChip active={item.is_active} label={item.revoked_at ? "Revoked" : item.is_active ? "Active" : "Scheduled / expired"}/></Link>)}</div><Pagination value={query.data.pagination} onPage={(next) => change(params, setParams, "page", String(next))}/></section>}</main>; }
export function ProfileAssignmentDetailPage() { const { id = "" } = useParams();
 const navigate = useNavigate();
 const query = useQuery({ queryKey: QUERY_KEYS.profileAssignment(id), queryFn: () => securityService.profileAssignments.get(id), enabled: Boolean(id) });
 const revoke = useMutation({ mutationFn: (input: DeletionReasonInput) => securityService.profileAssignments.revoke(id, input), onSuccess: () => void query.refetch() });
 if (query.isLoading)
    return <PageSkeleton />;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
 if (!query.data)
    return <GovernedError error={new Error("Profile assignment not found.")}/>;
 const item = query.data.data; return <main className="space-y-6"><PageHeader title={item.security_profile_name ?? "Profile assignment"} description={`Applied to ${item.user_display ?? item.user_id ?? item.role_name ?? item.role_id}`} actions={<><StatusChip active={item.is_active} label={item.revoked_at ? "Revoked" : item.is_active ? "Active" : "Scheduled / expired"}/>{!item.revoked_at ? <><Button variant="outline" onClick={() => navigate(ROUTES.PROFILE_ASSIGNMENT_EDIT(item.id))}>Edit assignment</Button>
<ConfirmButton label="Revoke" question="Revoke this profile assignment? Evidence will remain." pending={revoke.isPending}
 onConfirm={(input) => revoke.mutate(input)}/>
</> : null}</>}/>{revoke.error ? <MutationError error={revoke.error}/> : null}<Surface><DetailGrid><Detail label="Profile"><Link className="text-primary hover:underline" to={ROUTES.SECURITY_PROFILE_DETAIL(item.security_profile_id)}>{item.security_profile_name ?? item.security_profile_id}</Link></Detail><Detail label="Subject">{item.user_id ? `User ${item.user_display ?? item.user_id}` : `Role ${item.role_name ?? item.role_id}`}</Detail><Detail label="Precedence">{item.precedence}</Detail><Detail label="Valid from">{formatDate(item.valid_from)}</Detail><Detail label="Valid until">{formatDate(item.valid_until)}</Detail><Detail label="Assigned by"><span className="font-mono text-xs">{item.assigned_by}</span></Detail><Detail label="Revoked">{formatDate(item.revoked_at)}</Detail><Detail label="Identifier"><span className="font-mono text-xs">{item.id}</span></Detail></DetailGrid><h2 className="mt-6 font-medium">Justification</h2><p className="mt-2 text-sm text-muted-foreground">{item.reason}</p></Surface><AuditTimeline resourceType="security_profile_assignment" resourceId={item.id}/></main>; }
function AssignmentForm({ initial }: {
    readonly initial?: SecurityProfileAssignment;
}) { const navigate = useNavigate();
 const configuration = useSecurityConfiguration();
 const limits = configuration.data?.data.document.limits;
 const defaults = configuration.data?.data.document.defaults;
 const schema = z.object({ profile: z.string().uuid(), subject: z.string().uuid(), reason: z.string().trim().min(1).max(limits?.required_text_max_length ?? 1), precedence: z.number().int().min(limits?.row_priority_min ?? 0).max(limits?.row_priority_max ?? 0), validFrom: z.string().min(1), validUntil: z.string() });
 const [profile, setProfile] = useState(initial?.security_profile_id ?? "");
 const [subjectType, setSubjectType] = useState<"user" | "role">(initial?.role_id ? "role" : "user");
 const [subject, setSubject] = useState(initial?.user_id ?? initial?.role_id ?? "");
 const [precedence, setPrecedence] = useState(String(initial?.precedence ?? defaults?.profile_assignment_precedence ?? ""));
 const [validFrom, setValidFrom] = useState((initial?.valid_from ?? new Date().toISOString()).slice(0, 16));
 const [validUntil, setValidUntil] = useState(initial?.valid_until?.slice(0, 16) ?? "");
 const [reason, setReason] = useState(initial?.reason ?? "");
 const [error, setError] = useState("");
 const dirty = Boolean(profile || subject || reason); useUnsavedChanges(dirty);
 const lookupSize = limits?.lookup_page_size;
 const profiles = useQuery({ queryKey: QUERY_KEYS.profiles({ is_active: true, page_size: lookupSize }), queryFn: () => securityService.securityProfiles.list({ is_active: true, page_size: lookupSize }), enabled: lookupSize !== undefined });
 const roles = useQuery({ queryKey: QUERY_KEYS.roles({ is_active: true, page_size: lookupSize }), queryFn: () => securityService.roles.list({ is_active: true, page_size: lookupSize }), enabled: subjectType === "role" && lookupSize !== undefined });
 const mutation = useMutation({ mutationFn: () => initial ? securityService.profileAssignments.update(initial.id, { precedence: Number(precedence), valid_from: new Date(validFrom).toISOString(), valid_until: validUntil ? new Date(validUntil).toISOString() : null, reason }) : securityService.profileAssignments.create({ security_profile_id: profile, user_id: subjectType === "user" ? subject : null, role_id: subjectType === "role" ? subject : null, precedence: Number(precedence), valid_from: new Date(validFrom).toISOString(), valid_until: validUntil ? new Date(validUntil).toISOString() : null, reason }), onSuccess: (result) => navigate(ROUTES.PROFILE_ASSIGNMENT_DETAIL(result.data.id)) }); return <main className="space-y-6"><PageHeader title={initial ? "Edit profile assignment" : "Assign security profile"} description="Exactly one user or role is required; profile conflicts resolve by precedence and restriction."/><form className="space-y-6" onSubmit={(event) => { event.preventDefault();
 const parsed = schema.safeParse({ profile, subject, reason, precedence: Number(precedence), validFrom, validUntil });
 if (!parsed.success || (validUntil && validUntil <= validFrom)) {
    setError(validUntil && validUntil <= validFrom ? "Validity end must be after start." : parsed.error?.issues[0]?.message ?? "Review the assignment.");
    return;
} setError(""); mutation.mutate(); }}><Surface><div className="grid gap-5 sm:grid-cols-2"><label className="text-sm font-medium" htmlFor="profile-assignment-profile">Security profile<select id="profile-assignment-profile" required disabled={Boolean(initial) || profiles.isLoading} className="mt-1 block w-full rounded-md border bg-background p-2" value={profile} onChange={(event) => setProfile(event.target.value)}><option value="">Select profile</option>{profiles.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="text-sm font-medium" htmlFor="profile-subject-type">Subject type<select id="profile-subject-type" disabled={Boolean(initial)} className="mt-1 block w-full rounded-md border bg-background p-2" value={subjectType} onChange={(event) => { setSubjectType(event.target.value as "user" | "role"); setSubject(""); }}><option value="user">User</option><option value="role">Role</option></select></label>{subjectType === "role" ? <label className="text-sm font-medium" htmlFor="profile-role">Role<select id="profile-role" required disabled={Boolean(initial) || roles.isLoading} className="mt-1 block w-full rounded-md border bg-background p-2" value={subject} onChange={(event) => setSubject(event.target.value)}><option value="">Select role</option>{roles.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : <Input id="profile-user" label="User UUID" disabled={Boolean(initial)} required value={subject} onChange={(event) => setSubject(event.target.value)}/>}<Input id="profile-precedence" label="Precedence" type="number" value={precedence} onChange={(event) => setPrecedence(event.target.value)}/><Input id="profile-valid-from" label="Valid from" type="datetime-local" required value={validFrom} onChange={(event) => setValidFrom(event.target.value)}/><Input id="profile-valid-until" label="Valid until" type="datetime-local" value={validUntil} onChange={(event) => setValidUntil(event.target.value)}/></div><Textarea id="profile-assignment-reason" aria-label="Assignment reason" className="mt-5" required value={reason} onChange={(event) => setReason(event.target.value)}/>{error ? <p role="alert" className="mt-2 text-sm text-destructive">{error}</p> : null}</Surface>{profiles.error ? <GovernedError error={profiles.error} retry={() => void profiles.refetch()}/> : null}{roles.error ? <GovernedError error={roles.error} retry={() => void roles.refetch()}/> : null}{mutation.error ? <MutationError error={mutation.error}/> : null}<div className="flex justify-end gap-3"><Button type="button" variant="outline" onClick={() => { if (!dirty || window.confirm("Discard unsaved profile-assignment changes?"))
    navigate(initial ? ROUTES.PROFILE_ASSIGNMENT_DETAIL(initial.id) : ROUTES.PROFILE_ASSIGNMENTS); }}>Cancel</Button><Button type="submit" disabled={mutation.isPending || profiles.isLoading}>{mutation.isPending ? "Saving…" : "Save assignment"}</Button></div></form></main>; }
export function ProfileAssignmentCreatePage() { return <AssignmentForm />; }
export function ProfileAssignmentEditPage() { const { id = "" } = useParams();
 const query = useQuery({ queryKey: QUERY_KEYS.profileAssignment(id), queryFn: () => securityService.profileAssignments.get(id), enabled: Boolean(id) });
 if (query.isLoading)
    return <PageSkeleton />;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>; return query.data ? <AssignmentForm key={query.data.data.updated_at} initial={query.data.data}/> : <GovernedError error={new Error("Profile assignment not found.")}/>; }
