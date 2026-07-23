import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { useParams } from "react-router-dom";
import { GovernedError, PageHeader, PageSkeleton, StatusChip, Surface } from "../components/CustomizationUI";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function FieldImpactPage() { const { id = "" } = useParams(); return <ImpactView title="Field dependency impact" queryKey="field" load={() => service.getFieldImpact(id)}/>; }
export function FormImpactPage() { const { id = "" } = useParams(); return <ImpactView title="Form dependency impact" queryKey="form" load={() => service.getFormImpact(id)}/>; }
export function RuleImpactPage() { const { id = "" } = useParams(); return <ImpactView title="Rule dependency impact" queryKey="rule" load={() => service.getRuleImpact(id)}/>; }

function ImpactView({ title, queryKey, load }: { readonly title: string; readonly queryKey: string; readonly load: () => ReturnType<typeof service.getFieldImpact> }) {
  const query = useQuery({ queryKey: ["customization", "impact", queryKey], queryFn: load });
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data) return <GovernedError error={new Error("Impact report not found.")}/>;
  const report = query.data.data;
  const Icon = report.blocking ? ShieldAlert : ShieldCheck;
  const references = [...(report.forms ?? []).map(item => ({ ...item, kind: "form" })), ...(report.rules ?? []).map(item => ({ ...item, kind: "rule" }))];
  return <main className="space-y-6"><PageHeader title={title} description="Review free and paid-module dependencies before a breaking change."/><Surface><div className="flex items-start gap-4"><Icon className={`h-10 w-10 ${report.blocking ? "text-destructive" : "text-primary"}`}/><div><h2 className="font-semibold">{report.blocking ? "Resolve blocking dependencies first" : "Safe to change"}</h2><p className="mt-1 text-sm text-muted-foreground">{report.dependency_count} total dependencies · {report.blocking ? "change blocked" : "no blocking references"}</p>{report.capability_unavailable ? <p className="mt-2 text-sm text-destructive">A referenced module is unavailable; stored configuration remains readable.</p> : null}</div></div></Surface>{references.length ? <Surface><h2 className="font-semibold">Dependency graph</h2><ul className="mt-4 divide-y">{references.map((reference, index) => <li key={`${reference.kind}-${reference.version_id}-${index}`} className="flex items-center justify-between py-4"><div><p className="font-medium">{reference.kind} version</p><p className="font-mono text-xs text-muted-foreground">{reference.version_id}</p></div><StatusChip status={reference.status}/></li>)}</ul></Surface> : <Surface><p className="text-sm text-muted-foreground">No versioned form or rule dependencies reference this configuration.</p></Surface>}{report.field_references?.length ? <Surface><h2 className="font-semibold">Referenced fields</h2><p className="mt-3 font-mono text-sm">{report.field_references.join(", ")}</p></Surface> : null}</main>;
}
