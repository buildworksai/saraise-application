/* eslint-disable complexity -- dashboard panels retain independent governed states */
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { AIInsights } from '../components/AIInsights';
import { CrmPage, EmptyPanel, GovernedError, PageSkeleton } from '../components/CrmPage';
import { crmKeys, crmService } from '../services/crm-service';

export function SalesDashboardPage() {
  const pipeline = useQuery({ queryKey: crmKeys.forecast('pipeline', { period: 90 }), queryFn: () => crmService.getPipeline({ period: 90 }) });
  const win = useQuery({ queryKey: crmKeys.forecast('win-rate', { period: 90 }), queryFn: () => crmService.getWinRate({ period: 90 }) });
  const prediction = useQuery({ queryKey: crmKeys.forecast('prediction', { period: 90 }), queryFn: () => crmService.predictRevenue({ period: 90 }), retry: false });
  const stale = useQuery({ queryKey: crmKeys.opportunities({ status: 'open', ordering: 'last_activity_at', page_size: 25 }), queryFn: () => crmService.listOpportunities({ status: 'open', ordering: 'last_activity_at', page_size: 25 }) });
  if (pipeline.isLoading && win.isLoading) return <CrmPage title="Sales dashboard" description="Evidence-backed pipeline health and performance."><PageSkeleton label="Loading dashboard metrics and charts"/></CrmPage>;
  const opportunities = pipeline.data?.currencies.reduce((count, row) => count + row.opportunity_count, 0) ?? 0;
  const noData = opportunities === 0 && win.data?.total_closed === 0;
  const staleDeals = stale.data?.items.filter(opportunity => !opportunity.last_activity_at || Date.now() - new Date(opportunity.last_activity_at).getTime() > 14 * 86_400_000) ?? [];
  return <CrmPage title="Sales dashboard" description="Every number states its evidence source; unavailable predictions never become zero." actions={<><Link to="/crm/leads/new"><Button>Create lead</Button></Link><Link to="/crm/opportunities/pipeline"><Button variant="outline">Open pipeline</Button></Link></>}>
    {noData ? <EmptyPanel title="Start your customer acquisition journey" description="Create a lead in under two minutes. Pipeline and win-rate evidence will appear as you close real opportunities." action={<Link to="/crm/leads/new"><Button>Create first lead</Button></Link>}/> : null}
    <div className="grid gap-6 lg:grid-cols-2"><Card><CardHeader><CardTitle>Weighted pipeline</CardTitle></CardHeader><CardContent>{pipeline.isLoading?<div role="status" className="h-40 animate-pulse rounded bg-muted"><span className="sr-only">Loading pipeline chart</span></div>:pipeline.error?<GovernedError error={pipeline.error} onRetry={()=>void pipeline.refetch()} subject="Pipeline forecast"/>:<><div className="space-y-3">{pipeline.data?.currencies.map(row=><div key={row.currency} className="flex items-center justify-between rounded bg-muted p-3"><span>{row.currency}</span><strong>{new Intl.NumberFormat(undefined,{style:'currency',currency:row.currency}).format(Number(row.weighted_pipeline_value))}</strong></div>)}</div><p className="mt-3 text-xs text-muted-foreground">Evidence: weighted open opportunities · {opportunities} opportunities</p></>}</CardContent></Card>
    <Card><CardHeader><CardTitle>Historical win rate</CardTitle></CardHeader><CardContent>{win.isLoading?<div role="status" className="h-40 animate-pulse rounded bg-muted"><span className="sr-only">Loading win rate</span></div>:win.error?<GovernedError error={win.error} onRetry={()=>void win.refetch()} subject="Win rate"/>:<><p className="text-4xl font-bold">{win.data?.win_rate===null?'Insufficient evidence':`${Number(win.data?.win_rate??0).toFixed(1)}%`}</p><p className="mt-3 text-sm text-muted-foreground">{win.data?.won_count} won · {win.data?.lost_count} lost · last {win.data?.period_days} days</p><p className="mt-1 text-xs text-muted-foreground">Evidence: historical closed opportunities</p></>}</CardContent></Card></div>
    {stale.isError?<GovernedError error={stale.error} onRetry={()=>void stale.refetch()} subject="Stale-deal callouts"/>:staleDeals.length?<section className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-5"><h2 className="font-semibold">Stale deals need attention</h2><ul className="mt-2 space-y-2">{staleDeals.map(opportunity=><li key={opportunity.id}><Link className="text-primary hover:underline" to={`/crm/opportunities/${opportunity.id}`}>{opportunity.name}</Link> · last activity {opportunity.last_activity_at?new Date(opportunity.last_activity_at).toLocaleDateString():'not recorded'}</li>)}</ul></section>:null}
    {prediction.isLoading?<div role="status" className="h-36 animate-pulse rounded bg-muted"><span className="sr-only">Loading provider prediction</span></div>:prediction.error?<section><AIInsights prediction={null}/><Button className="mt-3" variant="outline" onClick={()=>void prediction.refetch()}>Retry prediction</Button></section>:<AIInsights prediction={prediction.data??null}/>} 
  </CrmPage>;
}
