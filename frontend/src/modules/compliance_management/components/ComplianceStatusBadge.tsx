export function ComplianceStatusBadge({ status }: { readonly status: string }) {
  return <span className="inline-flex rounded-full border bg-muted px-2.5 py-1 text-xs font-semibold capitalize text-foreground">{status.replaceAll('_', ' ')}</span>;
}
