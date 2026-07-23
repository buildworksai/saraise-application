import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ROUTES } from "../contracts";
import { masterDataService } from "../services/master-data-service";
import { ConfirmAction, Detail, DetailGrid, GovernedError, MutationNotice, PageHeader, PageSkeleton, QUERY_KEYS, StatusPill, Surface, useStableIdempotencyKey } from "../components/MdmUI";
import { RuleGovernancePanel } from "../components/RuleGovernancePanel";

export function MatchingRuleDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const query = useQuery({ queryKey: QUERY_KEYS.matchingRule(id), queryFn: () => masterDataService.matchingRules.get(id), enabled: Boolean(id) });
  const deactivateKey = useStableIdempotencyKey("matching-rule-deactivate");
  const remove = useMutation({ mutationFn: () => masterDataService.matchingRules.delete(id, { idempotency_key: deactivateKey }), onSuccess: () => navigate(ROUTES.MATCHING_RULES) });
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>;
  if (!query.data) return <GovernedError error={new Error("Matching rule not found.")}/>;
  const rule = query.data.data;
  return <main className="space-y-6">
    <PageHeader title={rule.name} description="Deterministic matching strategy" actions={<><StatusPill value={rule.is_active ? "active" : "inactive"}/><Link to={ROUTES.MATCHING_RULE_EDIT(rule.id)}><Button variant="outline">Edit</Button></Link><ConfirmAction label="Deactivate" title="Deactivate matching rule?" description="Existing candidates and review evidence remain immutable." pending={remove.isPending} danger onConfirm={() => remove.mutate()}/></>}/>
    <MutationNotice error={remove.error}/>
    <Surface><DetailGrid><Detail label="Entity type">{rule.entity_type_key ?? rule.entity_type}</Detail><Detail label="Algorithm">{rule.algorithm}</Detail><Detail label="Review threshold">{rule.review_threshold}</Detail><Detail label="Auto-confirm threshold">{rule.auto_confirm_threshold}</Detail><Detail label="Blocking fields">{rule.blocking_fields.join(", ") || "None"}</Detail></DetailGrid></Surface>
    <Surface title="Field weights"><div className="space-y-3">{Object.entries(rule.field_weights).map(([path, weight]) => <div key={path}><div className="mb-1 flex justify-between text-sm"><span className="font-mono">{path}</span><span>{(weight * 100).toFixed(1)}%</span></div><div className="h-2 rounded bg-muted"><div className="h-full rounded bg-primary" style={{ width: `${weight * 100}%` }}/></div>{rule.blocking_fields.includes(path) ? <span className="mt-1 inline-flex rounded-full bg-muted px-2 py-0.5 text-xs">blocking</span> : null}</div>)}</div></Surface>
    <RuleGovernancePanel kind="matching" ruleId={rule.id}/>
  </main>;
}
