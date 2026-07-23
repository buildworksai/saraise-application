/**
 * Lead Score Indicator Component
 *
 * Visual display of lead score with grade badge.
 */
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import type { CrmSemanticToken, Lead } from '../contracts';
import { useCrmConfiguration } from '../hooks/use-crm-configuration';
import { GovernedError, PageSkeleton } from './CrmPage';

interface LeadScoreIndicatorProps {
  lead: Lead;
  showTrend?: boolean;
}

export const LeadScoreIndicator = ({ lead, showTrend = false }: LeadScoreIndicatorProps) => {
  const configuration=useCrmConfiguration();
  if(configuration.isLoading)return <PageSkeleton label="Loading score presentation configuration"/>;
  if(configuration.error||!configuration.data)return <GovernedError error={configuration.error} onRetry={()=>void configuration.refetch()} subject="Lead score presentation"/>;
  const tokenClass:Record<CrmSemanticToken,{text:string;badge:string;bar:string}>={success:{text:'text-primary',badge:'bg-primary/10 text-primary',bar:'bg-primary'},positive:{text:'text-primary',badge:'bg-primary/10 text-primary',bar:'bg-primary'},info:{text:'text-foreground',badge:'bg-secondary text-secondary-foreground',bar:'bg-secondary-foreground'},warning:{text:'text-foreground',badge:'bg-accent text-accent-foreground',bar:'bg-accent-foreground'},danger:{text:'text-destructive',badge:'bg-destructive/10 text-destructive',bar:'bg-destructive'},muted:{text:'text-muted-foreground',badge:'bg-muted text-muted-foreground',bar:'bg-muted-foreground'},accent:{text:'text-accent-foreground',badge:'bg-accent text-accent-foreground',bar:'bg-accent-foreground'}};
  const bands=[...configuration.data.document.ui.score_bands].sort((left,right)=>right.minimum-left.minimum);
  const band=bands.find(candidate=>lead.score>=candidate.minimum);
  if(!band)return <GovernedError error={new Error('Tenant score bands do not cover this lead score.')} subject="Lead score presentation"/>;
  const style=tokenClass[band.semantic_token];
  const {score_min:minimum,score_max:maximum}=configuration.data.document.lead;
  const progress=Math.min(100,Math.max(0,(lead.score-minimum)/(maximum-minimum)*100));

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className={`text-3xl font-bold ${style.text}`}>{lead.score}</div>
          <div>
            <div className="text-sm font-medium">Score</div>
            <div className={`inline-block px-2 py-1 rounded text-xs font-semibold ${style.badge}`}>
              Grade {lead.grade}
            </div>
          </div>
        </div>
        {showTrend && (
          <div className="text-muted-foreground">
            {band === bands[0] ? (
              <TrendingUp className="w-5 h-5 text-primary" />
            ) : band === bands.at(-1) ? (
              <TrendingDown className="w-5 h-5 text-destructive" />
            ) : (
              <Minus className="w-5 h-5" />
            )}
          </div>
        )}
      </div>
      <div className="mt-2 w-full bg-muted rounded-full h-2">
        <div
          className={`h-2 rounded-full ${style.bar}`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </Card>
  );
};
