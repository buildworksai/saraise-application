/* eslint-disable max-lines-per-function, complexity */
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Plus, ShieldCheck } from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { AuditTimeline, ConfirmButton, Detail, DetailGrid, EmptyPanel, GovernedError, MutationError, PageHeader, PageSkeleton, Pagination, StatusChip, Surface, formatDate, useUnsavedChanges } from "../components/SecurityUI";
import { QUERY_KEYS, ROUTES, type DeletionReasonInput, type MfaRequired, type ProfileType, type SecurityConfigurationDocument, type SecurityProfile } from "../contracts";
import { securityService } from "../services/security-service";
import { useSecurityConfiguration } from "../hooks/use-security-configuration";
function change(params: URLSearchParams, set: (next: URLSearchParams) => void, key: string, value: string): void { const next = new URLSearchParams(params);
 if (value)
    next.set(key, value);
else
    next.delete(key);
 if (key !== "page")
    next.delete("page"); set(next); }
function tokens(value: string): readonly string[] { return value.split(",").map((item) => item.trim()).filter(Boolean); }
function RestrictionPreview({ profile }: {
    readonly profile: Pick<SecurityProfile, "mfa_required" | "session_timeout_minutes" | "absolute_session_timeout_hours" | "max_concurrent_sessions" | "download_allowed" | "print_allowed" | "copy_paste_allowed" | "mobile_access_allowed" | "allowed_countries" | "blocked_countries" | "ip_whitelist" | "ip_blacklist">;
}) { const restrictions = [`MFA: ${profile.mfa_required.replaceAll("_", " ")}`, `Idle timeout: ${profile.session_timeout_minutes} minutes`, `Absolute timeout: ${profile.absolute_session_timeout_hours} hours`, `Maximum sessions: ${profile.max_concurrent_sessions}`, profile.download_allowed ? "Downloads allowed" : "Downloads blocked", profile.print_allowed ? "Printing allowed" : "Printing blocked", profile.copy_paste_allowed ? "Copy/paste allowed" : "Copy/paste blocked", profile.mobile_access_allowed ? "Mobile allowed" : "Mobile blocked", profile.allowed_countries.length ? `Countries allowed: ${profile.allowed_countries.join(", ")}` : "No country allowlist", profile.blocked_countries.length ? `Countries blocked: ${profile.blocked_countries.join(", ")}` : "No country blocklist", profile.ip_whitelist.length ? `${profile.ip_whitelist.length} allowed networks` : "No network allowlist", profile.ip_blacklist.length ? `${profile.ip_blacklist.length} blocked networks` : "No network blocklist"]; return <div className="grid gap-2 sm:grid-cols-2">{restrictions.map((item) => <div key={item} className="flex gap-2 rounded border p-3 text-sm"><ShieldCheck className="h-4 w-4 shrink-0 text-primary"/>{item}</div>)}</div>; }
export function SecurityProfilesPage() { const navigate = useNavigate();
 const configuration = useSecurityConfiguration();
 const [params, setParams] = useSearchParams();
 const search = params.get("search") ?? "";
 const type = params.get("profile_type") ?? "";
 const mfa = params.get("mfa_required") ?? "";
 const active = params.get("is_active") ?? "";
 const page = Math.max(1, Number(params.get("page") ?? 1));
 const pageSize = configuration.data?.data.document.limits.list_page_size;
 const query = useQuery({ queryKey: QUERY_KEYS.profiles({ search, profile_type: type ? type as ProfileType : undefined, mfa_required: mfa ? mfa as MfaRequired : undefined, is_active: active ? active === "true" : undefined, page, page_size: pageSize }), queryFn: () => securityService.securityProfiles.list({ search: search || undefined, profile_type: type ? type as ProfileType : undefined, mfa_required: mfa ? mfa as MfaRequired : undefined, is_active: active ? active === "true" : undefined, page, page_size: pageSize }), enabled: pageSize !== undefined });
 const reset = () => setParams(new URLSearchParams());
 const filtered = Boolean(search || type || mfa || active);
 if (query.isLoading)
    return <PageSkeleton />;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
 if (!query.data)
    return <GovernedError error={new Error("No governed security-profile response was received.")}/>; return <main className="space-y-6"><PageHeader title="Security profiles" description="Combine contextual restrictions deterministically and preview the most restrictive effective posture." actions={<Button onClick={() => navigate(ROUTES.SECURITY_PROFILE_CREATE)}><Plus className="mr-2 h-4 w-4"/>Create profile</Button>}/><section aria-label="Profile filters" className="grid gap-3 rounded-xl border bg-card p-4 lg:grid-cols-[1fr_180px_190px_150px_auto]"><Input aria-label="Search security profiles" value={search} onChange={(event) => change(params, setParams, "search", event.target.value)} placeholder="Search name or description"/><select aria-label="Filter profile type" className="rounded-md border bg-background px-3" value={type} onChange={(event) => change(params, setParams, "profile_type", event.target.value)}><option value="">All profile types</option>{["standard", "privileged", "restricted", "high_security"].map((value) => <option key={value}>{value}</option>)}</select><select aria-label="Filter MFA requirement" className="rounded-md border bg-background px-3" value={mfa} onChange={(event) => change(params, setParams, "mfa_required", event.target.value)}><option value="">Any MFA posture</option>{["always", "conditional", "sensitive_actions", "never"].map((value) => <option key={value}>{value}</option>)}</select><select aria-label="Filter active profiles" className="rounded-md border bg-background px-3" value={active} onChange={(event) => change(params, setParams, "is_active", event.target.value)}><option value="">Any status</option><option value="true">Active</option><option value="false">Inactive</option></select><Button variant="outline" onClick={reset}>Reset</Button></section>{query.data.items.length === 0 ? <EmptyPanel filtered={filtered} noun="security profiles" onReset={reset} create={() => navigate(ROUTES.SECURITY_PROFILE_CREATE)}/> : <section className="overflow-hidden rounded-xl border bg-card"><div className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">{query.data.items.map((item) => <Link key={item.id} to={ROUTES.SECURITY_PROFILE_DETAIL(item.id)} className="rounded-lg border p-4 transition hover:border-primary focus-visible:outline-none focus-visible:ring-2"><div className="flex justify-between gap-3"><h2 className="font-semibold">{item.name}</h2><StatusChip active={item.is_active}/></div><p className="mt-2 text-sm text-muted-foreground">{item.profile_type.replaceAll("_", " ")} · MFA {item.mfa_required.replaceAll("_", " ")}</p><p className="mt-3 text-xs">{item.session_timeout_minutes}m idle · {item.max_concurrent_sessions} sessions · {item.assignment_count ?? 0} assignments</p></Link>)}</div><Pagination value={query.data.pagination} onPage={(next) => change(params, setParams, "page", String(next))}/></section>}</main>; }
export function SecurityProfileDetailPage() { const { id = "" } = useParams();
 const navigate = useNavigate();
 const query = useQuery({ queryKey: QUERY_KEYS.profile(id), queryFn: () => securityService.securityProfiles.get(id), enabled: Boolean(id) });
 const remove = useMutation({ mutationFn: (input: DeletionReasonInput) => securityService.securityProfiles.delete(id, input), onSuccess: () => navigate(ROUTES.SECURITY_PROFILES) });
 if (query.isLoading)
    return <PageSkeleton />;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
 if (!query.data)
    return <GovernedError error={new Error("Security profile not found.")}/>;
 const item = query.data.data; return <main className="space-y-6"><PageHeader title={item.name} description={item.description || "Contextual security restrictions."} actions={<><StatusChip active={item.is_active}/><Button variant="outline" onClick={() => navigate(ROUTES.PROFILE_ASSIGNMENTS)}>View assignments</Button><Button variant="outline" onClick={() => navigate(ROUTES.SECURITY_PROFILE_EDIT(item.id))}>Edit profile</Button>
<ConfirmButton label="Delete profile" question="Soft-delete this profile? Active assignments will prevent removal." pending={remove.isPending}
 onConfirm={(input) => remove.mutate(input)}/>
</>}/>{remove.error ? <MutationError error={remove.error}/> : null}<Surface><DetailGrid><Detail label="Profile type">{item.profile_type}</Detail><Detail label="MFA requirement">{item.mfa_required}</Detail><Detail label="MFA methods">{item.allowed_mfa_methods.join(", ") || "Owning authentication defaults"}</Detail><Detail label="Created">{formatDate(item.created_at)}</Detail><Detail label="Updated">{formatDate(item.updated_at)}</Detail><Detail label="Identifier"><span className="font-mono text-xs">{item.id}</span></Detail></DetailGrid></Surface><Surface title="Effective restriction preview"><RestrictionPreview profile={item}/></Surface><Surface title="Enforcement ownership"><div className="rounded-lg border border-accent bg-accent p-4 text-sm text-accent-foreground"><strong>Authentication-owned controls:</strong> MFA enrollment, password policy, and session lifecycle are advisory here and are enforced only when the owning authentication service reports support. Network, geography, and data-handling decisions are evaluated by the access-policy pipeline.</div></Surface><Surface title="Time restrictions"><p className="text-sm">Timezone {item.time_restrictions.timezone || "not configured"} · weekdays {item.time_restrictions.weekdays.join(", ") || "all"}</p>{item.time_restrictions.windows.length ? <ul className="mt-3">{item.time_restrictions.windows.map((window) => <li key={`${window.start}-${window.end}`}>{window.start}–{window.end}</li>)}</ul> : <p className="mt-2 text-sm text-muted-foreground">No daily window restriction.</p>}</Surface><AuditTimeline resourceType="security_profile" resourceId={item.id}/></main>; }
interface ToggleProps {
    readonly label: string;
    readonly checked: boolean;
    readonly onChange: (checked: boolean) => void;
}
function Toggle({ label, checked, onChange }: ToggleProps) { return <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)}/>{label}</label>; }
function ProfileForm({ initial }: {
    readonly initial?: SecurityProfile;
}) { const configuration = useSecurityConfiguration();
 if (configuration.isLoading)
    return <PageSkeleton />;
 if (configuration.error)
    return <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/>;
 if (!configuration.data)
    return <GovernedError error={new Error("Security configuration is required to edit profiles.")}/>; return <ConfiguredProfileForm initial={initial} document={configuration.data.data.document}/>; }
