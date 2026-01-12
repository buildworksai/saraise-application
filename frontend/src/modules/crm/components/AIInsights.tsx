/**
 * AI Insights Component
 *
 * Displays AI-powered insights including next best actions and risk alerts.
 */
import { AlertCircle, TrendingUp, Clock, CheckCircle2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';

interface Insight {
  type: 'action' | 'risk' | 'opportunity';
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
}

interface AIInsightsProps {
  insights?: Insight[];
  isLoading?: boolean;
}

const defaultInsights: Insight[] = [
  {
    type: 'action',
    title: 'Follow up with high-value opportunity',
    description: 'Opportunity "Enterprise Deal" has been in negotiation for 14 days. Schedule a call.',
    priority: 'high',
  },
  {
    type: 'risk',
    title: 'Stale opportunity detected',
    description: '3 opportunities have not been updated in the last 14 days. Review pipeline.',
    priority: 'medium',
  },
  {
    type: 'opportunity',
    title: 'High-scoring lead ready for conversion',
    description: 'Lead "John Doe" has a score of 85. Consider converting to opportunity.',
    priority: 'high',
  },
];

const getIcon = (type: Insight['type']) => {
  switch (type) {
    case 'action':
      return <CheckCircle2 className="w-4 h-4" />;
    case 'risk':
      return <AlertCircle className="w-4 h-4" />;
    case 'opportunity':
      return <TrendingUp className="w-4 h-4" />;
  }
};

const getPriorityColor = (priority: Insight['priority']) => {
  switch (priority) {
    case 'high':
      return 'text-red-600 dark:text-red-400';
    case 'medium':
      return 'text-yellow-600 dark:text-yellow-400';
    case 'low':
      return 'text-blue-600 dark:text-blue-400';
  }
};

export const AIInsights = ({ insights = defaultInsights, isLoading = false }: AIInsightsProps) => {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            AI Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="animate-pulse">
                <div className="h-4 bg-muted rounded w-3/4 mb-2"></div>
                <div className="h-3 bg-muted rounded w-full"></div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!insights || insights.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            AI Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No insights available at this time.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5" />
          AI Insights
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {insights.map((insight, index) => (
            <div
              key={index}
              className="flex items-start gap-3 p-3 rounded-lg border bg-background hover:bg-muted/50 transition-colors"
            >
              <div className={`mt-0.5 ${getPriorityColor(insight.priority)}`}>
                {getIcon(insight.type)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h4 className="text-sm font-semibold text-foreground">{insight.title}</h4>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      insight.priority === 'high'
                        ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                        : insight.priority === 'medium'
                          ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                          : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                    }`}
                  >
                    {insight.priority}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{insight.description}</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};
