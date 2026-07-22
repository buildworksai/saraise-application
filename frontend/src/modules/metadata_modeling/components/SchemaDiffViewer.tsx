import type { SchemaDiff } from "../contracts";
export function SchemaDiffViewer({ diff }: { diff: SchemaDiff | null }) {
  if (!diff) return <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">Save a candidate to calculate a server-authoritative diff.</p>;
  return <section aria-labelledby="schema-diff-title" className="rounded-lg border border-border bg-card p-4"><h2 id="schema-diff-title" className="font-semibold">Schema diff</h2><p className="mt-1 text-sm text-muted-foreground">Version {diff.from_version} → {diff.to_version} · {diff.compatibility.replace("_", " ")}</p><ul className="mt-3 space-y-2">{diff.changes.map((change) => <li key={`${change.kind}:${change.key}`} className="rounded bg-muted p-2 text-sm"><span className="font-medium capitalize">{change.kind}</span> <code>{change.key}</code></li>)}</ul></section>;
}
