import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { SchemaValidationReport } from "../contracts";
export function SchemaImpactPanel({ report }: { report: SchemaValidationReport | null }) {
  if (!report) return null;
  const Icon = report.valid ? CheckCircle2 : AlertTriangle;
  return <section aria-live="polite" className="rounded-lg border border-border bg-card p-4"><div className="flex items-center gap-2"><Icon className={report.valid ? "text-primary" : "text-destructive"} /><h2 className="font-semibold">Publication impact</h2></div><p className="mt-2 text-sm text-muted-foreground">{report.resource_count} records scanned; {report.incompatible_resource_count} incompatible. Compatibility: {report.compatibility.replace("_", " ")}.</p>{report.errors.length > 0 && <ul className="mt-3 list-disc pl-5 text-sm text-destructive">{report.errors.map((error, index) => <li key={`${error.code}:${index}`}>{error.message}</li>)}</ul>}</section>;
}