function ConfiguredProfileForm({ initial, document }: {
    readonly initial?: SecurityProfile;
    readonly document: SecurityConfigurationDocument;
}) {
    const navigate = useNavigate();
    const defaults = document.defaults.security_profile;
    const limits = document.limits;
    const schema = z.object({ name: z.string().trim().min(limits.name_min_length).max(limits.name_max_length), description: z.string().max(limits.description_max_length), session: z.number().int().min(limits.profile_idle_timeout_min_minutes).max(limits.profile_idle_timeout_max_minutes), absolute: z.number().int().min(limits.profile_absolute_timeout_min_hours).max(limits.profile_absolute_timeout_max_hours), concurrent: z.number().int().min(limits.profile_concurrent_sessions_min).max(limits.profile_concurrent_sessions_max) });
    const [name, setName] = useState(initial?.name ?? "");
    const [description, setDescription] = useState(initial?.description ?? "");
    const [type, setType] = useState<ProfileType>(initial?.profile_type ?? defaults.profile_type);
    const [mfa, setMfa] = useState<MfaRequired>(initial?.mfa_required ?? defaults.mfa_required);
    const [methods, setMethods] = useState(initial?.allowed_mfa_methods.join(", ") ?? defaults.allowed_mfa_methods.join(", "));
    const [allowCountries, setAllowCountries] = useState(initial?.allowed_countries.join(", ") ?? "");
    const [blockCountries, setBlockCountries] = useState(initial?.blocked_countries.join(", ") ?? "");
    const [allowIps, setAllowIps] = useState(initial?.ip_whitelist.join(", ") ?? "");
    const [blockIps, setBlockIps] = useState(initial?.ip_blacklist.join(", ") ?? "");
    const [timezone, setTimezone] = useState(initial?.time_restrictions.timezone ?? defaults.time_restrictions.timezone);
    const [weekdays, setWeekdays] = useState(initial?.time_restrictions.weekdays.join(",") ?? defaults.time_restrictions.weekdays.join(","));
    const [windowStart, setWindowStart] = useState(initial?.time_restrictions.windows[0]?.start ?? defaults.time_restrictions.windows[0]?.start ?? "");
    const [windowEnd, setWindowEnd] = useState(initial?.time_restrictions.windows[0]?.end ?? defaults.time_restrictions.windows[0]?.end ?? "");
    const [session, setSession] = useState(String(initial?.session_timeout_minutes ?? defaults.session_timeout_minutes));
    const [absolute, setAbsolute] = useState(String(initial?.absolute_session_timeout_hours ?? defaults.absolute_session_timeout_hours));
    const [concurrent, setConcurrent] = useState(String(initial?.max_concurrent_sessions ?? defaults.max_concurrent_sessions));
    const [download, setDownload] = useState(initial?.download_allowed ?? defaults.download_allowed);
    const [print, setPrint] = useState(initial?.print_allowed ?? defaults.print_allowed);
    const [copy, setCopy] = useState(initial?.copy_paste_allowed ?? defaults.copy_paste_allowed);
    const [mobile, setMobile] = useState(initial?.mobile_access_allowed ?? defaults.mobile_access_allowed);
    const [loginNotification, setLoginNotification] = useState(initial?.login_notification ?? defaults.login_notification);
    const [accessNotification, setAccessNotification] = useState(initial?.access_notification ?? defaults.access_notification);
    const [active, setActive] = useState(initial?.is_active ?? true);
    const [error, setError] = useState("");
    const dirty = Boolean(name || description);
    useUnsavedChanges(dirty);
    const preview = { mfa_required: mfa, session_timeout_minutes: Number(session), absolute_session_timeout_hours: Number(absolute), max_concurrent_sessions: Number(concurrent), download_allowed: download, print_allowed: print, copy_paste_allowed: copy, mobile_access_allowed: mobile, allowed_countries: tokens(allowCountries), blocked_countries: tokens(blockCountries), ip_whitelist: tokens(allowIps), ip_blacklist: tokens(blockIps) };
    const mutation = useMutation({ mutationFn: () => { const input = { name, description, profile_type: type, mfa_required: mfa, allowed_mfa_methods: tokens(methods), allowed_countries: tokens(allowCountries).map((item) => item.toUpperCase()), blocked_countries: tokens(blockCountries).map((item) => item.toUpperCase()), ip_whitelist: tokens(allowIps), ip_blacklist: tokens(blockIps), time_restrictions: { timezone, weekdays: tokens(weekdays).map(Number), windows: windowStart && windowEnd ? [{ start: windowStart, end: windowEnd }] : [] }, password_policy: {}, session_timeout_minutes: Number(session), absolute_session_timeout_hours: Number(absolute), max_concurrent_sessions: Number(concurrent), download_allowed: download, print_allowed: print, copy_paste_allowed: copy, mobile_access_allowed: mobile, login_notification: loginNotification, access_notification: accessNotification, is_active: active }; return initial ? securityService.securityProfiles.update(initial.id, input) : securityService.securityProfiles.create(input); }, onSuccess: (result) => navigate(ROUTES.SECURITY_PROFILE_DETAIL(result.data.id)) });
    function submit(event: React.FormEvent): void { event.preventDefault();
 const parsed = schema.safeParse({ name, description, session: Number(session), absolute: Number(absolute), concurrent: Number(concurrent) });
 const overlapCountries = tokens(allowCountries).some((item) => tokens(blockCountries).includes(item));
 const overlapIps = tokens(allowIps).some((item) => tokens(blockIps).includes(item));
 if (!parsed.success || overlapCountries || overlapIps || (windowStart && windowEnd && windowEnd <= windowStart)) {
        setError(overlapCountries ? "Allowed and blocked countries cannot overlap." : overlapIps ? "Allowed and blocked networks cannot overlap." : windowStart && windowEnd && windowEnd <= windowStart ? "The time window end must be after its start." : parsed.error?.issues[0]?.message ?? "Review the profile.");
        return;
    } setError(""); mutation.mutate(); }
    return <main className="space-y-6"><PageHeader title={initial ? "Edit security profile" : "Create security profile"} description="Preview the combined posture and distinguish runtime-enforced from authentication-owned settings."/><form className="space-y-6" onSubmit={submit}><div className="grid gap-6 xl:grid-cols-[1fr_420px]"><div className="space-y-6"><Surface><div className="grid gap-5 sm:grid-cols-2"><Input id="profile-name" label="Name" required value={name} onChange={(event) => setName(event.target.value)}/><label className="text-sm font-medium" htmlFor="profile-type">Profile type<select id="profile-type" className="mt-1 block w-full rounded-md border bg-background p-2" value={type} onChange={(event) => setType(event.target.value as ProfileType)}>{["standard", "privileged", "restricted", "high_security"].map((value) => <option key={value}>{value}</option>)}</select></label></div><Textarea id="profile-description" aria-label="Description" className="mt-5" value={description} onChange={(event) => setDescription(event.target.value)}/></Surface><Surface title="Context restrictions"><div className="grid gap-5 sm:grid-cols-2"><Input id="allowed-countries" label="Allowed countries (ISO codes)" value={allowCountries} onChange={(event) => setAllowCountries(event.target.value)}/><Input id="blocked-countries" label="Blocked countries" value={blockCountries} onChange={(event) => setBlockCountries(event.target.value)}/><Input id="allowed-networks" label="Allowed CIDR networks" value={allowIps} onChange={(event) => setAllowIps(event.target.value)}/><Input id="blocked-networks" label="Blocked CIDR networks" value={blockIps} onChange={(event) => setBlockIps(event.target.value)}/><Input id="profile-timezone" label="Timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)}/><Input id="profile-weekdays" label="Weekdays (1–7)" value={weekdays} onChange={(event) => setWeekdays(event.target.value)}/><Input id="window-start" label="Window start" type="time" value={windowStart} onChange={(event) => setWindowStart(event.target.value)}/><Input id="window-end" label="Window end" type="time" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)}/></div></Surface><Surface title="Authentication-owned policy"><div className="grid gap-5 sm:grid-cols-2"><label className="text-sm font-medium" htmlFor="profile-mfa">MFA requirement<select id="profile-mfa" className="mt-1 block w-full rounded-md border bg-background p-2" value={mfa} onChange={(event) => setMfa(event.target.value as MfaRequired)}>{["always", "conditional", "sensitive_actions", "never"].map((value) => <option key={value}>{value}</option>)}</select></label><Input id="mfa-methods" label="Allowed MFA methods" value={methods} onChange={(event) => setMethods(event.target.value)}/><Input id="session-timeout" label="Idle timeout minutes" type="number" min={limits.profile_idle_timeout_min_minutes} max={limits.profile_idle_timeout_max_minutes} value={session} onChange={(event) => setSession(event.target.value)}/><Input id="absolute-timeout" label="Absolute timeout hours" type="number" min={limits.profile_absolute_timeout_min_hours} max={limits.profile_absolute_timeout_max_hours} value={absolute} onChange={(event) => setAbsolute(event.target.value)}/><Input id="concurrent-sessions" label="Maximum sessions" type="number" min={limits.profile_concurrent_sessions_min} max={limits.profile_concurrent_sessions_max} value={concurrent} onChange={(event) => setConcurrent(event.target.value)}/></div><p className="mt-4 text-xs text-muted-foreground">Advisory until the owning authentication service confirms enforcement.</p></Surface><Surface title="Data handling and notifications"><div className="grid gap-3 sm:grid-cols-2"><Toggle label="Downloads allowed" checked={download} onChange={setDownload}/><Toggle label="Printing allowed" checked={print} onChange={setPrint}/><Toggle label="Copy/paste allowed" checked={copy} onChange={setCopy}/><Toggle label="Mobile access allowed" checked={mobile} onChange={setMobile}/><Toggle label="Login notifications" checked={loginNotification} onChange={setLoginNotification}/><Toggle label="Access notifications" checked={accessNotification} onChange={setAccessNotification}/><Toggle label="Profile active" checked={active} onChange={setActive}/></div></Surface></div><Surface title="Effective combined preview"><RestrictionPreview profile={preview}/><p className="mt-4 text-xs text-muted-foreground">Conflicts resolve by highest precedence and the most restrictive setting.</p></Surface></div>{error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}{mutation.error ? <MutationError error={mutation.error}/> : null}<div className="flex justify-end gap-3"><Button type="button" variant="outline" onClick={() => { if (!dirty || window.confirm("Discard unsaved profile changes?"))
        navigate(initial ? ROUTES.SECURITY_PROFILE_DETAIL(initial.id) : ROUTES.SECURITY_PROFILES); }}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Validating and saving…" : "Save security profile"}</Button></div></form></main>;
}
export function SecurityProfileCreatePage() { return <ProfileForm />; }
export function SecurityProfileEditPage() { const { id = "" } = useParams();
 const query = useQuery({ queryKey: QUERY_KEYS.profile(id), queryFn: () => securityService.securityProfiles.get(id), enabled: Boolean(id) });
 if (query.isLoading)
    return <PageSkeleton />;
 if (query.error)
    return <GovernedError error={query.error} retry={() => void query.refetch()}/>; return query.data ? <ProfileForm key={query.data.data.updated_at} initial={query.data.data}/> : <GovernedError error={new Error("Security profile not found.")}/>; }
