import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, Search } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PATHS, type InboxQuery, type NotificationStatus } from "../contracts";
import { NOTIFICATION_QUERY_KEYS, notificationService } from "../services/notification-service";
import { EmptyPanel, GovernedError, MutationError, PageShell, PageSkeleton, Pagination, PERMISSIONS, StatusPill, can, fieldClass, formatDate, transitionKey } from "../components/NotificationUI";

const storedFilters = (): InboxQuery => { try { return JSON.parse(sessionStorage.getItem("notifications.inbox.filters") ?? "{}") as InboxQuery; } catch { return {}; } };

// eslint-disable-next-line complexity -- coordinates filters, aggregate/list queries, keyboard navigation, and mutation state.
export function NotificationCenterPage() {
  const navigate = useNavigate(); const client = useQueryClient(); const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const [filters, setFilters] = useState<InboxQuery>(() => ({ page: 1, page_size: 25, ...storedFilters() }));
  const update = (patch: Partial<InboxQuery>) => { const next = { ...filters, page: 1, ...patch }; setFilters(next); sessionStorage.setItem("notifications.inbox.filters", JSON.stringify(next)); };
  const list = useQuery({ queryKey: NOTIFICATION_QUERY_KEYS.inbox(filters), queryFn: ({ signal }) => notificationService.inbox.list(filters, signal) });
  const unread = useQuery({ queryKey: NOTIFICATION_QUERY_KEYS.unread, queryFn: ({ signal }) => notificationService.inbox.unreadCount(signal) });
  const markAll = useMutation({ mutationFn: () => notificationService.inbox.markAllRead({ transition_key: transitionKey("mark-all-read") }), onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ["notifications", "inbox"] }), client.invalidateQueries({ queryKey: NOTIFICATION_QUERY_KEYS.unread })]); } });
  const capabilities = list.data?.capabilities;
  const items = list.data?.items ?? [];
  const description = unread.data ? `${unread.data.count.toLocaleString()} unread across your full inbox` : "A governed, tenant-safe record of alerts and actions.";
  const keyHandler = (index: number) => (event: React.KeyboardEvent) => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); const target = event.key === "ArrowDown" ? index + 1 : index - 1; itemRefs.current[target]?.focus(); } if (event.key === "Enter") navigate(PATHS.DETAIL(items[index]?.id ?? "")); };
  if (list.isLoading || unread.isLoading) return <PageSkeleton/>;
  if (list.error) return <PageShell title="Notification inbox" description={description}><GovernedError error={list.error} retry={() => void list.refetch()} subject="Inbox"/></PageShell>;
  return <PageShell title="Notification inbox" description={description} actions={can(capabilities, PERMISSIONS.inboxUpdate) && unread.data?.count ? <Button disabled={markAll.isPending} onClick={() => markAll.mutate()}><CheckCheck className="mr-2 h-4 w-4"/>{markAll.isPending ? "Marking…" : "Mark all read"}</Button> : undefined}>
    <MutationError error={markAll.error}/>
    <Card className="grid gap-3 p-4 md:grid-cols-[1fr_180px_180px]" aria-label="Inbox filters"><label className="relative"><span className="sr-only">Search notifications</span><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground"/><input className={`${fieldClass} pl-9`} placeholder="Search title or message" value={filters.search ?? ""} onChange={(event) => update({ search: event.target.value || undefined })}/></label><label><span className="sr-only">Status</span><select className={fieldClass} value={filters.status ?? ""} onChange={(event) => update({ status: (event.target.value || undefined) as NotificationStatus | undefined })}><option value="">All statuses</option><option value="unread">Unread</option><option value="read">Read</option><option value="archived">Archived</option></select></label><input aria-label="Category" className={fieldClass} placeholder="Category" value={filters.category ?? ""} onChange={(event) => update({ category: event.target.value || undefined })}/></Card>
    {!items.length ? <EmptyPanel title="No notifications found" description={filters.search || filters.status || filters.category ? "Change or clear the filters to broaden your inbox." : "You are all caught up. New notifications will appear here with their delivery evidence."}/> : <Card className="overflow-hidden"><ul className="divide-y" aria-label="Notifications">{items.map((item, index) => <li key={item.id} className={item.status === "unread" ? "bg-primary/5" : undefined}><Link ref={(node) => { itemRefs.current[index] = node; }} onKeyDown={keyHandler(index)} className="block p-4 transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" to={PATHS.DETAIL(item.id)}><div className="flex items-start justify-between gap-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold">{item.title}</h2><StatusPill value={item.status}/><StatusPill value={item.notification_type}/></div><p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{item.message}</p><p className="mt-2 text-xs text-muted-foreground">{item.category} · {formatDate(item.created_at)}</p></div>{item.status === "unread" ? <span className="mt-2 h-2.5 w-2.5 shrink-0 rounded-full bg-primary"><span className="sr-only">Unread</span></span> : null}</div></Link></li>)}</ul><Pagination page={list.data?.pagination.page ?? 1} totalPages={list.data?.pagination.total_pages ?? 1} onPage={(page) => setFilters((current) => ({ ...current, page }))}/></Card>}
    <p className="flex items-center gap-2 text-xs text-muted-foreground"><Bell className="h-4 w-4"/>Freshness: loaded on demand. This page does not claim live updates.</p>
  </PageShell>;
}
