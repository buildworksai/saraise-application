import type { DynamicResourceVersion } from "../contracts";
export function ResourceVersionTimeline({ versions }: { versions: readonly DynamicResourceVersion[] }) {
  if (versions.length === 0) return <p className="text-sm text-muted-foreground">No version history is available.</p>;
  return <ol className="relative space-y-4 border-l border-border pl-5">{versions.map((version) => <li key={version.id}><span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-primary" /><div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="font-medium">Version {version.version} · {version.operation}</h3><time className="text-xs text-muted-foreground">{new Date(version.changed_at).toLocaleString()}</time></div><p className="text-sm text-muted-foreground">{version.changed_fields.length > 0 ? `Changed: ${version.changed_fields.join(", ")}` : "Lifecycle transition"} · Correlation {version.correlation_id}</p></li>)}</ol>;
}
