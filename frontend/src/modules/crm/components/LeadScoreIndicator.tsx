/**
 * Lead Score Indicator Component
 *
 * Visual display of lead score with grade badge.
 */
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import type { Lead } from '../contracts';

interface LeadScoreIndicatorProps {
  lead: Lead;
  showTrend?: boolean;
}

export const LeadScoreIndicator = ({ lead, showTrend = false }: LeadScoreIndicatorProps) => {
  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-blue-600';
    if (score >= 40) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getGradeColor = (grade: string) => {
    if (grade === 'A') return 'bg-green-100 text-green-800';
    if (grade === 'B') return 'bg-blue-100 text-blue-800';
    if (grade === 'C') return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-800';
  };

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className={`text-3xl font-bold ${getScoreColor(lead.score)}`}>{lead.score}</div>
          <div>
            <div className="text-sm font-medium">Score</div>
            <div className={`inline-block px-2 py-1 rounded text-xs font-semibold ${getGradeColor(lead.grade)}`}>
              Grade {lead.grade}
            </div>
          </div>
        </div>
        {showTrend && (
          <div className="text-muted-foreground">
            {lead.score >= 60 ? (
              <TrendingUp className="w-5 h-5 text-green-600" />
            ) : lead.score < 40 ? (
              <TrendingDown className="w-5 h-5 text-red-600" />
            ) : (
              <Minus className="w-5 h-5" />
            )}
          </div>
        )}
      </div>
      <div className="mt-2 w-full bg-muted rounded-full h-2">
        <div
          className={`h-2 rounded-full ${getScoreColor(lead.score).replace('text-', 'bg-')}`}
          style={{ width: `${lead.score}%` }}
        />
      </div>
    </Card>
  );
};
